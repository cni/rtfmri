#!/usr/bin/env python
#
# @author:  Gunnar Schaefer

import string
import os
import sys
import glob
import time
import Queue as queue
import signal
import argparse
import datetime
import threading
import thread
import random
import re
from socket import *

import numpy as np
import dicom
import nibabel as nib
from nibabel.nicom import dicomreaders as dread
from nibabel.nicom import dicomwrappers as dwrap

CNI_TOP_DIR = '/net/cnimr/export/home1/sdc_image_pool/images/'

class Utilities(object):

    def __init__(self, dicom_prefix='i*'):
        self.server_dir = CNI_TOP_DIR

    def findrecentdir(self):
        all_dirs = [dir for dir in os.listdir('.') if os.path.isdir(dir)]
        if all_dirs:
            last_mod = max((os.path.getmtime(dir),dir) for dir in all_dirs)[1]
            return last_mod
        else:
            return False

    def erase_realtimedir(self):
        if os.path.exists(self.realtime_dir):
            shutil.rmtree(self.realtime_dir)
        os.mkdir(self.realtime_dir)

    def erase_waitingroom(self):
        if os.path.exists(self.waitingroom):
            shutil.rmtree(self.waitingroom)
        os.mkdir(self.waitingroom)

    def navigatedown(self):
        os.chdir(self.server_dir)
        current_dir = self.server_dir
        bottom = False
        while not bottom:
            sub_dir = self.findrecentdir()
            if not sub_dir:
                bottom = True
            else:
                os.chdir(sub_dir)
                current_dir = sub_dir
        return os.getcwd()

    def calibration(self,copyflag):
        most_recent_dir = self.navigatedown()
        os.chdir('../')
        if copyflag:
            plaincopy(directory=most_recent_dir,exclude=[],destination='calibration')
        all_dirs = [dir for dir in os.listdir('.') if os.path.isdir(dir)]
        return [os.getcwd(),all_dirs]

    def enternewdirectory(self,rootdir,exceptions,waittime):
        os.chdir(rootdir)
        baseT = time.time()
        while (time.time() - baseT) < waittime:
            recent_dir = self.findrecentdir()
            if not recent_dir in exceptions:
                print recent_dir
                os.chdir(recent_dir)
                return os.getcwd()
        return False

    def dicom_header_reader(dicom_file):
        start_time = time.time()
        file_data = dicom.read_file(dicom_file)
        print file_data.AcquisitionNumber
        end_time = time.time()
        print end_time-start_time


class DicomFinder(threading.Thread):

    """DicomFinder finds the latest dicom files and pushes them into the dicom queue as dicom objects."""

    def __init__(self, exam_path, dicom_q, interval):
        super(DicomFinder, self).__init__()
        self.exam_path = exam_path
        self.dicom_q = dicom_q
        self.interval = interval
        self.alive = True

    def halt(self):
        self.alive = False

    def run(self):
        files_dict = {}
        while self.alive:
            before_check = datetime.datetime.now()
            series_path = max(glob.glob(os.path.join(exam_path, 's*')), key=lambda d: os.stat(d).st_mtime)
            current_files = os.listdir(series_path)
            new_files = set(current_files) - files_dict.setdefault(series_path, set())
            for filename in new_files.copy():
                try:
                    dcm = dicom.read_file(os.path.join(series_path, filename))
                    if not len(dcm.PixelData) == 2 * dcm.Rows * dcm.Columns:
                        raise Exception
                except:
                    new_files.remove(filename)  # try this one again next time
                else:
                    self.dicom_q.put(dcm)
            files_dict[series_path] |= new_files

            sleeptime = (before_check + self.interval - datetime.datetime.now()).total_seconds()
            print '%s: %4d (%3d) [%f]' % (os.path.basename(series_path), len(files_dict[series_path]), len(new_files), sleeptime)
            if sleeptime > 0:
                time.sleep(sleeptime)


