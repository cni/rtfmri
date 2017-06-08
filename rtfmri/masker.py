"""Classes to handle volumizers and extract volume information with ROIs"""

import time
import os

from collections import OrderedDict
from numpy import mean as npm
from nilearn.input_data import NiftiMasker

from utilities import alphanum_key
import pdb
class Masker(object):
    def __init__(self, mask_img, center = None, radius=8):
        self.mask_img = mask_img
        self.masker = NiftiMasker(mask_img=mask_img)
        self.fit = False

        #set the mask center
        if center is None:
            self.find_center()
        else:
            self.center = center

        # the radius of the mask, used for determining what data to read.
        self.radius = radius

    def reduce_volume(self, volume, method='mean'):
        if not self.fit:
            self.masker.fit(volume)
        if method == 'mean':
            reduced = npm(self.masker.transform(volume['image']))
        return reduced

    def find_center(self):
        pass
        self.center = 16


class DicomFilter(object):
    """
    An object for determining if we should grab a dicom or not by
    determining the filenames corresponding to the slices which contain
    ROI information we care about.
    """
    def __init__(self, masker):

        #self.lock = Lock()
        #require lock

        self.first_dicom = None
        self.reduced_first_name = 0
        self.slices_per_volume = None
        self.ready = False
        self.have = set()
        self.need = set()


        self.masker = masker
        self.mask_center = masker.center
        self.radius = masker.radius
        self.legal_indices = None

        #information that could be useful in case we need to determine
        #slice order, though we don't rely on this
        self.trigger_times    = []
        self.instance_numbers = []
        self.locations = []



    def update(self, info):
        # info should be a dictionary consisting of
        # name, trigger_time, slices_per_volume, instance_number, volume_number

        if self.ready:
            return

        spv = info['slices_per_volume']
        #print(spv)
        if not self.slices_per_volume:
            self.slices_per_volume = spv
            self.need = set(range(1,self.slices_per_volume))
        else:
            if self.slices_per_volume != spv:
                raise ValueError("Slices per volume, cannot filter dicoms.")

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
            legal_indices = [x[0] for x in
                             sorted(enumerate(self.locations))
                             if abs(x[1] - self.mask_center) < self.radius + 4
            ]
            print("DETERMINED INDICES: \n\n\n\n\n")
            print(legal_indices)
            self.legal_indices = set(legal_indices)
            self.ready = True

    def reduce_name(self, fname):
        """
        Converts a name in to an int from the filenumber looking at the
        last two integer components of the name. (More than that is overkill.)
        """
        parts = alphanum_key(fname, only_digits=True)
        #reduced first name begins as zero, so we can use this to set it
        reduced = (parts[-2] * 1000 + parts[-1]) - self.reduced_first_name
        #print(reduced)
        return int(reduced)



    def filter(self, paths):
        """
        Given a list of paths to names, return only the legal ones that contain
        slices that we want.

        Example: Filenames are 1000, 1001, 1002, 1003, 1004...
        There are 40 slices per volume.
        The legal_indices tell us that our ROI should be in slices 1010..1015:
        Then we should return 1010...1015, 10050..10055, etc.
        """
        if not self.ready:
            raise(ValueError,"Cannot filter without a legal list.")

        #first take just the filenames. say we start with 1040...1079
        rn = [os.path.split(x)[-1] for x in paths]

        # reduce to (0,40) ..(39,79) for sorting
        rn = [(x[0], self.reduce_name(x[1])+1)
              for x in enumerate(rn)
        ]
        # reduce to (0, 0)... (39,39) for filtering
        rn = [(x[0], x[1] % self.slices_per_volume) for x in rn ]
        #print(rn)

        #now remove all illegal ones
        rn = [x for x in rn if x[1] in self.legal_indices]

        #now return filtered paths
        filtered = [paths[x[0]] for x in rn]

        ordered_set = OrderedDict()
        for x in filtered:
            ordered_set[x] = True
        return ordered_set
