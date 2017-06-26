from __future__ import print_function
import time

import nose.tools as nt
from nose import SkipTest

from .. import interface


class TestScannerInterface(object):
    @classmethod
    def setup_class(cls):

        cls.host = "localhost"
        cls.port = 2124
        cls.base_dir = "test_data"

        # Pass the default credentials to connect to the test FTP server
        cls.interface = interface.ScannerInterface(hostname=cls.host,
                                                   port=cls.port,
                                                   base_dir=cls.base_dir)
        cls.interface.start()
        cls.no_server = not cls.interface.has_sftp_connection

    @classmethod
    def teardown_class(cls):

        if not cls.no_server:
            cls.interface.shutdown()

    def test_sftp_connection(self):
        # Pass the default credentials to connect to the test FTP server


        if self.no_server:
            print("No connection")
            raise SkipTest


        nt.assert_equal(self.interface.series_finder.client.base_dir, 'test_data')
        nt.assert_equal(self.interface.dicom_finder.client.latest_exam,
                        'test_data/p004/e4120')

        nt.assert_equal(self.interface.series_finder.client.latest_series,
                        'test_data/p004/e4120/4120_11_1_dicoms')

        self.interface.shutdown()

    def test_get_volume(self):
        # This will currently fail if the volumizer crashes...

        vol = self.interface.get_volume(timeout=5)

        assert vol


