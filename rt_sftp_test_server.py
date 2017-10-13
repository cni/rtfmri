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

def get_test_key():
    # make sure we have the key:
    # the key is rsa from password 'test_pass'
    test_key = '-----BEGIN RSA PRIVATE KEY-----\nMIIEvAIBADANBgkqhkiG9w0BAQEFAASCBKYwggSiAgEAAoIBAQCZtHe5UahxLAkb\na7IXFnkvfpejJ+UqHGT23x6uPpLmKb1Yxjw3KmPQsd/QUjmrDr/hlN9oq5U6CANV\nIRipz8U+pdMfYB8ZI8q/kfUbCuFVBDdtdWBv7s/vabQT5g932KM8vdanUUkGwqXL\nGjQr7iS/e4tzsinUu6FnEl2pIH6BmkWLBB1QojSPfR0eQMU+Zy04rrB1Rztbmcad\nlw9+3mqfpba0YPuin1izA0SVfnlez73nxLkxGiGbf1DBHRlVr7re3VRVhTzm8Wru\ncbJGY+Q24kW04BUg6E1H9e8gWPjXlO744UGYmEwZO+MMtpSJIiWKDAezFr3nZefw\n6+GDxKYJAgMBAAECggEAOvASgIMpXcwO6e7P6T561ZVrO+rOWulsZaWEtDfWSF90\n9Zd9+4FLqPir48vDxS3wseVODWrN2+S6smfwdxzue2lGnV9UTWWGFxM2s1nmsZze\nTCCYDBO8tAcKQB8Vi1UMsvvwVVQ79lWpEUpI+xdkC/CptoF4vNP9vfIy6+lD2Rng\npzf6reMkLIkPwTxA90nFpxhvBGrRen07sw5Jvx5mbGwK/IcmCfAlxjrv/nKJ+0lu\nj/enMYgCUAIAJ8wpWroYhGJvktevaJFfyR2KnyI/dhQgNJHeFzcCxpprDrAy8bN+\nFEd7VlgbuG/aDIYZwfUxvXKEEjeF76TssEFURLY5AQKBgQDLjqZBRCuiUICCQ9wJ\nvBCv3Tyi1thk/eWVnX1W86BQ0vGSch7njO3Ks4kCACLm9DUPNsJep94Io5knKaVu\nI3ZUNUGzcsCrcLMYNEeljUTuRQ49NfCaWayhQHkoOMGWke/Moj/sI3MryeYG0HAp\nb6ZkoxI49Lju5PY2icgM8BS2cQKBgQDBTeB1UvWP6ASHBq/EnvnrtvHMIMR4eBS9\n/GR8SJPCCkopbZJtjngVGC8eSHsggcFQKXVadn+uC46NZ/4gMgF2KYwall9okY6d\nG57GfKRSvsE0ZRR+FpQtTnqUfOudLKl53h9FDunl7sRIYIoT5eL4uHrHv3NNPDqN\n1pDD3qilGQKBgFvgCtIyfq9IPniNQGd0ZuO5q4CkEA+lOVaKOuRgGd/hFf/PWnuQ\ndFOlLRWmEhrD5p7zTE+E3QZxMNMoTO6lOudPElR4WtYGjA9EqYHjfVU9/etKyUoh\nZ3VwsD6jP11CiUWHheqDJZyCCDzTH4zUQ/nwUG08p6vL1AVRsuWEBxVBAoGAUHFh\nLFH2wQlUAQEGWnOyG6bJXyJvwJZwQ1PqWVI2szRnAnCH1DHKxTSIPzj4jGGTGhH2\ntUvE/J/wleYl+i31L8BAfrv/Plv8lmLtIzqxg4HAk1ZRPduVlHkpR+vofUMd0Apg\nxvNa4QYJBvmt3HP5jXnwFnoUuJqM34PgQLLDSdkCgYBuQj5rG8Psuq06Q0j89/aV\nCm8hj3Q5qMKIaRotiQ1ZXN2kYVc6Nkx7kMN+Tv2vDPdIzMBEeJy5f5lDVUJvG9mR\nZ7BAm8bGGiklDisSItlotsbIE2q71kgrxI+fJ4nJeOfx7YcXlABjKb8kklWBSZo1\n/hpFAE/3OYFLWGVLBCuhiw==\n-----END RSA PRIVATE KEY-----\n'
    with open('test.key', 'w') as f:
        f.write(test_key)

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
    usage: python rt_sftp_test_server [options]
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
        '-k', '--keyfile', dest='keyfile', metavar='FILE', default='test.key',
        help='Path to private key, for example /tmp/test_rsa.key'
        )

    options, args = parser.parse_args()

    if options.keyfile is None:
        parser.print_help()
        sys.exit(-1)

    start_server(options.host, options.port, options.keyfile, options.level)

if __name__ == '__main__':
    get_test_key()
    #get_test_data()
    main()
