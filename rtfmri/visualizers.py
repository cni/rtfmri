"""High-levelest level visualization class for functional data that wraps
   a full scanner interface."""
import pdb
import sys, time
import signal
import logging
from random import randint, random
from time import sleep

import pygame
import numpy as np
from nilearn.input_data import NiftiMasker
from sklearn import decomposition as decomp
import matplotlib.pyplot as plt


logger = logging.getLogger(__name__)


class Visualizer(object):
    """Given an interface that gives you volumes,
       visualize something about those volumes"""

    def __init__(self, interface, timeout=0):
        self.interface = interface
        self.state = 0
        self.timeout = timeout
        self.alive = True
        self.setup_exit()

    def start_interface(self):
        self.interface.start()

    def setup_exit(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, sig, frame):
        print("Exiting the visualizer gracefully")
        self.halt()

    def get_volume(self, *args, **kwargs):
        """Gather new information from the interface, ie get volumes"""
        return self.interface.get_volume(*args, **kwargs)

    def update_state(self):
        """Any visualizer will need a function to update its internal
           representation of the data it's gathering from the interface"""
        new_volume = self.get_volume()
        # state never changes in base class
        self.state = self.state

        # sleep(self.timeout)

    def draw(self):
        """ Function to actually handle updating the screen"""
        pass

    def run(self):
        """structure of main run"""
        while self.alive:
            self.update_state()
            self.draw()
        self.halt()

    def halt(self):
        """Halt command"""
        self.alive = False
        self.interface.shutdown()

    def __del__(self):
        self.halt()


class RoiVisualizer(Visualizer):
    """Class that assumes you want to use a masking object"""

    def __init__(self, interface, masker, timeout=0):

        super(RoiVisualizer, self).__init__(interface, timeout)
        self.masker = masker
        # keep track of the ROI's information over time.
        self.roi_tc = []
        self.nvol = 0
        self.TR = 2
        self.ortho_tcs = [[] for x in self.masker.orthogonals]
        self.detrended = []

    def start_timer(self):
        self.start = time.time()
        self.last_time = self.start

    def log_times(self):
        n = len(self.roi_tc)
        toc = time.time()
        start_diff = toc - self.start
        last_diff  = toc - self.last_time
        volume_collected = self.start + self.nvol * self.TR - 2
        lag = toc - volume_collected

        self.last_time = toc
        print("Time since start: {}".format(start_diff ))
        print("Time since last: {}".format(last_diff))
        print("Average since start: {}".format(start_diff/n))
        print("Lag: {}".format(lag))

    def update_state(self):
        logger.debug("Fetching volume...")
        vol = self.get_volume()
        self.nvol += 1
        roi_mean = self.masker.reduce_volume(vol)
        self.roi_tc.append(roi_mean)
        if self.masker.use_orthogonal:
            ortho_means = self.masker.get_orthogonals(vol)
            for i, mean in enumerate(ortho_means):
                self.ortho_tcs[i].append(mean)
            if len(self.roi_tc) > 3:
                detrended = self.detrend()
                print(np.corrcoef(detrended[:,0], self.roi_tc[2:]))
                roi_mean = detrended[-1,0]
                self.detrended = detrended[:,0]

        self.state = roi_mean

    def detrend(self):
        # make a timepoint x num roi matrix and take pcs[].
        tcs = [self.roi_tc]
        for x in self.ortho_tcs:
            tcs.append(x)
        #leave out the noise of the first two time points
        tcm = np.transpose(np.array(tcs))[2:, :]

        #transform onto pcs
        pca = decomp.PCA()
        pca.fit(tcm)
        tf = pca.transform(tcm)

        # ica = decomp.FastICA()
        # ica.fit(tcm)
        # tf = ica.transform(tcm)

        return tf

class TextVisualizer(RoiVisualizer):
    """
    Most basic visualizer. Prints out the newest ROI
    """
    def draw(self):
        print(self.detrended)
        print(self.roi_tc)
        self.log_times()

class GraphVisualizer(RoiVisualizer):
    """
    Very basic visualizer that graphs ROI average time course in real time
    """
    def __init__(self, interface, masker, timeout=0):
        super(GraphVisualizer, self).__init__(interface, masker, timeout)
        plt.ion()
        self.old_n = 0
        self.tic = time.time()

    def draw(self):
        n = len(self.roi_tc)
        #n = len(self.detrended)

        #x = 2*range(2, n-1)
        x = range(1, n)
        y = []
        if n > 1:
            y = self.roi_tc[1:]
            #y = self.detrended[1:]
        self.log_times()
        plt.plot(x, y)

        plt.xlabel('time (s)')
        plt.ylabel('ROI activation - Raw')
        plt.title('Neurofeedback!!!')
        plt.grid(True)
        #plt.savefig("test.png")
        plt.show()

        plt.pause(0.1)



