"""Classes to handle ROI masks and dicom selection based on them"""
from __future__ import print_function
import time
import os, pdb
from threading import Lock
from collections import OrderedDict

import nibabel
import numpy as np
from numpy import mean as npm
from nilearn.input_data import NiftiMasker
from scipy.ndimage import measurements, interpolation

from utilities import alphanum_key


class Masker(object):
    """
    Class that takes a binary mask.nii file and allows us to use it
    within a volumizer in order to reduce the dimensionality of our data in
    realtime.

    If we have other ROI masks (e.g. wm, csf), we can use them detrend the data
    by setting them as orthogonals.
    """

    def __init__(self, mask_img, center=None, radius=8):
        self.mask_img = mask_img
        self.masker = NiftiMasker(mask_img=mask_img)
        self.fit = False
        # set the mask center
        if center is None:
            self.center = self.find_center_of_mass(self.masker)

        else:
            self.center = center
        print("Center=", center)
        print("COM calc=", self.find_center_of_mass(self.masker))

        # the radius of the mask, used for determining what data to read.
        self.radius = radius
        self.orthogonals = []
        self.use_orthogonal = False
        self.ortho_fits = []

    def reduce_volume(self, volume, method='mean'):
        if not self.fit:
            self.masker.fit(volume)
        if method == 'mean':
            reduced = npm(self.masker.transform(volume['image']))
        return reduced

    def find_center_of_mass(self, niftimasker):
        """
        Find the center of mass of an image given a nifti masker object
        in the z plane. We can use this information to only select dicoms
        we need in a DicomFilter object.
        """

        com = measurements.center_of_mass(
            nibabel.load(niftimasker.mask_img).get_data())
        affine = nibabel.load(niftimasker.mask_img).affine
        offset = affine[0:3, 3]
        tcom = np.dot(affine[0:3, 0:3], com) + offset
        return tcom[2]

    def add_orthogonal(self, mask_img):
        # add another mask_img to our orthogonals with get_orthogonal
        self.use_orthogonal = True
        self.orthogonals.append(NiftiMasker(mask_img=mask_img))
        self.ortho_fits.append(False)

    def get_orthogonals(self, volume):
        """
        Return a list of ROI averages for a volume given a set of
        orthogonal masks
        """
        for i, fit in enumerate(self.ortho_fits):
            if not fit:
                self.orthogonals[i].fit(volume)

        return [npm(x.transform(volume['image'])) for x in self.orthogonals]


class DicomFilter(object):
    """
    An object for determining if we should grab a dicom or not by
    determining which slices overlap with our ROI mask.

    Currently implementation relies on filenames for speed, since if we have
    time to check volume locations for each dicom, we don't need to use the
    filter in the first place because we would already have copied the dcm.
    """

    def __init__(self, masker):

        self.lock = Lock()
        self.first_dicom = None
        self.reduced_first_name = 0
        self.slices_per_volume = None
        self.fitted = False
        self.have = set()
        self.need = set()

        self.masker = masker
        self.mask_center = masker.center
        self.radius = masker.radius
        self.legal_indices = None

        # information that could be useful in case we need to determine
        # slice order, though we don't rely on this
        self.trigger_times = []
        self.instance_numbers = []
        self.locations = []

    def update(self, name, dcm):
        """Given a dicom with filname name, get its attributes to determine
           slice location and timing information"""

        # Don't allow updates if we have already updated on a whole volume.
        if self.fitted:
            raise(ValueError, "Trying to update a fitted dicom_filter.")

        info = {
            'name' : name,
            'trigger_time': dcm[(0x0018, 0x1060)].value,
            'slices_per_volume' : dcm[(0x0021, 0x104f)].value,
            'instance_number': dcm[(0x0020, 0x0013)].value,
            'location' : dcm[(0x0020, 0x1041)].value
        }

        spv = info['slices_per_volume']
        if not self.slices_per_volume:
            self.slices_per_volume = spv
            self.need = set(range(1, self.slices_per_volume))
        else:
            if self.slices_per_volume != spv:
                raise ValueError(
                    "Slices per volume differs from previous dicoms."
                )

        inum = info['instance_number']
        self.have.add(inum)
        if inum == 1:
            print(info)
            self.first_dicom = os.path.split(info['name'])[-1]
            self.reduced_first_name = self.reduce_name(self.first_dicom)
        self.instance_numbers.append(inum)
        self.trigger_times.append(info['trigger_time'])
        self.locations.append(info['location'])

        if self.need <= self.have:
            """
            If we have a full volume, we can now determine which volumes
            contain information near our ROI
            """
            # first sort everything by instance number:
            pairs = zip(self.instance_numbers, self.locations)

            legal_indices = [x[0] for x in
                             sorted(pairs, key=lambda tup: tup[1])
                             if abs(x[1] - self.mask_center) < self.radius + 4
                             ]
            print("DETERMINED INDICES: \n\n\n\n\n")
            print(legal_indices)
            self.legal_indices = set(legal_indices)
            self.fitted = True

    def reduce_name(self, fname):
        """
        Converts a name in to an int from the filenumber looking at the
        last two integer components of the name. (More than that is overkill.)
        """
        parts = alphanum_key(fname, only_digits=True)

        # reduced first name begins as zero, so we can use this to set it
        # this works on .dcm files sorted by name, but not on teh scanner
        reduced = (parts[-2] * 1000 + parts[-1]) - self.reduced_first_name

        # instead, on the scanner we use the raw instance number:
        #reduced = parts[-1]

        return int(reduced)


    def filter(self, paths, timing_vec=None):
        """
        Given a list of paths to names, return only the legal ones that contain
        slices that we want.
        If timing vec is passed, we skip volumes that don't have a zero in them.

        Example: Filenames are 1000, 1001, 1002, 1003, 1004...
        There are 40 slices per volume.
        The legal_indices tell us that our ROI should be in slices 1010..1015:
        Then we should return 1010...1015, 10050..10055, etc.
        """
        if not self.fitted:
            raise(ValueError, "Cannot filter without a legal list.")

        # first take just the filenames. say we start with 1040...1079
        rn = [os.path.split(x)[-1] for x in paths]

        #pdb.set_trace()
        # reduce to (0,40) ..(39,79) for sorting
        rn = [(x[0], self.reduce_name(x[1])) for x in enumerate(rn)]

        # reduce (0index dicom num, 1 index slice num, 0 index TR num)
        rn = [(x[0], 1 + ((x[1]) % self.slices_per_volume), (x[1])//self.slices_per_volume) for x in rn]

        # now remove all illegal ones
        rn = [x for x in rn if x[1] in self.legal_indices]

        #now check agains the timing vec if present
        if timing_vec is not None:
            skip_trs = [x[0] for x in enumerate(timing_vec) if x[1] == 0 and x[0] > 10]
            rn = [ x for x in rn if x[2]  not in skip_trs]

        filtered = [paths[x[0]] for x in rn]

        ordered_set = OrderedDict()
        for x in filtered:
            ordered_set[x] = True
        return list(ordered_set)
