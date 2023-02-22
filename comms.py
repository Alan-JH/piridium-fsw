# High level radio handling

from drivers import iridium, gpio
import datetime
import copy

global MAX_PACKET_SIZE, HEADER_SIZE, FLOAT_LEN, TIME_ERR_THRESHOLD, \
    transmission_queue, received_queue, ENCODED_REGISTRY
MAX_PACKET_SIZE = 300
HEADER_SIZE = 4
FLOAT_LEN = 3
TIME_ERR_THRESHOLD = 120 # Acceptable time difference between RTC and Iridium network
transmission_queue = []
received_queue = []

ENCODED_REGISTRY = {
    0: "filler"
}


def start():
    """
    Starts all items
    """
    gpio.start()
    gpio.power_modem_on()
    iridium.start()


def disconnect():
    """
    Shuts down the Iridium modem
    """
    try:
        iridium.check_buffer()
        iridium.shutdown()
    except Exception: pass  # serial doesn't work
    gpio.power_modem_off()


def append_to_queue(packet):
    """
    Splits a packet, sets time of execution, and appends to the transmission queue
    To be called at execution time
    :param packet: (Packet) to split, process, and append
    """
    global transmission_queue
    data = packet.return_data
    split_packet_list = [data[0 + i:(MAX_PACKET_SIZE-HEADER_SIZE)//FLOAT_LEN + i] for i in range(
        0, len(data), (MAX_PACKET_SIZE-HEADER_SIZE)//FLOAT_LEN)]
    result = [copy.deepcopy(packet) for _ in range(len(ls))]
    for idx, packet in enumerate(split_packet_list): result[idx].return_data, result[idx].index = packet, idx
    for packet in result[::-1]: transmission_queue += [packet]


def peek_command_queue():
    """
    Returns first packet from the queue
    """
    return received_queue[0]


def pop_command_queue():
    """
    Removes and returns first packet in queue
    """
    return received_queue.pop(0)


def _encode(packet):
    """
    Encodes a packet to raw byte list. Does NOT consider packet length
    :param packet: (Packet) packet to encode
    :return: (List) encoded data
    """
    encoded_bytes_list = [(packet.index << 1) & 0x7f | packet.numerical] # First byte numerical/index
    date = (packet.timestamp.day << 11) | (packet.timestamp.hour << 6) | packet.timestamp.minute  # second and third bytes date
    encoded_bytes_list += [(date >> 8) & 0xff, date & 0xff, ENCODED_REGISTRY.index(packet.descriptor)]  # 1st date byte, 2nd date byte, 4th byte descriptor
    if packet.numerical: # Encode float data if applicable
        for n in packet.return_data:
            #  convert from float or int to twos comp half precision, bytes are MSB FIRST
            flt, exp = 0, int(math.floor(math.log10(abs(n)))) if n != 0 else 0
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
            encoded_bytes_list += [(flt >> 16) & 0xff, (flt >> 8) & 0xff, flt & 0xff]  # MSB FIRST, ..., # LSB LAST
    else:
        data = "".join(packet.return_data).encode("ascii")
        encoded_bytes_list += data
    return encoded


def _decode(message):
    """
    Decodes processed SBDRB output and converts to packet
    :param message: (byte string) sbdrb output
    :return: (packet) output packet
    """
    length = message[1] + (message[0] << 8) # check length (first two bytes) and checksum (last two bytes) against message length and sum
    checksum = message[-1] + (message[-2] << 8)
    msg = message[2:-2]

    if checksum != (sum(msg) & 0xffff) or length != len(msg): raise ValueError("Incorrect checksum/length")
    if msg[0] < 0 or msg[0] >= len(ENCODED_REGISTRY): raise ValueError("Invalid command received")
    command, args = ENCODED_REGISTRY[msg[0]], []
    for i in range(1, len(msg) - 2, 3):
        num = (msg[i] << 16) | (msg[i + 1] << 8) | (msg[i + 2])  # MSB first
        exp = num >> 19  # extract exponent
        if exp & (1 << 4) == 1: exp = (exp & 0x10) - (1 << 4)  # convert twos comp

        coef = num & 0x7ffff  # extract coefficient
        if coef & (1 << 18) == 1: coef = (coef & 0x3ffff) - (1 << 18)  # convert twos comp
        if coef != 0: coef /= 10 ** int(math.log10(abs(coef)))
        args += [coef * 10 ** exp]
    return Packet(command, args=args)


def contact():
    """
    Transmits contents of transmission queue while reading in messages to received queue
    """
    # Check receive buffer
    stat = iridium.sbd_status()
    if stat[2] == 1: received_queue.append(_decode(iridium.read_mt())) # add error handling

    # While signal, transmit and receive, and update buffers
    while gpio.read_network_available():
        if len(transmission_queue) > 0:
            msg = _encode(transmission_queue[0])
            iridium.load_mo(msg) # add error handling
            transmission_queue.pop(0)
        result = iridium.sbd_initiate_x() # add error handling
        if result[0] not in {0, 1, 2, 3, 4}:
            if result[0] in {10, 11, 12, 13, 14, 17, 18, 19, 32, 35, 36, 37, 38}: break  # no signal
            else: raise ValueError(details=f"Error transmitting buffer, error code {result[0]}")  # hardware issue
        
        if result[2] == 1: received_queue.append(_decode(iridium.read_mt())) # add error handling
        if (result[2] == 0 or result[2] == 2) and len(transmission_queue) == 0: break#issue: this will call sbdix one time more than necessary, rack up overcharges
    iridium.clear_buffers()  #clear sbd buffers


def update_time():
    """
    Updates system time from Iridium time
    """
    current_datetime = datetime.datetime.utcnow()
    time = iridium.network_time()
    if time is not None and abs((current_datetime - iridium_datetime).total_seconds()) > TIME_ERR_THRESHOLD:
        os.system(f"sudo date -s \"{iridium_datetime.strftime('%Y-%m-%d %H:%M:%S UTC')}\" ")  # Update system time
        os.system("sudo hwclock -w")  # Write to RTC        

def geolocation():
    return iridium.geolocation() # add error handling
    

class Packet:
    def __init__(self, descriptor, args=None, return_data=None):
        self.descriptor = descriptor
        self.args = args if args is not None else []
        if return_data is None: self.return_data, self.numerical = [], 1
        elif type(return_data) == list: self.numerical, self.return_data = 1, return_data
        elif type(return_data) == str: self.numerical, self.return_data = 0, list(return_data)
        else: ValueError(f"Invalid return data type of {type(return_data)} with data: {return_data}")
        self.timestamp, self.index = None, 0

    def __str__(self):
        return f"{self.descriptor} at {self.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}, index: {self.index}, numerical {self.numerical}: {self.return_data}"

    def set_time(self):
        self.timestamp = datetime.datetime.utcnow()