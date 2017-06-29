"""High-level interface to manage moving parts of realtime code."""
import sys, os, time
import signal
import socket
from Queue import Queue
from threading import Lock


from .client import ScannerClient
from .queuemanagers import SeriesFinder, DicomFinder, Volumizer


class ScannerInterface(object):
    """Interface for getting real-time data off the scanner.

    There are a number of moving parts involved in talking to the
    scanner and getting useful data (in the form of nibabel image
    objects with metadata for each timeseries volume.

    This groups the various pieces into one object that's easy to
    interface with.

    """
    def __init__(self, hostname='localhost', username='', password='',
                 port=2124, base_dir='.', private_key=None, public_key=None,
                 use_series_finder=True):
        """Initialize the interface object.

        The positional and keyword arguments are passed through
        to the underlying scanner client objects.

        """
        # Keep two different FTP clients for the series and
        # volume queues so they don't interfere with each other

        #Track if we've started to avoid joining unstarted threads
        self.alive = False
        self.use_series_finder = use_series_finder
        self.mutex = Lock()

        try:
            client1 = ScannerClient(hostname=hostname, username=username,
                                 password=password, port=port,
                                 base_dir=base_dir, private_key=private_key,
                                 public_key=public_key, lock = self.mutex)

            client2 = ScannerClient(hostname=hostname, username=username,
                                 password=password, port=port,
                                 base_dir=base_dir, private_key=private_key,
                                 public_key=public_key, lock = self.mutex)
            try:
                client1.latest_exam
                self.has_sftp_connection = True
                print("SFTP connection established successfully.")
            except Exception:
                self.has_sftp_connection = False
                raise(socket.error,"SFTP failed to check dir...")

        except Exception as e:
            print(e)
            raise(socket.error, "Login failed")

        # Initialize the queue objects
        series_q = Queue()
        dicom_q = Queue()
        volume_q = Queue()

        # Initialize the queue manager threads
        if self.use_series_finder:
            self.series_finder = SeriesFinder(client1, series_q, interval=1)

        self.dicom_finder = DicomFinder(client2, series_q, dicom_q, interval=0.05)
        self.volumizer = Volumizer(dicom_q, volume_q, interval=0.05)

    def use_newest_exam_series(self, predict=False):

        client = self.dicom_finder.client
        latest_patient = client._latest_entry(client.base_dir, sort='mtime')
        latest_exam = client._latest_entry(latest_patient)
        newest_series = client._latest_entry(latest_exam)
        if predict:
            #add one to the current series number and use that
            path, file = os.path.split(newest_series)
            series_name = 's' + str(int(file[1:]) + 1) #
            newest_series = os.path.join(path, series_name)

        return self.use_series(newest_series)



    def use_series(self, series):
        with self.dicom_finder.series_q.mutex:
            self.dicom_finder.series_q.queue.clear()
        self.dicom_finder.series_q.put(series)
        print("Using series %s for the session only." % series)
        return series

    def set_dicom_filter(self, dcmf):
        self.dicom_finder.set_dicom_filter(dcmf)
        self.volumizer.set_dicom_filter(dcmf)

    def start(self):
        """Start the constituent threads."""
        self.alive = True
        if self.use_series_finder:
            self.series_finder.start()
        self.dicom_finder.start()
        self.volumizer.start()
        print("Interface initialized")

    def get_volume(self, *args, **kwargs):
        """Semantic wrapper for pulling a volume off the volume queue."""
        return self.volumizer.volume_q.get(*args, **kwargs)

    def shutdown(self):
        """Halt and join the threads so we can exit cleanly."""
        if self.alive:
            self.volumizer.halt()
            if self.use_series_finder:
                self.series_finder.halt()
            self.dicom_finder.halt()

            self.volumizer.join()
            if self.use_series_finder:
                self.series_finder.join()
            self.dicom_finder.join()

            self.alive = False

    def __del__(self):

        self.shutdown()


def setup_exit_handler(scanner, analyzer):
    """Method that will let us ctrl-c the object and kill threads."""
    def exit(signum, stack):
        scanner.shutdown()
        analyzer.halt()
        analyzer.join()
        sys.exit(0)

    signal.signal(signal.SIGINT, exit)
    signal.signal(signal.SIGTERM, exit)
