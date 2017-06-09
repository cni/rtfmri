"""High-level interface to manage moving parts of realtime code."""

import sys, os, time
import signal
import socket
from Queue import Queue
from threading import Lock

from clients import SFTPClient
from queuemanagers import SeriesFinder, DicomFinder, Volumizer


class ScannerInterface(object):
    """Interface for getting real-time data off the scanner.

    There are a number of moving parts involved in talking to the
    scanner and getting useful data (in the form of nibabel image
    objects with metadata for each timeseries volume.

    This groups the various pieces into one object that's easy to
    interface with.

    """

    def __init__(self, hostname='localhost', username='', password=None,
                 port=2124, base_dir='.', private_key=None, public_key=None):
        """Initialize the interface object.

        The positional and keyword arguments are passed through
        to the underlying scanner client objects.

        """
        # Keep two different FTP clients for the series and
        # volume queues so they don't interfere with each other

        #Track if we've started to avoid joining unstarted threads
        self.alive = False

        self.mutex = Lock()

        try:
            client1 = SFTPClient(hostname=hostname, username=username,
                                 password=password, port=port,
                                 base_dir=base_dir, private_key=private_key,
                                 public_key=public_key, mutex = self.mutex)

            client2 = SFTPClient(hostname=hostname, username=username,
                                 password=password, port=port,
                                 base_dir=base_dir, private_key=private_key,
                                 public_key=public_key, mutex = self.mutex)
            try:
                print(client1.latest_exam)
                print(client2.latest_exam)
                self.sftp_success = True
            except Error:
                self.sftp_success = False
                raise(socket.error,"SFTP failed to check dir...")

        except Exception as e:
            print(e)
            raise(socket.error, "Login failed")

        print("SUCCESS!")

        # Set an attribute so we know if we could connect
        #

        # Initialize the queue objects
        series_q = Queue()
        dicom_q = Queue()
        volume_q = Queue()

        # Initialize the queue manager threads
        self.series_finder = SeriesFinder(client1, series_q, interval=1)
        self.dicom_finder = DicomFinder(client2, series_q, dicom_q, interval=0.001)
        self.volumizer = Volumizer(dicom_q, volume_q, interval=0.001)


    def set_dicom_filter(self, dcmf):
        self.dicom_finder.set_dicom_filter(dcmf)
        self.volumizer.set_dicom_filter(dcmf)


    def start(self):
        """Start the constituent threads."""
        self.alive = True
        self.series_finder.start()
        self.dicom_finder.start()
        self.volumizer.start()
        print("Started...")

    def get_volume(self, *args, **kwargs):
        """Semantic wrapper for pulling a volume off the volume queue."""
        return self.volumizer.volume_q.get(*args, **kwargs)

    def shutdown(self):
        """Halt and join the threads so we can exit cleanly."""
        if self.alive:
            self.volumizer.halt()
            self.series_finder.halt()
            self.dicom_finder.halt()

            self.volumizer.join()
            self.series_finder.join()
            self.dicom_finder.join()

            self.alive = False

    def __del__(self):

        self.shutdown()

class ScannerFTPInterface(object):
    """Interface for getting real-time data off the scanner.

    There are a number of moving parts involved in talking to the
    scanner and getting useful data (in the form of nibabel image
    objects with metadata for each timeseries volume.

    This groups the various pieces into one object that's easy to
    interface with.

    """

    def __init__(self, *args, **kwargs):
        """Initialize the interface object.

        The positional and keyword arguments are passed through
        to the underlying scanner client objects.

        """
        # Keep two different FTP clients for the series and
        # volume queues so they don't interfere with each other
        client1 = SFTPClient(*args, **kwargs)
        client2 = SFTPClient(*args, **kwargs)

        # Set an attribute so we know if we could connect
        self.has_ftp_connection = client1.ftp is not None

        # Initialize the queue objects
        series_q = Queue()
        dicom_q = Queue()
        volume_q = Queue()

        # Initialize the queue manager threads
        self.series_finder = SeriesFinder(client1, series_q, interval=1)
        self.dicom_finder = DicomFinder(client2, series_q, dicom_q, interval=0)
        self.volumizer = Volumizer(dicom_q, volume_q, interval=0)

        #Track if we've started to avoid joining unstarted threads
        self.alive = False


    def start(self):
        """Start the constituent threads."""
        self.alive = True
        self.series_finder.start()
        self.dicom_finder.start()
        self.volumizer.start()

    def get_volume(self, *args, **kwargs):
        """Semantic wrapper for pulling a volume off the volume queue."""
        return self.volumizer.volume_q.get(*args, **kwargs)

    def shutdown(self):
        """Halt and join the threads so we can exit cleanly."""
        if self.alive:
            self.volumizer.halt()
            self.series_finder.halt()
            self.dicom_finder.halt()

            self.volumizer.join()
            self.series_finder.join()
            self.dicom_finder.join()

            self.alive = False

    def __del__(self):

        self.shutdown()





def setup_exit_handler(scanner, analyzer=None):
    """Method that will let us ctrl-c the object and kill threads."""
    def exit(signum, stack):
        scanner.shutdown()
        if analyzer != None:
            analyzer.halt()
            analyzer.join()
        sys.exit(0)

    signal.signal(signal.SIGINT, exit)
    signal.signal(signal.SIGTERM, exit)
