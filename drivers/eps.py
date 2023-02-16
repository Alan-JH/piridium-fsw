# EPS telemetry and telecommand
import spidev
import RPi.GPIO as gp
import time

ADC_VREF = 3
HANDSHAKE = 21 # Watchdog reset handshake
MODEM_ON_OFF = 20 # Modem power control
RING_INDICATOR = 16 # Modem ring indicator
NET_AVAIL = 12 # Modem net availability indicator
PAYLOAD_PWR = 26 # Payload power control
PAYLOAD_GPIO = 19 # Payload GPIO pin

class EPS():
    def __init__(self, gpio):
        self.gpio = gpio
        self.spibus = spidev.SpiDev()
        self.spibus.open(0, 0)
        self.spibus.max_speed_hz = 500000
        self.spibus.mode = 0b00

    def sample(self, channel):
        """
        Reads and returns the 12 bit reading of the specified ADC channel
        :param channel: (int) ADC channel, from 0 to 7 inclusive
        :return: (int) 12 bit reading
        """
        control = (0b11 << 3) | (channel & 0b111) # Start bit, single ended mode, then channel select bits
        mosi = [control >> 2, (control & 0b11) << 6, 0x00] # See fig 6-1 in mcp3208 datasheet
        miso = self.spibus.xfer2(mosi)
        return self.ADC_VREF * (((miso[1] & 0xf) << 8) | miso[2]) / 4096

    def handshake(self):
        self.gpio.handshake()

    def payload_on(self):
        self.gpio.payload_on()

    def payload_off(self):
        self.gpio.payload_off()

    def solar_i_1(self):
        return self.sample(0) / 0.4
    
    def solar_v_1(self):
        return self.sample(1) * 8.5

    def solar_i_2(self):
        return self.sample(2) / 0.4

    def solar_v_2(self):
        return self.sample(3) * 8.5

    def batt_v(self):
        return self.sample(4) * 3

    def batt_i(self):
        return self.sample(5) / 0.4

    def payload_i(self):
        return self.sample(6) / 0.4