#! /usr/bin/env python
"""Retrieve an image from a specific series in the current exam."""
from __future__ import print_function
import sys
import optparse
import textwrap


# Change this path to point to where the rtfmri code lives
try:
    sys.path.insert(0, "/home/cniuser/rt/rtfmri")
except:
    pass

from rtfmri.fetcher import SeriesFetcher


def main(arglist):
    args = parse_args(arglist)
    client = SeriesFetcher(hostname=args.hostname, username=args.username,
                            password=args.password, port=args.port,
                            base_dir=args.image_dir, outfile=args.output)


def parse_args(arglist):
    usage = """\
    usage: grab_image_from_scanner.py [options]
    -u / --username must be specified
    -p / --password must be specified
    -o / --output must be specified
    """
    parser = optparse.OptionParser(usage=textwrap.dedent(usage))
    parser.add_option(
        '-u', '--username', default='',
        help='login username USERNAME '
    )
    parser.add_option(
        '-p', '--password', default='',
        help='login PASSWORD'
    )
    parser.add_option(
        '-o', '--output',
        help='create new nii file OUTPUT [required]'
    )
    parser.add_option(
        '--host', dest='hostname', default='cnimr',
        help='find scanner at HOST [default: %default]')
    parser.add_option(
        '--port', dest='port', type='int', default=22,
        help='connect via PORT [default: %default]'
    )
    parser.add_option(
        '--image-dir', dest='image_dir',
        default='/export/home1/sdc_image_pool/images',
        help='directory containing patients/exams/sessions [default: %default]'
    )

    options, args = parser.parse_args()

    if options.output is None:
        parser.print_help()
        sys.exit(-1)
    return options


if __name__ == "__main__":
    main(sys.argv[1:])
