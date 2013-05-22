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
        self.description  = ('Real-time fMRI tools. Gets dicoms from the most recent series, builds volumes\n'
                             'from them, and computes motion parameters for timeseries scans. Dicoms are pulled\n'
                             'from the scanner via ftp. Use ctrl-c to terminate (it might take a moment for all\n'
                             'the threads to die).\n\n')
        self.add_argument('-u', '--username', help='scanner ftp username')
        self.add_argument('-p', '--password', help='scanner ftp password')
        self.add_argument('-o', '--hostname', default='cnimr', help='scanner hostname or ip address')
        self.add_argument('-d', '--dicomdir', default='/export/home1/sdc_image_pool/images', help='path to dicom file store on the scanner')
        self.add_argument('-i', '--interval', type=float, default=1.0, help='interval between checking for new files')
        self.add_argument('-s', '--seriesdir', default=None, help='series directory to use (will default to most recent series)')


if __name__ == '__main__':
    args = ArgumentParser().parse_args()
    dicom_q = queue.Queue()
    volume_q = queue.Queue()
    result_d = {'exam':0, 'series':0, 'patient_id':'', 'series_description':'', 'tr':0, 'mean_displacement':[], 'affine':[]}
    scanner = rtclient.RTClient(hostname=args.hostname, username=args.username, password=args.password,
                                image_dir=args.dicomdir)
    scanner.connect()
    if args.seriesdir:
        series_dir = args.seriesdir
    else:
        series_dir = scanner.series_dir()
    print series_dir
    if not series_dir:
        assert(false)

    dicom_finder = rtutil.IncrementalDicomFinder(scanner, series_dir, dicom_q, result_d)
    volumizer = rtutil.Volumizer(dicom_q, volume_q, result_d)
    analyzer = rtutil.Analyzer(volume_q, result_d)
    server = rtutil.Server(result_d)

    def term_handler(signum, stack):
        print 'Receieved SIGTERM - shutting down...'
        dicom_finder.halt()
        volumizer.halt()
        analyzer.halt()
        server.halt()
        print 'Asked all threads to terminate'
        dicom_finder.join()
        volumizer.join()
        analyzer.join()
        server.join()
        print 'Process complete'
        sys.exit(0)

    signal.signal(signal.SIGINT, term_handler)
    signal.signal(signal.SIGTERM, term_handler)

    dicom_finder.start()
    volumizer.start()
    analyzer.start()
    server.start()

    while True: time.sleep(1)  # stick around to receive and process signals


