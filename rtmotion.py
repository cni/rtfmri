#!/usr/bin/env python
#
# @author:  Gunnar Schaefer

import Queue as queue
import glob
import signal
import argparse
import sys
import time

import rtutil

#import string
#import os
#import glob
#import datetime
#import threading
#import thread
#import random
#import re
#from socket import *

CNI_TOP_DIR = '/net/cnimr/export/home1/sdc_image_pool/images/'

class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        super(ArgumentParser, self).__init__(formatter_class=argparse.RawTextHelpFormatter)
        self.description  = 'Facilitate real-time fMRI.\n\n'
        self.description += 'Use NFS mount options "noac,lookupcache=none" to avoid client-side caching.'
        self.add_argument('dicom_path', help='path to dicom root directory')
        self.add_argument('-i', '--interval', type=float, default=1.0, help='interval between checking for new files')


if __name__ == '__main__':
    #args = ArgumentParser().parse_args()
    dicom_q = queue.Queue()
    volume_q = queue.Queue()
    average_q = queue.Queue()

    [scan_top_dir,all_dirs] = rtutil.get_current(CNI_TOP_DIR)
    print all_dirs
    print scan_top_dir

    go = raw_input('Hit enter just before the scan starts:')

    # FIXME
    series_dir = rtutil.wait_for_new_directory(scan_top_dir, all_dirs, 60.0)
    print series_dir
    if not series_dir:
        assert(false)

    dicom_finder = rtutil.IncrementalDicomFinder(series_dir, dicom_q, 0.25)

    volumizer = rtutil.Volumizer(dicom_q, volume_q)

    analyzer = rtutil.Analyzer(volume_q, average_q)

    def term_handler(signum, stack):
        print 'Receieved SIGTERM - shutting down...'
        dicom_finder.halt()
        volumizer.halt()
        analyzer.halt()
        print 'Asked all threads to terminate'
        dicom_finder.join()
        volumizer.join()
        analyzer.join()
        print 'Process complete'
        sys.exit(0)

    signal.signal(signal.SIGINT, term_handler)
    signal.signal(signal.SIGTERM, term_handler)

    dicom_finder.start()
    volumizer.start()
    analyzer.start()

    while True: time.sleep(1)  # stick around to receive and process signals


