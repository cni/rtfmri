#!/usr/bin/env python
#
# @author:  Gunnar Schaefer

import string
import os
import sys
import glob
import time
import Queue as queue
import signal
import argparse
import datetime
import threading
import thread
import random
import re
from socket import *


import numpy as np
import dicom
import nibabel as nib
from nibabel.nicom import dicomreaders as dread
from nibabel.nicom import dicomwrappers as dwrap



SLICES_PER_VOLUME = 32
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
		self.server_inum = 0
		self.dicom_nums = []
		self.dicom_search_start = 0
		print 'initialized'
		
		
	def halt(self):
		self.alive = False
		
		
	def get_initial_filelist(self):
		time.sleep(0.1)
		files = os.listdir(self.series_path)
		print files
		if files:
			for file in files:
				spl = file.split('.')
				current_inum = int(spl[0][1:])
				if current_inum > self.server_inum:
					self.server_inum = current_inum
				self.dicom_nums.append(int(spl[2]))
			gaps = [x for x in range(max(self.dicom_nums)) if x not in self.dicom_nums]
			gaps.remove(0)
			if gaps:
				self.dicom_search_start = min(gaps)
			else:
				self.dicom_search_start = max(self.dicom_nums)+1
				
				
			return [os.path.join(self.series_path, fid) for fid in files]
		else:
			return False
    
		
		
	def run(self):
		take_a_break = False
		failures = 0
		
		while self.alive:
			#print sorted(self.dicom_nums)
			#print self.server_inum
			before_check = datetime.datetime.now()
			#print before_check
			
			if self.server_inum == 0:
				filenames = self.get_initial_filelist()
				for fid in filenames:
					dcm = dicom.read_file(fid)
					self.dicom_queue.put(dcm)
			
			elif take_a_break:
				
				#print '%s: (%d) [%f]' % (os.path.basename(self.series_path), self.server_inum, self.interval)
				time.sleep(self.interval)
				take_a_break = False
			
			else:
				loop_success = False
				first_failure = False
				
				ind_tries = [x for x in range(self.dicom_search_start, max(self.dicom_nums)+10) if x not in self.dicom_nums]
				#print ind_tries
				
				for d in ind_tries:
					try:
						current_filename = 'i'+str(self.server_inum+1)+'.MRDC.'+str(d)
						#print current_filename
						dcm = dicom.read_file(current_filename)
						if not len(dcm.PixelData) == 2 * dcm.Rows * dcm.Columns:
							print 'corruption error'
							print 'pixeldata: '+str(len(dcm.PixelData))
							print 'expected: '+str(2*dcm.Rows*dcm.Columns)
							raise Exception
					
					except:
						#print current_filename+', failed attempt'
						if not first_failure:
							self.dicom_search_start = d
							first_failure = True

					else:
						#print current_filename+', successful attempt'+'\n'
						self.dicom_queue.put(dcm)
						self.dicom_nums.append(d)
						self.server_inum += 1
						loop_success = True
						failures = 0
				
				if not loop_success:
					#print 'failure on: i'+str(self.server_inum+1)+'\n'
					refresher = glob.glob('i'+str(self.server_inum+1)+'*')
					#failures = failures+1
					take_a_break = True

        		
		
	
	
		


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
        global SLICES_PER_VOLUME
        global AFFINE
        volume_shape = None
        dicoms = {}
        complete_volumes = 0
        
        base_time = time.time()
        while self.alive:
            try:
                dcm = self.dicom_q.get(timeout=1)
            except queue.Empty:
                pass
            else:
                # TODO: convert incoming dicoms to 3D volumes
                dicom = dwrap.wrapper_from_data(dcm)
                if AFFINE is None:
                   AFFINE = dicom.get_affine()
                if not volume_shape:
					volume_shape = (SLICES_PER_VOLUME,dicom.image_shape[0],dicom.image_shape[1])
                dicoms[dicom.instance_number] = dicom
                #print 'put in dicom:' + str(dicom.instance_number)
                check_start = (complete_volumes*SLICES_PER_VOLUME)+1
                check_end = check_start+SLICES_PER_VOLUME
                if all([(ind in dicoms) for ind in range(check_start,check_end)]):
                    volume = np.zeros(volume_shape)
                    for i,ind in enumerate(range(check_start,check_end)):
                        volume[i] = dicoms[ind].get_data()
                    self.volume_q.put(volume)
                    complete_volumes += 1
                    print 'VOLUME COMPLETE!'
                    volimg = nib.Nifti1Image(volume, AFFINE)
                    nib.save(volimg,'/home/cni/Desktop/kiefer/volume.nii')
                    print time.time()-base_time
                    base_time = time.time()
        
                    


