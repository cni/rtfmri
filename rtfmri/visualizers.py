"""High-levelest level visualization class for functional data that wraps
   a full scanner interface."""
import pdb
import sys
import signal
import logging
from random import randint, random
from time import sleep

import pygame
import numpy as np
from nilearn.input_data import NiftiMasker

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
        self.halt()
        sys.exit(0)

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

class PyGameVisualizer(Visualizer):
    """ Handle pygame setup"""

    def __init__(self, interface, timeout=0):
        super(PyGameVisualizer, self).__init__(interface, timeout)
        self.interface = interface
        self.bg_color = (0, 0, 0)
        self.clock = pygame.time.Clock()
        self.state = 0
        self.tic = 0
        self.rate = 100
        self.period = 2000  # how often to refresh state
        self.pygame_live = False

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


class RoiVisualizer(PyGameVisualizer):
    """Class that assumes you want to use a masking object"""

    def __init__(self, interface, masker, timeout=0):

        super(RoiVisualizer, self).__init__(interface, timeout)
        self.masker = masker
        # keep track of the ROI's information over time.
        self.roi_tc = []

    def update_state(self):
        logger.debug("Fetching volume...")
        vol = self.get_volume()
        roi_mean = self.masker.reduce_volume(vol)
        self.roi_tc.append(roi_mean)
        self.state = roi_mean


class Thermometer(RoiVisualizer):
    """ The first fully functional visualizer that actually does something.
        Maintains a thermometer displayed on screen consisting of a red
        box that moves up and down a range corresponding to numbers 1 to 100.
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

    def run(self, random=False):
        mainloop = True

        while mainloop:
            # Limit frame speed to 50 FPS
            self.clock.tick(self.rate)
            self.tic += 1
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    mainloop = False
                elif event.type == pygame.VIDEORESIZE:
                    self.draw_box()

            # Redraw the background
            self.screen.fill(self.bg_color)
            self.draw_box()
            self.update_temp(random)
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
        if self.old_y == target_y:
            if random() > .5:
                target_y += randint(-10, 10)
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

    def get_temp(self):
        self.update_state()
        buffer_size = 5
        if len(self.roi_tc) > buffer_size:
            start_ind = max(len(roi.tc) - buffer_size, 0)
            mean = np.mean(self.roi_tc)
            std = np.std(self.roi_tc)
            temp = 50 + 25 * ((self.state - mean) / std)
            return temp
        else:
            return self.temp

    def get_random_temp(self):
        if self.tic % (self.period//self.rate) == 0:
            return max(min(self.temp + randint(-20, 20), 90), 10)
        else:
            return self.temp
