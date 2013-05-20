
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
from nibabel.nicom import dicomreaders as dread
from nibabel.nicom import dicomwrappers as dwrap
import nipy.algorithms.registration

def findrecentdir(start_dir):
    all_dirs = [os.path.join(start_dir,d) for d in os.listdir(start_dir) if os.path.isdir(os.path.join(start_dir,d))]
    if all_dirs:
        last_mod = max((os.path.getmtime(d),d) for d in all_dirs)[1]
        return last_mod
    else:
        return False

def navigatedown(start_dir):
    current_dir = start_dir
    bottom = False
    while not bottom:
        sub_dir = findrecentdir(current_dir)
        if not sub_dir:
            bottom = True
        else:
            current_dir = sub_dir
    return current_dir

def get_current(top_dir):
    most_recent_dir = navigatedown(top_dir)
    current_dir = os.path.abspath(os.path.join(most_recent_dir, '../'))
    all_dirs = [d for d in os.listdir(current_dir) if os.path.isdir(os.path.join(current_dir,d))]
    return [current_dir,all_dirs]

def wait_for_new_directory(root_dir, black_list, waittime):
    baseT = time.time()
    while (time.time() - baseT) < waittime:
        recent_dir = findrecentdir(root_dir)
        if not os.path.basename(recent_dir) in black_list:
            return recent_dir
        time.sleep(0.5)
    return False


class IncrementalDicomFinder(threading.Thread):
    """
    Find new DICOM files in the series_path directory and put them into the dicom_queue.
    """
    def __init__(self, rtclient, series_path, dicom_queue, result_d, interval):
        super(IncrementalDicomFinder, self).__init__()
        self.rtclient = rtclient
        self.series_path = series_path
        self.dicom_queue = dicom_queue
        self.interval = interval
        self.alive = True
        self.server_inum = 0
        self.dicom_nums = []
        self.dicom_search_start = 0
        self.exam_num = None
        self.series_num = None
        self.acq_num = None
        self.result_d = result_d
        print 'initialized'

    def halt(self):
        self.alive = False

    def get_initial_filelist(self):
        time.sleep(0.1)
        files = self.rtclient.get_file_list(self.series_path)
        files.sort()
        if files:
            for fn in files:
                spl = os.path.basename(fn).split('.')
                current_inum = int(spl[0][1:])
                if current_inum > self.server_inum:
                    self.server_inum = current_inum
                self.dicom_nums.append(int(spl[2]))
            gaps = [x for x in range(max(self.dicom_nums)) if x not in self.dicom_nums]
            gaps.remove(0)
            if gaps:
                self.dicom_search_start = min(gaps)
            else:
                self.dicom_search_start = max(self.dicom_nums)+1
            return files
        else:
            return False

    def check_dcm(self, dcm, verbose=True):
        if not self.exam_num:
            self.exam_num = int(dcm.StudyID)
            self.series_num = int(dcm.SeriesNumber)
            self.acq_num = int(dcm.AcquisitionNumber)
            self.series_description = dcm.SeriesDescription
            self.patient_id = dcm.PatientID
            # initialize the results dict
            self.result_d['exam'] = self.exam_num
            self.result_d['series'] = self.series_num
            self.result_d['patient_id'] = self.patient_id
            self.result_d['series_description'] = self.series_description
            self.result_d['tr'] = float(dcm.RepetitionTime) / 1000.

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
        take_a_break = False
        failures = 0

        while self.alive:
            #print sorted(self.dicom_nums)
            #print self.server_inum
            before_check = datetime.datetime.now()
            #print before_check

            if self.server_inum == 0:
                filenames = self.get_initial_filelist()
                for fn in filenames:
                    dcm = self.rtclient.get_dicom(fn)
                    if self.check_dcm(dcm):
                        self.dicom_queue.put(dcm)
            elif take_a_break:
                #print '%s: (%d) [%f]' % (os.path.basename(self.series_path), self.server_inum, self.interval)
                time.sleep(self.interval)
                take_a_break = False
            else:
                loop_success = False
                first_failure = False
                ind_tries = [x for x in range(self.dicom_search_start, max(self.dicom_nums)+10) if x not in self.dicom_nums]
                #print ind_tries
                for d in ind_tries:
                    try:
                        current_filename = 'i'+str(self.server_inum+1)+'.MRDC.'+str(d)
                        #print current_filename
                        dcm = self.rtclient.get_dicom(os.path.join(self.series_dir, current_filename))
                        if not len(dcm.PixelData) == 2 * dcm.Rows * dcm.Columns:
                            print 'corruption error'
                            print 'pixeldata: '+str(len(dcm.PixelData))
                            print 'expected: '+str(2*dcm.Rows*dcm.Columns)
                            raise Exception
                    except:
                        #print current_filename+', failed attempt'
                        if not first_failure:
                            self.dicom_search_start = d
                            first_failure = True
                    else:
                        #print current_filename+', successful attempt'+'\n'
                        if self.check_dcm(dcm):
                            self.dicom_queue.put(dcm)
                        self.dicom_nums.append(d)
                        self.server_inum += 1
                        loop_success = True
                        failures = 0

                if not loop_success:
                    #print 'failure on: i'+str(self.server_inum+1)+'\n'
                    refresher = glob.glob('i'+str(self.server_inum+1)+'*')
                    #failures = failures+1
                    take_a_break = True


