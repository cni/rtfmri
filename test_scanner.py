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
import sys, os, time
import signal
import socket
import cStringIO
import pdb
from Queue import Queue

from rtfmri.clients import SFTPClient
from rtfmri.interface import ScannerInterface
from rtfmri.queuemanagers import SeriesFinder, DicomFinder, Volumizer

def time_it(tic, message):
    toc = time.time()
    print(message + " {}".format(toc-tic))
    return toc-tic


class ClientMaker(object):
    def __init__(self, *args, **kwargs):
        self.cl = SFTPClient(*args, **kwargs)


if __name__ == '__main__':
    host="cnimr"
    port=22,
    username=""
    password="testpass"
    base_dir="/export/home1/sdc_image_pool/images"

    # host = "localhost"
    # port = 2124
    # base_dir = "nick_test_data"
    # private_key ='test.key'
    # public_key = 'CSR.csr'

    try:

        s1 = ClientMaker(hostname=host,
                         username=username,
                         port=port,
                         base_dir=base_dir,
                         password=password,
                         private_key=private_key,
                         public_key=public_key)

        s2 = ClientMaker(hostname=host,
                         port=port,
                         username=username,
                         base_dir=base_dir,
                         password=password,
                         private_key=private_key,
                         public_key=public_key)
        print(s1.cl.latest_exam)
        print(s2.cl.latest_exam)
    except Exception, e:
        print ("Failed to connect to sftp server, check login.")
        print(e)
        sys.exit(1)

    sq = Queue()
    dq = Queue()
    vq = Queue()

    sf = SeriesFinder(s1.cl, sq, interval=1)
    df = DicomFinder(s2.cl, sq, dq, interval=0.01)
    vo = Volumizer(dq, vq, interval=0.02)




    ### parameters for the actual scan.


    # Pass the default credentials to connect to the test FTP server
    interface = ScannerInterface(hostname=host,
                                 port=port,
                                 username=username,
                                 password=password,
                                 base_dir=base_dir)

    masker = Masker('nick_test_subject/naccf_pos.nii')
    #start_scan()
    #Logging some basic info:
    print(interface.series_finder.client.latest_exam)
    print(interface.series_finder.client.latest_series)

    #sys.exit(0)

    v = TextVisualizer(interface, masker)
    #v = GraphVisualizer(interface, masker)
    #v = Thermometer(interface, masker)
    #v.start_display()
    #start_scan()
    v.start_timer()
    #
    # pdb.set_trace()

    v.start_interface()
    v.run()
