#!/usr/bin/env python
#
# @author:  Robert Dougherty, Kiefer Katovich, Gunnar Schaefer

import Queue as queue
import signal
import argparse
import sys
import time

import rtutil
import rtclient

class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        super(ArgumentParser, self).__init__(formatter_class=argparse.RawTextHelpFormatter)
        self.description  = 'Real-time fMRI.\nConnects to the scanner via ftp. Use ctrl-c to terminate (might take a moment for all the threads to die).\n\n'
        self.add_argument('-u', '--username', help='scanner username')
        self.add_argument('-p', '--password', help='scanner password')
        self.add_argument('-o', '--hostname', default='cnimr', help='scanner hostname or ip address')
        self.add_argument('-d', '--dicomdir', default='/export/home1/sdc_image_pool/images', help='path to dicom file store on the scanner')
        self.add_argument('-i', '--interval', type=float, default=1.0, help='interval between checking for new files')


if __name__ == '__main__':
    args = ArgumentParser().parse_args()
    dicom_q = queue.Queue()
    volume_q = queue.Queue()
    average_q = queue.Queue()

    scanner = rtclient.RTClient(hostname=args.hostname, username=args.username, password=args.password, image_dir=args.dicomdir)
    scanner.connect()
    series_dir = scanner.series_dir()
    print series_dir
    if not series_dir:
        assert(false)

    dicom_finder = rtutil.IncrementalDicomFinder(scanner, series_dir, dicom_q, 0.25)

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


