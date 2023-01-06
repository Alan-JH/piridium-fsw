# High level radio handling

from iridium import Iridium

class Comms():
    def __init__(self, gpio):
        self.radio = Iridium(gpio)
        self.transmission_queue = []
        self.received_queue = []

    def encode(self, message):

    def decode(self, message):
    
    def contact(self, timeout):
        # Establishes contact with SBDI, updates time

    def geolocation(self, timeout):
        # Registers and returns geolocation

    def disconnect(self):
        # shuts down iridium
    

