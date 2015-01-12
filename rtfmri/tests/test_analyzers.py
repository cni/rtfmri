from __future__ import print_function

import nibabel as nib

import nose.tools as nt
import numpy.testing as npt

from nipy.algorithms.registration import Rigid

from .. import analyzers as anal

import numpy as np


class TestMotionAnalyzer(object):

    def test_rms(self):

        a = anal.MotionAnalyzer(None, None)

        T = np.eye(4)
        nt.assert_equal(a.compute_rms(Rigid(T)), 0)

        T[0, 3] = 1
        nt.assert_equal(a.compute_rms(Rigid(T)), 1)

        T[1, 3] = 1
        nt.assert_equal(a.compute_rms(Rigid(T)), np.sqrt(2))

        T1 = np.eye(4)
        T1[1:3, 1:3] = [(np.cos(.1), -np.sin(.1)),
                        (np.sin(.1), np.cos(.1))]
        rms1 = a.compute_rms(Rigid(T1))

        T2 = np.eye(4)
        T2[1:3, 1:3] = [(np.cos(.2), -np.sin(.2)),
                        (np.sin(.2), np.cos(.2))]
        rms2 = a.compute_rms(Rigid(T2))

        npt.assert_almost_equal(rms1 * 2, rms2, 1)

    def test_new_run_detection(self):

        a = anal.MotionAnalyzer(None, None)
        a.ref_vol = dict(exam=1, series=2, acquisition=6)

        assert not a.new_scanner_run(dict(exam=1, series=2, acquisition=6))
        assert a.new_scanner_run(dict(exam=2, series=2, acquisition=6))
        assert a.new_scanner_run(dict(exam=1, series=3, acquisition=6))
        assert a.new_scanner_run(dict(exam=1, series=2, acquisition=7))

    def test_compute_registration(self):

        x, y, = np.meshgrid(np.linspace(-100, 100, 100),
                            np.linspace(-100, 100, 100))

        e = (x ** 2 / 40 ** 2 + y ** 2 / 50 ** 2 < 1).astype(np.float)
        e *= np.sin(x / 4)
        e1 = np.zeros((100, 100, 10))
        e1[..., 5] = e
        e2 = np.roll(e1, 5, axis=1)

        eim1 = nib.Nifti1Image(e1, np.eye(4))
        eim2 = nib.Nifti1Image(e2, np.eye(4))

        a = anal.MotionAnalyzer(None, None)
        T = a.compute_registration(eim1, eim2)
        npt.assert_array_almost_equal(T.translation, [0, 5, 0], 1)
