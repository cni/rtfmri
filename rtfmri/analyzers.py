"""Thread-based objects that analyze data as it arrives in the queues."""
from __future__ import print_function, division
from threading import Thread
from Queue import Empty
from time import sleep

import numpy as np
import nibabel as nib

from nipy.algorithms.registration import Image4d, single_run_realign4d

from .queuemanagers import Finder


class MotionAnalyzer(Finder):
    """Compute real-time motion statistics for quality control."""

    # Ultimately we'll want to make this more extensible.
    # Because of how the queues work, you won't be able to run multiple
    # analyzers at the same time. So if you wanted to, say, run some
    # real-time GLM analysis and have real-time motion QA, you can't
    # just have those as two separate objects.
    # But it should work to be able to do that in an object-oriented
    # hierarchy sense, where you always get motion QA (and maybe other
    # stuff, like spike detection) and can optionally do more complicated
    # or domain-specific stuff on top of that.
    # For the time-being I'm not putting a ton of thought into that design
    # though, just because I'm not really sure exactly how you would want
    # it to look like.
    def __init__(self, volume_q, skip_vols=4):
        """Initialize the queue."""
        self.volume_q = volume_q
        self.skip_vols = skip_vols

        # The reference volume (first of each acquisition)
        self.ref_vol = None

        # The previous volume (for scan-to-scan motion)
        self.pre_vol = None

    def compute_registration(self, fixed, moving):
        """Estimate a linear, within-modality transform from moving to fixed.

        Parameters
        ----------
        fixed : nibabel image object
            Reference image.
        moving : nibabel image object
            Image to be registered to the reference image.

        Returns
        -------
        T : nipy Rigid object
            Rigid matrix giving transform from moving to fixed.

        """
        fixed_data = fixed.get_data()
        moving_data = moving.get_data()
        assert fixed_data.shape == moving_data.shape

        # Add a forth dimension and concatenate into one "timeseries"
        data = np.concatenate([fixed_data[..., np.newaxis],
                               moving_data[..., np.newaxis]], axis=3)

        # Create a nipy Image4d object
        # (apparently the nipy registration stuff needs this, although
        # it's been suggested that Image4d is thought of as an "internal"
        # object on the mailing list).
        img = Image4d(data, fixed.get_affine(), tr=1, slice_times=0)

        # Estimate the registration from moving to fixed
        # Currently this is using nipy's 4d realignment, which also
        # can do simultaneous slice-time correction (although that is
        # turned off here. It's not clear to me what the best way to
        # get a fast, reasonable image-to-image registration in nipy is,
        # but this is probably not it. Unfortunately, nipy's complex
        # organization and general lack of documentation makes this
        # difficult.
        _, T = single_run_realign4d(img, time_interp=False, loops=1)
        return T

    def compute_rms(self, T):
        """Compute root mean squared displacement of a transform matrix.

        Parameters
        ----------
        T : nipy Rigid object
            Transformation matrix.
        rms : scalar
            Root-mean-squared displacement corresponding to the transformation.

        Notes
        -----
        This is implemented as it is in FSL's mcflirt algorithm.
        See this technical report by Mark Jenkinson for the derivation:
        http://www.fmrib.ox.ac.uk/analysis/techrep/tr99mj1/tr99mj1/node3.html

        """
        T = T.as_affine() - np.eye(4)

        # Decompose the transformation
        A = T[:3, :3]
        t = T[:3, 3]

        # This is radius for our idealized head, which is a sphere
        R = 80

        # Compute the RMS displacemant
        rms = np.sqrt(R ** 2 / 5 * A.T.dot(A).trace() + t.T.dot(t))

        return rms

    def run(self):
        """This function gets looped over repetedly while thread is alive."""
        while self.alive:
            pass
            # Check if we need to update the reference image

            # Compute the transformation to the reference image

            # Compute the transformation to the previous image

            # Update the previous image with the current image

            # Compute the summary information for both transformations

            # Push the summary information to the frontend application
