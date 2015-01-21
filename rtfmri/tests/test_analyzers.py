from __future__ import print_function

from Queue import Queue, Empty
import numpy as np
import nibabel as nib

import nose.tools as nt
import numpy.testing as npt

from nipy.algorithms.registration import Rigid

from .. import analyzers as anal


class TestMotionAnalyzer(object):

    x, y, = np.meshgrid(np.linspace(-100, 100, 100),
                        np.linspace(-100, 100, 100))

    e = (x ** 2 / 40 ** 2 + y ** 2 / 50 ** 2 < 1).astype(np.float)
    e *= np.sin(x / 4)
    e1 = np.zeros((100, 100, 10))
    e1[..., 5] = e
    e2 = np.roll(e1, -5, axis=1)

    eim1 = nib.Nifti1Image(e1, np.eye(4))
    eim2 = nib.Nifti1Image(e2, np.eye(4))

    def test_rms(self):

        a = anal.MotionAnalyzer(None, None)

        T1, T2 = np.eye(4), np.eye(4)
        nt.assert_equal(a.compute_rms(Rigid(T1), Rigid(T2)), 0)

        T2[0, 3] = 1
        nt.assert_equal(a.compute_rms(Rigid(T1), Rigid(T2)), 1)

        T2[1, 3] = 1
        nt.assert_equal(a.compute_rms(Rigid(T1), Rigid(T2)), np.sqrt(2))

        T1 = np.eye(4)
        T1[1:3, 1:3] = [(np.cos(.1), -np.sin(.1)),
                        (np.sin(.1), np.cos(.1))]
        rms1 = a.compute_rms(Rigid(np.eye(4)), Rigid(T1))

        T2 = np.eye(4)
        T2[1:3, 1:3] = [(np.cos(.2), -np.sin(.2)),
                        (np.sin(.2), np.cos(.2))]
        rms2 = a.compute_rms(Rigid(np.eye(4)), Rigid(T2))

        npt.assert_almost_equal(rms1 * 2, rms2, 1)

    def test_new_run_detection(self):

        a = anal.MotionAnalyzer(None, None)
        a.ref_vol = dict(exam=1, series=2, acquisition=6)

        assert not a.new_scanner_run(dict(exam=1, series=2, acquisition=6))
        assert a.new_scanner_run(dict(exam=2, series=2, acquisition=6))
        assert a.new_scanner_run(dict(exam=1, series=3, acquisition=6))
        assert a.new_scanner_run(dict(exam=1, series=2, acquisition=7))

        a.ref_vol = dict()
        assert not a.new_scanner_run(dict(exam=1, series=2, acquisition=6))

    def test_compute_registration(self):

        a = anal.MotionAnalyzer(None, None)
        T = a.compute_registration(self.eim1, self.eim2, "rigid")
        npt.assert_array_almost_equal(T.translation, [0, -5, 0], 1)

    def test_volume_center(self):

        a = anal.MotionAnalyzer(None, None)
        img = nib.Nifti1Image(np.zeros((10, 10, 10)), np.eye(4))
        center = a.volume_center(img)
        npt.assert_array_equal(center, [4.5] * 3)

    def test_run_method(self):

        volume_q = Queue()

        class ScannerInterface(object):
            """Mock the ScannerInterface with just the queue we need."""
            def __init__(self, q):

                self.q = q

            def get_volume(self, *args, **kwargs):

                return self.q.get(*args, **kwargs)

        scanner = ScannerInterface(volume_q)
        result_q = Queue()

        a = anal.MotionAnalyzer(scanner, result_q, skip_vols=0)

        vol1 = dict(exam=1, series=1, acquisition=1, image=self.eim1)
        volume_q.put(vol1)

        vol2 = dict(exam=1, series=1, acquisition=1, image=self.eim2)
        volume_q.put(vol2)

        try:
            a.start()

            result = result_q.get(timeout=5)
            assert result
            for axis in ["x", "y", "z"]:
                nt.assert_equal(result["rot_" + axis], 0)
                nt.assert_equal(result["trans_" + axis], 0)
            nt.assert_equal(result["rms_ref"], 0)
            nt.assert_equal(result["rms_pre"], 0)
            nt.assert_equal(result["vol_number"], 0)

            result = result_q.get(timeout=5)
            # Quick and dirty tests
            nt.assert_less(2, result["trans_y"])
            nt.assert_less(2, result["rms_ref"])
            nt.assert_less(2, result["rms_pre"])
            nt.assert_equal(result["vol_number"], 1)

        finally:

            a.halt()
            a.join()

        a = anal.MotionAnalyzer(scanner, result_q, skip_vols=1)

        volume_q.put(vol1)
        volume_q.put(vol1)
        volume_q.put(vol1)

        try:
            a.start()

            result = result_q.get(timeout=5)
            nt.assert_equal(result["vol_number"], 1)

            result = result_q.get(timeout=5)
            nt.assert_equal(result["vol_number"], 2)

            with nt.assert_raises(Empty):
                result = result_q.get(timeout=1)

        finally:

            a.halt()
            a.join()
