"""
Contains class to interface with a GE scanner
via sftp to read directories and fetch dicoms.
This is the lowest layer of the rtfmri machinery.
"""
from __future__ import print_function
import re
import ftplib
import socket
import sys
import cStringIO
import os.path as op
from datetime import datetime

import libssh2
import dicom

from utilities import alphanum_key


class ScannerClient(object):
    """Client to interface via ssh protocol with GE scanner in realtime."""

    def __init__(self, hostname="cnimr", port=22,
                 username="", password="",
                 base_dir="/export/home1/sdc_image_pool/images",
                 private_key=None, public_key=None, lock=None):
        self.hostname = hostname
        self.username = username
        self.password = password
        self.port = port
        self.base_dir = base_dir

        self.public_key = public_key
        self.private_key = private_key

        # If using more than one SFTP client at a time, pass in a
        # threading.Lock as your mutex in order to avoid problems with gcrypt.
        self.lock = lock

        # Set the maximum buffer size for reading files via sftp
        self.max_buf_size = pow(2, 30)

        self.connect()

    def connect(self):

        try:
            if self.lock is not None: self.lock.acquire()
            self._prepare_sock()
        except socket.error as e:
            # Connection refused
            self.sftp = None
            raise(e)

        finally:
            if self.lock is not None: self.lock.release()

    def __del__(self):
        self.close()

    def _prepare_sock(self):
        """This code modified from
        https://github.com/wallix/pylibssh2/blob/master/examples/sftp_listdir.py
        """

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.hostname, self.port))
            self.sock.setblocking(1)
        except Exception, e:
            print("SockError: Can't connect socket to %s:%d" % (self.hostname, self.port))
            print(e)

        try:
            self.session = libssh2.Session()
            self.session.set_banner()
            self.session.startup(self.sock)

            # Support for keys would go like so, currently not tested but
            # included here because of poor documentation.
            if self.private_key is not None:
                self.session.userauth_publickey_fromfile(self.username,
                                                         self.public_key,
                                                         self.private_key,
                                                         self.password)
            else:
                self.session.userauth_password(self.username, self.password)
        except Exception, e:
            print("SSHError: Can't startup session")
            print(e)

        self.sftp = self.session._session.sftp_init()

    def close(self):
        """Close the connection to the SFTP server (if it exists)."""
        if self.session is not None:
            self.session.close()
            self.sock.close()

    def reconnect(self):
        """Reinitialize SFTP connection if it was dropped."""
        pass

    def path_exists(self, remote_path):
        '''Try to open remote dir, return false if we fail'''
        exist=True
        if self.lock is not None:
            self.lock.acquire()
        try:
            handle = self.sftp.opendir(remote_path)
            self.sftp.close(handle)
        except Exception:
            exist=False
        finally:
            if self.lock is not None:
                self.lock.release()
        return exist

    def list_dir(self, remote_path='.', sort='alpha', skip_parse = True):
        """Return a list of files in a directory sorted
        either alphanumerically if sort=='alpha' or based upon
        one of the attributes we get from sftp listdir which we put
        in a dictionary and pass to our parser.
        """

        if self.lock is not None:
            self.lock.acquire()
        try:
            handle = self.sftp.opendir(remote_path)
            if handle:
                files = []
                for file, attribute in self.sftp.listdir(handle):
                    size, uid, gid, mode, atime, mtime = attribute
                    files.append({
                        'name': file,
                        'size': size,
                        'uid': uid,
                        'gid': gid,
                        'mode': mode,
                        'atime': atime,
                        'mtime': mtime
                    })
            self.sftp.close(handle)
        finally:
            if self.lock is not None:
                self.lock.release()

        return self._parse_dir_output(files, sort=sort)

    def _parse_dir_output(self, file_list, sort='alpha'):
        """list_dir gives us a list of dictionaries for file names + stats.
           turn this into just the file names.
        """

        if sort == 'alpha':
            # Sort the files alphanumerically
            file_names = [x['name'] for x in file_list]
            self._alphanumeric_sort(file_names)
        else:
            # Sort the files based on attribute 'sort', eg mtime or size
            file_list.sort(key=lambda x: x[sort])
            file_names = [x['name'] for x in file_list]

        return self._clean(file_names)

    def _alphanumeric_sort(self, file_list):
        """Sort the file list by name respecting numeric order."""
        file_list.sort(key=alphanum_key)

    def _clean(self, files):
        # remove . files and things that aren't dicoms (useful in testing and
        # on scanner)
        return [x for x in files if '.DS_Store' not in x
                and '.txt' not in x
                and '.json' not in x
                and not x.startswith('.')
        ]

    def _latest_entry(self, path, sort='alpha'):
        """
        Return a path to the most recent entry in `path`.
        Most calls we make to this should be alphanumerically sorted, but
        in some cases we want the most recently modified on the scanner.
        """
        contents = self.list_dir(path, sort=sort)

        # Contents should be sorted, so we want last entry
        latest_name = contents[-1]

        # Build and return the full path
        path = op.join(path, latest_name)
        return path

    @property
    def latest_exam(self):
        """
        Dicoms are stored in basedir/patient/exam/session
        Return a path to the most recent exam directory.

        The latest patient, which will have a name like p2019,
        may not be the patient with the highest number in cases with
        multiple scans. Sorting by mtime will return the patient
        who has most recently been scanned, assuming at least one scan
        has been performed.
        """
        #print(self.base_dir)
        latest_patient = self._latest_entry(self.base_dir, sort='mtime')
        #print(latest_patient)
        return self._latest_entry(latest_patient)

    @property
    def latest_series(self):
        """Return a path to the most recent series directory."""
        # The series directory should always be three layers deep
        return self._latest_entry(self.latest_exam)


    def series_dirs(self, exam_dir=None):
        """Return a list of all series dirs for an exam."""
        if exam_dir is None:
            exam_dir = self.latest_exam

        # Get the list of entries in the exam dir
        exam_contents = self.list_dir(exam_dir)
        series_dirs = [op.join(exam_dir, n) for n in exam_contents]
        return series_dirs

    def series_files(self, series_dir=None):
        """Return a list of all files for a series."""
        if series_dir is None:
            series_dir = self.latest_series

        # Get the list of entries in the exam dir
        series_contents = self.list_dir(series_dir)
        series_files = [op.join(series_dir, n) for n in series_contents]
        return series_files

    def series_info(self, series_dir=None):
        """
        Return a dict with information about a series.
        In practice, this function adds significant overhead if performing
        neurofeedback, so we often will want to skip.
        """
        if series_dir is None:
            series_dir = self.latest_series

        # Get a list of all the files for this series
        series_files = self.list_dir(series_dir)

        # This directory could be empty
        if not series_files:
            return {}

        # Build the dictionary based off the first DICOM in the list
        filename = series_files[0]
        dicom_path = op.join(series_dir, filename)
        first_dicom = self.retrieve_dicom(dicom_path)
        dicom_timestamp = first_dicom.StudyDate + first_dicom.StudyTime
        n_timepoints = getattr(first_dicom, "NumberOfTemporalPositions", 1)

        series_info = {
            "Dicomdir": series_dir,
            "DateTime": datetime.strptime(dicom_timestamp, "%Y%m%d%H%M%S"),
            "Series": first_dicom.SeriesNumber,
            "Description": first_dicom.SeriesDescription,
            "NumTimepoints": n_timepoints,
            "NumAcquisitions": len(series_files)
        }

        return series_info

    def retrieve_file(self, filename):
        """Return a file as a cstring buffer."""

        if self.lock is not None: self.lock.acquire()
        buf = cStringIO.StringIO()

        try:
            handle = self.sftp.open(filename, 'r', self.max_buf_size)
            while True:
                # In practice, we will read all the data, but SFTP can be slow
                # when we read into a buffer smaller than the file.
                data = self.sftp.read(handle, self.max_buf_size)
                if not data:
                    break
                buf.write(data)
            buf.seek(0)
            self.sftp.close(handle)
        finally:
            if self.lock is not None: self.lock.release()

        return buf



    def retrieve_dicom(self, filename):
        """Return a file as a dicom object."""
        try:
            return dicom.read_file(self.retrieve_file(filename), force=True)
        except Exception as e:
            print("Received an exception:", e, filename)
            raise e







