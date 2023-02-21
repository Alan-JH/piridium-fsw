# Iridium 9602N Modem Driver

from serial import Serial
import time, datetime

# https://www.beamcommunications.com/document/328-iridium-isu-at-command-reference-v5
# https://docs.rockblock.rock7.com/reference/sbdwt
# https://www.ydoc.biz/download/IRDM_IridiumSBDService.pdf

# MO/Mobile Originated Buffer: Contains messages to be sent from iridium device
# MT/Mobile Terminated Buffer: Contains messages received from the Iridium constellation
# GSS: Iridium SBD Gateway Subsystem: Transfers messages from ISU to Ground
# ISU: Iridium Subscriber Unit: basically our radio
# FA: Field Application: basically our flight-pi

# FA <-UART/RS232 Interface-> ISU - MO buffer -> Iridium Constellation <-> GSS <-> IP Socket/Email
#                                <- MT buffer -
    
PORT = '/dev/serial0'
BAUDRATE = 19200

# Maximum permissible data size including descriptor size, in bytes. Hardware limitation should be 340 bytes total
MAX_DATASIZE = 300

EPOCH = datetime.datetime(2014, 5, 11, 14, 23, 55).timestamp()  # As of 2022, Epoch date is 5 May, 2014, at 14:23:55 GMT

LOAD_MSG_ERRORS = {1: "Iridium Timeout",
                    2: "Incorrect Checksum",
                    3: "Message too long"}

MODEM_INITIALIZED = False
serial = None

def check_initialized(func):
    """
    Decorator that checks whether GPIO has been initialized before attempting to interface
    """
    def wrap(*args, **kwargs):
        if MODEM_INITIALIZED:
            return func(*args, **kwargs)
        else:
            raise ValueError("GPIO Not yet initalized, you need to run start() first!")

    return wrap

def __is_hex(string):
    try:
        int(string, 16)
        return True
    except ValueError:
        return False

def start():
    """MUST be called after the modem is powered on"""
    if MODEM_INITIALIZED:
        raise Warning("GPIO Already Initialized!")
    else:
        serial = Serial(port=PORT, baudrate=BAUDRATE, timeout=1)  # connect serial
        while not serial.is_open:
            time.sleep(0.5)
        MODEM_INITIALIZED = True

@check_initialized
def shutdown():
    """
    Calls AT*F and closes serial
    """
    request("AT*F", 1)
    serial.close()
    MODEM_INITIALIZED = False

@check_initialized
def soft_reset():
    """
    Resets settings without a power cycle
    """
    request("ATZn", 1)
    
@check_initialized
def sbd_status():
    """
    Calls AT+SBDS
    SBDS return format: <MO flag>, <MOMSN>, <MT flag>, <MTMSN>
    MO flag: (1/0) whether message in mobile originated buffer
    MOMSN: sequence number that will be used in the next mobile originated SBD session
    MT flag: (1/0) whether message in mobile terminated buffer
    MTMSN: sequence number in the next mobile terminated SBD session, -1 if nothing in the MT buffer
    :return: (list) SBD Status return
    """
    return [int(i) for i in  process("AT+SBDS").split(",")]

@check_initialized
def read_mt():
    """
    Checks buffer for existing messages
    Doesnt use request because we don't to decode as utf-8
    :return: (list) raw list of bytes
    """
    write("AT+SBDRB")
    raw = serial.read(50)
    t = time.perf_counter()
    while raw.find(b'OK') == -1:
        if time.perf_counter() - t > 5:
            raise ValueError("Iridium Timeout")
        raw += serial.read(50)
    raw = raw[raw.find(b'SBDRB\r\n') + 7:].split(b'\r\nOK')[0]
    return list(raw)

@check_initialized
def load_mo(message):
    """
    Loads message into mo buffer
    :param message: (list) raw byte message to send
    """
    length = len(message)
    checksum = sum(message) & 0xffff
    message.append(checksum >> 8)  # add checksum bytes
    message.append(checksum & 0xff)
    # For SBDWB, input message byte length
    # Once "READY" is read in, write each byte, then the two least significant checksum bytes, MSB first
    # Final response: 0: success, 1: timeout (insufficient number of bytes transferred in 60 seconds)
    # 2: Checksum does not match calculated checksum, 3: message length too long or short
    # Keep messages 340 bytes or shorter for 9602N modem
    write(f"AT+SBDWB={length}")  # Specify bytes to write
    time.sleep(1)  # 1 second to respond
    if  read().find("READY") == -1:
        raise ValueError("Iridium Timeout")
    serial.write(message)
    time.sleep(1)  # 1 second to respond
    result = ""
    t = time.perf_counter()
    while result.find("OK") == -1:
        if time.perf_counter() - t > 5:
            raise ValueError("Iridium Timeout")
        result += read()
    i = int(result.split("\r\n")[1])  # '\r\n0\r\n\r\nOK\r\n' format
    if i in LOAD_MSG_ERRORS: raise ValueError(LOAD_MSG_ERRORS[i])

