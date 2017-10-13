"""The script to start neurofeedback--it should even start the scan!"""
from __future__ import print_function

import re, os
import pdb
import sys
from Queue import Queue, Empty

from appJar import gui

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

# handle button events
def press(button):
    if button == "Cancel":
        app.stop()
    elif button == "Set Params":
        usr = app.getEntry("Username")
        pwd = app.getEntry("Password")
        host = app.getEntry("Host", 'localhost')
        host = app.getEntry("Port", 2124)
        host = app.getEntry("Base Dir:")                

        print("User:", usr, "Pass:", pwd)

def handle_visualizer(button):
    if button != "Visualizer Type":
        return

    else:
        VISUALIZER_KIND = button

if __name__ == '__main__':
    if os.path.exists("/home"):
        host = "cnimr"
        port = "22"
        base_dir = "/export/home1/sdc_image_pool/images"
    else:
        host = "localhost"
        port = 2124
        base_dir ="new_test_data/scanner_data"


    params = {}

    app = gui("Neurofeedback", "1200x1000")
    app.setBg("orange")
    app.setFont(18)

    # add & configure widgets - widgets get a name, to help referencing them later
    app.addLabel("title", "Neurofeedback@CNI")
    app.setLabelBg("title", "blue")
    app.setLabelFg("title", "orange")

    app.addLabelEntry("Username")
    app.addLabelSecretEntry("Password")

    app.addLabelEntry("Host")
    app.setEntryDefault("Host", host)
    app.addLabelEntry("Port")
    app.setEntryDefault("Port", port)

    app.addLabelEntry("Base Dir")
    app.setEntryDefault("Base Dir", base_dir)

    app.addListBox("Visualizer_Type", ["thermometer", "graph", "text"])
    #link the buttons to the function called press
    app.addButtons(["Use_Params", "Cancel"], press)

    app.setFocus("Username")

    # start the GUI
    app.go()


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

    nf.set_series(use_newest=False, series ='new_test_data/scanner_data/p2173/e3765/s42148')

    visualizers = {1:'text', 2:'graph', 3:'thermometer'}
    nf.init_visualizer(visualizer=visualizers[VISUALIZER_KIND])

    timing_text = {0: 'Try to Relax', 1: 'Raise the bar!', 2: 'Lower the bar'}
    nf.set_timing(TIMING_FILE, timing_text, TR=2)

    #start the scan...
    nf.start_scan(dry_run=True)
