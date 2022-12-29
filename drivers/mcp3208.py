# MCP3208 Driver

import spidev

ADC_VREF = 3.3

class ADC():
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
        return ((miso[1] & 0xf) << 8) | miso[2]

    def solar_i_1(self):
        return (ADC_VREF * self.sample(0) / 4096) / 0.4

    def solar_v_1(self):
        return (ADC_VREF * self.sample(1) / 4096) * 8.5

    def solar_i_2(self):
        return (ADC_VREF * self.sample(2) / 4096) / 0.4

    def solar_v_2(self):
        return (ADC_VREF * self.sample(3) / 4096) * 8.5

    def batt_v(self):
        return (ADC_VREF * self.sample(4) / 4096) * 3

    def batt_i(self):
        return (ADC_VREF * self.sample(5) / 4096) / 0.4

    def payload_i(self):
        return (ADC_VREF * self.sample(6) / 4096) / 0.4