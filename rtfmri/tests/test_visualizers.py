from __future__ import print_function

import re
from Queue import Queue, Empty


import nose.tools as nt
import numpy as np

from nose import SkipTest

from ..masker import Masker
from ..interface import ScannerInterface
from ..visualizers import *


# class TestVisualizer(object):

#     def __init__(self):
#         self.interface = ScannerInterface('localhost',
#                                           2121,
#                                           base_dir='nick_test_data')

#     def test_control(self):

#         v = Visualizer(self.interface, timeout=2)
#         assert v.alive

#         v.halt()
#         assert not v.alive

#         nt.assert_equal(v.timeout, 2)
#         nt.assert_equal(v.state, 0)

#     def test_get_volume(self):
#         v = Visualizer(self.interface, timeout=2)
#         v.start_interface()
#         vol = v.get_volume()
#         v.halt()


# class TestPyGameVisualizer(TestVisualizer):

#     def test_control(self):
#         v = PyGameVisualizer(self.interface, timeout=2)
#         v.start_display()
#         assert v.alive
#         v.halt()
#         assert not v.alive
#         nt.assert_equal(v.timeout, 2)
#         nt.assert_equal(v.state, 0)

#     def test_interface(self):
#         v = PyGameVisualizer(self.interface, timeout=2)
#         v.start_interface()
#         v.halt()

#     def test_display(self):
#         v = PyGameVisualizer(self.interface)
#         v.start_display()
#         v.halt()

#     def test_display_and_interface(self):
#         v = PyGameVisualizer(self.interface)
#         v.start_display()
#         v.start_interface()
#         v.halt()


# class TestRoiVisualizer(TestVisualizer):

#     @classmethod
#     def setup_class(cls):

#         cls.host = "localhost"
#         cls.port = 2121
#         cls.base_dir = "nick_test_data"

#         # Pass the default credentials to connect to the test FTP server
#         cls.interface = ScannerInterface(hostname=cls.host,
#                                          port=cls.port,
#                                          base_dir=cls.base_dir)

#         cls.masker = Masker('cue_test_subject/naccf_pos.nii')

#     @classmethod
#     def teardown_class(cls):

#         if cls.interface.alive:
#             cls.interface.shutdown()

#     def test_control(self):
#         v = RoiVisualizer(self.interface, self.masker, timeout=2)
#         assert v.alive

#         v.halt()
#         assert not v.alive

#         nt.assert_equal(v.timeout, 2)
#         nt.assert_equal(v.state, 0)

#     def test_update_state(self):
#         v = RoiVisualizer(self.interface, self.masker, timeout=2)
#         v.start_interface()
#         states = []
#         for _ in range(2):
#             v.update_state()
#             states.append(v.state)
#         mu_v1, mu_v2 = states
#         np.testing.assert_almost_equal(
#             (mu_v1, mu_v2), (2317.28, 1806.17), decimal=2)
#         nt.assert_equal(v.interface.alive, True)
#         v.halt()

class TestGraphVisualizer(object):

    @classmethod
    def setup_class(cls):

        cls.host = "localhost"
        cls.port = 2121
        cls.base_dir = "nick_test_data"

        # Pass the default credentials to connect to the test FTP server
        cls.interface = ScannerInterface(hostname=cls.host,
                                         port=cls.port,
                                         base_dir=cls.base_dir)

        cls.masker = Masker('nick_test_subject/naccf_pos.nii')

    @classmethod
    def teardown_class(cls):

        if cls.interface.alive:
            cls.interface.shutdown()

    def test_graph(self):
        v = GraphVisualizer(self.interface, self.masker)
        v.start_interface()
        v.run()

        v.halt()


# class TestThermometer(object):

#     @classmethod
#     def setup_class(cls):

#         cls.host = "localhost"
#         cls.port = 2121
#         cls.base_dir = "nick_test_data"

#         # Pass the default credentials to connect to the test FTP server
#         cls.interface = ScannerInterface(hostname=cls.host,
#                                          port=cls.port,
#                                          base_dir=cls.base_dir)

#         cls.masker = Masker('nick_test_subject/naccf_pos.nii')

#     @classmethod
#     def teardown_class(cls):

#         if cls.interface.alive:
#             cls.interface.shutdown()

#     # def test_display(self):
#     #     v = Thermometer(self.interface, self.masker)
#     #     v.start_interface()
#     #     v.start_display()
#     #     v.run(random=True)
#     #     v.halt()

#     def test_thermo(self):
#         v = Thermometer(self.interface, self.masker)
#         v.start_interface()
#         v.start_display()
#         v.run(random=False)

#         v.halt()
