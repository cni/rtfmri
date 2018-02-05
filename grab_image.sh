#!/bin/bash

source ~/rt/rtfmri/venv/bin/activate
~/rt/rtfmri/grab_image_from_scanner.py -u [username] -p [password] --host='cnimr' --port=22 -o 'anat.nii.gz'