class Analyzer(threading.Thread):

    """Analyzer gets 3D volumes out of the volume queue and computes real-time statistics on them."""

    def __init__(self, volume_q, average_q, mask_data, mask_shape):
        super(Analyzer, self).__init__()
        self.volume_q = volume_q
        self.average_q = average_q
        self.alive = True
        self.whole_brain = None
        self.brain_list = []
        self.mask_data = mask_data
        self.mask_shape = mask_shape
        self.boolmask = np.zeros(mask_shape, np.bool)
        self.boolmask[:,:,:] = mask_data[:,:,:]

    def halt(self):
    	# temp saver:
    	global AFFINE
    	print np.shape(self.whole_brain)
    	print AFFINE
    	test_image = nib.Nifti1Image(self.whole_brain, AFFINE)
    	os.chdir('/home/cni/Desktop/kiefer/')
    	nib.save(test_image, 'test_brain.nii')
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
                if not vol_shape:
                    vol_shape = np.shape(volume)
                if self.whole_brain is None:
                    self.whole_brain = np.zeros((vol_shape[0],vol_shape[1],vol_shape[2],100))
                    self.whole_brain[:,:,:,0] = volume
                    next_vol = 1
                else:
              
                	#self.whole_brain  = np.zeros((vol_shape[0],vol_shape[1],vol_shape[2],next_vol+1))
                    #self.whole_brain.resize(vol_shape[0],vol_shape[1],vol_shape[2],next_vol+1)
                    self.whole_brain[:,:,:,next_vol] = volume
                    #self.whole_brain = np.concatenate((self.whole_brain, volume), axis=0)
                    next_vol += 1
                print np.shape(self.whole_brain)

				flat_volume_len = len(volume.flatten())
             	current_average = volume[self.boolmask].sum()/flat_volume_len
             	self.average_q.put(current_volume)

        #image_save = nib.nifti1.Nifti1Image(self.whole_brain, AFFINE)
		#nib.nifti1.save(image_save,')
                



class NeurofeedbackSocket(threading.Thread):

	def __init__(self, average_q, parameter_file):
        super(Analyzer, self).__init__()
        self.average_q = average_q
        self.alive = True
        
        self.act = [].insert(0,0)
        self.count = 0
        self.trial = 0
        self.message, self.colors, self.onsets = [], [], []
        self.setup_parameters(parameter_file)
        
        self.setup_socket()
        
  	def setup_parameters(self, parameter_file):
  		self.params = open(paramfileName).read().split('\n')
		self.tmp = params[0].split(' ')
		self.nTR = int(tmp[1])
		self.tmp = params[1].split(' ')
		self.waitTime = int(tmp[0])
		self.nEvent = int(params[3])
	
		for i in range(nEvent):
			self.cur = self.params[4 + i].split(' ')
			self.onsets.insert(i + 1, int(self.cur[0]))
			self.colors.insert(i, ";" + self.cur[1] + ";" + self.cur[2] + ";" + self.cur[3] +";")
			self.tmp = self.cur[4]
			self.message.insert(i, self.tmp[2:-1])
	
		self.onsets.insert(i + 1, self.onsets[i] + 1)
		
	
	def setup_socket(self):
		self.serverHost = 'localhost'
		self.serverPort = 8888
		self.sock = socket(AF_INET, SOCK_STREAM)
		self.sock.bind((self.serverHost, self.serverPort))
		self.sock.listen(1)
		print "waiting for display connection..."
		self.conn, self.addr = self.sock.accept()
		print "got it!"
	
        
    def halt(self):
    	self.alive = False
    	self.conn.close()
    	self.sock.close()
    	
    def run(self):
    	self.conn.send("n " + str(self.nTR - self.waitTime + 1) + "\n")
    	while self.alive:
    		try:
    			average = self.average_q.get(timeout=3)
    		except queue.Empty:
    			self.conn.close()
    			self.sock.close()
			else:
				if (self.count >= self.waitTime):
					self.conn.send("m " + self.message[self.trial] + "\n")
					self.conn.send("c " + self.colors[self.trial] + "\n")
					self.conn.send("d " + str(self.onsets[self.trial + 1] - self.onsets[self.trial]) + "\n")
					self.trial = self.trial + 1
					
				curAct = "a "+str(average) +"\n"
				dummyglobal = "g 0.01\n"
				print 'act: ', curAct
				self.conn.send(curAct)
				self.conn.send(dummyglobal)
				
			self.act.insert(count+1,0)
			self.count = self.count+1
			
			


