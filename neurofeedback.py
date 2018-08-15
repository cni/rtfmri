"""The script to start neurofeedback--it should even start the scan!"""
from __future__ import print_function

import re
import pdb
import sys
from Queue import Queue, Empty

from rtfmri.feedback import Neurofeedback

#================================================
                # USER PARAMS
#select the visualizer type:,1 = text, 2 = graph, 3 = thermometer
VISUALIZER_KIND = 1
TIMING_FILE     = 'test_data/10tr_rand_iti.1D'
MASK_NAME       = 'test_data/naccpos.nii.gz'
TIMING_FILE     = '10tr_rand_iti.1D'
TIMING_TEXT     = {0: '', 1: 'Nacc Up', 2: 'Nacc Down'}
MASK_NAME       = 'naccr.nii' #'ROI.finger_tapping.nii'
BUFFER_SIZE     = 8 # How many trs to use in moving average for thermometer
#================================================
#
# Choose file that specifies trial type per tr, where
# 0: 'Try to Relax', 1: 'Raise the bar!', 2: 'Lower the bar'



if __name__ == '__main__':

    ### parameters for the actual scan.
    host="cnimr"
    port=22
    username=""
    password=""
    base_dir="/export/home1/sdc_image_pool/images"


    nf = Neurofeedback(hostname=host,
                       port=port,
                       username=username,
                       password=password,
                       base_dir=base_dir, 
                       width = 1200, height = 1200, 
                       debug = True, 
                       feedback = True,
                       buffer_size=BUFFER_SIZE)



    # Choose the mask we'll need to use. when filter=True, we only get dicoms
    # that overlap with our ROI. Not necessary in practice on the scanner.
    nf.use_mask(MASK_NAME,
                center=None,
                radius=10,
                use_filter=True)

    timing_text = {0: '', 1: 'Raise the bar!', 2: 'Lower the bar'}
    nf.set_timing(TIMING_FILE, timing_text, TR=2)

    #if we use the newest and predict is true, we guess the next. Otherwise
    # we're working with old data.
    newest_series = nf.set_series(use_newest=True,
                                  predict=False)

    #nf.set_series(use_newest=False, series ='test_data/test_dicoms/20170831_1606/6_4_EPI29_2s_Excited1')

    visualizers = {1:'text', 2:'graph', 3:'thermometer'}
    nf.init_visualizer(visualizer=visualizers[VISUALIZER_KIND])

    #start the scan...
    nf.start_scan(dry_run=False)
