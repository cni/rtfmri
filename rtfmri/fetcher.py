"""A class to fetch sessions from a scanner and compile them to niftii files."""
from __future__ import print_function
import warnings
from pprint import pprint as pp

import progressbar
from dcmstack import DicomStack
from dcmstack.extract import default_extractor

from .queuemanagers import Volumizer
from .client import ScannerClient


class SeriesFetcher(object):
    """Given input args, open the newest exam and let the user chose the newest
       series, which will be saved to @outfile"""

    def __init__(self, hostname="cnimr", port=22, username="", password="",
                 base_dir="/export/home1/sdc_image_pool/images", outfile=None):

        self.client = ScannerClient(hostname=hostname, username=username,
                                    password=password, port=port,
                                    base_dir=base_dir)
        self.outfile = outfile
        self.meta = None

        self.tpid = -1
        self.volumizer = Volumizer(None, None)

        self.series = self.choose_series()
        self.build_nifti(self.series, self.outfile)

    def choose_series(self):
        """Allow user to select target series from existing series dirs."""
        self.client.latest_series
        series_dirs = self.client.series_dirs()

        series_info = {}

            # Report the description tag for each existing series in current exam
        print("Existing DICOM image series from current exam:")
        for i, series in enumerate(series_dirs, 1):
            info = self.client.series_info(series)
            series_info[series] = info
            description = info["Description"]
            num_dicoms = info["NumAcquisitions"]
            n_volumes = info["NumTimepoints"]
            if description != "Screen Save":
                print(" {:d}: {} ({:d} dicoms, {:d} volumes)".format(
                    i, description, num_dicoms, n_volumes))

        # Allow the user to select one of these series
        chosen_index = raw_input("Which series number? ")
        chosen_series = series_dirs[int(chosen_index) - 1]
        pp(series_info[chosen_series])
        chosen_description = series_info[chosen_series]["Description"]
        print("Retrieving DICOM data for '{}'".format(chosen_description))
        return chosen_series

    def fast_retrieve_dicom(self, path, meta=None):
        # add_dcm takes a lot of time if we have to reexamine metadata everytime
        # so we copy metadata if we're in the same volume of a time series

        dcm = self.client.retrieve_dicom(path)
        try:
            # get the volume number
            tpid = dcm[(0x0020, 0x0100)].value
        except KeyError:
            # then were not looking at a time series
            return(dcm, None)

        # otherwise
        if tpid != self.tpid:
            # then we're in a new volume
            meta = default_extractor(dcm)
        else:
            # we're in the same volume, so use old meta:
            meta = self.volumizer._get_meta(dcm, meta)

        return(dcm, meta)

    def valid_subseries(self, src_paths):
        """
        warn about less than recommended volumes, use only complete volumes
        we assume src_paths is in alphanum order...
        """

        dcm = self.client.retrieve_dicom(src_paths[0])
        try:
            slices_per_volume = int(dcm[(0x0021, 0x104f)].value)
            print("Time series detected")
        except KeyError:
            slices_per_volume = int(getattr(dcm, "ImagesInAcquisition"))
            print("Scan is not a time series...")

        if slices_per_volume > len(src_paths):
            print("Not enough slices to assemble a full volume.")
            return None

        left = len(src_paths) % slices_per_volume
        n_volumes = len(src_paths) // slices_per_volume
        n_prescribed = int(getattr(dcm, "NumberOfTemporalPositions", 1))

        end = len(src_paths)
        if left != 0:
            warnings.warn(
                "Number of files is not an even multiple of the number of unique slice positions", Warning)
            end -= left

        print(("Using the first {:d} of {:d} prescribed volumes .").format(
               n_volumes, n_prescribed))
        return src_paths[:end]

    def build_nifti(self, series, nii_fname):
        """Pull DICOM data from the scanner and build a Nifti image with it."""
        src_paths = self.client.series_files(series)
        src_paths = self.valid_subseries(src_paths)

        if not src_paths:
            return

        stack = DicomStack()

        # Retrieve the binary dicom data from the SFTP server, display progress
        meta = None
        with progressbar.ProgressBar(max_value=len(src_paths)) as bar:
            for i, path in enumerate(src_paths):
                dcm, meta = self.fast_retrieve_dicom(path, meta)
                stack.add_dcm(dcm, meta)
                bar.update(i)

        # Create a nibabel nifti object
        nii_img = stack.to_nifti()  # voxel_order="")

        if nii_fname is None:
            print("No output name given.")
        while nii_fname is None:
            nii_fname = raw_input("Please enter an outfile name: ")
            if not nii_fname.endswith('.nii') and not nii_fname.endswith('.nii.gz'):
                print("Filename must end with .nii or .nii.gz")
                nii_fname = None

        # Write the nifti to disk
        print("Writing to {}".format(nii_fname))
        nii_img.to_filename(nii_fname)