class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        super(ArgumentParser, self).__init__(formatter_class=argparse.RawTextHelpFormatter)
        self.description  = 'Facilitate real-time fMRI.\n\n'
        self.description += 'Use NFS mount options "noac,lookupcache=none" to avoid client-side caching.'
        self.add_argument('dicom_path', help='path to dicom root directory')
        self.add_argument('-i', '--interval', type=float, default=1.0, help='interval between checking for new files')


def load_mask_nifti(nifti):
	image = nib.load(nifti)
	shape = image.get_shape()
	idata = image.get_data()
	affine = image.get_affine()
	return [idata,affine,shape]



if __name__ == '__main__':
	#args = ArgumentParser().parse_args()

	dicom_q = queue.Queue()
	volume_q = queue.Queue()
	average_q = queue.Queue()

	#exam_path = max(glob.glob(os.path.join(args.dicom_path, 'p*/e*')), key=lambda d: os.stat(d).st_mtime)

	#dicom_finder = DicomFinder(exam_path, dicom_q, datetime.timedelta(seconds=args.interval))
    
	utils = Utilities()
	
	mask_name = raw_input('name of mask file: ')
	import glob
	mask_filename = glob.glob(mask_name)[0]
	if mask_filename:
		[maskdata,maskaffine,maskshape] = load_mask_nifti(mask_filename)
		
		
	param_name = raw_input('name of parameter file: ')
	parameter_file = glob.glob(param_name)[0]


	[scan_top_dir,all_dirs] = utils.calibration(False)
	print all_dirs
	print scan_top_dir

	go = raw_input('Hit it when you''re ready:')

	enter_dir = utils.enternewdirectory(scan_top_dir,all_dirs,200.0)

	print enter_dir

	dicom_finder = IncrementalDicomFinder(enter_dir, dicom_q, 0.25)

	volumizer = Volumizer(dicom_q, volume_q)

	analyzer = Analyzer(volume_q, average_q, maskdata, maskshape)
	
	neurosocket = NeurofeedbackSocket(average_q, parameter_file)

	def term_handler(signum, stack):
		print 'Receieved SIGTERM - shutting down...'
		dicom_finder.halt()
		volumizer.halt()
		analyzer.halt()
		neurosocket.halt()
		print 'Asked all threads to terminate'
		dicom_finder.join()
		volumizer.join()
		analyzer.join()
		neurosocket.join()
		print 'Process complete'
		sys.exit(0)

	signal.signal(signal.SIGINT, term_handler)
	signal.signal(signal.SIGTERM, term_handler)

	dicom_finder.start()
	volumizer.start()
	analyzer.start()
	neurosocket.start()

	while True: time.sleep(60)  # stick around to receive and process signals
	
	
