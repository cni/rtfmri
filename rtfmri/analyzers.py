"""Thread-based objects that analyze data as it arrives in the queues."""
from __future__ import print_function, division
import sys
import time
import logging
import contextlib
from cStringIO import StringIO
from Queue import Empty
from time import sleep

import numpy as np

from nipy.algorithms.registration import HistogramRegistration, Rigid

from .queuemanagers import Finder


logger = logging.getLogger(__name__)


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
    def __init__(self, scanner, result_q, skip_vols=4, interval=1):
        """Initialize the queue."""
        super(MotionAnalyzer, self).__init__(interval)
        self.scanner = scanner
        self.result_q = result_q
        self.skip_vols = skip_vols

        # The reference volume (first of each acquisition)
        self.ref_vol = None

        # The previous registration matrix
        # (used for computing the relative deviation)
        self.pre_T = None

    def compute_registration(self, moving, fixed, init=None, interp="tri"):
        """Estimate a linear, within-modality transform from moving to fixed.

        Parameters
        ----------
        moving : nibabel image object
            Image to be registered to the reference image.
        fixed : nibabel image object
            Reference image.
        init : transformation object or None
            Initialization for the transformation. If ``None``, the
            registration is seeded with a small rotation, which helps avoid
            getting stuck in the local minimum of no motion.

        Returns
        -------
        T : nipy Rigid object
            Rigid matrix giving transform from moving to fixed.

        """
        if init is None:
            # This applies a small rotation; code from Alexis Roche
            init = Rigid((0, 0, 0, 0.01, 0.01, 0.01, 0, 0, 0, 0, 0, 0))
        reg = HistogramRegistration(moving, fixed, interp=interp)
        with silent():  # Mute stdout due to verbose optimization info
            T = reg.optimize(init)
        return T

    def compute_rms(self, T1, T2, center=None, R=80):
        """Compute root mean squared displacement between two transform matrices.

        Parameters
        ----------
        T1, T2 : nipy Rigid object
            Transformation matrices.
        rms : scalar
            Root-mean-squared displacement corresponding to the transformation.
        center : vector of size 3
            Coordinate for the center of the head.
        R : float
            Radius of the idealized (sphere) head, in mm.

        Notes
        -----
        This is implemented as it is in FSL's mcflirt algorithm.
        See this technical report by Mark Jenkinson for the derivation:
        http://www.fmrib.ox.ac.uk/analysis/techrep/tr99mj1/tr99mj1/node3.html

        """
        isodiff = T1.as_affine().dot(np.linalg.inv(T2.as_affine())) - np.eye(4)

        # Decompose the transformation
        A = isodiff[:3, :3]
        t = isodiff[:3, 3]

        # Center the translation component
        if center is None:
            center = np.zeros(3)
        t += A.dot(center)

        # Compute the RMS displacemant
        rms = np.sqrt(R ** 2 / 5 * A.T.dot(A).trace() + t.T.dot(t))

        return rms

    def volume_center(self, img):
        """Find the coordinates of the center of a nibabel image."""
        center = .5 * (np.array(img.shape[:3]) - 1)
        center *= img.header.get_zooms()[:3]
        return center

    def new_scanner_run(self, vol):
        """Compare vol to ref to see if there has been a new scanner run."""
        if self.ref_vol is None:
            return True

        if not self.ref_vol:
            return False

        for item in ["exam", "series", "acquisition"]:
            if vol[item] != self.ref_vol[item]:
                return True
        return False

    def run(self):
        """This function gets looped over repetedly while thread is alive."""
        vol_number = 0
        while self.alive:
            try:
                vol = self.scanner.get_volume(timeout=1)
            except Empty:
                sleep(self.interval)
                continue

            # Check if we need to reset the volume counter
            if self.new_scanner_run(vol):
                logger.debug(("Received first volume from new scanner run - "
                              "exam: {} series: acquisition: {}"
                              .format(vol["exam"], vol["series"],
                                      vol["acquisition"])))
                self.ref_vol = {}
                vol_number = 0

            # Check if we are outside of the stabilization scans
            if vol_number < self.skip_vols:
                # Still too early in the scan, just increment and bail out
                vol_number += 1
                continue

            # Check if we need to reset the reference image
            elif vol_number == self.skip_vols:
                # Update the reference volume to start here
                self.ref_vol = vol
                logger.debug("Assigning new reference volume")

                # Set the previous affine matrix to identity
                self.pre_T = Rigid(np.eye(4))

                # Put a dictionary of null results in the queue
                result = dict(rot_x=0, rot_y=0, rot_z=0,
                              trans_x=0, trans_y=0, trans_z=0,
                              rms_ref=0, rms_pre=0, vol_number=vol_number,
                              new_acquisition=True)
                vol.update(result)
                self.result_q.put(vol)

                # Increment the volume counter and bail out
                vol_number += 1
                continue

            # Compute the transformation to the reference image
            start = time.time()
            T = self.compute_registration(vol["image"],
                                          self.ref_vol["image"],
                                          init=self.pre_T.copy(),
                                          interp="tri")
            end = time.time()
            logger.debug(("Computed motion for volume {:d} (took {:d} ms)"
                          .format(vol_number, int((end - start) * 1000))))

            # Compute the RMS displacement to the reference volume
            rms_ref = self.compute_rms(Rigid(np.eye(4)), T)

            # Compute the RMS displacement from the previous volume
            rms_pre = self.compute_rms(self.pre_T, T)

            # Get the realignment parameters
            rot_x, rot_y, rot_z = np.rad2deg(T.rotation)
            trans_x, trans_y, trans_z = T.translation

            # Put the summary information into the result queue
            result = dict(rot_x=rot_x, rot_y=rot_y, rot_z=rot_z,
                          trans_x=trans_x, trans_y=trans_y, trans_z=trans_z,
                          rms_ref=rms_ref, rms_pre=rms_pre,
                          vol_number=vol_number, new_acquisition=False)
            vol.update(result)
            self.result_q.put(vol)

            # Update the previous transformation matrix
            self.pre_T = T

            # Update the volume counter
            vol_number += 1


@contextlib.contextmanager
def silent():
    """Context manager to squelch stdout."""
    save_stdout = sys.stdout
    sys.stdout = StringIO()
    yield
    sys.stdout = save_stdout
