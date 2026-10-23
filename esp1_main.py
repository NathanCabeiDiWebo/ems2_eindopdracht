import network
import time
import socket
from machine import Pin, I2C

from wifi_secrets import SSID, PASSWORD

#i2c setup
i2c = I2C(0, scl=Pin(7), sda=Pin(6), freq=100000)
devices = i2c.scan()
RTC_ADDR = 0x6F

print("i2c chipadress:", devices)

if RTC_ADDR not in devices:
    raise OSError("MCP7940M RTC not found!")

def from_bcd(value):
    return ((value >> 4)*10) + (value & 0x0F)

def to_bcd(value):
    return ((value // 10) << 4) | (value % 10)

def init_rtc(datetime_string):
    date_part, time_part = datetime_string.split(" ")
    year, month, day = [int(x) for x in date_part.split("-")]
    hour, minute, second = [int(x) for x in time_part.split(":")]
    
    #format controle
    if not (2000 <= year <= 2099):
        raise ValueError("Year must be between 2000 and 2099")
    if not (1 <= month <= 12 and 1 <= day <= 31):
        raise ValueError("Invalid date")
    if not (0 <= hour <= 23 and 0 <= minute <= 59
            and 0 <= second <= 59):
        raise ValueError("Invalid time")

    weekday = time.mktime(
        (year, month, day, hour, minute, second, 0, 0)
    )
    weekday = time.localtime(weekday)[6] + 1

    # Preserve the RTC's battery-enable bit in the weekday register
    old_day = i2c.readfrom_mem(RTC_ADDR, 0x03, 1)[0]
    day_register = (old_day & 0x08) | weekday

    # MCP7940M registers: seconds, minutes, hours,
    # weekday, date, month, year
    registers = bytes([
        to_bcd(second) | 0x80,  # Start oscillator
        to_bcd(minute),
        to_bcd(hour),           # 24-hour format
        day_register,
        to_bcd(day),
        to_bcd(month) | (0x20 if
            (year % 4 == 0 and
             (year % 100 != 0 or year % 400 == 0))
            else 0),
        to_bcd(year - 2000)
    ])

    i2c.writeto_mem(RTC_ADDR, 0x00, registers)
    print("RTC time set:", datetime_string)


def get_rtc():
    registers = i2c.readfrom_mem(RTC_ADDR, 0x00, 7)

    second = from_bcd(registers[0] & 0x7F)
    minute = from_bcd(registers[1] & 0x7F)
    hour = from_bcd(registers[2] & 0x3F)
    day = from_bcd(registers[4] & 0x3F)
    month = from_bcd(registers[5] & 0x1F)
    year = 2000 + from_bcd(registers[6])

    return (
        "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}"
        .format(year, month, day, hour, minute, second)
    )


# Start the oscillator if it is not already enabled
seconds_register = i2c.readfrom_mem(RTC_ADDR, 0x00, 1)[0]
if not (seconds_register & 0x80):
    i2c.writeto_mem(
        RTC_ADDR, 0x00,
        bytes([seconds_register | 0x80])
    )

print("Current RTC time:", get_rtc())

#wifi setup
wlan = network.WLAN(network.STA_IF)
wlan.active(True)

wlan.connect(SSID, PASSWORD)  # Verbinden

print("Verbinding maken", end="")
while not wlan.isconnected():
    print(".", end="")
    time.sleep_ms(500)

print()

ip, subnet, gateway, dns = wlan.ifconfig()
print("IP-adres:\t", ip)
print("Subnetmasker:\t", subnet)
print("Gateway:\t", gateway)
print("DNS-server:\t", dns)

PORT = 2000
address = ("0.0.0.0", PORT)

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

server.bind(address)
server.listen(1)
server.settimeout(None)

print("TCP Server luistert op:", ip, "port:", PORT)

#main loop
while True:
    try:
        client, client_address = server.accept()
        print("Connected to:", client_address)

        try:
            while True:
                request = client.recv(100)
                
                if not request:
                    print("discon. from server")
                    break
                print("req received:", request)
                
                if request.strip() == b'GET_DATA':
                    message = (get_rtc() +"\n").encode()
                    client.send(message)
                    print("RTC tijd verstuurt:", message.strip())
                
                elif request.startswith(b"SET_TIME,"):
                    try:
                        datetime_string = request[9:].decode()
                        init_rtc(datetime_string)
                        client.send(b"OK\n")
                    except Exception as e:
                        print("RTC set error:", e)
                        client.send(b"ERROR\n")

                else:
                    client.send(b"UNKNOWN COMMAND\n")

        except OSError as e:
            print("Client disc.:", e)

        finally:
            client.close()
            print("Connection closed")

    except OSError as e:
        if len(e.args) == 0 or e.args[0] != 110:
            print("Waiting for client:", e)
