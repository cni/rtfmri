import datetime
import time
import os
import sys
import threading
import Queue as queue
import glob
import BaseHTTPServer
import json
from cgi import parse_header, parse_multipart
from urlparse import parse_qs

import numpy as np
import dicom
import nibabel as nib
#from nibabel.nicom import dicomwrappers as dwrap
import nipy.algorithms.registration

class SeriesFinder(threading.Thread):
    """
    SeriesFinder finds new exam/series directories and pushes
    them onto the series queue.
    """

    def __init__(self, scanner, series_queue):
        super(SeriesFinder, self).__init__()
        self.series_queue = series_queue
        self.cur_series_dir = None
        self.scanner = scanner
        self.alive = True

    def halt(self):
        self.alive = False

    def is_timeseries(self, series_path):
        filenames = self.scanner.get_file_list(series_path)
        # Just grab the first one we find and check it
        dcm = self.scanner.get_dicom(filenames[0])
        if getattr(dcm, 'NumberOfTemporalPositions', 1) < 6:
            print('Skipping series %d because it doesn''t look like a time series.' % int(dcm.SeriesNumber))
            return False
        else:
            return True

    def run(self):
        while self.alive:
            if not self.cur_series_dir:
                # This is the first time, so load all the series in the latest exam.
                all_series = self.scanner.series_dirs()
                for k in sorted(all_series):
                    if self.is_timeseries(all_series[k]):
                        self.series_queue.put(all_series[k])
                self.cur_series_dir = all_series[k]
            else:
                latest_series_dir = self.scanner.series_dir()
                if latest_series_dir != self.cur_series_dir and self.is_timeseries(latest_series_dir):
                    self.cur_series_dir = latest_series_dir
                    self.series_queue.put(latest_series_dir)
            time.sleep(1)


class IncrementalDicomFinder(threading.Thread):
    """
    Get a series path from the series queue, find new DICOM files
    in that series directory and put them into the dicom_queue.
    """
    def __init__(self, rtclient, series_queue, dicom_queue, interval=0.5):
        super(IncrementalDicomFinder, self).__init__()
        self.rtclient = rtclient
        self.series_queue = series_queue
        self.dicom_queue = dicom_queue
        self.interval = interval
        self.alive = True
        self.series_path = None
        self.dicom_files = set()
        self.exam_num = None
        self.series_num = None
        self.acq_num = None
        print 'initialized'

    def halt(self):
        self.alive = False

    def check_dcm(self, dcm, verbose=False):
        if not self.exam_num:
            self.exam_num = int(dcm.StudyID)
            self.series_num = int(dcm.SeriesNumber)
            self.acq_num = int(dcm.AcquisitionNumber)
            self.series_description = dcm.SeriesDescription
            self.patient_id = dcm.PatientID
            if verbose:
                print('Acquiring dicoms for exam %d, series %d (%s / %s)'
                        % (self.exam_num, self.series_num, self.patient_id, self.series_description))
        if self.exam_num != int(dcm.StudyID) or self.series_num != int(dcm.SeriesNumber):
            if verbose:
                print('Skipping dicom because of exam/series mis-match (%d, %d).' % (self.exam_num, self.series_num))
            return False
        else:
            return True

    def run(self):
        while self.alive:
            if not self.series_queue.empty():
                self.series_path = self.series_queue.get()
                self.server_inum = 0
                self.exam_num = None

            if self.series_path != None:
                before_check = datetime.datetime.now()
                filenames = set(self.rtclient.get_file_list(self.series_path))
                new_files = filenames - self.dicom_files
                for fn in new_files:
                    dcm = self.rtclient.get_dicom(fn)
                    if self.check_dcm(dcm):
                        self.dicom_queue.put(dcm)
                        self.dicom_files.add(fn)
                time.sleep(self.interval)


