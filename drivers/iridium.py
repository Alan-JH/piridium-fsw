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

def is_hex(string):
    try:
        int(string, 16)
        return True
    except ValueError:
        return False
    

class Iridium():
    PORT = '/dev/serial0'
    BAUDRATE = 19200

    # Maximum permissible data size including descriptor size, in bytes. Hardware limitation should be 340 bytes total
    MAX_DATASIZE = 300

    EPOCH = datetime.datetime(2014, 5, 11, 14, 23, 55).timestamp()  # As of 2022, Epoch date is 5 May, 2014, at 14:23:55 GMT

    def __init__(self, gpio):
        self.gpio = gpio
        self.gpio.modem_on()
        time.sleep(0.1)
        self.serial = Serial(port=self.PORT, baudrate=self.BAUDRATE, timeout=1)  # connect serial
        while not self.serial.is_open:
            time.sleep(0.5)

    def shutdown(self):
        """
        Calls AT*F and closes serial
        """
        self.radio.request("AT*F", 1)
        self.radio.serial.close()

    def net_avail(self):
        """
        Uses GPIO to determine whether network is available
        """
        return self.gpio.net_available()
        
    def sbd_status(self):
        """
        Calls AT+SBDS
        """
        return [int(i) for i in self.process("AT+SBDS").split(",")]

    def read_mt(self):
        """
        Checks buffer for existing messages
        Doesnt use request because we don't to decode as utf-8
        """
        self.write("AT+SBDRB")
        raw = self.serial.read(50)
        t = time.perf_counter()
        while raw.find(b'OK') == -1:
            if time.perf_counter() - t > 5:
                raise ValueError("Iridium Timeout")
            raw += self.serial.read(50)
        raw = raw[raw.find(b'SBDRB\r\n') + 7:].split(b'\r\nOK')[0]
        return list(raw)

    def load_mo(self, message):
        """
        Loads message into mo buffer
        :param message: (list) raw byte message to send
        """
        length = len(message)
        checksum = sum(message) & 0xffff
        message.append(checksum >> 8)  # add checksum bytes
        message.append(checksum & 0xff)
        self.SBD_WB(length)  # Specify bytes to write
        time.sleep(1)  # 1 second to respond
        if self.read().find("READY") == -1:
            raise ValueError("Iridium Timeout")
        self.serial.write(message)
        time.sleep(1)  # 1 second to respond
        result = ""
        t = time.perf_counter()
        while result.find("OK") == -1:
            if time.perf_counter() - t > 5:
                raise ValueError("Iridium Timeout")
            result += self.read()
        i = int(result.split("\r\n")[1])  # '\r\n0\r\n\r\nOK\r\n' format
        if i == 1:
            raise ValueError("Iridium Timeout")
        if i == 2:
            raise ValueError("Incorrect Checksum")
        if i == 3:
            raise ValueError("Message too long")

    def sbd_initiate_x(self):
        """
        AT+SBDIX call
        """
        return [int(i) for i in self.process("AT+SBDIX", timeout=60).split(",")]

    def clear_buffers(self):
        """
        Clears both SBD buffers
        """
        self.request("AT+SBDD2")

    def network_time(self):
        """
        System time, GMT, retrieved from satellite network (used as a network check)
        returns a 32 bit integer formatted in hex, with no leading zeros. Counts number of 90 millisecond intervals
        that have elapsed since the epoch
        Requests, reads, processes, and returns current system time retrieved from network
        :return: (datetime) current time (use str() to parse to string if needed)
        """
        raw = self.request("AT-MSSTM")
        if raw.find("OK") == -1:
            return None
        if raw.find("no network service") != -1:
            return None
        raw = raw.split("MSSTM:")[1].split("\n")[0].strip()
        if is_hex(raw):
            processed = int(raw, 16) * 90 / 1000
            return datetime.datetime.fromtimestamp(processed + Iridium.EPOCH)
        return None


    def geolocation(self):
        """
        Geolocation at time of last contact with iridium constellation
        raw return format: <x>, <y>, <z>, <time_stamp>
        time_stamp uses same 32 bit format as MSSTM, and indicates when the geolocation was last updated
        Converts from cartesian to lat/long/alt
        :return: (tuple) lat, long, altitude, time (unix timestamp)
        """
        raw = self.process("AT-MSGEO").split(",")  # raw x, y, z, timestamp
        timestamp_time = int(raw[3], 16) * 90 / 1000 + Iridium.EPOCH
        lon = math.degrees(math.atan2(float(raw[1]), float(raw[0])))
        lat = math.degrees(math.atan2(float(raw[2]), ((float(raw[1]) ** 2 + float(raw[0]) ** 2) ** 0.5)))
        alt = (float(raw[0]) ** 2 + float(raw[1]) ** 2 + float(raw[2]) ** 2) ** 0.5
        return (lat, lon, alt, timestamp_time)

    def register(self, location=None):
        """
        Performs a manual registration, consisting of attach and location update. No MO/MT messages transferred
        Optional param location: format [+|-]DDMM.MMM,[+|-]dddmm.mmm
        """
        if location:
            return self.process("AT+SBDREG", "=" + location)
        return self.process("AT+SBDREG")

    def check_signal_active(self):
        """
        Returns strength of satellite connection, may take up to ten seconds if iridium is in satellite handoff
        Actively check signal strength, for transmit/receive timing
        """
        raw = self.request("AT+CSQ", 10)  
        if raw.find("CSQ:") == -1:
            return 0
        return int(raw[raw.find("CSQ:") + 4: raw.find("CSQ:") + 5])

    def check_signal_passive(self):
        """
        Passively check signal strength, for transmit/receive timing. By default updates every 40 seconds
        """
        raw = self.request("AT+CSQF")  
        if raw.find("CSQF:") == -1:
            return 0
        return int(raw[raw.find("CSQF:") + 5: raw.find("CSQF:") + 6])

        self.RING_ALERT = lambda b="": self.request(f"AT+SBDMTA{b}")
        # Enable or disable ring indications for SBD Ring Alerts. When ring indication is enabled, ISU asserts RI
        # line and issues the unsolicited result code SBDRING when an SBD ring alert is received Ring alerts can only
        # be sent after the unit is registered :optional param b: set 1/0 enable/disable

        self.SOFT_RST = lambda: self.request("ATZn", 1)
        # Resets settings without power cycle

        # Load message into mobile originated buffer. SBDWT uses text, SBDWB uses binary. 
        self.SBD_WT = lambda message: self.request(f"AT+SBDWT={message}")
        # For SBDWB, input message byte length
        # Once "READY" is read in, write each byte, then the two least significant checksum bytes, MSB first
        # Final response: 0: success, 1: timeout (insufficient number of bytes transferred in 60 seconds)
        # 2: Checksum does not match calculated checksum, 3: message length too long or short
        # Keep messages 340 bytes or shorter
        self.SBD_WB = lambda length: self.write(f"AT+SBDWB={length}")
        # Read message from mobile terminated buffer. SBDRT uses text, SBDRB uses binary. Only one message is
        # contained in buffer at a time
        self.SBD_RT = lambda: self.request("AT+SBDRT")

        # Returns state of mobile originated and mobile terminated buffers
        # SBDS return format: <MO flag>, <MOMSN>, <MT flag>, <MTMSN>
        self.SBD_STATUS = lambda: self.request("AT+SBDS")  # beamcommunications 101-102
        # SBDSX return format: <MO flag>, <MOMSN>, <MT Flag>, <MTMSN>, <RA flag>, <msg waiting>
        self.SBD_STATUS_EX = lambda: self.request("AT+SBDSX")  # beamcommunications 103
        # MO flag: (1/0) whether message in mobile originated buffer
        # MOMSN: sequence number that will be used in the next mobile originated SBD session
        # MT flag: (1/0) whether message in mobile terminated buffer
        # MTMSN: sequence number in the next mobile terminated SBD session, -1 if nothing in the MT buffer
        # RA flag: (1/0) whether an SBD ring alert has been received and needs to be answered
        # msg waiting: how many SBD mobile terminated messages are queued at the gateway for collection by ISU

        self.SBD_TIMEOUT = lambda t=None: self.request(f"AT+SBDST={t}") if t else self.request("AT+SBDST")
        # Reads or sets session timeout settings, after which time ISU will stop trying to transmit/receive to GSS,
        # in seconds. 0 means infinite timeout

        self.SBD_TRANSFER_MOMT = lambda: self.request("AT+SBDTC")  # beamcommunications 104
        # Transfers contents of mobile originated buffer to mobile terminated buffer, to test reading and writing to
        # ISU without initiating SBD sessions with GSS/ESS returns response of the form "SBDTC: Outbound SBD copied
        # to Inbound SBD: size = <size>" followed by "OK", where size is message length in bytes

        # Transmits contents of mobile originated buffer to GSS, transfer oldest message in GSS queuefrom GSS to ISU
        self.SBD_INITIATE = lambda: self.request("AT+SBDI", 60)  # beamcommunications 94-95
        # Like SBDI but it always attempts SBD registration, consisting of attach and location update. a should be
        # "A" if in response to SBD ring alert, otherwise unspecified. location is an optional param,
        # format =[+|-]DDMM.MMM, [+|-]dddmm.mmm
        self.SBD_INITIATE_EX = lambda a="", location="": self.request("AT+SBDIX" + a, 60) if len(location) == 0 \
            else self.request("AT+SBDIX" + a + "=" + location)  # beamcommunications 95-96
        # returns: <MO status>,<MOMSN>,<MT status>,<MTMSN>,<MT length>,<MT queued>
        # MO status: 0: no message to send, 1: successful send, 2: error while sending
        # MOMSN: sequence number for next MO transmission
        # MT status: 0: no message to receive, 1: successful receive, 2: error while receiving
        # MTMSN: sequence number for next MT receive
        # MT length: length in bytes of received message
        # MT queued: number of MT messages in GSS waiting to be transferred to ISU

    def serial_test(self) -> bool:
        """
        Checks the state of the serial port (initializing it if needed) and verifies that AT returns OK
        :return: (bool) serial connection is working
        """
        if self.serial is None:
            self.serial = Serial(port=self.PORT, baudrate=self.BAUDRATE, timeout=1)  # connect serial
        self.serial.flush()
        result = self.request("AT", 1)  # Give Iridium one second to respond
        if result.find("OK") != -1:
            return True
        raise IridiumError(details="Serial test failed")

    def functional(self):
        """
        Tests Iridium by loading a message into one buffer, transferring to the other, and reading the message
        :return: (bool) buffers functional
        """
        self.serial_test()
        result = self.request("AT+SBDWT=test")
        if result.find("OK") == -1:
            return False
        result = self.request("AT+SBDTC", 1)
        if result.find("Outbound SBD Copied to Inbound SBD: size = 4") == -1:
            return False
        result = self.request("AT+SBDRT")
        if result.find("test") == -1:
            return False
        self.write("AT+SBDD2")  # clear all buffers
        return True

    def process(self, cmd, arg="", timeout=0.5):
        """
        Clean up data string
        :param cmd: (str) command, including AT+ or AT- prefix
        :param arg: (str) argument
        :param timeout: (float) seconds before it gives up
        """
        data = self.request(cmd + arg, timeout)
        return data.split(cmd[3:] + ":")[1].split("\r\nOK")[0].strip()

    def request(self, command: str, timeout=0.5) -> str:
        """
        Requests information from Iridium and returns unprocessed response
        :param command: Command to send
        :param timeout: maximum time to wait for a response
        :return: (str) Response from Iridium
        """
        self.serial.flush()
        self.write(command)
        result = ""
        sttime = time.perf_counter()
        while time.perf_counter() - sttime < timeout:
            time.sleep(.1)
            result += self.read()
            if result.find("ERROR") != -1:
                return command[2:] + "ERROR" + "\n"  # formatted so that process() can still decode properly
            if result.find("OK") != -1:
                return result
        raise ValueError("Iridium Timeout")

    def write(self, command: str) -> bool:
        """
        Write a command to the serial port.
        :param command: (str) Command to write
        :return: (bool) if the serial write worked
        """
        self.serial.write((command + "\r").encode("utf-8"))
        return True

    def read(self) -> str:
        """
        Reads in as many available bytes as it can if timeout permits.
        :return: (str) string read from iridium
        """
        output = bytes()
        for _ in range(50):
            try:
                next_byte = self.serial.read(size=1)
            except:
                break
            if next_byte == bytes():
                break
            output += next_byte
        return output.decode("utf-8")
