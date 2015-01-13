from __future__ import print_function

from nose import SkipTest
from .. import interface


class TestScannerInterface(object):

    def test_interface(self):

        # This is mostly just a smoketest to touch parts of the code

        scanner = interface.ScannerInterface("localhost", 2121,
                                             base_dir="test_data")

        if not scanner.has_ftp_connection:
            raise SkipTest

        try:
            scanner.start()
            vol = scanner.get_volume(timeout=5)
            assert vol

        finally:
            scanner.shutdown()