class Volumizer(threading.Thread):
    """
    Volumizer converts dicom objects from the dicom queue into 3D volumes
    and pushes them onto the volume queue.
    """

    def __init__(self, dicom_q, volume_q, affine=None):
        super(Volumizer, self).__init__()
        self.dicom_q = dicom_q
        self.volume_q = volume_q
        self.alive = True
        self.affine = affine
        self.slices_per_volume = None
        self.completed_vols = 0
        self.vol_shape = None

    def halt(self):
        self.alive = False

    def run(self):
        dicoms = {}
        tr = 1
        base_time = time.time()
        while self.alive:
            try:
                dcm = self.dicom_q.get(timeout=1)
            except queue.Empty:
                pass
            else:
                # convert incoming dicoms to 3D volumes
                if self.slices_per_volume is None:
                    TAG_SLICES_PER_VOLUME = (0x0021, 0x104f)
                    self.slices_per_volume = int(dcm[TAG_SLICES_PER_VOLUME].value) if TAG_SLICES_PER_VOLUME in dcm else int(getattr(dcm, 'ImagesInAcquisition', 0))
                #dicom = dwrap.wrapper_from_data(dcm)
                if self.affine is None:
                    # FIXME: dicom.get_affine is broken for our GE files. We should fix that!
                    #self.affine = dicom.get_affine()
                    self.affine = np.eye(4)
                    mm_per_vox = [float(i) for i in dcm.PixelSpacing + [dcm.SpacingBetweenSlices]] if 'PixelSpacing' in dcm and 'SpacingBetweenSlices' in dcm else [0.0, 0.0, 0.0]
                    pos = tuple(dcm.ImagePositionPatient)
                    self.affine[0:3,0:3] = np.diag(mm_per_vox)
                    self.affine[:,3] = np.array((-pos[0], -pos[1], pos[2], 1)).T
                    print(self.affine)
                dicoms[dcm.InstanceNumber] = dcm

                # The dicom instance number should indicate where this dicom belongs.
                # It should start at 1 for the first slice of the first volume, and increment
                # by 1 for each subsequent slice/volume.
                start_inst = (self.completed_vols * self.slices_per_volume) + 1
                vol_inst_nums = range(start_inst, start_inst + self.slices_per_volume)
                # test to see if the dicom dict contains at least the dicom instance numbers that we need
                if all([(ind in dicoms) for ind in vol_inst_nums]):
                    vol_shape = (dicoms[start_inst].pixel_array.shape[0],
                                 dicoms[start_inst].pixel_array.shape[1],
                                 self.slices_per_volume)
                    img = np.zeros(vol_shape)
                    for i,ind in enumerate(vol_inst_nums):
                        img[:,:,i] = dicoms[ind].pixel_array
                    volimg = nib.Nifti1Image(img, self.affine)
                    volume = {}
                    volume['exam'] = int(dicoms[start_inst].StudyID)
                    volume['series'] = int(dicoms[start_inst].SeriesNumber)
                    volume['acq_num'] = int(dicoms[start_inst].AcquisitionNumber)
                    volume['patient_id'] = dicoms[start_inst].PatientID
                    volume['series_description'] = dicoms[start_inst].SeriesDescription
                    volume['tr'] = float(dicoms[start_inst].RepetitionTime) / 1000.
                    tr = volume['tr']
                    volume['img'] = volimg
                    self.volume_q.put(volume)
                    #print 'VOLUME %03d COMPLETE in %0.2f seconds!' % (self.completed_vols, time.time()-base_time)
                    #nib.save(volimg,'/tmp/rtmc_volume_%03d.nii.gz' % self.completed_vols)
                    self.completed_vols += 1
                    base_time = time.time()
        time.sleep(tr/2.)

