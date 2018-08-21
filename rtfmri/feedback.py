"""The script to start neurofeedback--it should even start the scan!"""
from __future__ import print_function
import pprint
import re
import pdb
import time
import sys, socket
from Queue import Queue, Empty
from threading import Thread, Event, Lock

import numpy as np

from .analyzers import MotionAnalyzer
from .masker import Masker, DicomFilter
from .interface import ScannerInterface
from .visualizers import *
from .utilities import start_scanner


class Neurofeedback(object):

    def __init__(self, hostname='cnimr', port=22, username='', password='',
                 base_dir="/export/home1/sdc_image_pool/images",
                 buffer_size = 8, use_analyzer=False, width=1000, height=1000,
                 debug=False, feedback = True):
        # Pass the default credentials to connect to the test FTP server.
        # We also pass a dcm filter in order to only load needed dicoms
        # based on the mask.
        try:
            self.interface = ScannerInterface(hostname=hostname,
                                              port=port,
                                              username=username,
                                              password=password,
                                              base_dir=base_dir,
                                              use_series_finder=False)

            print("Latest exam: ",self.interface.dicom_finder.client.latest_exam)
            print("Latest series: ", self.interface.dicom_finder.client.latest_series)
        except Exception as e:
            print("Caught exception:", e)
            raise(socket.error, "Unable to open connection to scanner.")
            self.interface = None

        self.series=None
        self.use_analyzer=use_analyzer
        self.visualizer=None
        self.width=width
        self.height=height
        self.debug=debug

        self.feedback=feedback
        self.buffer_size=buffer_size

    def use_mask(self, mask_path, center=None, radius=8, use_filter=False):

        # Create the masking object and DicomFilter
        mask_center = None # this is the z coord of our roi (IS)
                           # if z is none, we get center of mass
        masker = Masker(mask_path, center=mask_center, radius=radius)
        #masker.add_orthogonal('emily_analysis/wm.nii.gz')
        #masker.add_orthogonal('emily_analysis/csf.nii.gz')
        if use_filter:
            dcm_filter = DicomFilter(masker)
            self.interface.set_dicom_filter(dcm_filter)
        self.masker=masker

        interface = self.analyzer if self.use_analyzer else self.interface

        self.data_manager = FeedbackDataManager(interface, masker)

    def set_series(self, use_newest=True, predict=True, series=None):
        if use_newest:
            self.series = self.interface.use_newest_exam_series(predict = predict)
        else:
            self.series = self.interface.use_series(series)

        return self.series

    def init_visualizer(self, visualizer='text'):
        print("* Initializing visualizer * ")
        self.visualizer_kind = visualizer


        interface = self.analyzer if self.use_analyzer else self.interface

        if visualizer=='text':
            v = TextVisualizer(self.data_manager)

        if visualizer=='graph':
            v = GraphVisualizer(self.data_manager)

        if visualizer=='thermometer':
            v = Thermometer(self.data_manager,
                            debug=self.debug,
                            feedback=self.feedback,
                            buffer_size=self.buffer_size)
            v.start_display(width = self.width, height=self.height)

        v.set_regressors(vec = self.vec, text=self.timing_texts, TR=self.TR)
        self.visualizer = v

    def set_timing(self, timing_file, timing_texts, TR=2):
        vec = np.genfromtxt(timing_file)
        self.data_manager.timing_vec = vec
        self.data_manager.interface.use_timing_vec(vec)
        self.vec = vec
        self.timing_texts = timing_texts
        self.TR = TR

        try:
            self.visualizer.set_regressors(vec = vec, text=timing_texts, TR=TR)
        except AttributeError:
            pass

    def start_scan(self, dry_run=False):
        if self.visualizer is None:
            print("No visualizer set, aborting scan")
            return


        client = self.interface.dicom_finder.client

        #First start the scan
        if not dry_run:
            start_scanner()
        self.visualizer.start_timer()
        self.data_manager.start_timer()


        #Now wait for the session we want to appear
        if not client.path_exists(self.series):
            print("Waiting for dicoms to appear...")
        while not client.path_exists(self.series):
            time.sleep(.01)
        print("Session found, beginning feedback...")


        #start the interface
        self.data_manager.start_interface()
        self.data_manager.run()

        #start the visualizer

        self.visualizer.run()


