# MCP3208 Driver

import spidev

class ADC():
    ADC_VREF = 3

    def __init__(self):
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
        return ADC_VREF * (((miso[1] & 0xf) << 8) | miso[2]) / 4096