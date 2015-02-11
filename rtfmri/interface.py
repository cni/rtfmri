"""High-level interface to manage moving parts of realtime code."""
import sys
import signal
from Queue import Queue
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
    def __init__(self, *args, **kwargs):
        """Initialize the interface object.

        The positional and keyword arguments are passed through
        to the underlying scanner client objects.

        """
        # Keep two different FTP clients for the series and
        # volume queues so they don't interfere with each other
        client1 = ScannerClient(*args, **kwargs)
        client2 = ScannerClient(*args, **kwargs)

        # Set an attribute so we know if we could connect
        self.has_ftp_connection = client1.ftp is not None

        # Initialize the queue objects
        series_q = Queue()
        dicom_q = Queue()
        volume_q = Queue()

        # Initialize the queue manager threads
        self.series_finder = SeriesFinder(client1, series_q)
        self.dicom_finder = DicomFinder(client2, series_q, dicom_q)
        self.volumizer = Volumizer(dicom_q, volume_q)

    def start(self):
        """Start the constituent threads."""
        self.series_finder.start()
        self.dicom_finder.start()
        self.volumizer.start()

    def get_volume(self, *args, **kwargs):
        """Semantic wrapper for pulling a volume off the volume queue."""
        return self.volumizer.volume_q.get(*args, **kwargs)

    def shutdown(self):
        """Halt and join the threads so we can exit cleanly."""
        self.series_finder.halt()
        self.dicom_finder.halt()
        self.volumizer.halt()

        self.series_finder.join()
        self.dicom_finder.join()
        self.volumizer.join()

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
