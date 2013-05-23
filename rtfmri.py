#!/usr/bin/env python
#
# @author:  Kiefer Katovich, Robert Dougherty, Gunnar Schaefer

import Queue as queue
import signal
import argparse
import sys
import time
import threading
from socket import *
import nibabel as nib
import numpy as np

import rtutil
import rtclient


class FmriAnalyzer(threading.Thread):

    """FmriAnalyzer gets 3D volumes out of the volume queue and computes real-time statistics on them."""

    def __init__(self, volume_q, average_q, mask_data, mask_shape):
        super(FmriAnalyzer, self).__init__()
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
        super(NeurofeedbackSocket, self).__init__()
        self.average_q = average_q
        self.alive = True

        self.act = [].insert(0,0)
        self.count = 0
        self.trial = 0
        self.message, self.colors, self.onsets = [], [], []
        self.setup_parameters(parameter_file)

        self.setup_socket()

    def setup_parameters(self, parameter_file):
        self.params = open(parameter_file).read().split('\n')
        self.tmp = self.params[0].split(' ')
        self.nTR = int(self.tmp[1])
        self.tmp = self.params[1].split(' ')
        self.waitTime = int(self.tmp[0])
        self.nEvent = int(self.params[3])

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
        self.add_argument('-m', '--maskfile', default=None, help='mask file to use for analysis (will prompt if not provided)')
        self.add_argument('-r', '--paramfile', default=None, help='parameter file to use for analysis (prompt if not provided)')


def load_mask_nifti(nifti):
    image = nib.load(nifti)
    shape = image.get_shape()
    idata = image.get_data()
    affine = image.get_affine()
    return [idata,affine,shape]


import glob

if __name__ == '__main__':
    args = ArgumentParser().parse_args()

    dicom_q = queue.Queue()
    volume_q = queue.Queue()
    average_q = queue.Queue()
    result_d = {'exam':0, 'series':0, 'patient_id':'', 'series_description':'', 'tr':0}

    if args.maskfile:
        mask_filename = args.maskfile
    else:
        mask_name = raw_input('name of mask file: ')
        mask_filename = glob.glob(mask_name)[0]
    if mask_filename:
        [maskdata,maskaffine,maskshape] = load_mask_nifti(mask_filename)

    if args.paramfile:
        parameter_file = args.paramfile
    else:
        param_name = raw_input('name of parameter file: ')
        parameter_file = glob.glob(param_name)[0]

    scanner = rtclient.RTClient(hostname=args.hostname, username=args.username, password=args.password,
                                image_dir=args.dicomdir)

    scanner.connect()

    exam_dir = scanner.exam_dir()
    exam_info = scanner.exam_info(exam_dir)
    print('')
    for k,v in exam_info.iteritems():
        print('%20s: %s' % (k,v))
    print('')
    go = raw_input('Hit it when you''re ready:')

    series_dir = scanner.series_dir(exam_dir)
    print series_dir
    if not series_dir:
        assert(false)

    dicom_finder = rtutil.IncrementalDicomFinder(scanner, series_dir, dicom_q, result_d)
    volumizer = rtutil.Volumizer(dicom_q, volume_q, result_d)
    analyzer = FmriAnalyzer(volume_q, average_q, maskdata, maskshape)
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