class IncrementalDicomFinder(threading.Thread):

    def __init__(self, series_path, dicom_queue, interval):
        super(IncrementalDicomFinder, self).__init__()
        self.series_path = series_path
        self.dicom_queue = dicom_queue
        self.interval = interval
        self.alive = True
        self.server_inum = 0
        self.dicom_nums = []
        self.dicom_search_start = 0
        print 'initialized'

    def halt(self):
        self.alive = False

    def get_initial_filelist(self):
        time.sleep(0.1)
        files = os.listdir(self.series_path)
        print files
        if files:
            for file in files:
                spl = file.split('.')
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


            return [os.path.join(self.series_path, fid) for fid in files]
        else:
            return False

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
                for fid in filenames:
                    dcm = dicom.read_file(fid)
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
                        dcm = dicom.read_file(current_filename)
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

    """Volumizer converts dicom objects from the dicom queue into 3D volumes and pushes them onto the volume queue."""

    def __init__(self, dicom_q, volume_q, affine=None):
        super(Volumizer, self).__init__()
        self.dicom_q = dicom_q
        self.volume_q = volume_q
        self.alive = True
        self.affine = affine
        self.slices_per_volume = None

    def halt(self):
        self.alive = False

    def run(self):
        dicoms = {}
        complete_volumes = 0

        base_time = time.time()
        while self.alive:
            try:
                dcm = self.dicom_q.get(timeout=1)
            except queue.Empty:
                pass
            else:
                # TODO: convert incoming dicoms to 3D volumes
                if self.slices_per_volume is None:
                    TAG_SLICES_PER_VOLUME = (0x0021, 0x104f)
                    self.slices_per_volume = int(dcm[TAG_SLICES_PER_VOLUME].value) if TAG_SLICES_PER_VOLUME in dcm else int(getattr(dcm, 'ImagesInAcquisition', 0))
                dicom = dwrap.wrapper_from_data(dcm)
                if self.affine is None:
                    #self.affine = dicom.get_affine()
                    self.affine = np.eye(4)
                    mm_per_vox = [float(i) for i in dcm.PixelSpacing + [dcm.SpacingBetweenSlices]] if 'PixelSpacing' in dcm and 'SpacingBetweenSlices' in dcm else [0.0, 0.0, 0.0]
                    pos = tuple(dcm.ImagePositionPatient)
                    self.affine[0:3,0:3] = np.diag(mm_per_vox)
                    self.affine[:,3] = np.array((-pos[0], -pos[1], pos[2], 1)).T
                    print(self.affine)
                dicoms[dicom.instance_number] = dicom

                print 'put in dicom:' + str(dicom.instance_number)

                check_start = (complete_volumes * self.slices_per_volume) + 1
                check_end = check_start + self.slices_per_volume
                if all([(ind in dicoms) for ind in range(check_start,check_end)]):
                    volume_shape = (self.slices_per_volume, dicom.image_shape[0], dicom.image_shape[1])
                    volume = np.zeros(volume_shape)
                    for i,ind in enumerate(range(check_start,check_end)):
                        volume[i] = dicoms[ind].get_data()
                    complete_volumes += 1
                    print 'VOLUME COMPLETE!'
                    volimg = nib.Nifti1Image(volume, self.affine)
                    self.volume_q.put(volimg)
                    nib.save(volimg,'/tmp/rtmc_volume.nii.gz')
                    print time.time()-base_time
                    base_time = time.time()


