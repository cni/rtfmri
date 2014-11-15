from __future__ import print_function
from Queue import Queue, Empty

from nose import SkipTest
import nose.tools as nt

from .. import client, queuemanagers as qm

import numpy as np


class TestFinder(object):

    def test_control(self):

        f = qm.Finder(interval=2)
        assert f.alive

        f.halt()
        assert not f.alive

        nt.assert_equal(f.interval, 2)


class TestFinders(object):

    @classmethod
    def setup_class(cls):
        # TODO abstract this out into a base testing class, as it
        # is currently getting copied throughout the codebase

        cls.host = "localhost"
        cls.port = 2121
        cls.base_dir = "test_data"

        # Pass the default credentials to connect to the test FTP server
        cls.client = client.ScannerClient(hostname=cls.host,
                                          port=cls.port,
                                          base_dir=cls.base_dir)
        cls.no_server = cls.client.ftp is None

    @classmethod
    def teardown_class(cls):

        if cls.client.ftp is not None:
            cls.client.close()

    def test_series_finder(self):

        if self.no_server:
            raise SkipTest

        q = Queue()
        f = qm.SeriesFinder(self.client, q)
        f.start()

        # We want to be able to stop the thead when tests fail
        try:

            for want_series in self.client.series_dirs():
                got_series = q.get(block=False)
                nt.assert_equal(want_series, got_series)

        finally:
            f.halt()
            f.join()

    def test_dicom_finder(self):

        if self.no_server:
            raise SkipTest

        series_q = Queue()
        series_q.put(self.client.latest_series)

        dicom_q = Queue()
        f = qm.SeriesFinder(self.client, series_q, dicom_q)
        f.start()

        # We want to be able to stop the thead when tests fail
        try:

            for want_fname in self.client.series_files():
                got_fname = dicom_q.get(block=False)
                nt.assert_equal(want_fname, got_fname)

        finally:
            f.halt()
            f.join()

    def test_volumizer_affine(self):

        class MockDicom(object):

            PixelSpacing = ['2', '2']
            SpacingBetweenSlices = '2.2'
            ImagePositionPatient = ['-106.289', '-76.0826', '115.279']

            def __contains__(self, name):

                try:
                    getattr(self, name)
                    return True
                except AttributeError:
                    return False

        want_affine = np.array([
            [2, 0, 0,   106.289],
            [0, 2, 0,   76.0826],
            [0, 0, 2.2, 115.279],
            [0, 0, 0,   1]]
            )

        volumizer = qm.Volumizer(None, None)
        dcm = MockDicom()

        got_affine = volumizer.generate_affine_matrix(dcm)

        np.testing.assert_array_equal(want_affine, got_affine)

    def test_volumizer_volume_assembly(self):

        series = "test_data/p004/e4120/4120_11_1_dicoms"
        files = self.client.series_files(series)[:40]
        slices = [self.client.retrieve_dicom(f) for f in files]

        volumizer = qm.Volumizer(None, None)
        volume = volumizer.assemble_volume(slices)

        image_data = volume["image"].get_data()
        nt.assert_equal(image_data.shape, (120, 120, 40))
        nt.assert_equal(volume["tr"], 1.5)

        nt.assert_equal(volume["exam"], 4120)
        nt.assert_equal(volume["series"], 11)
        nt.assert_equal(volume["acquisition"], 1)

    def test_volumizer(self):

        dicom_q = Queue()
        series = "test_data/p004/e4120/4120_11_1_dicoms"
        files = self.client.series_files(series)[:80]
        for f in files:
            dicom_q.put(self.client.retrieve_dicom(f))

        volume_q = Queue()
        volumizer = qm.Volumizer(dicom_q, volume_q)

        try:
            volumizer.start()

            vol1 = volume_q.get(timeout=5)
            vol2 = volume_q.get(timeout=5)

            for vol in [vol1, vol2]:
                image_shape = vol["image"].get_data().shape
                nt.assert_equal(image_shape, (120, 120, 40))

            with nt.assert_raises(Empty):
                volume_q.get(block=False)

        finally:
            volumizer.halt()
            volumizer.join()
