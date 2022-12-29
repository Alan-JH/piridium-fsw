# piridium-fsw
Flight Software Framework for Piridium Bus

Setup instructions - Raspberry Pi Zero with Raspbian Lite
Set date and time, connect to wifi
sudo apt install git
sudo apt install python3-pip
sudo apt install screen
pip3 install pyserial
pip3 install smbus2
sudo apt install i2c-tools
sudo raspi config
-enable i2c, spi, uart (do not allow login shell on serial)
git clone https://github.com/Alan-JH/piridium-fsw

set up RTC:
sudo apt-get -y remove fake-hwclock
sudo update-rc.d -f fake-hwclock remove
sudo systemctl disable fake-hwclock

sudo nano /boot/config.txt
add dtoverlay=i2c-rtc,ds3231 to the end of the file

sudo nano /lib/udev/hwclock-set

Comment out
if [ -e /run/systemd/system ] ; then
exit 0
fi

and

/sbin/hwclock --rtc=$dev --systz --badyear

and 

/sbin/hwclock --rtc=$dev --systz

save and reboot

set rtc time to pi time using sudo hwclock -w and read time from rtc using sudo hwclock -r. -r does not update system time

