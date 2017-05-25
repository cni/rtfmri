"""The script to start neurofeedback--it should even start the scan!"""
from __future__ import print_function

import re
import pdb
import sys
from Queue import Queue, Empty

import nose.tools as nt
import numpy as np

from nose import SkipTest

from rtfmri.masker import Masker
from rtfmri.interface import ScannerInterface
from rtfmri.visualizers import *
from rtfmri.utilities import start_scan



if __name__ == '__main__':

    ### parameters for the actual scan.
    host="cnimr"
    port=21,
    username=""
    password=""
    base_dir="/export/home1/sdc_image_pool/images"

    host = "localhost"
    port = 2121
    base_dir = "nick_test_data"

    # Pass the default credentials to connect to the test FTP server
    interface = ScannerInterface(hostname=host,
                                 port=port,
                                 username=username,
                                 password=password,
                                 base_dir=base_dir)

    masker = Masker('nick_test_subject/naccf_pos.nii')
    #start_scan()
    #Logging some basic info:
    print(interface.series_finder.scanner.latest_exam)
    print(interface.series_finder.scanner.latest_series)

    #v = TextVisualizer(interface, masker)
    v = GraphVisualizer(interface, masker)
    #start_scan()
    v.start_timer()
    print(interface.series_finder.scanner.latest_exam)
    print(interface.series_finder.scanner.latest_series)
    #sys.exit(0)
    # pdb.set_trace()

    v.start_interface()
    v.run()
