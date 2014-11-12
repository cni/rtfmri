from __future__ import print_function
from Queue import Queue, Empty

from nose import SkipTest
import nose.tools as nt

from .. import client, queues


class TestFinder(object):

    def test_control(self):

        f = queues.Finder(interval=2)
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
        f = queues.SeriesFinder(self.client, q)
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
        f = queues.SeriesFinder(self.client, series_q, dicom_q)
        f.start()

        # We want to be able to stop the thead when tests fail
        try:

            for want_fname in self.client.series_files():
                got_fname = dicom_q.get(block=False)
                nt.assert_equal(want_fname, got_fname)

        finally:
            f.halt()
            f.join()
