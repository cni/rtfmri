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


import numpy as np
import dicom
import nibabel as nib
from nibabel.nicom import dicomreaders as dread
from nibabel.nicom import dicomwrappers as dwrap



SLICES_PER_VOLUME = 46
AFFINE = None
CNI_TOP_DIR = '/net/cnimr/export/home1/sdc_image_pool/images/'



class Utilities(object):


	def __init__(self, dicom_prefix='i*'):
		self.server_dir = CNI_TOP_DIR
		self.slices = SLICES_PER_VOLUME
		
			
	def findrecentdir(self):
		all_dirs = [dir for dir in os.listdir('.') if os.path.isdir(dir)]
		if all_dirs:
			last_mod = max((os.path.getmtime(dir),dir) for dir in all_dirs)[1]
			return last_mod
		else: 
			return False
			
			
	def erase_realtimedir(self):
		if os.path.exists(self.realtime_dir):
			shutil.rmtree(self.realtime_dir)
		os.mkdir(self.realtime_dir)
		
		
	def erase_waitingroom(self):
		if os.path.exists(self.waitingroom):
			shutil.rmtree(self.waitingroom)
		os.mkdir(self.waitingroom)
		

	def navigatedown(self):
		os.chdir(self.server_dir)
		current_dir = self.server_dir
		bottom = False
		while not bottom:
			sub_dir = self.findrecentdir()
			if not sub_dir:
				bottom = True
			else:
				os.chdir(sub_dir)
				current_dir = sub_dir
		return os.getcwd()


	def plaincopy(self,directory='.',exclude=[],destination=''):
		if directory:
			os.chdir(directory)
		print 'Copying files from: '+directory
		all_files = os.listdir('.')
		for dicom_file in all_files:
			if not dicom_file in exclude:
				if not os.path.exists(self.realtime_dir+destination):
					curdir = os.getcwd()
					os.chdir(self.realtime_dir)
					os.mkdir(destination)
					os.chdir(curdir)
				shutil.copy(dicom_file,self.realtime_dir+destination)
		if directory or not directory == '.':
			os.chdir('../')


	def calibration(self,copyflag):
		most_recent_dir = self.navigatedown()
		os.chdir('../')
		if copyflag:
			plaincopy(directory=most_recent_dir,exclude=[],destination='calibration')
		all_dirs = [dir for dir in os.listdir('.') if os.path.isdir(dir)]
		return [os.getcwd(),all_dirs]
		

	def enternewdirectory(self,rootdir,exceptions,waittime):
		os.chdir(rootdir)
		baseT = time.time()
		while (time.time() - baseT) < waittime:
			recent_dir = self.findrecentdir()
			if not recent_dir in exceptions:
				print recent_dir
				os.chdir(recent_dir)
				return os.getcwd()
		return False
		
	
	def dicom_header_reader(dicom_file):
		start_time = time.time()
		file_data = dicom.read_file(dicom_file)
		print file_data.AcquisitionNumber
		end_time = time.time()
		print end_time-start_time








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
                
           
           
                
class IncrementalDicomFinder(threading.Thread):

	
	def __init__(self, series_path, dicom_queue, interval):
		super(IncrementalDicomFinder, self).__init__()
		self.series_path = series_path
		self.dicom_queue = dicom_queue
		self.interval = interval
		self.alive = True
		self.slice_bin = 0
		self.slice_num = 0
		self.filenames = []
		self.dicom_str_template = ''
		
		
	def halt(self):
		self.alive = False
		
		
	def get_initial_filelist(self):
		files = os.listdir(self.series_path)
		print files
		if files:
			for file in files:
				spl = file.split('.')
				dicom_num = int(spl[-2])
				bin = int(spl[-3])
				self.template = '.'.join(spl[:-3])
				if bin >= self.slice_bin:
				    if bin > self.slice_bin:
				        self.slice_bin = bin
				        self.slice_num = 0
				    if dicom_num > self.slice_num:
				        self.slice_num = dicom_num
			return [os.path.join(self.series_path, fid) for fid in files]
		else:
			return False
			
			
				     
	def increment_dicom(self):
		if self.slice_num == 999:
			self.slice_num = 1
			self.slice_bin += 1
		else:
			self.slice_num += 1
	
		nextfile = os.path.join(self.series_path, '.'.join(self.template, str(self.series_bin), str(self.slice_num), 'dcm'))
		self.filenames.insert(0, nextfile)
    
		
		
	def run(self):
		take_a_break = False
		while self.alive:
			before_check = datetime.datetime.now()
			if self.slice_bin == 0:
				self.filenames = self.get_initial_filelist()
			elif take_a_break:
				sleeptime = (before_check + self.interval - datetime.datetime.now()).total_seconds())
            	print '%s: %d (%d) [%f]' % (os.path.basename(self.series_path), self.slice_bin, self.slice_num, sleeptime)
				if sleeptime > 0:
		            time.sleep(sleeptime)
			else:
				if not self.filenames:
					self.increment_dicom()
				current_filename = self.filenames.pop()
				try:
	                dcm = dicom.read_file(current_filename)
	                if not len(dcm.PixelData) == 2 * dcm.Rows * dcm.Columns:
	                    raise Exception
	            except:
	                self.filenames.insert(0, current_filename)  # try this one again next time
	                take_a_break = True
	            else:
	                self.dicom_q.put(dcm)
	                self.increment_dicom()
	                take_a_break = False

        		
		
	
	
		


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
        volume_shape = None
        dicoms = {}
        complete_volumes = 0
        while self.alive:
            try:
                dcm = self.dicom_q.get(timeout=1)
            except queue.Empty:
                pass
            else:
                # TODO: convert incoming dicoms to 3D volumes
                dicom = dwrap.wrapper_from_data(dcm)
                if not AFFINE:
                   AFFINE = dicom.get_affine()
                if not volume_size:
                    volume_shape = (SLICES_PER_VOLUME,dicom.image_shape[1],
                                    dicom.image_shape[2])
                dicoms[dicom.instance_number] = dicom
                check_start = complete_volumes*SLICES_PER_VOLUME
                check_end = check_start+SLICES_PER_VOLUME
                if all([(ind in dicoms) for ind in range(check_start,check_end)]):
                    volume = np.zeros(volume_shape)
                    for i in range(check_start,check_end):
                        volume[i] = dicoms[i].get_data()
                    self.volume_q.put(volume)
                    complete_volumes += 1
                    