class Analyzer(threading.Thread):
    """
    Analyzer gets 3D volumes out of the volume queue and computes real-time statistics on them.
    """

    def __init__(self, volume_q, result_d, skip_vols=2):
        super(Analyzer, self).__init__()
        self.volume_q = volume_q
        self.result_d = result_d
        self.alive = True
        self.ref_vol = None
        self.cur_esa = None
        self.mean_img = 0.
        self.max_displacement = 0.
        self.skip_vols = skip_vols

    def halt(self):
        # temp saver:
        #test_image = nib.Nifti1Image(self.ref_vol)
        #nib.save(test_image, '/tmp/rtmc_test_brain.nii')
        self.alive = False

    def run(self):
        while self.alive:
            try:
                volume = self.volume_q.get(timeout=1)
            except queue.Empty:
                pass
            else:
                vol_esa = (volume['exam'], volume['series'], volume['acq_num'])
                print 'ANALYZER: processing %s' % str(vol_esa)
                if not self.cur_esa or self.cur_esa != vol_esa:
                    # This volume is not like the others-- re-initialize.
                    vol_num = -1
                    self.ref_vol = volume
                    self.cur_esa = vol_esa
                    self.mean_img = 0.
                    self.max_displacement = 0.
                    self.result_d[self.cur_esa] = {}
                    self.result_d[self.cur_esa]['tr'] = volume['tr']
                    self.result_d[self.cur_esa]['patient_id'] = volume['patient_id']
                    self.result_d[self.cur_esa]['series_description'] = volume['series_description']
                    self.result_d[self.cur_esa]['mean_displacement'] = []
                    self.result_d[self.cur_esa]['affine'] = []
                else:
                    vol_num += 1
                if vol_num>=self.skip_vols:
                    if vol_num==self.skip_vols:
                        print "SETTING REF VOL TO VOLUME #%03d" % vol_num
                        self.ref_vol = volume
                    else:
                        # compute motion
                        # TODO: detect 4d datasets. Also check for diffusion scans, and use histogram registration for those.
                        #print "COMPUTING MOTION ON VOLUME #%03d" % vol_num
                        ref = self.ref_vol['img'].get_data()
                        img = volume['img'].get_data()
                        # Ensure the arrays are 4d:
                        ref.shape += (1,) * (4 - ref.ndim)
                        img.shape += (1,) * (4 - img.ndim)
                        #print((ref.shape, img.shape))
                        # TODO: clean this up. We will be more efficient to use the lower-level routines
                        # like single_run_realign4d. Or write our own very simple alignment algorithm.
                        # BEGIN STDOUT SUPRESSION
                        actualstdout = sys.stdout
                        sys.stdout = open(os.devnull,'w')
                        im4d = nib.Nifti1Image(np.concatenate((ref, img), axis=3), self.ref_vol['img'].get_affine())
                        reg = nipy.algorithms.registration.FmriRealign4d(im4d, 'ascending', time_interp=False)
                        reg.estimate(loops=2)
                        T = reg._transforms[0][1]
                        aligned_raw = reg.resample(0).get_data()[...,1]
                        sys.stdout = actualstdout
                        # END STDOUT SUPRESSION
                        #reg = nipy.algorithms.registration.HistogramRegistration(volimg, self.ref_vol)
                        #T = reg.optimize('rigid')
                        #aligned_raw = nipy.algorithms.registration.resample(volimg, T, self.ref_vol).get_data()
                        self.mean_img += aligned_raw.astype(float)
                        # get the full affine for this volume by pre-multiplying by the reference affine
                        mc_affine = np.dot(self.ref_vol['img'].get_affine(), T.as_affine())
                        # Compute the error matrix
                        T_error = T.as_affine() - np.eye(4)
                        A = np.matrix(T_error[0:3,0:3])
                        t = np.matrix(T_error[0:3,3]).T
                        # radius of the spherical head assumption (in mm):
                        R = 80.
                        # The center of the volume. Assume 0,0,0 in world coordinates.
                        xc = np.matrix((0,0,0)).T
                        mean_disp = np.sqrt( R**2. / 5 * np.trace(A.T * A) + (t + A*xc).T * (t + A*xc) ).item()
                        self.result_d[self.cur_esa]['mean_displacement'].append(mean_disp)
                        if mean_disp > self.max_displacement:
                            self.max_displacement = mean_disp
                        self.result_d[self.cur_esa]['affine'].append(T)
                        print "VOL %03d: mean displacement = %f mm, max displacement = %f mm" % (vol_num, mean_disp, self.max_displacement)
                else:
                    # put dummy values in so that we know these volumes were skipped
                    #print(self.result_d)
                    # TODO: this check should not be necessary. The dict should always have been initialized by the time we get here.
                    self.result_d[self.cur_esa]['mean_displacement'].append(0.)
                    self.result_d[self.cur_esa]['affine'].append(nipy.algorithms.registration.affine.Affine(np.eye(4)))


