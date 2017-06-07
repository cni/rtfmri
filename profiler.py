from __future__ import print_function

import sys, os, time
import signal
import re
import pdb
import logging
from Queue import Queue, Empty

import nose.tools as nt
import numpy as np

from rtfmri.queuemanagers import SeriesFinder, DicomFinder, Volumizer
from rtfmri.masker import Masker
from rtfmri.client import  ScannerClient, ScannerSFTPClient
from rtfmri.clients import SFTPClient
from rtfmri.interface import ScannerInterface, ScannerFTPInterface
from rtfmri.visualizers import *
from rtfmri.utilities import start_scan

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logging.basicConfig(format='%(asctime)s %(message)s')

TEST = True

def time_it(tic, message):
    toc = time.time()
    logger.debug(message + " {}".format(toc-tic))
    return toc-tic


class Profiler(object):

    def __init__(self, hostname="cnimr", port=21, username="", password="",
                 base_dir="/export/home1/sdc_image_pool/images"):

        self.hostname = hostname
        self.port = port
        self.username = username,
        self.password = password,
        self.base_dir = base_dir
        self.client1 = ScannerSFTPClient(hostname=hostname, port=port,
                               username=username, password=password,
                               base_dir=base_dir)

        self.client2 = ScannerSFTPClient(hostname=hostname, port=port,
                               username=username, password=password,
                               base_dir=base_dir)

        self.ftpclient = ScannerClient(hostname=hostname, port=2121,
                               username=username, password=password,
                               base_dir=base_dir)

    # @profile
    def log_paths(self):
        logger.debug(self.client1.list_dir(base_dir))
        logger.debug(self.client1.latest_exam)
        latest_series = self.client1.latest_series
        logger.debug(latest_series)
        latest_files = self.client1.series_files(latest_series)

    # @profile
    def profile_series(self):

        series_q = Queue()
        series_finder = SeriesFinder(self.client1, series_q, interval=00000.1)
        series_finder.start()
        time.sleep(30)
        series_finder.halt()
        nq = series_finder.nqueued
        logger.info("Series queued: {}  at {} per second ".format(nq, nq/30.0))

    # @profile
    def profile_dicoms(self):

        series_q = Queue()
        series_finder = SeriesFinder(self.client1, series_q, interval=00000.1)

        dicom_q = Queue()
        dicom_finder = DicomFinder(self.client2, series_q, dicom_q, interval=0)
        series_finder.start()
        dicom_finder.start()
        time.sleep(30)

        series_finder.halt()
        dicom_finder.halt()
        nq = dicom_finder.nqueued
        logger.info("Dicoms queued: {}  at {} per second ".format(nq, nq/30.0))
    # @profile
    def profile_volumizers(self):
        series_q = Queue()
        series_finder = SeriesFinder(self.client1, series_q, interval=00000.1)

        dicom_q = Queue()
        dicom_finder = DicomFinder(self.client2, series_q, dicom_q, interval=0)

        volume_q = Queue()
        volumizer = Volumizer(dicom_q, volume_q, interval=0)

        series_finder.start()
        dicom_finder.start()
        volumizer.start()
        time.sleep(30)

        series_finder.halt()
        dicom_finder.halt()
        nq = volumizer.nqueued
        logger.info("Volumes queued: {}  at {} per second ".format(nq, nq/30.0))
        ng = volumizer.n_gotten
        logger.info("Dicoms dequeued: {}  at {} per second ".format(ng, ng/30.0))

    # @profile
    def time_ftp(self, hostname="cnimr", port=21, username="", password="",
                 base_dir="/export/home1/sdc_image_pool/images"):
        pdb.set_trace()

        sc = SFTPClient(hostname=self.hostname
                        port =self.port
                        base_dir=self.base_dir
                        password='test.pass',
                        private_key='test.key',
                        public_key='CSR.csr'
        )


        dicom_q = Queue()
        latest_series = self.client1.latest_series
        latest_files = self.client1.series_files(latest_series)
        latest_series = sc.latest_series

        n = min(len(latest_files), 1)
        ftpt, sftpt, sft = [], [], []
        for i in range(n):
            tic = time.time()

            dicom_q.put(self.ftpclient.retrieve_dicom(latest_files[i]))
            ftpt.append(time_it(tic, "Queued a dicom with ftp in: "))

            tic = time.time()
            dicom_q.put(self.client1.retrieve_dicom(latest_files[i]))
            sftpt.append(time_it(tic, "Queued a dicom with sftp in: "))

            tic = time.time()
            dicom_q.put(sc.retrieve_dicom(latest_files[i]))
            sft.append(time_it(tic, "Queued a dicom with sftp2 in: "))



        logger.debug("paramiko dicom queue time: {}".format(np.mean(sftpt)))
        logger.debug("pyftplib dicom queue time: {}".format(np.mean(ftpt)))
        logger.debug("pylibssh2 dicom queue time: {}".format(np.mean(sft)))
        logger.debug("pyftplib speedup over paramiko, average across {} trials: {}x".format(n, np.mean(sftpt)/np.mean(ftpt)))
        logger.debug("libssh2 speedup over paramiko, average across {} trials: {}x".format(n, np.mean(sftpt)/np.mean(sft)))
        logger.debug("libssh2 speedup average over pyftplib, average across {} trials: {}x".format(n, np.mean(ftpt)/np.mean(sft)))
        files = sc.list_dir(latest_series)


if __name__ == '__main__':

    ### parameters for the actual scan.
    host="cnimr"
    port=22
    username, password = "", ""
    base_dir="/export/home1/sdc_image_pool/images"

    if TEST:
        host = "localhost"
        port = 2124
        base_dir = "test_data"


    p = Profiler(hostname=host, port=port, username=username,
                 password=password, base_dir=base_dir)

    p.log_paths()
    p.time_ftp()