class Analyzer(threading.Thread):

    """Analyzer gets 3D volumes out of the volume queue and computes real-time statistics on them."""

    def __init__(self, volume_q):
        super(Analyzer, self).__init__()
        self.volume_q = volume_q
        self.alive = True
        self.whole_brain = None

    def halt(self):
        self.alive = False

    def run(self):
        vol_shape = None
        next_vol = 0
        while self.alive:
            try:
                volume = self.volume_q.get(timeout=1)
            except queue.Empty:
                pass
            else:
                # TODO: append to 4D volume
                if not brain_shape:
                    vol_shape = np.shape(volume)
                if not self.whole_brain:
                    self.whole_brain = np.zeros(1,vol_shape[0],vol_shape[1],
                                                vol_shape[2])
                    self.whole_brain[0] = volume
                    next_vol = 1
                else:
                    self.whole_brain.resize((next_vol+1,vol_shape[0],vol_shape[1],
                                             vol_shape[2]))
                    self.whole_brain[next_vol] = volume
                    next_vol += 1
                


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

    #exam_path = max(glob.glob(os.path.join(args.dicom_path, 'p*/e*')), key=lambda d: os.stat(d).st_mtime)

    #dicom_finder = DicomFinder(exam_path, dicom_q, datetime.timedelta(seconds=args.interval))
    
	utils = Utilities()
	
	[scan_top_dir,all_dirs] = utils.calibration(False)
	print all_dirs
	print scan_top_dir
	
	go = raw_input('Hit it when ya ready:')
	
	enter_dir = utils.enternewdirectory(scan_top_dir,all_dirs,200.0)
	
	print enter_dir
    
    dicom_finder = IncrementalDicomFinder(enter_dir, dicom_q, datetime.timedelta(seconds=args.interval))
    
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
