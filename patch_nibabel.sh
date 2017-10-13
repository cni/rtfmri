#!/bin/bash
### fix nibabel (comments out a line that wastes a lot of time)


cp patchcsa.nibabel venv/lib/python2.7/site-packages/nibabel-2.1.0-py2.7.egg/nibabel/nicom
cd venv/lib/python2.7/site-packages/nibabel-2.1.0-py2.7.egg/nibabel/nicom
patch csareader.py -i patchcsa.nibabel -o csareader2.py
mv csareader2.py csareader.py
cd ~/rtfmri
