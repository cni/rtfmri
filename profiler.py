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
from rtfmri.client import  ScannerSFTPClient
from rtfmri.interface import ScannerInterface
from rtfmri.visualizers import *
from rtfmri.utilities import start_scan

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logging.basicConfig(format='%(asctime)s %(message)s')


def profile_series(hostname="cnimr", port=21, username="", password="",
                   base_dir="/export/home1/sdc_image_pool/images"):
    client = ScannerSFTPClient(hostname=hostname,
                               port=port,
                               username=username,
                               password=password,
                               base_dir=base_dir)
    series_q = Queue()
    series_finder = SeriesFinder(client, series_q, interval=1)
    series_finder.start()
    time.sleep(30)
    series_finder.halt()
    nq = series_finder.nqueued
    logger.info("Series queued: {}  at {} per second ".format(nq, nq/30.0))


def profile_dicoms(hostname="cnimr", port=21, username="", password="",
                   base_dir="/export/home1/sdc_image_pool/images"):
    client1 = ScannerSFTPClient(hostname=hostname,
                                port=port,
                                username=username,
                                password=password,
                                base_dir=base_dir)

    client2 = ScannerSFTPClient(hostname=host,
                                port=port,
                                username=username,
                                password=password,
                                base_dir=base_dir)

    series_q = Queue()
    series_finder = SeriesFinder(client1, series_q, interval=1)

    dicom_q = Queue()
    dicom_finder = DicomFinder(client2, series_q, dicom_q, interval=0)
    series_finder.start()
    dicom_finder.start()
    time.sleep(30)

    series_finder.halt()
    dicom_finder.halt()
    nq = dicom_finder.nqueued
    logger.info("Dicoms queued: {}  at {} per second ".format(nq, nq/30.0))

def profile_volumizers(hostname="cnimr", port=21, username="", password="",
                       base_dir="/export/home1/sdc_image_pool/images"):
    client1 = ScannerSFTPClient(hostname=hostname,
                                port=port,
                                username=username,
                                password=password,
                                base_dir=base_dir)

    client2 = ScannerSFTPClient(hostname=host,
                                port=port,
                                username=username,
                                password=password,
                                base_dir=base_dir)
    series_q = Queue()
    series_finder = SeriesFinder(client1, series_q, interval=1)

    dicom_q = Queue()
    dicom_finder = DicomFinder(client2, series_q, dicom_q, interval=0)

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




if __name__ == '__main__':
    ### parameters for the actual scan.
    host="cnimr"
    port=22,
    username=""
    password="testpass"
    base_dir="/export/home1/sdc_image_pool/images"

    host = "localhost"
    port = 2121
    base_dir = "test_data"

    interface = ScannerInterface(hostname=host,
                                 port=port,
                                 username=username,
                                 password=password,
                                 base_dir=base_dir)

    #masker = Masker('nick_test_subject/naccf_pos.nii')
    #start_scan()
    #Logging some basic info:
    logger.debug(interface.series_finder.client.list_dir(base_dir))
    logger.debug(interface.series_finder.client.latest_exam)
    latest_series = interface.series_finder.client.latest_series
    logger.debug(latest_series)
    logger.debug(interface.series_finder.client.series_files(latest_series))

    #profile_series(hostname=host, port=port, username=username,
    #               password=password, base_dir=base_dir)
    #profile_dicoms(hostname=host, port=port, username=username,
    #               password=password, base_dir=base_dir)
    profile_volumizers(hostname=host, port=port, username=username,
                   password=password, base_dir=base_dir)


