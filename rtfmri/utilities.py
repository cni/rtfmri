"""Utilities for starting a scan and collecting pulse timings."""

import serial
import sys, signal, time
from datetime import datetime

def start_scan(device = '/dev/tty.usbmodem123451'):
    if device:
        device = '/dev/ttyACM0' #this should be the linux path...

    if not os.path.exists(device):
        sys.stderr.write("ERROR: Serial device %r not found!\n\n" % (device,))
        return 1

    ser = serial.Serial(device, 115200, timeout=1)
    #time.sleep(0.05)
    # Send an out pulse
    ser.write('[t]\n');
    ser.close()

### BELOW is the code for gathering pulse timings, which should be
### Useful for precise timing information.

# import serial
# import sys, signal, time
# from datetime import datetime

# # Be sure to set this to the correct device! Under linux, it is something
# # like /dev/ttyACM0. On OSX, it will be /dev/ttyUSBNNNN, where NNNN is
# # some cryptic number. On windows, it will be a COM port (e.g., COM4).
# device = '/dev/ttyACM0'

# running = True

# def handler(signum, frame):
#     global running
#     running = False

# # Set the signal handler to allow clean exit with a TERM signal
# signal.signal(signal.SIGTERM, handler)

# if __name__ == "__main__":
#     filename = sys.argv[1]
#     timeRef = datetime.now()
#     with open(filename, 'a') as f:
#         f.write('%% Reference time: %s\n' % str(timeRef))
#         ser = serial.Serial(device, 115200, timeout=1)
#         time.sleep(0.1)
#         # Send a trigger pulse to start scanning
#         ser.write('[t]\n');
#         # Display the firmware greeting
#         out = ser.readlines()
#         for l in out: print(l),
#         # Send the command to enable input pulses
#         ser.write('[p]\n');

#         while running:
#             n = ser.inWaiting()
#             if n>0:
#               s = ser.read(n)
#               if s[0]=='p':
#                 ts = datetime.now() - timeRef
#                 totalSeconds = (ts.microseconds + (ts.seconds + ts.days * 24 * 3600) * 10**6) / float(10**6)
#                 # Print the time stamp as an offset from the reference time, in milliseconds.
#                 f.write('%0.9f\n' % totalSeconds)

#         ser.close()

# exit(0)
