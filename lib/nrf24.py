#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
  Python Library for nRF24 Research Firmware

  Ported to Python 3 by Matthias Deeg

  Copyright (C) 2016 Bastille Networks
  Copyright (C) 2019 Matthias Deeg, SySS GmbH

  This program is free software: you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.

  This program is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.

  You should have received a copy of the GNU General Public License
  along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import logging
import usb

import struct

# Check pyusb dependency
try:
    from usb import core as _usb_core
except ImportError:
    print("""
------------------------------------------
| PyUSB was not found or is out of date. |
------------------------------------------

Please update PyUSB using pip:

sudo pip install -U -I pip && sudo pip install -U -I pyusb
""")
    import sys
    sys.exit(1)

# USB commands
TRANSMIT_PAYLOAD               = 0x04
ENTER_SNIFFER_MODE             = 0x05
ENTER_PROMISCUOUS_MODE         = 0x06
ENTER_TONE_TEST_MODE           = 0x07
TRANSMIT_ACK_PAYLOAD           = 0x08
SET_CHANNEL                    = 0x09
GET_CHANNEL                    = 0x0A
ENABLE_LNA_PA                  = 0x0B
TRANSMIT_PAYLOAD_GENERIC       = 0x0C
ENTER_PROMISCUOUS_MODE_GENERIC = 0x0D
RECEIVE_PAYLOAD                = 0x12

# nRF24LU1+ registers
RF_CH = 0x05

# RF data rates
RF_RATE_250K = 0
RF_RATE_1M   = 1
RF_RATE_2M   = 2


class nrf24:
    """Nordic Semiconductor nRF24LU1+ radio dongle"""

    # Sufficiently long timeout for use in a VM
    usb_timeout = 2500

    def __init__(self, index=0):
        """Constructor"""
        try:
            self.dongle = list(usb.core.find(idVendor=0x1915, idProduct=0x0102, find_all=True))[index]
            self.dongle.set_configuration()
        except usb.core.USBError as ex:
            raise ex
        except:
            raise Exception('Cannot find USB dongle.')

    def enter_promiscuous_mode(self, prefix=[], rate=RF_RATE_2M, addrlen=5):
        """Put the radio in pseudo-promiscuous mode"""

        data = struct.pack("BBB", rate, addrlen, len(prefix)) + prefix
        self.send_usb_command(ENTER_PROMISCUOUS_MODE, data)
        self.dongle.read(0x81, 64, timeout=nrf24.usb_timeout)
        if len(prefix) > 0:
            logging.debug('Entered promiscuous mode with address prefix {0}'.format(prefix))
        else:
            logging.debug('Entered promiscuous mode')

    def enter_promiscuous_mode_generic(self, prefix=b"", rate=RF_RATE_2M, payload_length=32):
        """Put the radio in pseudo-promiscuous mode without CRC checking"""

        data = struct.pack("BBB", len(prefix), rate, payload_length) + prefix
        self.send_usb_command(ENTER_PROMISCUOUS_MODE_GENERIC, data)

        self.dongle.read(0x81, 64, timeout=nrf24.usb_timeout)
        if len(prefix) > 0:
            logging.debug('Entered generic promiscuous mode with address prefix {0}'.format(prefix))
        else:
            logging.debug('Entered promiscuous mode')

    def enter_sniffer_mode(self, address, rate=RF_RATE_2M):
        """Put the radio in ESB "sniffer" mode (ESB mode w/o auto-acking)"""

        data = struct.pack("BB", rate, len(address)) + address
        self.send_usb_command(ENTER_SNIFFER_MODE, data)
        self.dongle.read(0x81, 64, timeout=nrf24.usb_timeout)
        logging.debug('Entered sniffer mode with address {0}'.format(address))
        # logging.debug('Entered sniffer mode with address {0}'.
                      # format(':'.join('{:02X}'.format(ord(b)) for b in address[::-1])))

    def enter_tone_test_mode(self):
        """Put the radio into continuous tone (TX) test mode"""

        self.send_usb_command(ENTER_TONE_TEST_MODE, b"")
        self.dongle.read(0x81, 64, timeout=nrf24.usb_timeout)
        logging.debug('Entered continuous tone test mode')

    def receive_payload(self):
        """Receive a payload if one is available"""

        self.send_usb_command(RECEIVE_PAYLOAD, b"")
        return self.dongle.read(0x81, 64, timeout=nrf24.usb_timeout)

    def transmit_payload_generic(self, payload, address=b"\x33\x33\x33\x33\x33"):
        """Transmit a generic (non-ESB) payload"""

        data = struct.pack("BB", len(payload), len(address)) + payload + address
        self.send_usb_command(TRANSMIT_PAYLOAD_GENERIC, data)
        return self.dongle.read(0x81, 64, timeout=nrf24.usb_timeout)[0] > 0

    def transmit_payload(self, payload, timeout=4, retransmits=15):
        """Transmit an ESB payload"""

        data = struct.pack("BBB", len(payload), timeout, retransmits) + payload
        self.send_usb_command(TRANSMIT_PAYLOAD, data)
        return self.dongle.read(0x81, 64, timeout=nrf24.usb_timeout)[0] > 0

    def transmit_ack_payload(self, payload):
        """Transmit an ESB ACK payload"""

        data = struct.pack("B", len(payload)) + payload
        self.send_usb_command(TRANSMIT_ACK_PAYLOAD, data)
        return self.dongle.read(0x81, 64, timeout=nrf24.usb_timeout)[0] > 0

    def set_channel(self, channel):
        """Set the RF channel"""

        if channel > 125:
            channel = 125

        data = struct.pack("B", channel)
        self.send_usb_command(SET_CHANNEL, data)
        self.dongle.read(0x81, 64, timeout=nrf24.usb_timeout)
        logging.debug('Tuned to {0}'.format(channel))

    def get_channel(self):
        """Get the current RF channel"""

        self.send_usb_command(GET_CHANNEL, b"")
        return self.dongle.read(0x81, 64, timeout=nrf24.usb_timeout)

    def enable_lna(self):
        """Enable the LNA (CrazyRadio PA)"""

        self.send_usb_command(ENABLE_LNA_PA, b"")
        self.dongle.read(0x81, 64, timeout=nrf24.usb_timeout)

    def send_usb_command(self, request, data):
        """Send a USB command"""

        data = struct.pack("B", request) + data
        self.dongle.write(0x01, data, timeout=nrf24.usb_timeout)
