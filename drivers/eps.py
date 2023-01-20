# High Level EPS telemetry and telecommand
from mcp3208 import ADC

class EPS():
    def __init__(self, gpio):
        self.gpio = gpio
        self.adc = ADC()

    def handshake(self):
        self.gpio.handshake()

    def payload_on(self):
        self.gpio.payload_on()

    def payload_off(self):
        self.gpio.payload_off()

    def solar_i_1(self):
        return self.adc.sample(0) / 0.4
    
    def solar_v_1(self):
        return self.adc.sample(1) * 8.5

    def solar_i_2(self):
        return self.adc.sample(2) / 0.4

    def solar_v_2(self):
        return self.adc.sample(3) * 8.5

    def batt_v(self):
        return self.adc.sample(4) * 3

    def batt_i(self):
        return self.adc.sample(5) / 0.4

    def payload_i(self):
        return self.adc.sample(6) / 0.4