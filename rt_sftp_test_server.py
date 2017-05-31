"""
Modified from https://gist.github.com/Girgitt/2df036f9e26dba1baaddf4c5845a20a2
"""
import time
import socket
import optparse
import sys
import textwrap

import paramiko

from sftpserver.stub_sftp import StubServer, StubSFTPServer

import threading

HOST, PORT = 'localhost', 2121
BACKLOG = 10


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
    main()
