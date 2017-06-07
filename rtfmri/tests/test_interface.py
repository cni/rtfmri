from __future__ import print_function

import time

import nose.tools as nt
from nose import SkipTest

from .. import interface




class TestScannerInterface(object):

    # def test_sftp_connection(self):
    #     # Pass the default credentials to connect to the test FTP server
    #     scanner = interface.ScannerInterface(hostname='localhost',
    #                                                  port=2124,
    #                                                  base_dir='test_data',
    #                                                  password='test.pass',
    #                                                  private_key='test.key',
    #                                                  public_key='CSR.csr')
    #     # except Exception, e:
    #     #     print ("Failed to connect to sftp server, check login.")
    #     #     print(e)
    #     #     raise SkipTest

    #     scanner.start()

    #     if not scanner.sftp_success:
    #         print("No connection")
    #         raise SkipTest


    #     nt.assert_equal(scanner.series_finder.client.base_dir, 'test_data')
    #     nt.assert_equal(scanner.dicom_finder.client.latest_exam,
    #                     'test_data/p004/e4120')

    #     # nt.assert_equal(scanner.series_finder.client.latest_series,
    #     #                 'test_data/p004/e4120')

    #     scanner.shutdown()

    def test_get_volume(self):
        scanner = interface.ScannerInterface(hostname='localhost',
                                             port=2124,
                                             base_dir='../test_data',
                                             password='../test.pass',
                                             private_key='test.key',
                                             public_key='CSR.csr')
        # except Exception, e:
        #     print ("Failed to connect to sftp server, check login.")
        #     print(e)
        #     raise SkipTest

        scanner.start()
        while scanner.volumizer.volume_q.qsize()<1:
            print("Waiting...")
            time.sleep(1)


        # vol = scanner.get_volume()
        assert True
        scanner.shutdown()

