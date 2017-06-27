"""
A test sftp server. Will get test data if we don't have it.
The server will create a new thread to handle each new socket.
Implementation of the server modified from
https://gist.github.com/Girgitt/2df036f9e26dba1baaddf4c5845a20a2
"""
import os
import time
import socket
import optparse
import sys
import textwrap
import threading
from glob import glob

import paramiko
from sftpserver.stub_sftp import StubServer, StubSFTPServer

HOST, PORT = 'localhost', 2124
BACKLOG = 10

# TODO add new test data that includes ROI masks and more recent dicoms
# with newer naming convventions
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




class ConnHandlerThd(threading.Thread):
    def __init__(self, conn, keyfile):
        threading.Thread.__init__(self)
        self._conn = conn
        self._keyfile = keyfile

    def run(self):
        host_key = paramiko.RSAKey.from_private_key_file(self._keyfile)
        transport = paramiko.Transport(self._conn)
        transport.add_server_key(host_key)
        transport.set_subsystem_handler(
            'sftp', paramiko.SFTPServer, StubSFTPServer)

        server = StubServer()
        transport.start_server(server=server)

        channel = transport.accept()
        while transport.is_active():
            time.sleep(.00001)


def start_server(host, port, keyfile, level):
    paramiko_level = getattr(paramiko.common, level)
    paramiko.common.logging.basicConfig(level=paramiko_level)

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
    server_socket.bind((host, port))
    server_socket.listen(BACKLOG)
    print("Listening for new connections...")
    while True:
        conn, addr = server_socket.accept()

        srv_thd = ConnHandlerThd(conn, keyfile)
        srv_thd.setDaemon(True)
        srv_thd.start()


def main():
    usage = """\
    usage: sftpserver [options]
    -k/--keyfile should be specified
    """
    parser = optparse.OptionParser(usage=textwrap.dedent(usage))
    parser.add_option(
        '--host', dest='host', default=HOST,
        help='listen on HOST [default: %default]')
    parser.add_option(
        '-p', '--port', dest='port', type='int', default=PORT,
        help='listen on PORT [default: %default]'
        )
    parser.add_option(
        '-l', '--level', dest='level', default='INFO',
        help='Debug level: WARNING, INFO, DEBUG [default: %default]'
        )
    parser.add_option(
        '-k', '--keyfile', dest='keyfile', metavar='FILE',
        help='Path to private key, for example /tmp/test_rsa.key',
        default='test.key'
        )

    options, args = parser.parse_args()

    if options.keyfile is None:
        parser.print_help()
        sys.exit(-1)

    start_server(options.host, options.port, options.keyfile, options.level)

if __name__ == '__main__':
    get_test_data()
    main()
