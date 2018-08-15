#!/bin/csh
# script to generate rois from anat in current directory.
#export PATH=$PATH:~/abin

set MASKPATH='/home/cniuser/rt/rtfmri/rois'

3dcalc -overwrite -a $MASKPATH/'finger_tapping_ns+tlrc' -expr 'ispositive(a)' -prefix $MASKPATH/finger_tapping+tlrc
3dcalc -overwrite -a $MASKPATH/'nacc8mm+tlrc' -expr 'ispositive(a)' -prefix $MASKPATH/naccpos+tlrc

set MASKS=(finger_tapping naccpos )

3dcopy anat.nii.gz anat+orig
3drefit -space orig anat+orig

foreach mask ($MASKS)
    echo warping $mask ...
    echo @fast_roi -twopass -base $MASKPATH/TT_N27_r2+tlrc -roi_grid $MASKPATH/testepi+orig -anat anat+orig -drawn_roi $MASKPATH/${mask}+tlrc -prefix ${mask}
    time @fast_roi -twopass -base $MASKPATH/TT_N27_r2+tlrc -roi_grid $MASKPATH/testepi+orig -anat anat+orig -drawn_roi $MASKPATH/${mask}+tlrc -prefix ${mask}
    3dAFNItoNIFTI ROI.${mask}+orig
    3drefit -space orig ROI.${mask}.nii.gz 
end