@check_initialized
def sbd_initiate_x():
    """
    AT+SBDIX call, initiates an SBD session and transfers messages out of MO buffer and into MT buffer
    SBDIX return format: <MO status>,<MOMSN>,<MT status>,<MTMSN>,<MT length>,<MT queued>
    MO status: 0: no message to send, 1: successful send, 2: error while sending
    MOMSN: sequence number for next MO transmission
    MT status: 0: no message to receive, 1: successful receive, 2: error while receiving
    MTMSN: sequence number for next MT receive
    MT length: length in bytes of received message
    MT queued: number of MT messages in GSS waiting to be transferred to ISU
    :return: (list) SBDIX call result
    """
    return [int(i) for i in  process("AT+SBDIX", timeout=60).split(",")]

@check_initialized
def clear_buffers():
    """
    Clears both SBD buffers
    """
    request("AT+SBDD2")

@check_initialized
def network_time():
    """
    Processed system time, GMT, retrieved from satellite network (used as a network check)
    MSSTM returns a 32 bit integer formatted in hex, with no leading zeros. Counts number of 90 millisecond intervals
    that have elapsed since the epoch
    :return: (datetime) current time (use str() to parse to string if needed)
    """
    raw = request("AT-MSSTM")
    if raw.find("OK") == -1 or raw.find("no network service") != -1:
        return None
    raw = raw.split("MSSTM:")[1].split("\n")[0].strip()
    if __is_hex(raw):
        processed = int(raw, 16) * 90 / 1000
        return datetime.datetime.fromtimestamp(processed + Iridium.EPOCH)

@check_initialized
def geolocation():
    """
    Geolocation at time of last contact with iridium constellation
    MSGEO return format: <x>, <y>, <z>, <time_stamp>
    time_stamp uses same 32 bit format as MSSTM, and indicates when the geolocation was last updated
    Converts from cartesian to lat/long/alt
    :return: (tuple) lat, long, altitude, time (unix timestamp)
    """
    raw = process("AT-MSGEO").split(",")  # raw x, y, z, timestamp
    timestamp_time = int(raw[3], 16) * 90 / 1000 + Iridium.EPOCH
    lon = math.degrees(math.atan2(float(raw[1]), float(raw[0])))
    lat = math.degrees(math.atan2(float(raw[2]), ((float(raw[1]) ** 2 + float(raw[0]) ** 2) ** 0.5)))
    alt = (float(raw[0]) ** 2 + float(raw[1]) ** 2 + float(raw[2]) ** 2) ** 0.5
    return (lat, lon, alt, timestamp_time)

@check_initialized
def register(location=None):
    """
    Performs a manual registration, consisting of attach and location update. No MO/MT messages transferred
    :param location: (str) Optional location param, format [+|-]DDMM.MMM,[+|-]dddmm.mmm
    :return: (str) raw processed result
    """
    if location: return process("AT+SBDREG", "=" + location)
    else: return process("AT+SBDREG")

@check_initialized
def check_signal_active():
    """
    Actively requests strength of satellite connection, may take up to ten seconds if iridium is in satellite handoff
    :return: (int) CSQ from 0 (weakest) to 5 (strongest)
    """
    raw = request("AT+CSQ", 10)  
    if raw.find("CSQ:") == -1:
        return 0
    return int(raw[raw.find("CSQ:") + 4: raw.find("CSQ:") + 5])

@check_initialized
def check_signal_passive():
    """
    Passively check signal strength, for transmit/receive timing. By default updates every 40 seconds
    :return: (int) last known CSQ from 0 (weakest) to 5 (strongest)
    """
    raw = request("AT+CSQF")  
    if raw.find("CSQF:") == -1:
        return 0
    return int(raw[raw.find("CSQF:") + 5: raw.find("CSQF:") + 6])

def process(cmd, arg="", timeout=0.5):
    """
    Clean up data string
    :param cmd: (str) command, including AT+ or AT- prefix
    :param arg: (str) argument
    :param timeout: (float) seconds before it gives up
    """
    data = request(cmd + arg, timeout)
    return data.split(cmd[3:] + ":")[1].split("\r\nOK")[0].strip()

def request(command: str, timeout=0.5) -> str:
    """
    Requests information from Iridium and returns unprocessed response
    :param command: Command to send
    :param timeout: maximum time to wait for a response
    :return: (str) Response from Iridium
    """
    serial.flush()
    write(command)
    result = ""
    sttime = time.perf_counter()
    while time.perf_counter() - sttime < timeout:
        time.sleep(.1)
        result +=  read()
        if result.find("ERROR") != -1:
            return command[2:] + "ERROR" + "\n"  # formatted so that process() can still decode properly
        if result.find("OK") != -1:
            return result
    raise ValueError("Iridium Timeout")

def write(command: str) -> bool:
    """
    Write a command to the serial port.
    :param command: (str) Command to write
    :return: (bool) if the serial write worked
    """
    serial.write((command + "\r").encode("utf-8"))

def read() -> str:
    """
    Reads in as many available bytes as it can if timeout permits.
    :return: (str) string read from iridium
    """
    output = bytes()
    for _ in range(50):
        try: next_byte = serial.read(size=1)
        except Exception: break
        if next_byte == bytes(): break
        output += next_byte
    return output.decode("utf-8")
