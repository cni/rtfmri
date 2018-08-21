"""High-levelest level visualization class for functional data that wraps
   a full scanner data_manager."""
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
logger.setLevel(logging.DEBUG)

class Visualizer(object):
    """Given an data_manager that gives you state data,
       visualize something about those data"""

    def __init__(self, data_manager, timeout=0):
        self.data_manager = data_manager
        self.state = 0
        self.timeout = timeout
        self.alive = True
        self.setup_exit()
        self.state_history = []

    def setup_exit(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, sig, frame):
        print("Exiting the visualizer gracefully")
        self.halt()

    def get_state(self):
        """Gather new information from the data_manager, ie get state"""
        return self.data_manager.get_state()

    def draw(self):
        """ Function to actually handle updating the screen"""
        pass

    def run(self):
        """structure of main run"""
        logger.debug("running visualizer")
        while self.alive:
            self.update_state()
            self.draw()
        self.halt()

    def halt(self):
        """Halt command"""
        self.alive = False
        self.data_manager.halt()

    def __del__(self):
        self.halt()

    def start_timer(self):
        self.start = time.time()

    @property
    def current_tr(self):
        return int((time.time() - self.start) // self.TR)

    def update_state(self):
        logger.debug("Visualizer attempting to fetch volume...")
        state = self.get_state()
        self.state_history.append(state)
        self.state = state

    def set_regressors(self, vec, text, TR):
        self.timing_vector = [int(x) for x in vec]
        self.timing_text = text
        self.TR = TR

class TextVisualizer(Visualizer):

    """
    Most basic "visualizer". Prints out the newest ROI value (raw)
    """
    def draw(self):
        print(self.state_history)

class GraphVisualizer(Visualizer):
    """
    Very basic visualizer that graphs ROI average time course in real time
    """
    def __init__(self, data_manager, timeout=0):
        super(GraphVisualizer, self).__init__(data_manager, timeout)
        plt.ion()
        self.old_n = 0
        self.tic = time.time()

    def draw(self):
        n = len(self.state_history)
        x = range(1, n)
        y = []
        if n > 1:
            y = self.state_history[1:]
        plt.plot(x, y)

        plt.xlabel('time (s)')
        plt.ylabel('ROI activation - Raw')
        plt.title('Neurofeedback!!!')
        plt.grid(True)
        #plt.savefig("test.png")
        plt.show()
        plt.pause(0.1)



class PyGameVisualizer(Visualizer):
    """ Handle pygame setup"""

    def __init__(self, data_manager, timeout=0, debug=False):
        super(PyGameVisualizer, self).__init__(data_manager, timeout)
        self.debug = debug
        self.bg_color = (0, 0, 0)
        self.clock = pygame.time.Clock()
        self.state = 0
        self.rate = 50
        self.period = 10  # how often to refresh state
        self.pygame_live = False

        # will be a vector of zeros and ones
        self.timing_vector = None

    def halt(self):
        self.alive = False
        self.data_manager.halt()
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



    def center_text(self, message, x = None, y=None, size = 50):
        sw, sh = self.screen.get_size()
        font = pygame.font.Font(None, size)
        text = font.render(message, True, (255,255,0))
        x = sw /2 if x is None else x
        y = sw /2 if y is None else y


        text_rect = text.get_rect(center=(x, y))
        self.screen.blit(text, text_rect)

    @property
    def current_message(self):
        return self.timing_text[self.timing_vector[self.current_tr]]


    @property
    def next_trial_type(self):
        # keep repeating the same trials from the beginning if we run out of trs
        tr = (self.current_tr + 1) % len(self.timing_vector)
        return self.timing_vector[tr]


    def display_timing_text(self, feedback=True):
        if self.timing_vector is None:
            raise ValueError('regressor does not exist')

        font = pygame.font.SysFont("monospace", 30)
        label = font.render(self.current_message, 1, (255,255,0))

        w,h = self.screen.get_size()
        y = h//15 if feedback else None
        self.center_text(self.timing_text[self.timing_vector[self.current_tr]], y=y)



class Thermometer(PyGameVisualizer):
    """ The first fully functional visualizer that actually does something.
        Maintains a thermometer displayed on screen consisting of a red
        box that moves up and down a range corresponding to numbers 1 to 100.

        temp = 50 + 15 * ((self.state - mean) / std) for a buffer
    """
    def __init__(self, data_manager, buffer_size=8, feedback=True,
                 timeout=0, debug=False):
        super(Thermometer, self).__init__(data_manager, timeout, debug)
        self.temp = 50
        self.max_move = 100
        self.feedback = feedback
        self.buffer_size = buffer_size

    def centered_rectangle_xy(self, width, height):
        # Returns the upper left corner of a rectangle (w,h) centered on screen
        w, h = self.screen.get_size()
        center_y = (h - height) // 2
        center_x = (w - width) // 2
        return (center_x, center_y)

    @property
    def width(self):
        w, _ = self.screen.get_size()
        return (w * .1) // 1

    @property
    def height(self):
        _, h = self.screen.get_size()
        return (h * .7) // 1

    def draw_box(self):
        box_color = (255, 253, 251)
        w, h = self.width, self.height
        x, y = self.centered_rectangle_xy(w, h)
        self.xywh = (x, y, w, h)
        pygame.draw.rect(self.screen, box_color, self.xywh, 4)

    def draw_stats(self):
        # Prints statistics at the bottom of screen for debugging
        # these need to be updated for skipping trs
        # last_volume_collection_finished = self.start + self.n_volumes_reduced * self.TR
        # lag = time.time() - last_volume_collection_finished

        # time_elapsed = time.time() - self.start_time
        # stats1 = "Time: {}, Time2TR: {}, TrialType: {}".format(
        #     str(time_elapsed)[:-7],
        #     str(time_elapsed // 2 + 1),
        #     self.timing_vector[self.current_tr]

        # )
        # self.center_text(stats1, y= self.xywh[3]//9 * 12, size = 20)

        # stats2 = "Volumes_Assembled: {}, Volumes_Averaged: {}, Lag {}".format(
        #     self.data_manager.volumizer.n_volumes_queued,
        #     self.n_volumes_reduced,
        #     str(lag)[:-7]
        # )
        # self.center_text(stats2, y= self.xywh[3]//9 * 12 + 30, size = 20)
        pass
    
    def run(self, random=False):
        mainloop = True
        self.itival = 0
        self.draw_box()
        old_tr = 0

        while mainloop:
            # Limit frame speed to self.rate
            self.clock.tick(self.rate)
            tic = time.time()

            #Handle screen size changes
            # This currently doesn't always work.
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    mainloop = False
                elif event.type == pygame.VIDEORESIZE:
                    self.draw_box()

            # Redraw the background
            self.screen.fill(self.bg_color)

            # Get the newest temperature
            self.update_temp(random)

            if self.debug:
                self.draw_stats()
                if self.current_tr != old_tr:
                    print(self.temp)
                    old_tr = self.current_tr

            # If we're displaying feedback...
            if self.next_trial_type != self.itival:
                if self.feedback:
                #draw the thermometer...
                    self.draw_box()
                    self.draw_temp()

            else:
                self.center_text('x')
            self.display_timing_text(feedback=self.feedback)

            pygame.display.flip()


    def draw_temp(self):
        # Draw a small rectangle within the box corresponding to temperature

        sw, sh = self.screen.get_size()
        temp_indicator_width = int(sw * .1 // 1) - 6 + 1
        temp_indicator_heigth = int(sh * .05 // 1)

        thermometer_height = self.xywh[3]
        thermometer_top = (sh - thermometer_height) // 2
        thermometer_bottom = thermometer_top + thermometer_height

        temp_x = int((sw - self.xywh[2]) // 2) + 3
        temp_y = thermometer_top + int(((thermometer_bottom - thermometer_top) * (100-self.temp)/100) // 1)

        # If we are limiting how much thermometer can move, check limits:
        if not hasattr(self, 'old_y'):
            self.old_y = temp_y

        diff = temp_y - self.old_y
        if abs(diff) > self.max_move:
            temp_y = self.old_y + self.max_move if diff > 0 else self.old_y - self.max_move

        # Limit to box
        temp_y = max(thermometer_top, temp_y)
        temp_y = min(thermometer_bottom, temp_y)

        self.temp_box = pygame.draw.rect(self.screen, (255, 0, 0), (temp_x, temp_y, temp_indicator_width, temp_indicator_heigth), 0)

        self.old_y = temp_y

    def update_temp(self, random=False):
        if not random:
            self.temp = self.get_temp()
            logger.debug("New temp = {}".format(self.temp))
        else:
            self.temp = self.get_random_temp()

    def get_temp(self):
        self.update_state()

        if len(self.state_history) > self.buffer_size:
            start_ind = max(len(self.state_history) - self.buffer_size, 0)
            mean = np.mean(self.state_history[start_ind:])
            std = np.std(self.state_history[start_ind:])
            temp = 50 + 15 * ((self.state - mean) / std)
            return temp
        else:
            return self.temp

    def get_random_temp(self):
        if self.tic % (self.period // self.rate) == 0:
            return max(min(self.temp + randint(-20, 20), 90), 10)
        else:
            return self.temp
