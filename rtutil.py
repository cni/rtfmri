
import datetime
import time
import os
import threading
import Queue as queue
import glob
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
        files.sort()
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
    """
    Analyzer gets 3D volumes out of the volume queue and computes real-time statistics on them.
    """

    def __init__(self, volume_q, average_q):
        super(Analyzer, self).__init__()
        self.volume_q = volume_q
        self.average_q = average_q
        self.alive = True
        self.whole_brain = None
        self.brain_list = []
        self.ref_vol = None
        self.mean_img = 0.
        self.mc_xform = []
        self.mean_displacement = []
        self.max_displacement = 0.

    def halt(self):
        # temp saver:
        #test_image = nib.Nifti1Image(self.ref_vol)
        #nib.save(test_image, '/tmp/rtmc_test_brain.nii')
        self.alive = False

    def run(self):
        while self.alive:
            try:
                volimg = self.volume_q.get(timeout=1)
            except queue.Empty:
                pass
            else:
                if not self.ref_vol:
                    self.ref_vol = volimg
                else:
                    # compute motion
                    hist_reg = nipy.algorithms.registration.HistogramRegistration(volimg, self.ref_vol)
                    T = hist_reg.optimize('rigid')
                    aligned_img = nipy.algorithms.registration.resample(volimg, T, self.ref_vol)
                    self.mean_img += aligned_img.get_data().astype(float)
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
                    self.mean_displacement.append(mean_disp)
                    if mean_disp > self.max_displacement:
                        self.max_displacement = mean_disp
                    self.mc_xform.append(T)
                    print "mean displacement: %f mm, max displacement = %f mm" % (mean_disp, self.max_displacement)



