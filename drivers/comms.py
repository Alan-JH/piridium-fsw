# High level radio handling

from iridium import Iridium
import datetime
import copy

class Comms():
    MAX_PACKET_SIZE = 300
    HEADER_SIZE = 4
    FLOAT_LEN = 3
    def __init__(self, gpio, time_err_threshold = 120):
        self.radio = Iridium(gpio)
        self.transmission_queue = []
        self.received_queue = []
        self.TIME_ERR_THRESHOLD = time_err_threshold # Two minutes acceptable time error between iridium and rtc

    def append_to_queue(self, packet):
        """
        Splits a packet, sets time of execution, and appends to the transmission queue
        To be called at execution time
        :param packet: (Packet) to split, process, and append
        """
        data = packet.return_data
        ls = [data[0 + i:(MAX_PACKET_SIZE-HEADER_SIZE)//FLOAT_LEN + i] for i in range(
            0, len(data), (MAX_PACKET_SIZE-HEADER_SIZE)//FLOAT_LEN)]
        result = [copy.deepcopy(packet) for _ in range(len(ls))]
        for _ in range(len(ls)):
            result[_].return_data = ls[_]
            result[_].index = _
        for i in range(len(result) - 1, -1, -1):
            self.transmission_queue.append(result[i])


    def __encode(self, packet):
        """
        Encodes a packet to raw byte list. Does NOT consider packet length
        :param packet: (Packet) packet to encode
        :return: (List) encoded data
        """
        encoded = [(packet.index << 1) & 0x7f | packet.numerical] # First byte numerical/index
        date = (packet.timestamp.day << 11) | (packet.timestamp.hour << 6) | packet.timestamp.minute  # second and third bytes date
        encoded.append((date >> 8) & 0xff)
        encoded.append(date & 0xff)
        encoded.append(self.ENCODED_REGISTRY.index(packet.descriptor)) # Fourth byte descriptor
        if packet.numerical: # Encode float data if applicable
            for n in packet.return_data:
                #  convert from float or int to twos comp half precision, bytes are MSB FIRST
                flt = 0
                exp = int(math.floor(math.log10(abs(n)))) if n != 0 else 0
                if exp < 0:
                    exp = (1 << 4) - (abs(exp) & 0xf) # make sure exp is 4 bits, cut off anything past the 4th, take abs val and twos comp
                    flt |= 1 << 23 # set sign bit
                flt |= (exp & 0xf) << 19  # make sure exp is 4 bits, cut off anything past the 4th, shift left 19. Leaves sign untouched
                # num will always have five digits, with trailing zeros if necessary to fill it in
                num = abs(int((n / (10 ** exp)) * 10000))
                if n < 0:
                    num = (1 << 18) - (num & 0x3ffff)  # make sure num is 18 bits long, then twos comp
                    flt |= (1 << 18)  # set sign bit
                flt |= num & 0x3ffff  # make sure num is 18 bits long (in the positive case), leaves sign untouched
                encoded += [(flt >> 16) & 0xff, (flt >> 8) & 0xff, flt & 0xff]  # MSB FIRST, ..., # LSB LAST
        else:
            data = "".join(packet.return_data).encode("ascii")
            for d in data: encoded.append(d)
        return encoded

    def __decode(self, message):
        """
        Decodes processed SBDRB output and converts to packet
        :param message: (byte string) sbdrb output
        :return: (packet) output packet
        """
        length = message[1] + (message[0] << 8) # check length (first two bytes) and checksum (last two bytes) against message length and sum
        checksum = message[-1] + (message[-2] << 8)
        msg = message[2:-2]

        if checksum != (sum(msg) & 0xffff) or length != len(msg):
            raise ValueError("Incorrect checksum/length")
        if msg[0] < 0 or msg[0] >= len(self.ENCODED_REGISTRY):
            raise ValueError("Invalid command received")
        command = self.ENCODED_REGISTRY[msg[0]]
        args = []
        for i in range(1, len(msg) - 2, 3):
            num = (msg[i] << 16) | (msg[i + 1] << 8) | (msg[i + 2])  # MSB first
            exp = num >> 19  # extract exponent
            if exp & (1 << 4) == 1:  # convert twos comp
                exp = (exp & 0x10) - (1 << 4)
            coef = num & 0x7ffff  # extract coefficient
            if coef & (1 << 18) == 1:  # convert twos comp
                coef = (coef & 0x3ffff) - (1 << 18)
            if coef != 0:
                coef /= 10 ** int(math.log10(abs(coef)))
            args.append(coef * 10 ** exp)
        return Packet(command, args=args)
    
    def contact(self):
        """
        Transmits contents of transmission queue while reading in messages to received queue, and updates time with Iridium time
        """
        # Check receive buffer
        stat = self.radio.sbd_status()
        if stat[2] == 1:
            self.received_queue.append(self.decode(self.radio.read_mt())) # add error handling

        # While signal, transmit and receive, and update buffers
        while self.radio.net_avail():
            if len(self.transmission_queue) > 0:
                msg = self.encode(self.transmission_queue[0])
                self.radio.load_mo(msg) # add error handling
                self.transmission_queue.pop(0)
            result = self.radio.sbd_initiate_x() # add error handling
            if result[0] not in [0, 1, 2, 3, 4]:
                if result[0] in [10, 11, 12, 13, 14, 17, 18, 19, 32, 35, 36, 37, 38]:
                    # These all vaguely indicate no signal, or at least the issue is not hardware fault
                    break
                else:
                    raise ValueError(details=f"Error transmitting buffer, error code {result[0]}")
            
            if result[2] == 1:
                self.received_queue.append(self.decode(self.radio.read_mt())) # add error handling
            
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
        return self.radio.geolocation() # add error handling

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
    def __init__(self, descriptor, args=[], return_data=None):
        self.descriptor = ""
        self.args = []
        if return_data is None:
            self.return_data = []
            self.numerical = 1
        elif type(return_data) == list:
            self.numerical = 1
            self.return_data = return_data
        elif type(return_data) == str:
            self.numerical = 0
            self.return_data = list(return_data)
        self.timestamp = None
        self.index = 0
    
    def __str__(self):
        return f"{self.descriptor} at {self.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}, index: {self.index}, numerical {self.numerical}: {self.return_data}"

    def set_time(self):
        self.timestamp = datetime.datetime.utcnow()