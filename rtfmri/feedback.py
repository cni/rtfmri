"""The script to start neurofeedback--it should even start the scan!"""
from __future__ import print_function

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

        #pdb.set_trace()
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

        self.brain_data = {}
        self.thread = FeedbackDataThread(interface, masker, self.brain_data, interval)
        self.interface = interface

    def start_interface(self):
        self.interface.start()

    def start_timer(self):
        self.thread.start_timer()

    @property
    def current_tr(self):
        return int((time.time() - self.start) // self.TR)

    def run(self):
        self.thread.run()

    def get_state(self):
        return self.brain_data

    def halt(self):
        """Make it so the thread will halt within a run method."""
        self.thread.halt()


class FeedbackDataThread(Thread):
    # Thread that manages the current feedback session's fmri data

    def __init__(self, interface, masker, brain_data, interval=0):
        super(FeedbackDataThread, self).__init__()

        self.brain_data = brain_data

        self.daemon = True
        self.stop_event = Event()

        self.interface = interface
        self.masker = masker
        self.interval = interval

        self.roi_tc = []
        self.n_volumes_reduced = 0
        self.TR = 2
        self.ortho_tcs = [[] for x in self.masker.orthogonals]
        self.detrended = []
        self.total_masker_roi_average_time = 0

        self.brain_data['state'] = 0



    def halt(self):
        """Make it so the thread will halt within a run method."""
        self.stop_event.set()

    @property
    def is_alive(self):
        return not self.stop_event.is_set()

    def start_timer(self):
        self.start = time.time()
        self.last_reduced_time = self.start

    @property
    def current_tr(self):
        return int((time.time() - self.start) // self.TR)


    def run(self):
        while self.is_alive:
            tic = time.time()
            self.get_and_reduce_volume()

    def get_and_reduce_volume(self):

        vol = self.interface.get_volume()

        self.n_volumes_reduced += 1
        tic = time.time()
        roi_mean = self.masker.reduce_volume(vol)
        self.total_masker_roi_average_time += (time.time() - tic)

        self.roi_tc.append(roi_mean)
        self.log_times()

        if self.masker.use_orthogonal:
            ortho_means = self.masker.get_orthogonals(vol)
            for i, mean in enumerate(ortho_means):
                self.ortho_tcs[i].append(mean)
            # if len(self.roi_tc) > 3:
            #     detrended = self.detrend()
            #     print(np.corrcoef(detrended[:,0], self.roi_tc[2:]))
            #     roi_mean = detrended[-1,0]
            #     self.detrended = detrended[:,0]

        self.brain_data['roi_tc'] = self.roi_tc

    def get_state(self):
        return self.state

    def detrend(self):
        # make a timepoint x num roi matrix and take pcs[].
        tcs = [self.roi_tc]
        for x in self.ortho_tcs:
            tcs.append(x)
        #leave out the noise of the first two time points
        tcm = np.transpose(np.array(tcs))[2:, :]

        #transform onto pcs
        pca = decomp.PCA()
        pca.fit(tcm)
        tf = pca.transform(tcm)

        # ica = decomp.FastICA()
        # ica.fit(tcm)
        # tf = ica.transform(tcm)

        return tf

    def log_times(self):
        n = len(self.roi_tc)
        toc = time.time()
        start_diff = toc - self.start
        last_diff  = toc - self.last_reduced_time
        volume_collected = self.start + self.n_volumes_reduced * self.TR - 2
        lag = toc - volume_collected

        try:
            avg_retrival = self.interface.dicom_finder.total_time_dicom_retrival / self.interface.dicom_finder.n_dicoms_queued
            avg_dequeue = self.interface.volumizer.total_dequeue_time / self.interface.volumizer.n_dicoms_dequeued
            avg_assembly = self.interface.volumizer.total_assembly_time / self.interface.volumizer.n_volumes_queued
            avg_roi = self.total_masker_roi_average_time / self.n_volumes_reduced
            avg_rda = 46 * (avg_retrival + avg_dequeue) + avg_assembly + avg_roi
        except ZeroDivisionError:
            return

        self.last_time = toc
        print("============== TIMING ===================")
        print("Display Volume/Scanner Volume: {}/{}".format(self.n_volumes_reduced, self.current_tr))
        print("Lag since collection: {}".format(lag))
        print ('')
        print("Time since start: {}".format(start_diff ))
        print("Time since last: {}".format(last_diff))
        print("Average since start: {}".format(start_diff/n))
        print("***************** STATS *****************")
        print("*** Average DCM Retrival: {}".format(avg_retrival))
        print("*** Average DCM Dequeue: {}".format(avg_dequeue))
        print("*** Average Volume Assembly: {}".format(avg_assembly))
        print("*** Average Mask Average: {}".format(avg_roi))
        print("*** Average Retrival/Dequeue/Assembly/Mask (46 dicoms): {}".format(avg_rda))
        print("========================================")











