#!/usr/bin/env python
#
# @author:  Robert Dougherty, Kiefer Katovich, Gunnar Schaefer

"""
To test this code without a scanner, start the scan simulator:



Then run this with appropriate args:

    ./rtmotion.py -u anonymous -p foo -o localhost -d test_data -f 2121

Refactor:
    * Add a thread to find new exams/series and queue them up for dicomFinder thread
    * Dicom finder just keeps pushing dicoms to the dicom queue
    * Volumizer volumizes as before, but also tags each volume with exam/series/acq (e/s/a)
    * Analyzer analyzes each e/s/a separately, pushing to results queue
    * Make results a queue of exams, with each containing a queue of s/a items
    * Server probes the results queue to see what e/s/a options to list in the GUI
    * GUI list is updated every 5 seconds via ajax, and discards old exam items from the
      results queue, AFTER it has updated the available exam list for the ajax call.
"""

import Queue as queue
import signal
import sys
import time

import rtutil
import rtclient

if __name__ == '__main__':
    import argparse

    arg_parser = argparse.ArgumentParser()
    arg_parser.description  = ('Real-time fMRI tools. Gets dicoms from the most recent series, builds volumes\n'
                               'from them, and computes motion parameters for timeseries scans. Dicoms are pulled\n'
                               'from the scanner via ftp. Use ctrl-c to terminate (it might take a moment for all\n'
                               'the threads to die).\n\n')
    arg_parser.add_argument('-u', '--username', help='scanner ftp username')
    arg_parser.add_argument('-p', '--password', help='scanner ftp password')
    arg_parser.add_argument('-o', '--hostname', default='cnimr', help='scanner hostname or ip address (default: cnimr)')
    arg_parser.add_argument('-d', '--dicomdir', default='/export/home1/sdc_image_pool/images', help='path to dicom file store on the scanner (default: /export/home1/sdc_image_pool/images)')
    arg_parser.add_argument('-f', '--ftpport', type=int, default=21, help='scanner FTP port (default: 21)')
    arg_parser.add_argument('-i', '--interval', type=float, default=1.0, help='interval between checking for new files')
    arg_parser.add_argument('-r', '--port', type=int, default=8080, help='port to serve the results (default: 8080)')
    arg_parser.add_argument('-n', '--nskip', type=int, default=2, help='number of volumes to skip (default=2)')
    args = arg_parser.parse_args()

    series_q = queue.Queue()
    dicom_q = queue.Queue()
    volume_q = queue.Queue()
    result_d = {}
    # We use two ftp connections, one for the series_finder thread and one for the dicom_finder thread,
    # so they don't interfere with each other.
    scanner1 = rtclient.RTClient(hostname=args.hostname, username=args.username, password=args.password,
                                image_dir=args.dicomdir, port=args.ftpport)
    scanner2 = rtclient.RTClient(hostname=args.hostname, username=args.username, password=args.password,
                                image_dir=args.dicomdir, port=args.ftpport)
    scanner1.connect()
    scanner2.connect()
    series_finder = rtutil.SeriesFinder(scanner1, series_q, interval=args.interval)
    dicom_finder = rtutil.IncrementalDicomFinder(scanner2, series_q, dicom_q)
    volumizer = rtutil.Volumizer(dicom_q, volume_q)
    analyzer = rtutil.Analyzer(volume_q, result_d, skip_vols=args.nskip)
    server = rtutil.Server(result_d, port=args.port)

    def term_handler(signum, stack):
        print 'Receieved SIGTERM - shutting down...'
        series_finder.halt()
        dicom_finder.halt()
        volumizer.halt()
        analyzer.halt()
        server.halt()
        print 'Asked all threads to terminate'
        series_finder.join()
        dicom_finder.join()
        volumizer.join()
        analyzer.join()
        server.join()
        print 'Process complete'
        sys.exit(0)

    signal.signal(signal.SIGINT, term_handler)
    signal.signal(signal.SIGTERM, term_handler)

    series_finder.start()
    dicom_finder.start()
    volumizer.start()
    analyzer.start()
    server.start()

    while True: time.sleep(1)  # stick around to receive and process signals


