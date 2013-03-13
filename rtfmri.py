#!/usr/bin/env python
#
# @author:  Gunnar Schaefer

import os
import sys
import glob
import time
import Queue as queue
import signal
import argparse
import datetime
import threading

import dicom


class DicomFinder(threading.Thread):

    """DicomFinder finds the latest dicom files and pushes them into the dicom queue as dicom objects."""

    def __init__(self, exam_path, dicom_q, interval):
        super(DicomFinder, self).__init__()
        self.exam_path = exam_path
        self.dicom_q = dicom_q
        self.interval = interval
        self.alive = True

    def halt(self):
        self.alive = False

    def run(self):
        files_dict = {}
        while self.alive:
            before_check = datetime.datetime.now()
            series_path = max(glob.glob(os.path.join(exam_path, 's*')), key=lambda d: os.stat(d).st_mtime)
            current_files = os.listdir(series_path)
            new_files = set(current_files) - files_dict.setdefault(series_path, set())
            for filename in new_files.copy():
                try:
                    dcm = dicom.read_file(os.path.join(series_path, filename))
                    if not len(dcm.PixelData) == 2 * dcm.Rows * dcm.Columns:
                        raise Exception
                except:
                    new_files.remove(filename)  # try this one again next time
                else:
                    self.dicom_q.put(dcm)
            files_dict[series_path] |= new_files

            sleeptime = (before_check + self.interval - datetime.datetime.now()).total_seconds()
            print '%s: %4d (%3d) [%f]' % (os.path.basename(series_path), len(files_dict[series_path]), len(new_files), sleeptime)
            if sleeptime > 0:
                time.sleep(sleeptime)


class Volumizer(threading.Thread):

    """Volumizer converts dicom objects from the dicom queue into 3D volumes and pushes them onto the volume queue."""

    def __init__(self, dicom_q, volume_q):
        super(Volumizer, self).__init__()
        self.dicom_q = dicom_q
        self.volume_q = volume_q
        self.alive = True

    def halt(self):
        self.alive = False

    def run(self):
        while self.alive:
            try:
                dcm = self.dicom_q.get(timeout=1)
            except queue.Empty:
                pass
            else:
                # TODO: convert incoming dicoms to 3D volumes
                volume = dcm
                self.volume_q.put(volume)


class Analyzer(threading.Thread):

    """Analyzer gets 3D volumes out of the volume queue and computes real-time statistics on them."""

    def __init__(self, volume_q):
        super(Analyzer, self).__init__()
        self.volume_q = volume_q
        self.alive = True

    def halt(self):
        self.alive = False

    def run(self):
        while self.alive:
            try:
                volume = self.volume_q.get(timeout=1)
            except queue.Empty:
                pass
            else:
                # TODO: append to 4D volume
                pass


class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        super(ArgumentParser, self).__init__(formatter_class=argparse.RawTextHelpFormatter)
        self.description  = 'Facilitate real-time fMRI.\n\n'
        self.description += 'Use NFS mount options "noac,lookupcache=none" to avoid client-side caching.'
        self.add_argument('dicom_path', help='path to dicom root directory')
        self.add_argument('-i', '--interval', type=float, default=1.0, help='interval between checking for new files')


if __name__ == '__main__':
    args = ArgumentParser().parse_args()

    dicom_q = queue.Queue()
    volume_q = queue.Queue()

    exam_path = max(glob.glob(os.path.join(args.dicom_path, 'p*/e*')), key=lambda d: os.stat(d).st_mtime)

    dicom_finder = DicomFinder(exam_path, dicom_q, datetime.timedelta(seconds=args.interval))
    volumizer = Volumizer(dicom_q, volume_q)
    analyzer = Analyzer(volume_q)

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

    while True: time.sleep(60)  # stick around to receive and process signals
