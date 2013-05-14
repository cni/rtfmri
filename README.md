rtfmri
======
Real-time fMRI for a GE MRI system.

Project Goal
------------
Our goal is to process functional MRI data in near real-time, as the brain measurements are made. There are several potential applications for such a system, including neuro-feedback experiments, and well as real-time monitoring of data quality for any study.

The system tries to pull dicoms from the scanner as fast as possible, ideally just as they arrive from the recon engine. So, it bypasses the dicom server and accesses the dicom filestore directly, finding the latest folder (which corresponds to the currently running scan) and pulling any new images from that folder. A separate thread assembles the images into a volume as they arrive. Each time a complete volume is made, it is handed off to yet another thread for processing.

History
-------
The project was started with a multi-threading skeleton by Gunnar Schaefer. Kiefer Katovich then built the current system on top of this and got the basic process working. Bob Dougherty trimmed the code down and incorporated nipy realignment tools to make a simple real-time subject motion tracker.

License
-------
Copyright (c) 2012 Gunnar Schaefer
Copyright (c) 2012 Kiefer Katovich
Copyright (c) 2013 Bob Dougherty

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.


