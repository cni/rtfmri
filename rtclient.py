from ftplib import FTP
import datetime
import os
import cStringIO
import dicom

class RTClient():
    """
    Class for talking to a GE scanner in real-time.
    """

    def __init__(self, hostname='cnimr', username='', password='', image_dir='/export/home1/sdc_image_pool/images'):
        self.hostname = hostname
        self.username = username
        self.password = password
        self.image_dir = image_dir
        self.ftp = None

    def connect(self):
        # connect, if needed. (Checks existing connections and reconnects if needed.)
        if self.ftp:
            try:
                self.ftp.voidcmd('NOOP')
            except:
                self.ftp.close()
                self.ftp = FTP(self.hostname, user=self.username, passwd=self.password)
        else:
            self.ftp = FTP(self.hostname, user=self.username, passwd=self.password)

    def listdir(self, imdir):
        # Returns a dict of all files in imdir, where the file mod time is the key (as a datetime obj)
        # and the value is a tuple of (file_size, file_name). E.g.,  {datetime.datetime(2013, 5, 14, 23, 2): ('4096', 'p939')}
        file_list = []
        self.ftp.dir(imdir, file_list.append)
        if len(file_list) == 0:
            return None
        cur_year = datetime.date.today().year
        # clean up the list (each item is a string like 'drwxrwxr-x    3 564      201          4096 May 10 01:56 p909')
        # Note that for old items, the timestamp is replaced by the year. So, we filter on ':' to get rid of those.
        file_list = [l.split()[4:] for l in file_list]
        file_dict = dict([(datetime.datetime.strptime('%d %s' % (cur_year,' '.join(t[1:4])), '%Y %b %d %H:%M'), (t[0],t[4])) for t in file_list if ':' in t[3]])
        return file_dict

    def latest_dir(self, imdir):
        if not imdir:
            return None
        file_dict = self.listdir(imdir)
        if file_dict:
            latest = os.path.join(imdir, file_dict[max(file_dict.keys())][1])
        else:
            latest = None
        return latest

    def exam_dir(self):
        self.connect()
        # The exam dir is exactly 2 layers deep:
        return self.latest_dir(self.latest_dir(self.image_dir))

    def series_dir(self):
        self.connect()
        return self.latest_dir(self.exam_dir())

    def get_file_list(self, series_dir):
        # If we need to worry about partial files, then we should use listdir and check file sizes.
        # But that is really slow.
        return self.ftp.nlst(series_dir)

    def get_file(self, filename):
        buf = cStringIO.StringIO()
        self.ftp.retrbinary('RETR ' + filename, buf.write)
        buf.seek(0)
        return buf

    def get_dicom(self, filename):
        return dicom.ReadFile(self.get_file(filename))
