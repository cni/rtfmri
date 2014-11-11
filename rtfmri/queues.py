"""Contains classes to organize information we're getting from the scanner.

"""
from __future__ import print_function
import os.path as op
from Queue import Queue, Empty
from threading import Thread
from datetime import datetime
from time import sleep


class ThreadedQueue(Thread):
    """An object that is both a Thread and a Queue, sort of.

    You can't just multiple inherit from both Thread and Queue
    because both objects have a ``join`` method. Instead, use
    inheritance to extend ``threading.Thread`` and then add some
    methods that turn around and update an internally-tracked
    ``Queue.Queue`` object.

    """
    def __init__(self):
        """Initialize the queue."""
        super(ThreadedQueue, self).__init__()
        self.alive = True
        self._queue = Queue()

    def halt(self):
        """Make it so the thread will halt within a run method."""
        self.alive = False

    def put(self, *args, **kwargs):
        """Put an object into the internal queue."""
        return self._queue.put(*args, **kwargs)

    def get(self, *args, **kwargs):
        """Get an object into the internal queue."""
        return self._queue.get(*args, **kwargs)


class SeriesQueue(ThreadedQueue):
    """Expose a queue of series directories on the scanner.

    This queue will only be populated with series that look like they
    are timeseries, because that is what is useful for real-time analysis.

    """
    def __init__(self, scanner, interval=1):
        """Initialize the queue."""
        super(SeriesQueue, self).__init__()

        self.scanner = scanner
        self.current_series = None
        self.interval = interval

    def run(self):

        while self.alive:

            if self.current_series is None:
                # Load up all series for the current exam
                for series in self.scanner.series_dirs():
                    self.put(series)
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
                    self.put(latest_series)
            
            sleep(self.interval)


class DicomQueue(ThreadedQueue):
    """Expose a queue of DICOM files on the scanner."""
    def __init__(self, scanner, series_q, interval=1):
        """Initialize the queue."""
        super(DicomQueue, self).__init__()
        self.interval = interval

    def run(self):

        while self.alive:
            sleep(self.interval)
