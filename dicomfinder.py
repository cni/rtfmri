

import glob
import sys
import os


def finder():
    files = []## GET INITIAL FILE LIST...
    maxbig = 0
    maxsmall = 0
    template = ''
    
    for file in files:
        spl = file.split('.')
        small = int(spl[-2])
        big = int(spl[-3])
        template = '.'.join(spl[:-3])
        if big >= maxbig:
            if big > maxbig:
                maxbig = big
                maxsmall = 0
            if small > maxsmall:
                maxsmall = small
    
    return [template,maxbig,maxsmall]
    
def getnext(template,mb,ms,path):
    
    filesgotten = []
    
    while True:
        mb += 1
        ms += 1
        try:
            nextfile = os.path.join(path,'.'.join(template,str(mb),str(ms),'dcm'))
            filesgotten.append(open(nextfile))
        except IOError as e:
            break
    
    return filesgotten

