# GPIO wrapper driver, for use by other drivers

import RPi.GPIO as gp
import time

HANDSHAKE = 21 # Watchdog reset handshake
MODEM_ON_OFF = 20 # Modem power control
RING_INDICATOR = 16 # Modem ring indicator
NET_AVAIL = 12 # Modem net availability indicator
PAYLOAD_PWR = 26 # Payload power control
PAYLOAD_GPIO = 19 # Payload GPIO pin


class GPIO():
    def __init__(self):
        gp.setmode(gp.BCM)
        gp.setup(HANDSHAKE, gp.OUT)
        gp.output(HANDSHAKE, gp.LOW)
        gp.setup(MODEM_ON_OFF, gp.OUT)
        gp.output(MODEM_ON_OFF, gp.LOW)
        gp.setup(RING_INDICATOR, gp.IN)
        gp.setup(NET_AVAIL, gp.IN)
        gp.setup(PAYLOAD_PWR, gp.OUT)
        gp.output(PAYLOAD_PWR, gp.LOW)
        self.payload_gpio_mode = 0 # Initialize with gpio set to input
        self.set_gpio_mode(0)

    def set_gpio_mode(self, mode, pull = 0):
        """
        Sets payload GPIO to input or output
        mode: 0 input 1 output
        pull (only used for input): none 0 pullup 1 pulldown 2
        """
        self.payload_gpio_mode = mode
        if mode:
            gp.setup(PAYLOAD_GPIO, gp.OUT)
            gp.output(PAYLOAD_GPIO, gp.LOW)
        else:
            if pull == 0:
                gp.setup(PAYLOAD_GPIO, gp.IN)
            if pull == 1:
                gp.setup(PAYLOAD_GPIO, gp.IN, pull_up_down=gp.PUD_UP)
            if pull == 2:
                gp.setup(PAYLOAD_GPIO, gp.IN, pull_up_down=gp.PUD_DOWN)

    def handshake(self):
        gp.output(HANDSHAKE, gp.HIGH)
        time.sleep(.01)
        gp.output(HANDSHAKE, gp.LOW)

    def modem_on(self):
        gp.output(MODEM_ON_OFF, gp.HIGH)

    def modem_off(self):
        gp.output(MODEM_ON_OFF, gp.LOW)

    def ring_indicator(self):
        return gp.input(RING_INDICATOR)

    def net_available(self):
        return gp.input(NET_AVAIL)

    def payload_on(self):
        gp.output(PAYLOAD_PWR, gp.HIGH)

    def payload_off(self):
        gp.output(PAYLOAD_PWR, gp.LOW)

    def set_payload_gpio(self, state):
        """
        Sets payload gpio if it is in output mode
        state: 0 - LOW, 1 - HIGH
        returns True if successful
        """
        if mode:
            gp.output(PAYLOAD_GPIO, state)
            return True
        return False

    def read_payload_gpio(self):
        """
        Reads payload gpio if it is in input mode
        returns 0 for low, 1 for high, 2 if not in input mode
        """
        if mode: return 2
        return gp.input(PAYLOAD_GPIO)