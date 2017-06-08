import re
import socket
import sys
import cStringIO
import pdb

import os.path as op
from datetime import datetime

import libssh2
import pydicom

from utilities import alphanum_key

# usage = """Do a SFTP file listing of <directory> with username@hostname
# Usage: %s <hostname> <username> <password> <directory>""" %
# __file__[__file__.rfind('/')+1:]


class BaseClient(object):

    def __init__(self, hostname='localhost', username='', password='',
                 port=2124, base_dir='.'):
        self.hostname = hostname
        self.username = username
        self.password = password
        self.port = port
        self.base_dir = base_dir

        self.connect()

    def connect(self):
        pass

    def retrieve_dicom(self, filename):
        """Return a file as a dicom object."""
        try:
            return pydicom.read_file(self.retrieve_file(filename), force=True)
        except Exception as e:
            print(filename)
            print(type(e).__name__)
            raise(e)
            # pdb.set_trace()

    def _alphanumeric_sort(self, file_list):
        """Sort the file list by name respecting numeric order.

        DICOM filenames are numerically sequential, but not zero-padded.
        The SFTP server gives us a list of files in "sorted" order, but
        that means the files are not in sequential order. Fix that here.

        """

        file_list.sort(key=alphanum_key)

    def list_dir(self, dir):
        raise(NotImplementedError("Base class does not need to list dir"))


    def _latest_entry(self, dir):
        """Return a path to the most recent entry in `dir`."""
        contents = self.list_dir(dir)

        # Contents should be sorted, so we want last entry
        latest_name = contents[-1][-1]

        # Build and return the full path
        path = op.join(dir, latest_name)
        return path

    @property
    def latest_exam(self):
        """Return a path to the most recent exam directory."""
        # The exam directory should always be two layers deep
        latest_patient = self._latest_entry(self.base_dir)
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
        """Return a dicts with information about a series."""
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
        #dicom_timestamp = first_dicom.StudyDate + first_dicom.StudyTime
        n_timepoints = getattr(first_dicom, "NumberOfTemporalPositions", 1)

        series_info = {
            #"Dicomdir": series_dir,
            #"DateTime": datetime.strptime(dicom_timestamp, "%Y%m%d%H%M%S"),
            #"Series": first_dicom.SeriesNumber,
            #"Description": first_dicom.SeriesDescription,
            "NumTimepoints": n_timepoints,
            #"NumAcquisitions": len(series_files),
        }

        return series_info


class FTPClient(BaseClient):

    def connect(self):
        """Connect to the FTP server."""
        self.ftp = ftplib.FTP()
        self.ftp.connect(host=self.hostname, port=self.port)
        self.ftp.login(user=self.username, passwd=self.password)

    def reconnect(self):
        """Reinitialize FTP connection if it was dropped."""
        try:
            self.ftp.voidcmd("NOOP")
        except ftplib.error_temp:
            # Connection has timed out, so reconnect
            self.connect()

    def close(self):
        """Close the connection to the FTP server (if it exists)."""
        if self.ftp is not None:
            self.ftp.close()

    def __del__(self):
        """Close the connection when the object is destroyed."""
        self.close()

    def list_dir(self, dir):
        """Return (timestamp, size, name) for contents in a directory."""
        self.reconnect()

        # Get an ls style list of items in `dir`
        file_list = []
        self.ftp.dir(dir, file_list.append)

        # Parse the output and return
        return self._parse_dir_output(file_list)

    def _parse_dir_output(self, file_list):
        """Parse a UNIX-style ls output from the FTP server."""
        # Sort the file list, respecting alphanumeric order
        self._alphanumeric_sort(file_list)
        file_list = [x for x in file_list if not x.startswith(
            '.') and '.DS_Store' not in x]
        # Now go back through each entry and parse out the useful bits
        contents = []
        for i, entry in enumerate(file_list, 1):
            _, _, _, _, size, month, day, time, name = entry.split()
            year = datetime.now().year

            # If the entry is more than a year old, the `time` entry
            # will be a year. But we don't care about those files for
            # real-time usage, so skip them.
            if ":" not in time:
                continue

            # The ls output only gives us timestamps at minute resolution
            # so we are going to use the index in the list to mock a
            # microsecond timestamp. This assumes that we're getting the
            # directory contents in a meaningful sequential order.
            # That should be true because of a) how the scanner names DICOMS
            # and b) the sorting operation we performed above
            time_str = "{} {} {} {}:{:06d}".format(year, month, day, time, i)

            # Get a unique timestamp for this entry
            timestamp = datetime.strptime(time_str, "%Y %b %d %H:%M:%f")

            # Insert a tuple of (timestamp, size, name) for this entry
            contents.append((timestamp, int(size), name))

        # Return this list sorted, which will be in timestamp order.
        # Because of how timestamps work, this is going to be somewhat
        # incorrect. If we created File A on November 16, 2013 and today
        # is November 15, 2014, a file created today is going to look "older"
        # than File A. However I think this won't be a problem in practice,
        # because the scanner doesn't keep files on it for that long.
        # (But maybe it will be an issue right around New Years?)
        contents.sort()
        return contents

    def retrieve_file(self, filename):
        """Return a file as a string buffer."""
        self.reconnect()
        buf = StringIO()
        self.ftp.retrbinary("RETR {}".format(filename), buf.write)
        buf.seek(0)
        return buf


