from ftplib import FTP
import datetime
import os
import cStringIO
import dicom

class RTClient():
    """
    Class for talking to a GE scanner in real-time.
    """

    def __init__(self, hostname='cnimr', username='', password='', image_dir='/export/home1/sdc_image_pool/images', port=21):
        self.hostname = hostname
        self.port = port
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
                self.ftp = None
        if not self.ftp:
            self.ftp = FTP()
            self.ftp.connect(host=self.hostname, port=self.port)
            self.ftp.login(user=self.username, passwd=self.password)

    def close(self):
        if self.ftp:
            self.ftp.close()

    def listdir(self, imdir):
        # Returns a dict of all files in imdir, where the file mod time is the key (as a datetime obj)
        # and the value is a tuple of (file_size, file_name). E.g.,  {datetime.datetime(2013, 5, 14, 23, 2): ('4096', 'p939')}
        file_list = []
        self.connect()
        self.ftp.dir(imdir, file_list.append)
        if len(file_list) == 0:
            return None
        cur_year = datetime.date.today().year
        # clean up the list (each item is a string like 'drwxrwxr-x    3 564      201          4096 May 10 01:56 p909')
        # Note that for old items, the timestamp is replaced by the year. So, we filter on ':' to get rid of those.
        file_list = [l.split()[4:] for l in file_list]
        # We have to ensure the keys are unique. The timestamps from ftp have a coarse resolution,
        # so we can get multiple files with the same timestamp. As a simple hack, we'll fake
        # the microseconds by using the file index. (We could fake seconds, but then we'd have to
        # worry about the 0-59 limit.)
        file_dict = dict([(datetime.datetime.strptime('%d %s:%d' % (cur_year,' '.join(t[1:4]),s), '%Y %b %d %H:%M:%f'), (t[0],t[4])) for s,t in enumerate(file_list) if ':' in t[3]])
        return file_dict

    def exam_info(self, exam_dir=None):
        self.connect()
        if not exam_dir:
            exam_dir = self.exam_dir()
        all_series = self.series_dirs(exam_dir=exam_dir)
        exam_info = {}
        first_series_dir = sorted(all_series.iteritems())[0][1]
        file_dict = self.listdir(first_series_dir)
        if file_dict:
            dcm = self.get_dicom(os.path.join(first_series_dir, file_dict[min(file_dict.keys())][1]))
            exam_info['Exam'] = dcm.StudyID
            exam_info['ID'] = dcm.PatientID
            exam_info['Operator'] = dcm.OperatorsName.translate(None,'^')
            exam_info['Protocol'] = dcm.ProtocolName
            exam_info['exam_dir'] = exam_dir
            exam_info['first_series_dir'] = first_series_dir
        return exam_info

    def series_info(self, exam_dir=None):
        self.connect()
        if not exam_dir:
            exam_dir = self.exam_dir()
        all_series = self.series_dirs(exam_dir=exam_dir)
        series_info = []
        for s in iter(sorted(all_series.iteritems())):
            file_dict = self.listdir(s[1])
            if file_dict:
                dcm = self.get_dicom(os.path.join(s[1], file_dict[min(file_dict.keys())][1]))
                series_info.append({'Dicomdir':s[1],
                                    'DateTime':datetime.datetime.strptime(dcm.StudyDate + dcm.StudyTime, '%Y%m%d%H%M%S'),
                                    'Series':dcm.SeriesNumber,
                                    'Acquisition':dcm.AcquisitionNumber,
                                    'Description':dcm.SeriesDescription})
        return series_info

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
        # The exam dir is exactly 2 layers deep
        return self.latest_dir(self.latest_dir(self.image_dir))

    def series_dirs(self, exam_dir=None):
        """
        Returns a dictionary of files in exam_dir, with timestamps as keys.
        Basically a thin wrapper around listdir, but removes the file size and
        makes each entry a full file path.
        """
        self.connect()
        if not exam_dir:
            exam_dir = self.exam_dir()
        file_dict = self.listdir(exam_dir)
        all_series = {}
        if file_dict:
            for k in file_dict:
                all_series[k] = os.path.join(exam_dir, file_dict[k][1])
        return all_series

    def series_dir(self, exam_dir=None, series_num=None):
        self.connect()
        if not exam_dir:
            exam_dir = self.exam_dir()
        if not series_num:
            series_dir = self.latest_dir(exam_dir)
        else:
            series_dir = next((sd['Dicomdir'] for sd in self.series_info(exam_dir=exam_dir) if sd['Series']==series_num), None)
        return series_dir

    def get_file_list(self, series_dir):
        # If we need to worry about partial files, then we should use listdir and check file sizes.
        # But that is really slow.
        self.connect()
        files = self.ftp.nlst(series_dir)
        if files[0][0]!='/':
            files = [os.path.join(series_dir,f) for f in files]
        return files

    def get_file(self, filename):
        buf = cStringIO.StringIO()
        self.ftp.retrbinary('RETR ' + filename, buf.write)
        buf.seek(0)
        return buf

    def get_dicom(self, filename):
        return dicom.filereader.read_file(self.get_file(filename))
