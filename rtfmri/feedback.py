"""The script to start neurofeedback--it should even start the scan!"""
from __future__ import print_function

import re
import pdb
import sys, socket
from Queue import Queue, Empty

import numpy as np

from .analyzers import MotionAnalyzer
from .masker import Masker, DicomFilter
from .interface import ScannerInterface
from .visualizers import *
from .utilities import start_scan


class Neurofeedback(object):

    def __init__(self, hostname='cnimr', port=22, username='', password='',
                 base_dir="/export/home1/sdc_image_pool/images",
                 use_analyzer=False):
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

    def use_mask(self, mask_path, center=None, radius=8, use_filter=False):

        # Create the masking object and DicomFilter
        mask_center = None # this is the z coord of our roi (IS)
                           # if z is none, we get center of mass
        masker = Masker(mask_path, center=mask_center, radius=radius)
        #masker.add_orthogonal('emily_analysis/wm.nii.gz')
        #masker.add_orthogonal('emily_analysis/csf.nii.gz')
        if use_filter:
            dcm_filter = DicomFilter(masker)
            interface.set_dicom_filter(dcm_filter)
        self.masker=masker

    def set_series(self, use_newest=True, predict=True, series=None):
        if use_newest:
            self.series = self.interface.use_newest_exam_series(predict = predict)
        else:
            self.series = self.interface.use_series(series)

        return self.series

    def init_visualizer(self, visualizer='text'):
        self.visualizer_kind = visualizer

        interface = self.analyzer if self.use_analyzer else self.interface

        if visualizer=='text':
            v = TextVisualizer(interface, self.masker)

        if visualizer=='graph':
            v = GraphVisualizer(interface, self.masker)

        if visualizer=='thermometer':
            v = Thermometer(interface, self.masker)
            v.start_display()

        self.visualizer = v

    def set_timing(self, timing_file, timing_texts, TR=2):
        vec = np.genfromtxt(timing_file)
        self.visualizer.set_regressors(vec = vec, text=timing_texts, TR=TR)


    def start_scan(self, dry_run=False):
        if self.visualizer is None:
            print("No visualizer set, aborting scan")
            return


        client = self.interface.dicom_finder.client

        #First start the scan
        if not dry_run:
            start_scan()
        self.visualizer.start_timer()

        #pdb.set_trace()
        #Now wait for the session we want to appear
        if not client.path_exists(self.series):
            print("Waiting for dicoms to appear...")
        while not client.path_exists(self.series):
            time.sleep(.01)
        print("Session found, beginning feedback...")

        #start the interface
        self.visualizer.start_interface()

        #start the visualizer
        self.visualizer.run()
