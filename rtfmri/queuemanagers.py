"""Thread-based objects that manage data as it arrives from the scanner."""
from __future__ import print_function, division

import time
import os
import pdb
from threading import Thread, Event, Lock
from Queue import Empty
import logging

import numpy as np
from dcmstack import DicomStack
from dcmstack.extract import default_extractor


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.setLevel(logging.WARNING)
logging.basicConfig(format='%(asctime)s %(message)s')

def time_it(tic, message, level='debug'):
    """Logging conveninece Function. Message should describe the timed event."""
    toc = time.time()
    elapsed = toc-tic

    if level=='info':
        logger.info(message + ": {}(s)".format(elapsed))
    if level=='debug':
        logger.debug(message + ": {}(s)".format(elapsed))
    return elapsed


class Finder(Thread):
    """Base class that uses a slightly different approach to thread control."""

    def __init__(self, interval):
        """Initialize the Finder."""
        super(Finder, self).__init__()
        self.interval = interval
        # daemon: these threads shouldn't continue to run if main live
        self.daemon = True
        self.stop_event = Event()

    def halt(self):
        """Make it so the thread will halt within a run method."""
        self.stop_event.set()

    @property
    def is_alive(self):
        return not self.stop_event.is_set()

    def set_dicom_filter(self, dfilter):
        """A dicom filter will allow us to not fetch dicoms that
        we do not need if we intend to use only ROI information."""
        self.dicom_filter = dfilter


class SeriesFinder(Finder):
    """Manage a queue of series directories on the scanner.

    The queue will only be populated with series that look like they
    are timeseries, because that is what is useful for real-time analysis.

    """

    def __init__(self, client, queue, interval=1):
        """Initialize the queue."""
        super(SeriesFinder, self).__init__(interval)

        self.client = client  # ScannerClient instance
        self.current_series = None
        self.queue = queue
        self.nqueued = 0

    def run(self):
        """This function gets looped over repeatedly while thread is alive."""

        while self.is_alive:
            tic = time.time()

            if self.current_series is None:
                """We shouldn't really ever need to end up here unless
                   we need to preserve information across scans, but doing
                """
                logger.debug("Series Finder: Starting series collection")

                # Load up all series for the current exam
                time_it(tic, "Series Finder: Grabbed a series")
                for series in self.client.series_dirs():
                    #add a live check in case there are many series
                    if not self.is_alive:
                        break
                    # print(series)
                    logger.debug("Checking series {}".format(series))
                    #
                    """We are only interested in timeseries data.
                       However, if we are time sensitive, doing the
                       num timepoints check is very slow and adds lag,
                       in which case we should set the current series."""
                    tic = time.time()
                    latest_info = self.client.series_info(series)
                    time_it(tic, "Got series info")
                    if latest_info["NumTimepoints"] > 6:
                        logger.debug(("Series appears to be 4D; "
                                      "adding to series queue"))
                        self.queue.put(series, timeout=self.interval)
                        self.nqueued += 1

                self.current_series = series
            else:
                # Only do anything if there's a new series
                latest_series = self.client.latest_series

                if self.current_series != latest_series:
                    time_it(tic, "Grabbed a NEW series")
                    logger.debug("Found new series: {}".format(series))

                    # Update what we think the current series is
                    self.current_series = latest_series

                    # Get a dictionary of information about it
                    # Be explicit to avoid possible race condition
                    latest_info = self.client.series_info(latest_series)

                    # We are only interested in timeseries data
                    if latest_info["NumTimepoints"] > 1:
                        logger.debug(("Series appears to be 4D; "
                                      "adding to series queue"))
                        self.queue.put(latest_series, timeout=self.interval)
                        self.nqueued += 1

            time.sleep(self.interval)


