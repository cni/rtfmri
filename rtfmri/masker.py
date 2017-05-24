"""Classes to handle volumizers and extract volume information with ROIs"""
from numpy import mean as npm
from nilearn.input_data import NiftiMasker

import pdb
class Masker(object):
    def __init__(self, mask_img):
        self.mask_img = mask_img
        self.masker = NiftiMasker(mask_img=mask_img)
        self.fit = False

    def reduce_volume(self, volume, method='mean'):
        if not self.fit:
            self.masker.fit(volume)
        if method == 'mean':
            reduced = npm(self.masker.transform(volume['image']))
        return reduced
