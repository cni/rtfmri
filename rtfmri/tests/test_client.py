import os.path as op
from datetime import datetime

import dicom

from nose import SkipTest
import nose.tools as nt

from .. import client


# TODO find some way to programatically know the ground truth for attributes
# of the test FTP server, currently the expected values are all hard-coded


class TestScannerClient(object):

    @classmethod
    def setup_class(cls):

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

    def test_ftp_connection(self):

        if self.no_server:
            raise SkipTest

        nt.assert_equal(self.client.ftp.host, self.host)
        nt.assert_equal(self.client.ftp.port, self.port)

    def test_list_dir(self):

        if self.no_server:
            raise SkipTest

        # List the base directory of the test server
        contents = self.client.list_dir(self.client.base_dir)

        nt.assert_equal(len(contents), 1)
        _, _, name = contents[0]
        nt.assert_equal(name, "p004")

    def test_alphanum_sort(self):

        test_list = ["1", "10", "2", "3", "4", "5", "6", "7", "8", "9"]
        want_list = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]

        self.client._alphanumeric_sort(test_list)
        nt.assert_equal(test_list, want_list)

        test_list = [
            '-rw-rw-r-- 1 mwaskom  staff 27304 Nov 1 22:04 MR.1.2.840.10.dcm',
            '-rw-rw-r-- 1 mwaskom  staff 27304 Nov 1 22:04 MR.1.2.840.100.dcm',
            '-rw-rw-r-- 1 mwaskom  staff 27304 Nov 1 22:04 MR.1.2.840.11.dcm',
        ]

        want_list = [
            '-rw-rw-r-- 1 mwaskom  staff 27304 Nov 1 22:04 MR.1.2.840.10.dcm',
            '-rw-rw-r-- 1 mwaskom  staff 27304 Nov 1 22:04 MR.1.2.840.11.dcm',
            '-rw-rw-r-- 1 mwaskom  staff 27304 Nov 1 22:04 MR.1.2.840.100.dcm',
        ]

        self.client._alphanumeric_sort(test_list)
        nt.assert_equal(test_list, want_list)

    def test_parse_dir_output(self):

        test_list = [
            "drwx------   3 mwaskom  staff   102 May 26 12:39 Applications",
            "drwx------+  9 mwaskom  staff   306 Nov  7  2013 Desktop",
            "drwx------+  3 mwaskom  staff   109 May 24 17:20 Documents",
            "drwx------+ 34 mwaskom  staff  1156 Oct 26 11:19 Downloads"
        ]

        parsed = self.client._parse_dir_output(test_list)

        # We expect the "Desktop" entry to get dropped
        nt.assert_equal(len(parsed), 3)

        # Pull out the first entry (the earliest item in the list)
        entry = parsed[0]
        timestamp, size, name = entry

        # Build the timestamp we expect for the first entry
        year = datetime.now().year
        expected_time = "{} May 24 17:20:000003".format(year)
        expected_timestamp = datetime.strptime(expected_time,
                                               "%Y %b %d %H:%M:%f")

        # Test the entries we got against what we want
        nt.assert_equal(timestamp, expected_timestamp)
        nt.assert_equal(size, 109)
        nt.assert_equal(name, "Documents")

        # Test that the names are in the right order
        ordered_names = ["Documents", "Applications", "Downloads"]
        for (_, _, got_name), want_name in zip(parsed, ordered_names):
            nt.assert_equal(got_name, want_name)

    def test_latest_entry(self):

        if self.no_server:
            raise SkipTest

        path = self.client._latest_entry("test_data")
        nt.assert_equal(path, "test_data/p004")

    def test_latest_exam(self):

        if self.no_server:
            raise SkipTest

        nt.assert_equal(self.client.latest_exam, "test_data/p004/e4120")

    def test_latest_series(self):

        if self.no_server:
            raise SkipTest

        nt.assert_equal(self.client.latest_series,
                        "test_data/p004/e4120/4120_4_1_dicoms")

    def test_series_dirs(self):

        if self.no_server:
            raise SkipTest

        exam_dir = self.client.latest_exam
        file_list = self.client.list_dir(exam_dir)
        path_list = self.client.series_dirs(exam_dir)

        # File list and path list should match
        for path, (_, _, name) in zip(path_list, file_list):
            nt.assert_equal(path, op.join(exam_dir, name))

    def test_series_files(self):

        if self.no_server:
            raise SkipTest

        series_dir = self.client.latest_series
        file_list = self.client.list_dir(series_dir)
        path_list = self.client.series_files(series_dir)

        # File list and path list should match
        for path, (_, _, name) in zip(path_list, file_list):
            nt.assert_equal(path, op.join(series_dir, name))

    def test_series_info(self):

        if self.no_server:
            raise SkipTest

        series_info = self.client.series_info()

        nt.assert_is_instance(series_info, dict)
        nt.assert_equal(set(series_info.keys()),
                        {"Dicomdir", "Series",
                         "DateTime", "Description",
                         "NumAcquisitions", "NumTimepoints"})

        series_dirs = self.client.series_dirs()
        nt.assert_in(series_info["Dicomdir"], series_dirs)

        nt.assert_equal(series_info["NumAcquisitions"],
                        len(self.client.list_dir(series_info["Dicomdir"])))

    def test_file_retrieval(self):

        if self.no_server:
            raise SkipTest

        series_dir = self.client.latest_series
        _, _, name = self.client.list_dir(series_dir)[0]
        filename = op.join(series_dir, name)

        dcm1 = self.client.retrieve_dicom(filename)
        binary_data = self.client.retrieve_file(filename)
        dcm2 = dicom.filereader.read_file(binary_data)
        nt.assert_equal(dcm1.PixelData, dcm2.PixelData)