class PyGameVisualizer(RoiVisualizer):
    """ Handle pygame setup"""

    def __init__(self, interface, masker, timeout=0):
        super(PyGameVisualizer, self).__init__(interface, masker, timeout)
        self.interface = interface
        self.bg_color = (0, 0, 0)
        self.clock = pygame.time.Clock()
        self.state = 0
        self.tic = 0
        self.rate = 50
        self.period = 2000  # how often to refresh state
        self.pygame_live = False
        self.vec_set = False

    def halt(self):
        self.alive = False
        self.interface.shutdown()
        if self.pygame_live:
            pygame.display.quit()
            pygame.quit()
            self.pygame_live = False

    def start_display(self, width=640, height=500, title='nrfdbk'):
        self.pygame_live = True
        pygame.init()
        w, h = (int(width), int(height))
        self.screen = pygame.display.set_mode((w, h), pygame.RESIZABLE)
        pygame.display.set_caption(title)

    def set_regressors(self, vec, text, TR=2):
        """At each TR, if vec has value x, display text[x] on screen"""
        self.vec = [int(x) for x in vec]
        self.text = text
        self.TR = TR
        self.vec_set=True


    def display_vectext(self):
        if not self.vec_set:
            raise ValueError('regressor does not exist')

        myfont = pygame.font.SysFont("monospace", 30)

        tr = int((time.time() - self.start) // self.TR)
        label = myfont.render(self.text[self.vec[tr]], 1, (255,255,0))
        self.trial_type = label
        self.next_trial_type = self.vec[min(len(self.vec)-1, tr+1)]
        w,h = self.screen.get_size()
        self.screen.blit(label, (w//3,h//15))
        #pdb.set_trace()

class Thermometer(PyGameVisualizer):
    """ The first fully functional visualizer that actually does something.
        Maintains a thermometer displayed on screen consisting of a red
        box that moves up and down a range corresponding to numbers 1 to 100.

        TODO: refactor the ugly
    """

    def __init__(self, interface, masker, timeout=0):
        super(Thermometer, self).__init__(interface, masker, timeout)
        self.temp = 50
        self.max_move = 100


    def _center_rect(self, width, height):
        sw, sh = self.screen.get_size()
        center_y = (sh - height)//2
        center_x = (sw - width) // 2
        return (center_x, center_y)

    def _get_wh(self):
        sw, sh = self.screen.get_size()
        w = sw*.1//1
        h = sh*.7//1
        return (w, h)

    def draw_box(self):
        box_color = (255, 253, 251)
        w, h = self._get_wh()
        x, y = self._center_rect(w, h)
        xywh = (x, y, w, h)
        self.xywh = xywh
        pygame.draw.rect(self.screen, box_color, xywh, 4)

    def center_text(self, message):
        sw, sh = self.screen.get_size()
        font = pygame.font.Font(None, 50)
        text = font.render(message, True, (255,255,0))
        text_rect = text.get_rect(center=(sw/2, sh/2))
        self.screen.blit(text, text_rect)


    def run(self, random=False):
        mainloop = True
        self.itival = 0
        self.next_trial_type=self.itival
        self.draw_box()
        start_time = time.time()


        while mainloop:
            # Limit frame speed to 50 FPS
            self.clock.tick(self.rate)
            self.tic += 1

            #reframe if needed
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    mainloop = False
                elif event.type == pygame.VIDEORESIZE:
                    self.draw_box()

            # Redraw the background
            self.screen.fill(self.bg_color)

            if self.next_trial_type != self.itival:
                #draw the thermometer...
                self.draw_box()
                self.update_temp(random)


            else:
                self.center_text(str(time.time()-start_time))
            if self.vec_set:
                self.display_vectext()
            pygame.display.flip()

    def _draw_temp(self):
        sw, sh = self.screen.get_size()
        w = int(sw*.1//1) - 6 + 1
        h = int(sh*.05//1)
        top_y = (sh - self.xywh[3])//2
        bottom_y = (sh - self.xywh[3])//2 + self.xywh[3] - h
        x = int((sw - self.xywh[2]) // 2) + 3
        target_y = top_y + int(((bottom_y - top_y) * (100-self.temp)/100)//1)
        if not hasattr(self, 'old_y'):
            self.old_y = target_y
        # if self.old_y == target_y:
        #     if random() > .5:
        #         target_y += randint(-10, 10)
        diff = target_y - self.old_y
        if abs(diff) > self.max_move:
            y = self.old_y + self.max_move if diff > 0 else self.old_y - self.max_move
        else:
            y = target_y

        if y < top_y:
            y = top_y
            print self.temp
        if y > bottom_y:
            y = bottom_y
        self.blob = pygame.draw.rect(self.screen, (255, 0, 0), (x, y, w, h), 0)
        self.old_y = y

    def update_temp(self, random=False):
        if not random:
            self.temp = self.get_temp()
            logger.debug("New temp = {}".format(self.temp))
        else:
            # get a random temperature
            self.temp = self.get_random_temp()
        self._draw_temp()
        print(self.temp)

    def get_temp(self):
        self.update_state()
        buffer_size = 5
        if len(self.roi_tc) > buffer_size:
            start_ind = max(len(self.roi_tc) - buffer_size, 0)
            mean = np.mean(self.roi_tc)
            std = np.std(self.roi_tc)
            temp = 50 + 25 * ((self.state - mean) / std)

            greer_temp = 50 + 100*((self.state - mean) / mean)
            temp = greer_temp
            return temp
        else:
            return self.temp

    def get_random_temp(self):
        if self.tic % (self.period//self.rate) == 0:
            return max(min(self.temp + randint(-20, 20), 90), 10)
        else:
            return self.temp
