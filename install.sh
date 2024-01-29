#!/bin/bash

# install pip
apt-get install -y python3-pip

# allow system-wide installation of Python packages via pip
rm /usr/lib/python3.11/EXTERNALLY-MANAGED

# activate I2C port
raspi-config nonint do_i2c 0

# change I2C bus speed
sed -i 's/dtparam=i2c_arm=on/dtparam=i2c_arm=on,i2c_arm_baudrate=400000/g' /boot/config.txt

# install additional packages
apt-get install -y python3-pip git
pip3 install pyusb
pip3 install adafruit-circuitpython-charlcd

# install init.d service
cp ./init.d/radiohackbox /etc/init.d/
chmod +x /etc/init.d/radiohackbox
update-rc.d radiohackbox defaults

# install udev rule
cp rules.d/99-crazyflie.rules /etc/udev/rules.d/

# configure read-only file system
sudo apt-get -y install git
cd /home/pi
git clone https://github.com/JasperE84/root-ro.git
cd root-ro
chmod +x install.sh
./install.sh
reboot