class Volumizer(threading.Thread):
    """
    Volumizer converts dicom objects from the dicom queue into 3D volumes
    and pushes them onto the volume queue.
    """

    def __init__(self, dicom_q, volume_q, result_d, affine=None):
        super(Volumizer, self).__init__()
        self.dicom_q = dicom_q
        self.volume_q = volume_q
        self.result_d = result_d
        self.alive = True
        self.affine = affine
        self.slices_per_volume = None
        self.completed_vols = 0
        self.vol_shape = None

    def halt(self):
        self.alive = False

    def run(self):
        dicoms = {}

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
                dicom = dwrap.wrapper_from_data(dcm)
                if self.affine is None:
                    # FIXME: dicom.get_affine is broken for our GE files. We should fix that!
                    #self.affine = dicom.get_affine()
                    self.affine = np.eye(4)
                    mm_per_vox = [float(i) for i in dcm.PixelSpacing + [dcm.SpacingBetweenSlices]] if 'PixelSpacing' in dcm and 'SpacingBetweenSlices' in dcm else [0.0, 0.0, 0.0]
                    pos = tuple(dcm.ImagePositionPatient)
                    self.affine[0:3,0:3] = np.diag(mm_per_vox)
                    self.affine[:,3] = np.array((-pos[0], -pos[1], pos[2], 1)).T
                    print(self.affine)
                dicoms[dicom.instance_number] = dicom

                #print 'put in dicom:' + str(dicom.instance_number)

                # The dicom instance number should indicate where this dicom belongs.
                # It should start at 1 for the first slice of the first volume, and increment
                # by 1 for each subsequent slice/volume.
                start_inst = (self.completed_vols * self.slices_per_volume) + 1
                vol_inst_nums = range(start_inst, start_inst + self.slices_per_volume)
                # test to see if the dicom dict contains at least the dicom instance numbers that we need
                if all([(ind in dicoms) for ind in vol_inst_nums]):
                    cur_vol_shape = (dicoms[start_inst].image_shape[0], dicoms[start_inst].image_shape[1], self.slices_per_volume)
                    if not self.vol_shape:
                        self.vol_shape = cur_vol_shape
                    volume = np.zeros(self.vol_shape)
                    if self.vol_shape != cur_vol_shape:
                        print 'WARNING: Volume %03d is the wrong shape! Skipping...' % self.completed_vols
                    else:
                        for i,ind in enumerate(vol_inst_nums):
                            volume[:,:,i] = dicoms[ind].get_data()
                        volimg = nib.Nifti1Image(volume, self.affine)
                        self.volume_q.put(volimg)
                        print 'VOLUME %03d COMPLETE in %0.2f seconds!' % (self.completed_vols, time.time()-base_time)
                        #nib.save(volimg,'/tmp/rtmc_volume_%03d.nii.gz' % self.completed_vols)
                    self.completed_vols += 1
                    base_time = time.time()


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
        self.mean_img = 0.
        self.max_displacement = 0.
        self.skip_vols = skip_vols

    def halt(self):
        # temp saver:
        #test_image = nib.Nifti1Image(self.ref_vol)
        #nib.save(test_image, '/tmp/rtmc_test_brain.nii')
        self.alive = False

    def run(self):
        vol_num = -1
        while self.alive:
            try:
                volimg = self.volume_q.get(timeout=1)
            except queue.Empty:
                pass
            else:
                vol_num += 1
                if vol_num>=self.skip_vols:
                    if not self.ref_vol:
                        print "SETTING REF VOL TO VOLUME #%03d" % vol_num
                        self.ref_vol = volimg
                    else:
                        # compute motion
                        # TODO: detect 4d datasets. Also check for diffusion scans, and use histogram registration for those.
                        #print "COMPUTING MOTION ON VOLUME #%03d" % vol_num
                        ref = self.ref_vol.get_data()
                        img = volimg.get_data()
                        # Ensure the arrays are 4d:
                        ref.shape += (1,) * (4 - ref.ndim)
                        img.shape += (1,) * (4 - img.ndim)
                        #print((ref.shape, img.shape))
                        # TODO: clean this up. We will be more efficient to use the lower-level routines
                        # like single_run_realign4d. Or write our own very simple alignment algorithm.
                        # BEGIN STDOUT SUPRESSION
                        actualstdout = sys.stdout
                        sys.stdout = open(os.devnull,'w')
                        im4d = nib.Nifti1Image(np.concatenate((ref, img), axis=3), self.ref_vol.get_affine())
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
                        mc_affine = np.dot(self.ref_vol.get_affine(), T.as_affine())
                        # Compute the error matrix
                        T_error = self.ref_vol.get_affine() - mc_affine
                        A = np.matrix(T_error[0:3,0:3])
                        t = np.matrix(T_error[0:3,3]).T
                        # radius of the spherical head assumption (in mm):
                        R = 70.
                        # The center of the volume. Assume 0,0,0 in world coordinates.
                        xc = np.matrix((0,0,0)).T
                        mean_disp = np.sqrt( R**2. / 5 * np.trace(A.T * A) + (t + A*xc).T * (t + A*xc) ).item()
                        self.result_d['mean_displacement'].append(mean_disp)
                        if mean_disp > self.max_displacement:
                            self.max_displacement = mean_disp
                        self.result_d['affine'].append(T)
                        print "VOL %03d: mean displacement = %f mm, max displacement = %f mm" % (vol_num, mean_disp, self.max_displacement)
                else:
                    # put dummy values in so that we know these volumes were skipped
                    #print(self.result_d)
                    self.result_d['mean_displacement'].append(0.)
                    self.result_d['affine'].append(nipy.algorithms.registration.affine.Affine(np.eye(4)))


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

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()

    def do_GET(self):
        """Respond to a GET request."""
        self.do_HEAD()
        # Build a nice dict to summarize all the quantitative data
        # *** WORK HERE
        #    'time':t*self.server.result_d['tr'], 'd_mean':d,
        #         't_x':a.translation[0], 't_y':a.translation[1], 't_z':a.translation[2],
        #         'r_x':a.rotation[0], 'r_y':a.rotation[1], 'r_z':a.rotation[2]}
        #         for t,a,d in enumerate(zip(self.server.result_d['affine'], self.server.result_d['mean_displacement']))]
        if self.path.lower() in ['/','/index.html']:
            self.wfile.write('<html><head><title>CNI MR Real-time Server</title>')
            # TODO: serve this as a file so the browser will cache it.`
            with open('plot_head.js') as fp:
                self.wfile.write(fp.read())
            self.wfile.write('</head>\n<body>\n')
            self.wfile.write('<div id="content">\n')
            self.wfile.write('<h1>%s: Exam %d, Series %d (%s)</h1>\n' %
                    (self.server.result_d['patient_id'],
                     self.server.result_d['exam'],
                     self.server.result_d['series'],
                     self.server.result_d['series_description']))
            self.wfile.write('  <div id="chart-container">\n')
            self.wfile.write('    <div id="chart"></div>\n')
            self.wfile.write('    <div id="slider"></div>\n')
            self.wfile.write('  </div>\n')
            self.wfile.write('</div>\n')
            with open('plot.js') as fp:
                self.wfile.write(fp.read())
            # When "http://host.com/foo/bar/" is hit, self.path equals "/foo/bar/".
            self.wfile.write("</body></html>\n")
        elif self.path.lower() in ['/names','/names.json']:
            self.wfile.write(json.dumps(['Mean Displacement']))
        elif self.path.lower() in ['/data','/data.json']:
            # TODO: check for vars start, end, length and return the requested range of samples.
            self.wfile.write(self.jsonify_result(self.server.result_d))

    def do_POST(self):
        """Handle a post request."""
        # test using curl-- see https://httpkit.com/resources/HTTP-from-the-Command-Line/
        # Or, try:
        # import httplib, urllib
        # c = httplib.HTTPConnection("spgr.stanford.edu", port=8080)
        # c.request("POST", "", urllib.urlencode({'@type':'data', '@start':0, '@end':100}, {"Content-type": "application/x-www-form-urlencoded","Accept": "text/plain"}))
        # c.getresponse().read()
        length = int(self.headers['content-length'])
        postvars = parse_qs(self.rfile.read(length), keep_blank_values=1)
        self.send_response(200)
        self.end_headers()
        if self.path.lower() in ['/test','/test.html']:
            self.wfile.write(postvars)
        elif self.path.lower() in ['/names','/names.json']:
            self.wfile.write(json.dumps(['Mean Displacement']))
        elif self.path.lower() in ['/data','/data.json']:
            # TODO: check for vars start, end, lenght and return the requested range of samples.
            self.wfile.write(self.jsonify_result(self.server.result_d))

    def jsonify_result(self, res):
        d = [{'name':'Mean Displacement', 'data':[{'x':round(t*res['tr'],3), 'y':round(d,3)} for t,d in enumerate(res['mean_displacement'])]}]
        return json.dumps(d)

    def timeseries_plot(self):
        js = ('<!doctype>\n'
              '<link type="text/css" rel="stylesheet" href="http://code.shutterstock.com/rickshaw/rickshaw.min.css">\n'
              '<script src="https://ajax.googleapis.com/ajax/libs/jquery/1.7.2/jquery.min.js"></script>\n'
              '<script src="https://ajax.googleapis.com/ajax/libs/jqueryui/1.8.21/jquery-ui.min.js"></script>\n'
              '<script src="http://d3js.org/d3.v2.js"></script>\n'
              '<script src="http://code.shutterstock.com/rickshaw/rickshaw.min.js"></script>\n'
              '<div id="chart-container">\n'
              '  <div id="graph"></div>\n'
              '  <div id="legend"></div>\n'
              '  <div class="clear"></div>\n'
              '</div>\n'
              '<script>\n'
              'var graph;\n'
              'graph = new Rickshaw.Graph.Ajax( {\n'
              '  	element: document.getElementById("graph"),\n'
              '  	width: 800, height: 200, renderer: "line", interpolation: "linear",\n'
              '  	dataURL: "data.json",\n'
              '     series: [{name:"Mean Displacement", color:"#c05020"}],\n'
              '     onComplete: function(transport) {\n'
              '         var graph = transport.graph;\n'
              '         var detail = new Rickshaw.Graph.HoverDetail({ graph: graph,\n'
              '             xFormatter: function(x) { return x + " seconds" },'
              '             yFormatter: function(y) { return y + " mm" }\n'
              '         });\n'
              '         var x_axis = new Rickshaw.Graph.Axis.X({ graph: graph });\n'
              '         x_axis.graph.update();\n'
              '         var y_axis = new Rickshaw.Graph.Axis.Y({ graph: graph,\n'
              '             tickFormat: Rickshaw.Fixtures.Number.formatKMBT,\n'
              '         });\n'
              '         y_axis.graph.update();\n'
              '     }\n'
              '} );\n'
              '</script>\n'
              '<style type="text/css">\n'
              '  /*<![CDATA[*/\n'
              '    #chart-container { width: 1000px; margin: auto; margin-top: 100px }\n'
              '    #graph { float: left; }\n'
              '    #legend { float: right; }\n'
              '    .clear { clear: both; }\n'
              '  /*]]>*/\n'
              '</style>\n')
        return js

    def timeseries_plot_full(self):
        js = ('<!doctype>\n'
              '<link type="text/css" rel="stylesheet" href="http://code.shutterstock.com/rickshaw/rickshaw.min.css">\n'
              '<script src="https://ajax.googleapis.com/ajax/libs/jquery/1.7.2/jquery.min.js"></script>\n'
              '<script src="https://ajax.googleapis.com/ajax/libs/jqueryui/1.8.21/jquery-ui.min.js"></script>\n'
              '<script src="http://d3js.org/d3.v2.js"></script>\n'
              '<script src="http://code.shutterstock.com/rickshaw/rickshaw.min.js"></script>\n'
              '<script type="text/javascript">\n'
              'var palette = new Rickshaw.Color.Palette();'
              'var series = []\n'
              '$.post("names.json", function(d) {\n'
              '  d.forEach(function(s) { series.push({ name: s, color: palette.color(s) }); });\n'
              '  var ajaxGraph = new Rickshaw.Graph.Ajax( {\n'
              '  	element: document.getElementById("graph"),\n'
              '  	width: 800, height: 500, renderer: "line",'
              '  	dataURL: "data.json", series: series,\n'
              '  	onData: function(d) { Rickshaw.Series.zeroFill(d); return d; },\n'
              '  	onComplete: function(transport) {\n'
              '  	  var graph = transport.graph;\n'
              '  	  var detail = new Rickshaw.Graph.HoverDetail({ graph: graph,\n'
              '  	    xFormatter: function(x) { return x.toFixed(2) },\n'
              '  	    yFormatter: function(y) { return y.toFixed(2) }\n'
              '  	  });\n'
              '  	 var legend = new Rickshaw.Graph.Legend({ graph: graph, element: document.querySelector("#legend") });\n'
              '      var shelving = new Rickshaw.Graph.Behavior.Series.Toggle({ graph: graph, legend: legend });\n'
              '      var highlighter = new Rickshaw.Graph.Behavior.Series.Highlight({ graph: graph, legend: legend });\n'
              '      var yAxis = new Rickshaw.Graph.Axis.Y({ graph: graph, tickFormat: function(y) { return (y).toFixed(2) } });\n'
              '      yAxis.render();\n'
              '  	}\n'
              '  } );\n'
              '}, "json");\n'
              '</script>\n'
              '<div id="chart-container">\n'
              '  <div id="graph"></div>\n'
              '  <div id="legend"></div>\n'
              '  <div class="clear"></div>\n'
              '</div>\n'
              '<style type="text/css">\n'
              '  /*<![CDATA[*/\n'
              '    #chart-container { width: 1000px; margin: auto; margin-top: 100px }\n'
              '    #graph { float: left; }\n'
              '    #legend { float: right; }\n'
              '    .clear { clear: both; }\n'
              '  /*]]>*/\n'
              '</style>\n')
        return js

class HttpServer(BaseHTTPServer.HTTPServer):
    """
    Subclass the HTTPServer so that we can pass the results dict to the handler (as self.server.results_d).
    """
    def __init__(self, hostport, handler, result_d):
        BaseHTTPServer.HTTPServer.__init__(self, hostport, handler)
        self.result_d = result_d



