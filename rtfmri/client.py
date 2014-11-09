"""Contains class to interface with GE Scanner.

This is the lowest layer of the rtfmri machinery.

"""
from __future__ import print_function
import os.path as op
import ftplib
import socket
from cStringIO import StringIO
from datetime import datetime

import dicom


class ScannerClient(object):
    """Client to interface with GE scanner in real-time."""
    def __init__(self, hostname="cnimr", port=21,
                 username="", password="",
                 base_dir="/export/home1/sdc_image_pool/images"):
        """Inialize the client and connect to the FTP server.

        """
        self.hostname = hostname
        self.port = port
        self.username = username
        self.password = password
        self.base_dir = base_dir

        # Try to connect to the server, but catch errors
        # so that we can test aspects of this class without
        # an active FTP server
        try:
            self.connect()
        except socket.error:
            # Connection refused
            self.ftp = None
            print("Could not connect to FTP server.""")

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
        # Go through each entry and parse out the useful bits
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
            # TODO verify that this is true somehow
            time_str = "{} {} {} {}:{:06d}".format(year, month, day, time, i)

            # Get a unique timestamp for this entry
            timestamp = datetime.strptime(time_str, "%Y %b %d %H:%M:%f")

            # Insert a tuple of (timestamp, size, name) for this entry
            contents.append((timestamp, int(size), name))

        # Return this list sorted, which will be in timestamp order
        contents.sort()
        return contents

    def _latest_entry(self, dir):
        """Return a path to the most recent entry in `dir`."""
        contents = self.list_dir(dir)

        # Contents should be sorted, so we want first entry
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
        series_dirs = [op.join(exam_dir, n) for t, s, n in exam_contents]
        return series_dirs

    def series_info(self, exam_dir=None):
        """Return a dicts with information for all series from an exam."""
        if exam_dir is None:
            exam_dir = self.latest_exam

        # Get the list of series directories for this exam
        series_dirs = self.series_dirs(exam_dir)

        # Iterate over the files and build a list of dictionaries
        series_info = []
        for path in series_dirs:

            # Get a list of all the files for this series
            series_files = self.list_dir(path)

            # This directory could be empty
            if not series_files:
                continue

            # Build the dictionary based off the first DICOM in the list
            _, _, filename = series_files[0]
            dicom_path = op.join(path, filename)
            first_dicom = self.retrieve_dicom(dicom_path)
            dicom_timestamp = first_dicom.StudyDate + first_dicom.StudyTime
            dicom_info = {"Dicomdir": path,
                          "DateTime": datetime.strptime(dicom_timestamp,
                                                        "%Y%m%d%H%M%S"),
                          "Series": first_dicom.SeriesNumber,
                          "Description": first_dicom.SeriesDescription,
                          "NumAcquisitions": len(series_files),
                          }
            series_info.append(dicom_info)

        return series_info

    def retrieve_file(self, filename):
        """Return a file as a string buffer."""
        self.reconnect()
        buf = StringIO()
        self.ftp.retrbinary("RETR {}".format(filename), buf.write)
        buf.seek(0)
        return buf

    def retrieve_dicom(self, filename):
        """Return a file as a dicom object."""
        return dicom.filereader.read_file(self.retrieve_file(filename))
