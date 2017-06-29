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
VISUALIZER_KIND = 3
TIMING_FILE     = '5tr_rand_iti.1D'
MASK_NAME       = 'new_test_data/trial_mask.nii.gz'
#================================================
#
# Choose file that specifies trial type per tr, where
# 0: 'Try to Relax', 1: 'Raise the bar!', 2: 'Lower the bar'



if __name__ == '__main__':

    ### parameters for the actual scan.
    # host="cnimr"
    # port=22
    username=""
    password=""
    base_dir="/export/home1/sdc_image_pool/images"

    host = "localhost"
    port = 2124
    base_dir = "new_test_data/scanner_data"


    nf = Neurofeedback(hostname=host,
                       port=port,
                       username=username,
                       password=password,
                       base_dir=base_dir)


    # Choose the mask we'll need to use. when filter=True, we only get dicoms
    # that overlap with our ROI. Not necessary in practice on the scanner.
    nf.use_mask(MASK_NAME,
                center=None,
                radius=10,
                use_filter=False)

    #if we use the newest and predict is true, we guess the next. Otherwise
    # we're working with old data.
    newest_series = nf.set_series(use_newest=True,
                                  predict=False)

    visualizers = {1:'text', 2:'graph', 3:'thermometer'}
    nf.init_visualizer(visualizer=visualizers[VISUALIZER_KIND])

    timing_text = {0: 'Try to Relax', 1: 'Raise the bar!', 2: 'Lower the bar'}
    nf.set_timing(TIMING_FILE, timing_text, TR=2)

    #start the scan...
    nf.start_scan(dry_run=True)
