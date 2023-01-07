# High level radio handling

from iridium import Iridium

class Comms():
    def __init__(self, gpio):
        self.radio = Iridium(gpio)
        self.transmission_queue = []
        self.received_queue = []
        self.TIME_ERR_THRESHOLD = 120 # Two minutes acceptable time error between iridium and rtc

    def split_packet(self, message):
        #call before appending to transmission queue

    def encode(self, message):

    def decode(self, message, msn):
    
    def contact(self, timeout):
        # Establishes contact with SBDI, updates time
        # Check receive buffer
        stat = self.radio.sbd_status()
        if stat[2] == 1:
            self.received_queue.append(self.decode(self.radio.read_mt(), stat[3])) # add error handling

        # While signal, transmit and receive, and update buffers
        while self.radio.net_avail():
            if len(self.transmission_queue) > 0:
                msg = self.encode(self.transmission_queue[0])
                self.radio.load_mo(msg) # add error handling
                self.transmission_queue.pop(0)
            result = self.radio.sbd_initiate_x() # add error handling
            if result[2] == 1:
                self.received_queue.append(self.decode(self.radio.read_mt(), result[3])) # add error handling
            
            if (result[2] == 0 or result[2] == 2) and len(self.transmission_queue) == 0: #issue: this will call sbdix one time more than necessary, rack up overcharges
                break
        
        # update time
        current_datetime = datetime.datetime.utcnow()
        time = self.radio.network_time()
        if time is not None and abs((current_datetime - iridium_datetime).total_seconds()) > self.TIME_ERR_THRESHOLD:
            os.system(f"sudo date -s \"{iridium_datetime.strftime('%Y-%m-%d %H:%M:%S UTC')}\" ")
            # Update system time
            os.system("sudo hwclock -w")  # Write to RTC        

    def geolocation(self, timeout):
        # Registers and returns geolocation
        # sbd registration
        # geolocation call

    def disconnect(self):
        # shuts down iridium
    

class Packet():
    