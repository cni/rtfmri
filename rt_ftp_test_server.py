#!/usr/bin/env python

import sys
import time
import os
from glob import glob
from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer

def get_test_data(data_dir='test_data', url='http://cni.stanford.edu/download/rtfmri_test_data.tgz'):
    # Ensure data_dir is a full path
    data_dir = os.path.realpath(data_dir)
    if len(glob(os.path.join(data_dir,'*/*/*/*.dcm')))<100:
        import tarfile
        from urllib2 import urlopen, URLError, HTTPError
        from io import BytesIO
        print('"'+data_dir+'" does not exist or is empty. Fetching test data...')
        # Test data: http://cni.stanford.edu/download/rtfmri_test_data.tgz
        try:
            f = urlopen(url)
            print "downloading " + url
            tmpfile = BytesIO()
            while True:
                s = f.read(16384)
                if not s:
                    break
                tmpfile.write(s)
            f.close()
            tmpfile.seek(0)
            tfile = tarfile.open(fileobj=tmpfile, mode="r:gz")
            tfile.extractall(path=os.path.dirname(data_dir))
            tfile.close()
            tmpfile.close()
        #handle errors
        except HTTPError, e:
            print "HTTP Error:", e.code, url
        except URLError, e:
            print "URL Error:", e.reason, url
    else:
        print('"'+data_dir+'" seems to contain some usable data. No need to fetch.')
    print('updating timestamps on files so they appear new...')
    # touch the files so they appear new-ish (the dicom finder ignores really old files)
    series_dirs = sorted(glob(os.path.join(data_dir,'*/*/*')))
    t = time.time() - len(series_dirs)*600 - 60
    for series_dir in series_dirs:
        os.utime(series_dir, (t,t))
        for dcm in glob(os.path.join(series_dir,'*')):
            os.utime(dcm, (t,t))
        t += 600



if __name__ == '__main__':
    import argparse

    arg_parser = argparse.ArgumentParser()
    arg_parser.description  = ('FTP server for testing the eal-time fMRI tools. This will grab some test data\n'
                               '(if it doesn''t already exist locally) and run an FTP server that mimics the GE\n'
                               'scanner FTP server. The server will accept annonymous connections.\n\n')
    arg_parser.add_argument('-o', '--hostname', default='localhost', help='hostname or ip address (default: localhost)')
    arg_parser.add_argument('-p', '--port', type=int, default=2121, help='port for FTP server (default: 2121)')
    arg_parser.add_argument('-d', '--datadir', default='test_data', help='directory containing test data (default: ./test_data). Will be fetched if it doesn''t exist.')
    args = arg_parser.parse_args()

    # Ensure that we have the test data
    get_test_data(data_dir=args.datadir)

    authorizer = DummyAuthorizer()
    authorizer.add_anonymous(os.getcwd())
    handler = FTPHandler
    handler.authorizer = authorizer
    handler.banner = "VirtualScanner ready to serve.."

    address = (args.hostname, args.port)
    server = FTPServer(address, handler)
    server.serve_forever()