class Server(threading.Thread):
    """
    Delivers results from the analyzer via a little HTTP server.
    """
    def __init__(self, result_d, hostname='', port=8080):
        super(Server, self).__init__()
        self.result_d = result_d
        self.hostname = hostname
        self.port = port
        self.alive = True

    def halt(self):
        self.alive = False

    def run(self):
        httpd = HttpServer((self.hostname, self.port), HttpHandler, self.result_d)
        print('Starting http server at http://%s:%d/' % (self.hostname, self.port))
        while self.alive:
            httpd.handle_request()
        httpd.server_close()


class HttpHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    """The HTTP handler."""

    def do_HEAD(self, mime_type="text/html"):
        self.send_response(200)
        self.send_header("Content-type", mime_type)
        self.end_headers()

    def do_GET(self):
        """Respond to a GET request."""
        # Build a nice dict to summarize all the quantitative data
        # *** WORK HERE
        #    'time':t*self.server.result_d['tr'], 'd_mean':d,
        #         't_x':a.translation[0], 't_y':a.translation[1], 't_z':a.translation[2],
        #         'r_x':a.rotation[0], 'r_y':a.rotation[1], 'r_z':a.rotation[2]}
        #         for t,a,d in enumerate(zip(self.server.result_d['affine'], self.server.result_d['mean_displacement']))]
        path = self.path.lower()
        if '?' in path:
            path, tmp = path.split('?', 1)
            qs = parse_qs(tmp)
        else:
            qs = None

        if path in ['/','/index.html']:
            self.do_HEAD()
            if qs and 'e' in qs and 's' in qs and 'a' in qs:
                esa = (int(qs['e'][0]), int(qs['s'][0]), int(qs['a'][0]))
            else:
                esa = None
            self.wfile.write('<html><head><title>CNI MR Real-time Server</title>')
            # TODO: serve this as a file so the browser will cache it.`
            with open('plot_head.js') as fp:
                self.wfile.write(fp.read())
            self.wfile.write('</head>\n<body>\n')
            self.wfile.write('<div id="content">\n')
            if self.server.result_d:
                if not esa:
                    esa = next(self.server.result_d.iterkeys())
                if esa in self.server.result_d:
                    self.wfile.write('<script>e=%d;s=%d;a=%d;</script>\n' % (esa[0], esa[1], esa[2]))
                    self.wfile.write('<h1>%s: Exam %d, Series %d, Acquisition %d (%s)</h1>\n' %
                            (self.server.result_d[esa]['patient_id'],
                             esa[0], esa[1], esa[2],
                             self.server.result_d[esa]['series_description']))
                    self.wfile.write('  <div id="main-container">\n')
                    self.wfile.write('    <div id="legend"></div>\n')
                    self.wfile.write('    <div id="graph-container">\n')
                    self.wfile.write('      <div id="graph"></div>\n')
                    self.wfile.write('      <div id="x_label">Time (seconds)</div>\n')
                    #self.wfile.write('      <div id="y_label">Displacement (mm/deg)</div>\n')
                    self.wfile.write('      <div id="slider"></div>\n')
                    self.wfile.write('    </div>\n')
                    self.wfile.write('  </div>\n')
                    self.wfile.write('</div>\n')
                    with open('plot.js') as fp:
                        self.wfile.write(fp.read())
                else:
                    self.wfile.write('<h1>e/s/a %s not found</h1>\n' % str(esa))
            else:
                self.wfile.write('<h1>No data</h1>\n')
            self.wfile.write("</body></html>\n")
        elif path.startswith('/pub/'):
            # TODO: detect the appropriate mime type
            self.do_HEAD(mime_type="application/javascript")
            filename = os.path.join('pub', path[5:])
            if os.path.isfile(filename):
                with open(filename) as fp:
                    self.wfile.write(fp.read())
        elif path in ['/names','/names.json']:
            self.do_HEAD(mime_type="application/json")
            self.wfile.write(json.dumps(['Mean Displacement',
                'Translation_X', 'Translation_Y', 'Translation_Z',
                'Rotation_X', 'Rotation_Y', 'Rotation_Z']))
        elif path in ['/data','/data.json']:
            if qs and 'start' in qs:
                start_ind = max(0, int(qs['start'][0]))
            else:
                start_ind = 0
            if qs and 'e' in qs and 's' in qs and 'a' in qs:
                esa = (int(qs['e'][0]), int(qs['s'][0]), int(qs['a'][0]))
            else:
                esa = None
            self.do_HEAD(mime_type="application/json")
            if self.server.result_d:
                if not esa:
                    esa = next(self.server.result_d.iterkeys())
                if esa in self.server.result_d:
                    self.wfile.write(self.jsonify_result(self.server.result_d[esa], start_ind))
                else:
                    self.wfile.write(json.dumps({}))

    def do_POST(self):
        """Handle a post request."""
        # test using curl-- see https://httpkit.com/resources/HTTP-from-the-Command-Line/
        # Or, try:
        # import httplib, urllib
        # c = httplib.HTTPConnection("spgr.stanford.edu", port=8080)
        # c.request("POST", "", urllib.urlencode({'@type':'data', '@start':0, '@end':100}, {"Content-type": "application/x-www-form-urlencoded","Accept": "text/plain"}))
        # c.getresponse().read()
        length = int(self.headers['content-length'])
        qs = parse_qs(self.rfile.read(length), keep_blank_values=1)
        self.send_response(200)
        self.end_headers()
        if self.path.lower() in ['/test','/test.html']:
            self.wfile.write(postvars)

    def jsonify_result(self, res, start_ind=0):
        start_ind = max(0, start_ind)
        md = res['mean_displacement'][start_ind:]
        transrot = [t.translation.tolist() + (t.rotation/3.14*180.).tolist() for t in res['affine'][start_ind:]]
        # TODO: While elegant in some ways, this code seems highly inefficient. There must be a better way...
        d = [{'name':'Mean Displacement', 'unitY':'mm', 'data':[{'x':round((t+start_ind)*res['tr'],3), 'y':round(d,3)} for t,d in enumerate(md)]},
             {'name':'Translation_X', 'unitY':'mm', 'data':[{'x':round((t+start_ind)*res['tr'],3), 'y':round(r[0],3)} for t,r in enumerate(transrot)]},
             {'name':'Translation_Y', 'unitY':'mm', 'data':[{'x':round((t+start_ind)*res['tr'],3), 'y':round(r[1],3)} for t,r in enumerate(transrot)]},
             {'name':'Translation_Z', 'unitY':'mm', 'data':[{'x':round((t+start_ind)*res['tr'],3), 'y':round(r[2],3)} for t,r in enumerate(transrot)]},
             {'name':'Rotation_X', 'unitY':'deg', 'data':[{'x':round((t+start_ind)*res['tr'],3), 'y':round(r[3],3)} for t,r in enumerate(transrot)]},
             {'name':'Rotation_Y', 'unitY':'deg', 'data':[{'x':round((t+start_ind)*res['tr'],3), 'y':round(r[4],3)} for t,r in enumerate(transrot)]},
             {'name':'Rotation_Z', 'unitY':'deg', 'data':[{'x':round((t+start_ind)*res['tr'],3), 'y':round(r[5],3)} for t,r in enumerate(transrot)]}]
        return json.dumps(d)


class HttpServer(BaseHTTPServer.HTTPServer):
    """
    Subclass the HTTPServer so that we can pass the results dict to the handler (as self.server.results_d).
    """
    def __init__(self, hostport, handler, result_d):
        BaseHTTPServer.HTTPServer.__init__(self, hostport, handler)
        self.result_d = result_d



