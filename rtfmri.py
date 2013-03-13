#!/usr/bin/env python
#
# @author:  Gunnar Schaefer

import os
import sys
import time
import Queue as queue
import shlex
import signal
import argparse
import datetime
import threading
import subprocess
import collections

import dicom

QUANTIZATION_CORRECTION = datetime.timedelta(seconds=2)


class DicomFinder(threading.Thread):

    """DicomFinder finds the latest dicom files and pushes them into the dicom queue as dicom objects."""

    def __init__(self, exam_dir, dicom_q, interval):
        super(DicomFinder, self).__init__()
        self.exam_dir = exam_dir
        self.dicom_q = dicom_q
        self.interval = interval
        self.alive = True

    def halt(self):
        self.alive = False

    def run(self):
        #find_cmd_str = 'find %s -type f -newermt "%s"'
        find_cmd_str = 'find %s -type f'
        series_dir_cmd = 'find %s -mindepth 1 -maxdepth 1 -exec stat -c "%%Y;%%n" {} +' % self.exam_dir
        #hist_len = int((2 * QUANTIZATION_CORRECTION.seconds / self.interval.total_seconds()) + 0.5)
        #history = collections.deque([set() for i in range(hist_len)], maxlen=hist_len)
        last_check = datetime.datetime.now()
        filenames_dict = {}
        while self.alive:
            all_series_dirs = subprocess.check_output(shlex.split(series_dir_cmd), stderr=subprocess.STDOUT).split()
            all_series_dirs = dict([ex.split(';') for ex in all_series_dirs])
            series_dir = all_series_dirs[max(all_series_dirs)]

            this_check = datetime.datetime.now()
            #find_cmd = find_cmd_str % (series_dir, last_check-QUANTIZATION_CORRECTION)
            find_cmd = find_cmd_str % (series_dir)

            try:
                #find_out = subprocess.check_output(shlex.split(find_cmd), stderr=subprocess.STDOUT).split()
                find_out = [os.path.join(series_dir, d) for d in os.listdir(series_dir)]
            except subprocess.CalledProcessError:
                print 'Error while checking for new files'
            else:
                last_check = this_check
                #filenames = set(find_out) - set.union(*history)
                filenames = set(find_out) - filenames_dict.setdefault(series_dir, set())
                for filename in filenames.copy():
                    try:
                        dcm = dicom.read_file(filename)
                        if not len(dcm.PixelData) == 2 * dcm.Rows * dcm.Columns:
                            raise Exception
                    except:
                        filenames.remove(filename)  # try this one again next time
                    else:
                        #print ' dicom %5s in' % dcm.InstanceNumber
                        print filename
                        self.dicom_q.put(dcm)
                #history.append(filenames)
                filenames_dict[series_dir] |= filenames

            sleeptime = (this_check + self.interval - datetime.datetime.now()).total_seconds()
            print '%4d (%3d): %s (%f)' % (len(filenames_dict[series_dir]), len(filenames), last_check, sleeptime)
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
        super(ArgumentParser, self).__init__()
        self.description = """
            Facilitate real-time fMRI.
            """
        self.add_argument('dicom_dir', help='path to dicom root directory')
        self.add_argument('-i', '--interval', type=float, default=1.0, help='interval between checking for new files')


if __name__ == '__main__':
    args = ArgumentParser().parse_args()

    dicom_q = queue.Queue()
    volume_q = queue.Queue()

    exam_dir_cmd = 'find %s -mindepth 2 -maxdepth 2 -exec stat -c "%%Y;%%n" {} +' % args.dicom_dir
    all_exam_dirs = subprocess.check_output(shlex.split(exam_dir_cmd), stderr=subprocess.STDOUT).split()
    all_exam_dirs = dict([ex.split(';') for ex in all_exam_dirs])
    exam_dir = all_exam_dirs[max(all_exam_dirs)]

    dicom_finder = DicomFinder(exam_dir, dicom_q, datetime.timedelta(seconds=args.interval))
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
