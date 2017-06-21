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
        cls.port = 2124
        cls.base_dir = "test_data"

        # Pass the default credentials to connect to the test FTP server
        cls.client = client.ScannerClient(hostname=cls.host,
                                          port=cls.port,
                                          base_dir=cls.base_dir)
        cls.no_server = cls.client.sftp is None

    @classmethod
    def teardown_class(cls):

        if cls.client.sftp is not None:
            cls.client.close()

    def test_sftp_connection(self):

        if self.no_server:
            raise SkipTest

        nt.assert_equal(self.client.hostname, self.host)
        nt.assert_equal(self.client.port, self.port)

    def test_list_dir(self):

        if self.no_server:
            raise SkipTest

        # List the base directory of the test server
        contents = self.client.list_dir(self.client.base_dir)

        nt.assert_equal(len(contents), 1)
        name = contents[0]
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

    def test_clean(self):
        filenames = [
            'MR.1.2.840.113619.2.283.4120.7575399.15401.1363019204.97.dcm',
            'MR.1.2.840.113619.2.283.4120.7575399.15401.1363019204.98.dcm',
            'MR.1.2.840.113619.2.283.4120.7575399.15401.1363019204.99.dcm',
            '.files',
            '.DS_Store',
            'record.json',
            'notes.txt',
            '.',
            '..'
        ]

        cleaned_filenames = [
            'MR.1.2.840.113619.2.283.4120.7575399.15401.1363019204.97.dcm',
            'MR.1.2.840.113619.2.283.4120.7575399.15401.1363019204.98.dcm',
            'MR.1.2.840.113619.2.283.4120.7575399.15401.1363019204.99.dcm'
        ]

        nt.assert_equal(cleaned_filenames, self.client._clean(filenames))


    def test_parse_dir_output(self):

        #construct a file list of dictionaries containing attributes
        import os
        import stat

        test_files = []

        session_path = 'test_data/p004/e4120'
        for f in os.listdir(session_path):
            fpath = os.path.join(session_path, f)
            stats = os.stat(fpath)
            test_files.append({
                'name': f,
                'size': stats[stat.ST_SIZE],
                'uid': stats[stat.ST_UID],
                'gid': stats[stat.ST_GID],
                'mode': stats[stat.ST_MODE],
                'atime': stats[stat.ST_ATIME],
                'mtime': stats[stat.ST_MTIME]
            })

        #sort them alphanumerically
        file_names = [x['name'] for x in test_files]
        self.client._alphanumeric_sort(file_names)
        alpha_sorted = self.client._clean([x for x in file_names])


        #sort them by mtime
        test_files.sort(key=lambda x: x['mtime'])
        mtime_sorted = self.client._clean([x['name'] for x in test_files])

        alpha_parsed = self.client._parse_dir_output(test_files)
        mtime_parsed = self.client._parse_dir_output(test_files, sort='mtime')

        nt.assert_equal(alpha_parsed, alpha_sorted)
        nt.assert_equal(mtime_parsed, mtime_sorted)

        #we should get the same list when called with list_dir
        alpha_listed = self.client.list_dir(session_path)
        mtime_listed = self.client.list_dir(session_path, sort='mtime')

        nt.assert_equal(alpha_listed, alpha_sorted)
        nt.assert_equal(mtime_listed, mtime_sorted)

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
                        "test_data/p004/e4120/4120_11_1_dicoms")

    def test_series_dirs(self):

        if self.no_server:
            raise SkipTest

        exam_dir = self.client.latest_exam
        file_list = self.client.list_dir(exam_dir)
        path_list = self.client.series_dirs(exam_dir)

        # File list and path list should match
        for path, name in zip(path_list, file_list):
            nt.assert_equal(path, op.join(exam_dir, name))

    def test_series_files(self):

        if self.no_server:
            raise SkipTest

        series_dir = self.client.latest_series
        file_list = self.client.list_dir(series_dir)
        path_list = self.client.series_files(series_dir)

        # File list and path list should match
        for path, name in zip(path_list, file_list):
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
        name = self.client.list_dir(series_dir)[0]
        filename = op.join(series_dir, name)

        dcm1 = self.client.retrieve_dicom(filename)
        binary_data = self.client.retrieve_file(filename)
        dcm2 = dicom.filereader.read_file(binary_data)
        nt.assert_equal(dcm1.PixelData, dcm2.PixelData)