class Analyzer(threading.Thread):

    """Analyzer gets 3D volumes out of the volume queue and computes real-time statistics on them."""

    def __init__(self, volume_q, average_q):
        super(Analyzer, self).__init__()
        self.volume_q = volume_q
        self.average_q = average_q
        self.alive = True
        self.whole_brain = None
        self.brain_list = []
        self.ref_vol = None
        self.mean_img = 0
        self.mc_xform = []
        self.mean_displacement = []

    def halt(self):
        # temp saver:
        #test_image = nib.Nifti1Image(self.ref_vol)
        #nib.save(test_image, '/tmp/rtmc_test_brain.nii')
        self.alive = False

    def run(self):

        import nipy.algorithms.registration

        while self.alive:
            try:
                volimg = self.volume_q.get(timeout=1)
            except queue.Empty:
                pass
            else:
                if not self.ref_vol:
                    # compute motion
                    hist_reg = nipy.algorithms.registration.HistogramRegistration(volimg, self.ref_img)
                    T = hist_reg.optimize('rigid')
                    aligned_img = nipy.algorithms.registration.resample(volimg, T, self.ref_img)
                    self.mean_img += aligned_img.get_data()
                    # get the full affine for this volume by pre-multiplying by the reference affine
                    mc_affine = self.ref_img.get_affine() * T.as_affine()
                    # Compute the error matrix
                    T_error = self.ref_img.get_affine() - mc_affine
                    A = T_error[0:3,0:3]
                    t = T_error[0:3,3]
                    # The center of the volume. Assume 0,0,0 in world coordinates.
                    xc = np.matrix((0,0,0)).T
                    mean_disp = np.sqrt( R**2. / 5 * np.trace(A.T * A) + (t + A*xc).T * (t + A*xc) )
                    mean_displacement.append(mean_disp)
                    if self.mean_disp > self.max_displmean_displacement:
                        self.max_displacement = mean_disp
                    self.mc_xform.append(T)
                    print "mean displacement: %f mm, max displacement = %f mm" % (mean_disp, self.max_displacement)
                else:
                    self.ref_vol = volimg


class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        super(ArgumentParser, self).__init__(formatter_class=argparse.RawTextHelpFormatter)
        self.description  = 'Facilitate real-time fMRI.\n\n'
        self.description += 'Use NFS mount options "noac,lookupcache=none" to avoid client-side caching.'
        self.add_argument('dicom_path', help='path to dicom root directory')
        self.add_argument('-i', '--interval', type=float, default=1.0, help='interval between checking for new files')

if __name__ == '__main__':
    #args = ArgumentParser().parse_args()

    dicom_q = queue.Queue()
    volume_q = queue.Queue()
    average_q = queue.Queue()

    #exam_path = max(glob.glob(os.path.join(args.dicom_path, 'p*/e*')), key=lambda d: os.stat(d).st_mtime)

    #dicom_finder = DicomFinder(exam_path, dicom_q, datetime.timedelta(seconds=args.interval))

    utils = Utilities()

    import glob

    [scan_top_dir,all_dirs] = utils.calibration(False)
    print all_dirs
    print scan_top_dir

    go = raw_input('Hit enter just before the scan starts:')

    # FIXME
    enter_dir = utils.enternewdirectory(scan_top_dir, all_dirs, 60.0)
    #enter_dir = utils.enternewdirectory(scan_top_dir, [], 10.0)
    #enter_dir = all_dirs[-1]
    print enter_dir
    if not enter_dir:
        assert(false)

    dicom_finder = IncrementalDicomFinder(enter_dir, dicom_q, 0.25)

    volumizer = Volumizer(dicom_q, volume_q)

    analyzer = Analyzer(volume_q, average_q)

    def term_handler(signum, stack):
        print 'Receieved SIGTERM - shutting down...'
        dicom_finder.halt()
        volumizer.halt()
        analyzer.halt()
        print 'Asked all threads to terminate'
        dicom_finder.join()
        volumizer.join()
        analyzer.join()
        print 'Process complete'
        sys.exit(0)

    signal.signal(signal.SIGINT, term_handler)
    signal.signal(signal.SIGTERM, term_handler)

    dicom_finder.start()
    volumizer.start()
    analyzer.start()

    while True: time.sleep(1)  # stick around to receive and process signals


