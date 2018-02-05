# Instructions for running neurofeedback. 

Before running neurofeedback, we must first create subject specific ROIs on the same grid as the EPI you will collect for feedback. ROI files should be binary 0/1 masks. 

To do this, you can either:
* Draw rois manually on an EPI 
* Use a MNI/TLRC space ROI, collect a T1/EPI, calculate relevant transform, apply to the roi

The `grab_image.sh` script illustrates the commands needed to gather an or epi. 

If you are using a TLRC space ROI and have collected and anatomical, the script `rois/make_rois.sh` will take a file `anat.nii.gz` and use AFNI's fastroi command to warp the roi to original space and save this as a nifti file in the present directory. (AFNI is currently installed on voxel2). 

Given a native space ROI nifti, edit the neurofeedback.py script to point to the ROI of your choice. 

# The neurofeedback script. 

At present, the main mechanism for neurofeedback is a Theremometer visualizer. 

```
BUFFER_SIZE     = 8 # How many trs to use in moving average for thermometer
```
As currently configured, thermometer keeps last 8 buffers. 

Timing is specified by using a text file consisting of one integer per line, where each integer corresponds to text to be displayed on screen as specified in the timing text dictionary. 

```
TIMING_FILE     = '10tr_rand_iti.1D'
TIMING_TEXT     = {0: '', 1: 'Nacc Up', 2: 'Nacc Down'}
```

At present, when timing is 0, we display a fixation cross. For all other values, we display
the text above the thermometer. 