Stanford CNI Real-time fMRI
===========================

Real-time interface for a GE MRI system.

Project Goal
------------
Our goal is to process functional MRI data in near real-time as brain measurements are made. Potential applications for this system include neuro-feedback experiments and real-time monitoring of data quality for any study.

History
-------

The project was started with a multi-threading skeleton by Gunnar Schaefer. Kiefer Katovich then built the current system on top of this and got the basic process working. Bob Dougherty refactored the dicom finder to use a more robust ftp-based method and incorporated nipy realignment tools to make a simple real-time subject motion tracker. Michael Waskom refactored the above work into a more modular, testable system.

Getting started
---------------

Interfacing with the scanner is accomplished through the `ScannerInterface` class. If the test ftp server is running, you can connect to it by doing:

```python
from rtfmri import ScannerInterface
scanner = ScannerInterface("localhost", 2121, base_dir="test_data")
scanner.start()
```

This will launch several threads in the background which will poll the scanner for new dicom files, extact the image data from them, and assemble the images into complete volumes (represented as `nibabel.Nifti1Image` objects). Internally, these are stored in a first-in-first-out Python `Queue`. The `ScannerInterface` object exposes a `get_volume()` method to pull volumes off that queue. (It is a wrapper around the `Queue.get()` method).

To use the real-time motion analyzer, you need to initalize a `Queue` object (part of the Python standard library) and pass it to the `MotionAnalyzer` class, which also takes a reference to the scanner interface:

```python
from rtfmri import MotionAnalyzer
from Queue import Queue

results = Queue()
rtmotion = MotionAnalyzer(scanner, results)
rtmotion.start()
```

The code will then run in the backgound and add a dictionary to the result queue for each volume with summary statistics about the motion on that frame. These can be retrived by calling `results.get()`.

These objects are thread-based, and you need to take an extra step so that they will listen to keyboard interrupts:

```python
from rtfmri import setup_exit_handler
setup_exit_handler(scanner, rtmotion)
```

You can also shut the threads down directly in your code:

```python
scanner.shutdown()
rtmotion.halt()
rtmotion.join()
```

Most users will be interested in the web-app bassed interface for viewing the real-time motion results. Currently, that can be activated by running the following commands in a terminal:

```
bokeh-server &
python interface_prototype.py -hostname localhost -port 2121 -base_dir test_data
```

The current implementation of this app is highly experimental and will change. Currently it just shows the results from the current run and will refresh the plots when a new run starts on the scanner.

Testing
-------

Testing is accomplished using `nose`. Most of the code needs the mock scanner ftp server running (see `rt_ftp_test_server.py`), but the test suite should be able to pass without a live server. Call `nosetests` from the root source directory to exercise the test suite.

Dependencies
------------

Main scanner interface:

- Python 2.7
- numpy
- nibabel
- pydicom

Real-time motion analyzer:

- nipy 0.4+

Motion analyzer web-app:

- seaborn
- bokeh 0.7+

License
-------
Copyright (c) 2012 Gunnar Schaefer
Copyright (c) 2012 Kiefer Katovich
Copyright (c) 2013-2015 Bob Dougherty
Copyright (c) 2014-2015 Michael Waskom

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.


