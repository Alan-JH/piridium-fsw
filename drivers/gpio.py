# GPIO wrapper driver, with both GPIO and ADC

from spidev import SpiDev
import RPi.GPIO as gp
import time

global ADC_VREF, HANDSHAKE, MODEM_ON_OFF, RING_INDICATOR, NET_AVAIL, \
    PAYLOAD_PWR, PAYLOAD_GPIO, GPIO_INITIALIZED, PAYLOAD_GPIO_MODE, spibus
ADC_VREF = 3
HANDSHAKE = 21 # Watchdog reset handshake
MODEM_ON_OFF = 20 # Modem power control
RING_INDICATOR = 16 # Modem ring indicator
NET_AVAIL = 12 # Modem net availability indicator
PAYLOAD_PWR = 26 # Payload power control
PAYLOAD_GPIO = 19 # Payload GPIO pin

GPIO_INITIALIZED = False
PAYLOAD_GPIO_MODE = 0

spibus = None

def start():
    global GPIO_INITIALIZED, spibus, HANDSHAKE, MODEM_ON_OFF, RING_INDICATOR, NET_AVAIL, PAYLOAD_PWR, PAYLOAD_GPIO_MODE
    if GPIO_INITIALIZED:
        raise Warning("GPIO Already Initialized!")
    else:
        spibus = SpiDev()
        spibus.open(0, 0)
        spibus.max_speed_hz = 500000
        spibus.mode = 0b00
        gp.setmode(gp.BCM)
        gp.setup(HANDSHAKE, gp.OUT)
        gp.output(HANDSHAKE, gp.LOW)
        gp.setup(MODEM_ON_OFF, gp.OUT)
        gp.output(MODEM_ON_OFF, gp.LOW)
        gp.setup(RING_INDICATOR, gp.IN)
        gp.setup(NET_AVAIL, gp.IN)
        gp.setup(PAYLOAD_PWR, gp.OUT)
        gp.output(PAYLOAD_PWR, gp.LOW)
        PAYLOAD_GPIO_MODE = 0 # Initialize with gpio set to input
        GPIO_INITIALIZED = True
        set_gpio_mode(0)
        
def check_initialized(func):
    """
    Decorator that checks whether GPIO has been initialized before attempting to interface
    """
    def wrap(*args, **kwargs):
        global GPIO_INITIALIZED
        if GPIO_INITIALIZED: return func(*args, **kwargs)
        else: raise ValueError("GPIO Not yet initalized, you need to run start() first!")

    return wrap

@check_initialized
def set_gpio_mode(mode, pull = 0):
    """
    Sets payload GPIO to input or output
    mode: 0 input 1 output
    pull (only used for input): none 0 pullup 1 pulldown 2
    """
    global PAYLOAD_GPIO_MODE
    PAYLOAD_GPIO_MODE = mode
    if mode:
        gp.setup(PAYLOAD_GPIO, gp.OUT)
        gp.output(PAYLOAD_GPIO, gp.LOW)
    else:
        if pull == 0: gp.setup(PAYLOAD_GPIO, gp.IN)
        elif pull == 1: gp.setup(PAYLOAD_GPIO, gp.IN, pull_up_down=gp.PUD_UP)
        elif pull == 2: gp.setup(PAYLOAD_GPIO, gp.IN, pull_up_down=gp.PUD_DOWN)
        else: raise Warning("Invalid pull value, not proceeding")

@check_initialized
def reset_watchdog():
    global HANDSHAKE
    gp.output(HANDSHAKE, gp.HIGH)
    time.sleep(.01)
    gp.output(HANDSHAKE, gp.LOW)

@check_initialized
def power_modem_on():
    global MODEM_ON_OFF
    gp.output(MODEM_ON_OFF, gp.HIGH)

@check_initialized
def power_modem_off():
    global MODEM_ON_OFF
    gp.output(MODEM_ON_OFF, gp.LOW)

@check_initialized
def read_ring_indicator():
    global RING_INDICATOR
    return gp.input(RING_INDICATOR)

@check_initialized
def read_network_available():
    global NET_AVAIL
    return gp.input(NET_AVAIL)

@check_initialized
def power_payload_on():
    global PAYLOAD_PWR
    gp.output(PAYLOAD_PWR, gp.HIGH)

@check_initialized
def power_payload_off():
    global PAYLOAD_PWR
    gp.output(PAYLOAD_PWR, gp.LOW)

@check_initialized
def set_payload_gpio(state):
    """
    Sets payload gpio if it is in output mode
    state: 0 - LOW, 1 - HIGH
    """
    global PAYLOAD_GPIO
    if mode: gp.output(PAYLOAD_GPIO, state)
    else: raise Warning("Payload GPIO is not in output mode, not setting output")

@check_initialized
def read_payload_gpio():
    """
    Reads payload gpio if it is in input mode
    returns 0 for low, 1 for high, None if gpio not in input
    """
    global PAYLOAD_GPIO
    if mode: raise Warning("Payload GPIO is not in input mode, not reading input")
    else: return gp.input(PAYLOAD_GPIO)

def _sample(channel):
    """
    Reads and returns the 12 bit reading of the specified ADC channel
    :param channel: (int) ADC channel, from 0 to 7 inclusive
    :return: (int) 12 bit reading
    """
    global ADC_VREF, spibus
    control = (0b11 << 3) | (channel & 0b111) # Start bit, single ended mode, then channel select bits
    mosi = [control >> 2, (control & 0b11) << 6, 0x00] # See fig 6-1 in mcp3208 datasheet
    miso = spibus.xfer2(mosi)
    return ADC_VREF * (((miso[1] & 0xf) << 8) | miso[2]) / 4096

@check_initialized
def solar_i_1():
    return _sample(0) / 0.4

@check_initialized
def solar_v_1():
    return _sample(1) * 8.5

@check_initialized
def solar_i_2():
    return _sample(2) / 0.4

@check_initialized
def solar_v_2():
    return _sample(3) * 8.5

@check_initialized
def battery_v():
    return _sample(4) * 3

@check_initialized
def battery_i():
    return _sample(5) / 0.4

@check_initialized
def payload_i():
    return _sample(6) / 0.4