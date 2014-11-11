from __future__ import print_function
from Queue import Empty

from nose import SkipTest
import nose.tools as nt

from .. import client, queues


class TestThreadedQueue(object):

    def test_queue_basics(self):

        q = queues.ThreadedQueue()

        # Can we put stuff into and take it back out of the queue?
        q.put("hello")
        q.put("world")

        nt.assert_equal(q.get(), "hello")
        nt.assert_equal(q.get(), "world")

        with nt.assert_raises(Empty):
            q.get(block=False)

    def test_halt(self):

        q = queues.ThreadedQueue()
        assert q.alive

        q.halt()
        assert not q.alive


class TestSeriesQueue(object):

    @classmethod
    def setup_class(cls):
        # TODO abstract this out into a base testing class, as it
        # is currently getting copied throughout the codebase

        cls.host = "localhost"
        cls.port = 2121
        cls.base_dir = "test_data"

        # Pass the default credentials to connect to the test FTP server
        cls.client = client.ScannerClient(hostname=cls.host,
                                          port=cls.port,
                                          base_dir=cls.base_dir)
        cls.no_server = cls.client.ftp is None
        
    @classmethod
    def teardown_class(cls):

        if cls.client.ftp is not None:
            cls.client.close()

    def test_queue(self):

        if self.no_server:
            raise SkipTest

        q = queues.SeriesQueue(self.client)
        q.start()

        # We want to be able to stop the thead when tests fail
        try:

            for want_series in self.client.series_dirs():
                got_series = q.get(block=False)
                nt.assert_equal(want_series, got_series)

        finally:
            q.halt()
            q.join()
