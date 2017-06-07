#!/bin/bash
#

#cd ~/rt/rtfmri
#git pull origin nick


#fix pydicom
pip uninstall dicom
pip uninstall pydicom

git clone https://github.com/pydicom/pydicom.git
cd pydicom
python setup.py install
cd ..
rm -rf pydicom


#fix dcmstack
pip uninstall dcmstack
git clone https://github.com/moloney/dcmstack.git
cd dcmstack
#python setup.py sdist
python setup.py install
cd ..
#pip install dcmstack/dist/dcmstack-0.7.0.dev0.tar.gz
rm -rf dcmstack


### fix nibabel (comments out a line that wastes a lot of time)
cp patchcsa.nibabel venv/lib/python2.7/site-packages/nibabel/nicom
cd venv/lib/python2.7/site-packages/nibabel/nicom
patch csareader.py -i patchcsa.nibabel -o csareader2.py
mv csareader2.py csareader.py
cd ~/rt/rtfmri





3dfractionize -overwrite -template 14937_5_1.nii.gz -input nacc8mm.nii -warp anat_at.nii -preserve -clip 0.1 -prefix naccf+orig

3dcalc -a naccf.nii -expr 'ispositive(a)' -prefix naccf_pos.nii

3dmaskave -overwrite -mask naccf+orig -quiet -mrange 0.1 2 \
              14937_5_1.nii.gz > "nacc_raw.tc"


#scanner scratch

