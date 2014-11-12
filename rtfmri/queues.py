"""Contains classes to organize information we're getting from the scanner.

"""
from __future__ import print_function
from threading import Thread
from time import sleep


class Finder(Thread):
    """An object that is both a Thread and a Queue, sort of.

    You can't just multiple inherit from both Thread and Queue
    because both objects have a ``join`` method. Instead, use
    inheritance to extend ``threading.Thread`` and then add some
    methods that turn around and update an internally-tracked
    ``Queue.Queue`` object.

    """
    def __init__(self, interval):
        """Initialize the Finder."""
        super(Finder, self).__init__()

        self.interval = interval
        self.alive = True

    def halt(self):
        """Make it so the thread will halt within a run method."""
        self.alive = False


class SeriesFinder(Finder):
    """Manage a queue of series directories on the scanner.

    The queue will only be populated with series that look like they
    are timeseries, because that is what is useful for real-time analysis.

    """
    def __init__(self, scanner, queue, interval=1):
        """Initialize the queue."""
        super(SeriesFinder, self).__init__(interval)

        self.scanner = scanner
        self.current_series = None

        self.queue = queue
        self.alive = True

    def halt(self):
        """Make it so the thread will halt within a run method."""
        self.alive = False

    def run(self):
        """This function gets looped over repetedly while thread is alive."""
        while self.alive:

            if self.current_series is None:
                # Load up all series for the current exam
                for series in self.scanner.series_dirs():
                    self.queue.put(series)
                self.current_series = series
            else:
                # Only do anything if there's a new series
                latest_series = self.scanner.latest_series
                if self.current_series != latest_series:

                    # Update what we think the current series is
                    self.current_series = latest_series

                    # Get a dictionary of information about it
                    # Be explicit to avoid possible race condition
                    latest_info = self.scanner.series_info(latest_series)

                    # We are only interested in timeseries data
                    if latest_info["NumTimepoints"] < 6:
                        continue

                    # If we get to here, we want this series in the queue
                    self.queue.put(latest_series)

            sleep(self.interval)


class DicomFinder(Finder):
    """Manage a queue of DICOM files on the scanner.

    This class talks to the scanner and to a separately-managed series queue.

    """
    def __init__(self, scanner, series_q, dicom_q, interval=1):
        """Initialize the queue."""
        super(DicomFinder, self).__init__(interval)

        # Referneces to the external objects we need to talk to
        self.scanner = scanner
        self.series_q = series_q
        self.dicom_q = dicom_q

        # We'll want to keep track of the current series
        self.current_series = None

        # A set to keep track of files we've added onto the queue
        # (This is needed because we'll likely be running over the same
        # series directory multiple times, so we need to know what's in
        # the queue). We use a set because the relevant operations are
        # quite a bit faster than they would be with lists.
        self.dicom_files = set()

    def run(self):
        """This function gets looped over repetedly while thread is alive."""
        while self.alive:

            if self.current_series is not None:

                # Find all the dicom files in this series
                series_files = self.scanner.series_files(self.current_series)

                # Compare against the set of files we've already placed
                # in the queue, keep only the new ones
                new_files = [f for f in series_files
                             if f not in self.dicom_files]

                # Place each new file onto the queue
                for fname in new_files:
                    self.dicom_q.put(fname)

                # Update the set of files on the queue
                self.dicom_files.update(set(new_files))

            if not self.series_q.empty():

                # Grab the next series path off the queue
                self.current_series = self.series_q.get()

                # Reset the set of dicom files. Once we've moved on to
                # the next series, we don't need to track these any more
                # and this keeps it from growing too large
                self.dicom_files = set()
                

            sleep(self.interval)