class SFTPClient(BaseClient):

    def __init__(self, hostname='localhost', username='', password=None,
                 port=2124, base_dir='.', private_key=None, public_key=None):
        self.public_key = public_key
        self.private_key = private_key
        self.max_buf_size = pow(2, 30)  # 30 is max

        super(SFTPClient, self).__init__(hostname=hostname, username=username,
                                         password=password, port=port,
                                         base_dir=base_dir)

    def connect(self):

        try:
            self._prepare_sock()
            #print("Connected!")
        except socket.error:
            # Connection refused
            self.sftp = None
            print("Socket error: could not connect to SFTP server.""")

    def _prepare_sock(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.hostname, self.port))
            self.sock.setblocking(1)
        except Exception, e:
            print "SockError: Can't connect socket to %s:%d" % (self.hostname, self.port)
            print e

        try:
            self.session = libssh2.Session()
            self.session.set_banner()
            self.session.startup(self.sock)

            # Support for private key would go like so, currently not tested.
            self.private_key = None
            if self.private_key:
                self.session.userauth_publickey_fromfile(self.username,
                                                         self.public_key,
                                                         self.private_key,
                                                         self.password)
            else:
                self.session.userauth_password(self.username, self.password)
        except Exception, e:
            print "SSHError: Can't startup session"
            print e

        # use low level layer because we don't yet provide High layer for sftp
        self.sftp = self.session._session.sftp_init()

    def list_dir(self, remote_path='.', sort='alpha'):
        """Return a dictionary for contents in a directory."""
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
        return self._parse_dir_output(files, sort=sort)

    def _parse_dir_output(self, file_list, sort='alpha'):
        """list_dir gives us a dictionary of files + attributes.
           turn this into just the file names.
        """
        # You can sort by any of the attributes in the dictionary, or use
        # the old alphanumeric sort.
        # On scanner, sorting by atime should be fastest (no re) and simple.
        if sort == 'alpha':
            file_names = [x['name'] for x in file_list]
            self._alphanumeric_sort(file_names)
        else:
            file_list.sort(key=lambda x: x[sort])
            file_names = [x['name'] for x in file_list]
        return self._clean(file_names)

    def _clean(self, files):
        return [x for x in files if '.DS_Store' not in x
                and '.txt' not in x
                and '.json' not in x
        ]

    def _latest_entry(self, dir):
        """Return a path to the most recent entry in `dir`."""
        #print dir
        contents = self.list_dir(dir)

        # Contents should be sorted, so we want last entry
        latest_name = contents[-1]

        # Build and return the full path
        path = op.join(dir, latest_name)
        return path

    def retrieve_file(self, filename):
        """Return a file as a buffer."""
        #print filename
        buf = cStringIO.StringIO()
        handle = self.sftp.open(filename, 'r', self.max_buf_size)
        while True:
            data = self.sftp.read(handle, self.max_buf_size)
            if not data:
                break
            buf.write(data)
        buf.seek(0)
        self.sftp.close(handle)
        return buf

    def reconnect(self):
        """Reinitialize FTP connection if it was dropped."""
        # not sure the best way to implement this yet...
        pass

    def close(self):
        """Close the connection to the SFTP server (if it exists)."""
        if self.session is not None:
            self.session.close()
            self.sock.close()

    def __del__(self):
        self.close()

