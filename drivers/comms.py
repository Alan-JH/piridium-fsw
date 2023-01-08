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
    
    def contact(self):
        """
        Transmits contents of transmission queue while reading in messages to received queue, and updates time with Iridium time
        """
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
            if result[0] not in [0, 1, 2, 3, 4]:
                match result[0]:
                    case 33:
                        raise ValueError(details="Error transmitting buffer, Antenna fault")
                    case 16:
                        raise ValueError(details="Error transmitting buffer, ISU locked")
                    case 15:
                        raise ValueError(details="Error transmitting buffer, Gateway reports that Access is Denied")
                    case 10 | 11| 12 | 13 | 14 | 17 | 18 | 19 | 32 | 35 | 36 | 37 | 38: 
                        # These all vaguely indicate no signal, or at least the issue is not hardware fault
                        break
                    case 65:
                        raise ValueError(details="Error transmitting buffer, Hardware Error (PLL Lock failure)")
                    case 34:
                        raise ValueError(details="Error transmitting buffer, Radio is disabled (see AT*Rn)")
                    case _:
                        raise ValueError(details=f"Error transmitting buffer, error code {result[0]}")
            if result[2] == 1:
                self.received_queue.append(self.decode(self.radio.read_mt(), result[3])) # add error handling
            
            if (result[2] == 0 or result[2] == 2) and len(self.transmission_queue) == 0: #issue: this will call sbdix one time more than necessary, rack up overcharges
                break
        #clear sbd buffers
        self.radio.clear_buffers()

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
        """
        Shuts down the Iridium modem
        """
        try:
            self.radio.check_buffer()
            self.radio.shutdown()
        except:  # serial doesn't work
            pass
        self.radio.gpio.modem_off()
    

class Packet():
    