class DicomFinder(Finder):
    """Manage a queue of DICOM files on the scanner.

    This class talks to the scanner and to a separately-managed series queue.

    Note
    ----

    The queue order will reflect the timestamps and filenames of the dicom
    files on the scanner. This is *not* guaranteed to order the files in the
    actual order of acquisition. Downstream components of the processing
    pipeline should inspect the files for metadata that can be used to
    put them in the right order.

    """

    def __init__(self, client, series_q, dicom_q, interval=0.05):
        """Initialize the queue."""
        super(DicomFinder, self).__init__(interval)

        # Referneces to the external objects we need to talk to
        self.client = client
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

        # keep track of dicoms queued for timing evaluation.
        self.nqueued = 0
        self.dicom_filter = None

    #@profile
    def run(self):
        """This function gets looped over repeatedly while thread is alive."""
        # Keep track of when we last grabbed a dicom so that if dicoms stop
        # appearing we can kill the thread.
        self.last_dicom_time = time.time()
        while self.is_alive:

            tic = time.time()
            if self.current_series is not None:
                # Find all the dicom files in this series
                series_files = self.client.series_files(self.current_series)
                time_it(tic, "DicomSeries: Grabbed the series dicoms ")
                tic = time.time()
                # Compare against the set of files we've already placed
                # in the queue, keep only the new ones
                new_files = [f for f in series_files
                             if f not in self.dicom_files]

                if not new_files:
                    if time.time() - self.last_dicom_time > 5:
                        print("No dicoms left, halting...")
                        self.halt()

                # If we only want get certain slices, then assuming
                # we have a legal list we need to check
                if self.dicom_filter is not None and self.dicom_filter.fitted:
                    new_files = self.dicom_filter.filter(new_files)

                if new_files:
                    logger.debug(("Putting {:d} files into dicom queue"
                                  .format(len(new_files))))

                # Place each new file onto the queue
                filtered_files = set(new_files)

                for fname in new_files:
                    # do not fetch unwanted files if using a dicom filter.
                    if fname not in filtered_files:
                        continue

                    if not self.is_alive:
                        break


                    dcm = self.client.retrieve_dicom(fname)
                    self.last_dicom_time = time.time()

                    if self.dicom_filter is not None and not self.dicom_filter.fitted:
                        # then we're collecting first volume to setup filter
                        logger.debug("Updating dicom filter...")
                        volume_number = int(dcm[(0x0020, 0x0100)].value)
                        with self.dicom_filter.lock:
                            self.dicom_filter.update(fname, dcm)

                        if self.dicom_filter.fitted:
                            logger.info("Dicom filter ready.")
                            filtered_files = self.dicom_filter.filter(
                                new_files)
                            # print(filtered_files)

                    self.dicom_q.put(dcm, timeout=self.interval)
                    self.nqueued += 1
                    time_it(tic, "Dicom series: Retrieved a dicom ")
                    tic = time.time()

                # Update the set of files on the queue
                self.dicom_files.update(set(new_files))

            if not self.series_q.empty():
                # Grab the next series path off the queue
                self.current_series = self.series_q.get()

                logger.debug(("Beginning DICOM collection for new series: {}"
                              .format(self.current_series)))

                # Reset the set of dicom files. Once we've moved on to
                # the next series, we don't need to track these any more
                # and this keeps it from growing too large
                self.dicom_files = set()

            time.sleep(self.interval)


