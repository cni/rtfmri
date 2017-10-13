import pdb
import subprocess
import os.path as op
from datetime import datetime
from Queue import Queue, Empty

import dicom

from nose import SkipTest
import nose.tools as nt
from nilearn.input_data import NiftiMasker
import numpy.testing as npt

from .. import client, masker
from .. import queuemanagers as qm



class TestScannerClient(object):

    @classmethod
    def setup_class(cls):

        cls.host = "localhost"
        cls.port = 2124
        cls.base_dir = "test_data"

        # Pass the default credentials to connect to the test FTP server
        cls.client = client.ScannerClient(hostname=cls.host,
                                          port=cls.port,
                                          base_dir=cls.base_dir)
        cls.no_server = cls.client.sftp is None
        cls.mask = 'test_data/naccpos.nii.gz'

    @classmethod
    def teardown_class(cls):

        if cls.client.sftp is not None:
            cls.client.close()

    def test_masker(self):
        """test init"""
        m = masker.Masker(self.mask)
        nt.assert_equal(m.mask_img, self.mask)
        nt.assert_equal(m.center, -2.1443950479680893)
        nt.assert_equal(m.fit, False)
        nt.assert_equal(m.use_orthogonal, False)
        nt.assert_equal(m.radius, 8)
        nt.assert_equal(m.ortho_fits, [])
        nt.assert_equal(m.orthogonals, [])

    def test_com(self):
        """ Check the z COM vs AFNI, requires AFNI on path"""
        try:
            subprocess.check_output(['which', '3dCM'])
        except CalledProcessError:

            raise SkipTest

        m = masker.Masker(self.mask)
        z_com_rtfmri = m.find_center_of_mass(m.masker)

        #requires afni
        output = subprocess.check_output(['3dCM', self.mask ])
        z_com_afni =  float(output.strip().split()[2])

        npt.assert_almost_equal(z_com_rtfmri, z_com_afni, decimal=4)



    def test_reduce_volume(self):
        m = masker.Masker(self.mask)

        try:
            subprocess.check_output(['which', '3dmaskave'])
        except CalledProcessError:
            raise SkipTest
        """ Test if we get proper volume reduction """ 
        test_niftii = 'test_data/15940_6_1.nii.gz'

        mask_command = ['3dmaskave', '-quiet', '-mask',self.mask, test_niftii]
        ts = subprocess.check_output(mask_command)
        ts = [ float(x) for x in ts.split('\n')[:-1] ]

        #set up a volumizer
        dicom_q = Queue()
        series = "/test_data/test_dicoms/20170831_1710/6_1_EPI29_2s_ExcitedFB1/15940_6_1_dicoms"
        files = self.client.series_files(series)
        #print(files)

        # Randomize the order of the files
        # The dicoms in the test dataset happen to be in the
        # correct temporal order when sorted by file name, but
        # this is not garunteed and the code should be able to
        # handle slices that are out of order

        # for f in files:
        #     dicom_q.put(self.client.retrieve_dicom(f))

        volume_q = Queue()
        volumizer = qm.Volumizer(dicom_q, volume_q)

        last = 0
        counter = 0
        try:
            volumizer.start()
            print('started volumizer')
            while counter  < 4: #len(ts):
                try:

                    vol = volume_q.get(timeout=.1)
                    reduced = m.reduce_volume(vol)
                    if reduced!=last:
                        last=reduced
                        npt.assert_almost_equal(reduced, ts[counter], decimal=2)
                        print(reduced, ts[counter])
                        counter += 1
                except Empty, e:
                    print(e)
                    for i in range(46):
                        f = files.pop(0)
                        print(f)
                        dicom_q.put(self.client.retrieve_dicom(f))

        finally:
            volumizer.halt()
            volumizer.join()


