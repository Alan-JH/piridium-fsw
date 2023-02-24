# Iridium 9602N Modem Driver

from serial import Serial
import time, math
from datetime import datetime

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

# Maximum permissible data size including descriptor size, in bytes. Hardware limitation should be 340 bytes total
MAX_DATASIZE = 300

EPOCH = datetime(2014, 5, 11, 14, 23, 55).timestamp()  # As of 2022, Epoch date is 5 May, 2014, at 14:23:55 GMT

LOAD_MSG_ERRORS = { 1: "Iridium Timeout",
                    2: "Incorrect Checksum",
                    3: "Message too long" }

class Iridium:
    def __init__(self, port, baudrate):
        """
        MUST be called after the modem is powered on
        """
        self.serial = Serial(port=port, baudrate=baudrate, timeout=1)  # connect serial
        while not self.serial.is_open:
            time.sleep(0.5)


    def shutdown(self):
        """
        Calls AT*F and closes serial
        """
        self._request("AT*F", 1)
        self.serial.close()


    def soft_reset(self):
        """
        Resets settings without a power cycle
        """
        self._request("ATZn", 1)
        

    def sbd_status(self):
        """
        Calls AT+SBDS
        SBDS return format: <MO flag>, <MOMSN>, <MT flag>, <MTMSN>
        MO flag: (1/0) whether message in mobile originated buffer
        MOMSN: sequence number that will be used in the next mobile originated SBD session
        MT flag: (1/0) whether message in mobile terminated buffer
        MTMSN: sequence number in the next mobile terminated SBD session, -1 if nothing in the MT buffer
        :return: (list) SBD Status return
        """
        return [int(i) for i in self._process("AT+SBDS").split(",")]


    def read_mt(self):
        """
        Checks buffer for existing messages
        Doesnt use request because we don't to decode as utf-8
        :return: (list) raw list of bytes
        """
        self._write("AT+SBDRB")
        raw = self.serial.read(50)
        t = time.perf_counter()
        while raw.find(b'OK') == -1:
            if time.perf_counter() - t > 5: raise ValueError("Iridium Timeout")
            raw += self.serial.read(50)
        return list(raw[raw.find(b'SBDRB') + 6:].split(b'\r\nOK')[0])


    def load_mo(self, message):
        """
        Loads message into mo buffer
        :param message: (list) raw byte message to send
        """
        length = len(message)
        checksum = sum(message) & 0xffff
        message.append(checksum >> 8)  # add checksum bytes
        message.append(checksum & 0xff)
        self._write(f"AT+SBDWB={length}")  # Specify bytes to write
        time.sleep(1)  # 1 second to respond
        if self._read().find("READY") == -1: raise ValueError("Iridium Timeout")
        self.serial.write(message)  # Once "READY", write each byte, then the two LSB checksum bytes, MSB first
        time.sleep(1)  # 1 second to respond
        result, t = "", time.perf_counter()
        while result.find("OK") == -1:
            if time.perf_counter() - t > 5: raise ValueError("Iridium Timeout")
            result += self._read()
        i = int(result.split("\r\n")[1])  # '\r\n0\r\n\r\nOK\r\n' format
        if i in LOAD_MSG_ERRORS: raise ValueError(LOAD_MSG_ERRORS[i])


    def sbd_initiate_x(self):
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
        return [int(i) for i in self._process("AT+SBDIX", timeout=60).split(",")]


    def clear_buffers(self):
        """
        Clears both SBD buffers
        """
        self._request("AT+SBDD2")


    def network_time(self):
        """
        Processed system time, GMT, retrieved from satellite network (used as a network check)
        MSSTM returns a 32 bit integer formatted in hex, with no leading zeros. Counts number of 90 millisecond intervals
        that have elapsed since the epoch
        :return: (datetime) current time (use str() to parse to string if needed)
        """
        raw = self._request("AT-MSSTM")
        if raw.find("OK") != -1 and raw.find("no network service") == -1:
            raw = raw.split("MSSTM:")[1].split("\n")[0].strip()
            return datetime.fromtimestamp(int(raw, 16) * 90 / 1000 + EPOCH)

    def geolocation(self):
        """
        Geolocation at time of last contact with iridium constellation
        MSGEO return format: <x>, <y>, <z>, <time_stamp>
        time_stamp uses same 32 bit format as MSSTM, and indicates when the geolocation was last updated
        Converts from cartesian to lat/long/alt
        :return: (tuple) lat, long, altitude, time (unix timestamp)
        """
        raw = self._process("AT-MSGEO").split(",")  # raw x, y, z, timestamp
        location_timestamp = int(raw[3], 16) * 90 / 1000 + EPOCH
        # Convert XYZ cartesian to latitude, longitude, altitude
        lon = math.degrees(math.atan2(float(raw[1]), float(raw[0])))
        lat = math.degrees(math.atan2(float(raw[2]), ((float(raw[1]) ** 2 + float(raw[0]) ** 2) ** 0.5)))
        alt = (float(raw[0]) ** 2 + float(raw[1]) ** 2 + float(raw[2]) ** 2) ** 0.5
        return lat, lon, alt, location_timestamp


    def register(self, location=None):
        """
        Performs a manual registration, consisting of attach and location update. No MO/MT messages transferred
        :param location: (str) Optional location param, format [+|-]DDMM.MMM,[+|-]dddmm.mmm
        :return: (str) raw processed result
        """
        if location: return self._process("AT+SBDREG", "=" + location)
        else: return self._process("AT+SBDREG")


    def check_signal_active(self):
        """
        Actively requests strength of satellite connection, may take up to ten seconds if iridium is in satellite handoff
        This uses the serial interface rather than GPIO
        :return: (int) CSQ from 0 (weakest) to 5 (strongest)
        """
        raw = self._request("AT+CSQ", 10)  
        if raw.find("CSQ:") == -1: return 0
        return int(raw[raw.find("CSQ:") + 4: raw.find("CSQ:") + 5])


    def check_signal_passive(self):
        """
        Passively check signal strength, for transmit/receive timing. By default updates every 40 seconds
        This is the serial interface equivalent of checking net_avail using GPIO
        :return: (int) last known CSQ from 0 (weakest) to 5 (strongest)
        """
        raw = self._request("AT+CSQF")  
        if raw.find("CSQF:") == -1: return 0
        return int(raw[raw.find("CSQF:") + 5: raw.find("CSQF:") + 6])


    def _process(self, cmd, arg="", timeout=0.5):
        """
        Clean up data string
        :param cmd: (str) command, including AT+ or AT- prefix
        :param arg: (str) argument
        :param timeout: (float) seconds before it gives up
        """
        data = self._request(cmd + arg, timeout)
        return data.split(cmd[3:] + ":")[1].split("\r\nOK")[0].strip()


    def _request(self, command: str, timeout=0.5):
        """
        Requests information from Iridium and returns unprocessed response
        :param command: Command to send
        :param timeout: maximum time to wait for a response
        :return: (str) Response from Iridium
        """
        self.serial.flush()
        self._write(command)
        result, sttime = "", time.perf_counter()
        while time.perf_counter() - sttime < timeout:
            time.sleep(.1)
            result += self._read()
            if result.find("ERROR") != -1: return command[2:] + "ERROR" + "\n"  # formatted so that process() can still decode properly
            if result.find("OK") != -1: return result
        raise ValueError("Iridium Timeout")


    def _write(self, command: str):
        """
        Write a command to the serial port.
        :param command: (str) Command to write
        :return: (bool) if the serial write worked
        """
        self.serial.write((command + "\r").encode("utf-8"))


    def _read(self):
        """
        Reads in as many available bytes as it can if timeout permits.
        :return: (str) string read from iridium
        """
        output = bytes()
        for _ in range(50):
            try: next_byte = self.serial.read(size=1)
            except Exception: break
            if next_byte == bytes(): break
            output += next_byte
        return output.decode("utf-8")