class Volumizer(Finder):
    """Reconstruct MRI volumes and manage a queue of them.

    This class talks to the Dicom queue, but does not need to talk to
    the scanner.

    """

    def __init__(self, dicom_q, volume_q, interval=0.01, keep_vols=True):
        """Initialize the queue."""
        super(Volumizer, self).__init__(interval)

        # The external queue objects we are talking to
        self.dicom_q = dicom_q
        self.volume_q = volume_q
        self.nqueued = 0
        self.n_gotten = 0

        #whether to store all volumes assembled in the volumizer.
        self.keep_vols = keep_vols
        self.assembled_volumes = []
        self.last_assembled_time = time.time()

        self.dicom_filter = None

    def dicom_esa(self, dcm):
        """Extract the exam, series, and acquisition metadata.

        These three values will uniquely identify the scanner run.

        """
        exam = int(dcm.StudyID)
        series = int(dcm.SeriesNumber)
        acquisition = int(dcm.AcquisitionNumber)

        return exam, series, acquisition

    def _get_meta(self, dcm, meta):
        """
        Given the slices dicoms meta data, get the rest of meta data
        from the dicoms for the parameters that differ across slices.
        This should signifantly speed up call times to add_dcm
        (This, plus some tweaks to nicom code found in patch,
        takes assembly time down from ~3.5s to 0.2s for 46 slices.)

        I do not know if this is comprehensive in general, but they are
        the only features that change in the data I have so far tested.
        """
        meta = dict(meta)

        meta['SOPInstanceUID'] = dcm[(0x0008, 0x0018)].value
        meta['AcquisitionTime'] = dcm[(0x0008, 0x0032)].value
        meta['ContentTime'] = dcm[(0x0008, 0x0033)].value
        meta['InstanceNumber'] = dcm[(0x0020, 0x0013)].value
        meta['ImagePositionPatient'] = dcm[(0x0020, 0x0032)].value
        meta['SliceLocation'] = dcm[(0x0020, 0x1041)].value
        meta['InStackPositionNumber'] = dcm[(0x0020, 0x9057)].value
        meta['LargestImagePixelValue'] = dcm[(0x0028, 0x0107)].value
        meta['WindowCenter'] = dcm[(0x0028, 0x1050)].value
        meta['WindowWidth'] = dcm[(0x0028, 0x1051)].value
        meta['TriggerTime'] = dcm[(0x0018, 0x1060)].value

        # Potentially useful for future debugging...:
        #echo = dcm[(0x0018, 0x0086)].value
        #tpid = dcm[(0x0020, 0x0100)].value
        #print(meta['InstanceNumber'],tpid, meta['InStackPositionNumber'],
        #      meta['TriggerTime'], meta['SliceLocation'],
        #      meta['ContentTime'], meta['SOPInstanceUID'])

        try:
            #This is sometimes missing.
            meta['GroupLength_0X18_0X0'] = dcm[(0x0018, 0x0000)].value
        except KeyError:
            pass

        return meta

    #@profile
    def assemble_volume(self, slices):
        """Put each dicom slice together into a nibabel nifti image object."""
        # Build a DicomStack from each of the slices
        tic = time.time()

        meta = default_extractor(slices[0])

        stack = DicomStack()
        for f in slices:
            # without new_meta, this takes 99% of time in this function by
            # wasting cycles on looking up redundant data.
            new_meta = self._get_meta(f, meta)
            stack.add_dcm(f, new_meta)

        # Convert into a Nibabel Nifti object
        nii_img = stack.to_nifti(voxel_order="")

        # Build the volume dictionary we will put in the dicom queue
        dcm = slices[0]
        exam, series, acquisition = self.dicom_esa(dcm)
        volume = dict(
            exam=exam,
            series=series,
            acquisition=acquisition,
            patient_id=dcm.PatientID,
            series_description=dcm.SeriesDescription,
            tr=float(dcm.RepetitionTime) / 1000,
            ntp=float(dcm.NumberOfTemporalPositions),
            image=nii_img,
        )
        time_it(tic, "Assembled a volume", level='info')

        if self.keep_vols:
            self.assembled_volumes.append(volume)
        self.last_assembled_time = time.time()
        return volume

    def missing_slices(self, need, have):
        return set(list(need)) - set(list(have))

    # @profile
    def run(self):
        """This function gets looped over repetedly while thread is alive."""
        # Initialize the list we'll using to track progress
        instance_numbers_needed = []  # None
        instance_numbers_gathered = []
        current_esa = None
        current_slices = []

        last_assembled = time.time()
        trigger_times_acquired = []

        #whether or not we've updated instance_numbers_needed with dicom filter
        self.filtered = False

        while self.is_alive:
            tic = time.time()

            try:
                dcm = self.dicom_q.get(timeout=self.interval)
                time_it(tic, "grabbed a dicom in volumizer:")
                self.n_gotten += 1
            except Empty:
                print
                # condition where dicom queue is empty but we
                # can assemble the next slice

                slices_missing = self.missing_slices(instance_numbers_needed,
                                                     instance_numbers_gathered)
                if time.time() - self.last_assembled_time > 20:
                    print("More than 10 seconds since last volume, halting...")
                    self.halt()
                if len(instance_numbers_needed) and not slices_missing:
                    pass
                else:
                    time.sleep(self.interval)
                    continue

            try:
                # This is the dicom tag for "Number of locations"
                slices_per_volume = int(dcm[(0x0021, 0x104f)].value)
            except KeyError:
                # TODO In theory, we shouldn't get to here, because the
                # series queue should only have timeseries images in it.
                # Need to figure out under what circumstances we'd get a
                # file that doesn't have a "number of locations" tag,
                # and what we should do with it when we do.
                # The next line is just taken from the original code.
                slices_per_volume = int(getattr(dcm, "ImagesInAcquisition"))


            # Determine if this is a slice from a new acquisition
            this_esa = self.dicom_esa(dcm)
            if current_esa is None or this_esa != current_esa:
                # Begin tracking the slices we need for the first volume
                # from this acquisition
                instance_numbers_needed = np.arange(slices_per_volume) + 1
                current_esa = this_esa
                logger.debug(("Collecting slices for new scanner run - "
                              "\n(exam: {}\n series: {}\n acquisition: {})"
                              .format(*current_esa)))

            # Get the DICOM instance for this volume
            # This is an incremental index that reflects position in time
            # and space (i.e. the index is the same for interleaved or
            # not sequential acquisitisions) so we can trust it to put
            # the volumes in the correct order.
            current_slice = int(dcm.InstanceNumber)

            # Add this slice index and dicom object to current list

            instance_numbers_gathered.append(current_slice)

            current_slices.append(dcm)

            if self.dicom_filter is not None and not self.filtered:
                """If we are using a filter, we will only need to gather
                instance numbers if their slice number is allowed by the filter"""
                if self.dicom_filter.fitted:
                    instance_numbers_needed = [
                        x for x in instance_numbers_needed
                        if x % slices_per_volume in self.dicom_filter.legal_indices
                    ]
                    instance_numbers_needed = np.array(instance_numbers_needed)
                    self.filtered = True

            #If you really need to debug the dicom_filter...
            # print("Missing:",self.missing_slices(instance_numbers_needed,instance_numbers_gathered))
            # print(("Have: {}".format(instance_numbers_gathered)))

            if set(instance_numbers_needed) <= set(instance_numbers_gathered):
                # Files are not guaranteed to enter the DICOM queue in any
                # particular order. If we get here, then we have picked up
                # all the slices we need for this volume, but they might be
                # out of order, and we might have other slices that belong to
                # the next volume. So we need to figure out the correct order
                # and then extract what we need, leaving the rest to be dealt
                # with later.

                volume_slices = []

                for slice_number in instance_numbers_needed:
                    # print(sorted_indices)
                    slice_index = instance_numbers_gathered.index(slice_number)
                    #print(slice_index, slice_number)
                    volume_slices.append(current_slices.pop(slice_index))
                    instance_numbers_gathered.pop(slice_index)

                # Assemble all the slices together into a nibabel object
                logger.debug(("Assembling full volume for slices {:d}-{:d}"
                              .format(min(instance_numbers_needed),
                                      max(instance_numbers_needed))))
                tic = time.time()
                volume = self.assemble_volume(volume_slices)
                time.sleep(1)

                # Put that object on the dicom queue
                self.volume_q.put(volume, timeout=self.interval)
                self.nqueued += 1
                time_it(last_assembled, "Volumizer: Assemble and queue volume")
                last_assembled = time.time()

                # Update the array of slices we need for the next volume
                instance_numbers_needed += slices_per_volume