class FeedbackDataManager(object):
    # Object that manages the current feedback session's fmri data, independent
    # of the display.

    def __init__(self, interface, masker, interval=0):
        super(FeedbackDataManager, self).__init__()
        self.brain_data_queue = Queue()
        self.thread = FeedbackDataThread(interface, masker, self.brain_data_queue, interval)
        self.interface = interface
        self.roi_state = 0

    def start_interface(self):
        self.interface.start()

    def start_timer(self):
        self.thread.start_timer()

    def run(self):
        self.thread.start()

    def get_state(self):
        try:
            self.roi_state = self.brain_data_queue.get()
        except Empty:
            pass
        return self.roi_state


    def halt(self):
        """Make it so the thread will halt within a run method."""
        self.thread.halt()


class FeedbackDataThread(Thread):
    # Thread that manages the current feedback session's fmri data

    def __init__(self, interface, masker, brain_data_q, interval=0.001):
        super(FeedbackDataThread, self).__init__()
        self.brain_data_q = brain_data_q
        self.daemon = True
        self.stop_event = Event()
        self.interface = interface
        self.masker = masker
        self.interval = interval
        self.n_volumes_reduced = 0
        self.TR = 2
        self.total_get_and_reduce_time = 0
        self.total_reduce_time = 0
        self.total_get_time = 0

    def halt(self):
        """Make it so the thread will halt within a run method."""
        self.stop_event.set()

    @property
    def is_alive(self):
        return not self.stop_event.is_set()

    def start_timer(self):
        self.start_time = time.time()
        self.last_reduced_time = self.start_time

    @property
    def current_tr(self):
        return int((time.time() - self.start_time) // self.TR)


    def run(self):
        print("running the thread")
        while self.is_alive:
            self.get_and_reduce_volume()

    def get_and_reduce_volume(self):
        start_get = time.time()
        vol = self.interface.get_volume()
        end_get = time.time()
        roi_mean = self.masker.reduce_volume(vol)
        end_reduce = time.time()
        self.n_volumes_reduced += 1
        self.total_get_and_reduce_time += end_reduce - start_get
        self.total_reduce_time += end_reduce - end_get
        self.total_get_time += end_get - start_get
        self.brain_data_q.put(roi_mean)
        self.log_times()
        self.last_reduced_time = end_reduce


    def log_times(self):
        start_diff = time.time() - self.start_time
        last_diff = time.time() - self.last_reduced_time
        volume_collected_tail = self.start_time + self.n_volumes_reduced * self.TR
        lag = time.time() - volume_collected_tail

        try:
            avg_retrival = self.interface.dicom_finder.total_time_dicom_retrival / self.interface.dicom_finder.n_dicoms_queued
            avg_dequeue = self.interface.volumizer.total_dequeue_time / self.interface.volumizer.n_dicoms_dequeued
            avg_assembly = self.interface.volumizer.total_assembly_time / self.interface.volumizer.n_volumes_queued
            avg_get_time = self.total_get_time / self.n_volumes_reduced
            avg_mask_time = self.total_reduce_time / self.n_volumes_reduced            
        except ZeroDivisionError:
            return

        print("============== TIMING ===================")
        print("Display Volume/Scanner Volume: {}/{}".format(self.n_volumes_reduced, self.current_tr))
        print("Lag since collection: {}".format(lag))
        print ('')
        print("Time since start: {}".format(start_diff ))
        print("Time since last: {}".format(last_diff))
        print("Average since start: {}".format(start_diff/self.n_volumes_reduced))
        print("***************** STATS *****************")
        print("*** Average DCM Retrival: {}".format(avg_retrival))
        print("*** Average DCM Dequeue: {}".format(avg_dequeue))
        print("*** Average Volume Assembly: {}".format(avg_assembly))
        print("*** Average Volume Dequeue Time: {}".format(avg_get_time))        
        print("*** Average Reduce Time: {}".format(avg_mask_time))
        print("========================================")
