import network
import time
import socket
from machine import Pin, SPI

SPI_TRANSFER_SIZE = 20

#spi init
spi = SPI(
    1,
    baudrate=100000,
    polarity=0,
    phase=0,
    bits=8,
    firstbit=SPI.MSB,
    sck=Pin(4),
    mosi=Pin(5),
    miso=Pin(6)
)

cs = Pin(7, Pin.OUT, value=1)

#set (write) datetime command to/from mcxa rtc
def set_rtc_spi(datetime_string):
    datetime_bytes = datetime_string.encode("ascii")

    if len(datetime_bytes) != 19:
        raise ValueError("Datetime must be YYYY-MM-DD HH:MM:SS")

    # 19 characters + terminating null byte = 20 bytes
    tx_data = bytearray(SPI_TRANSFER_SIZE)
    tx_data[:19] = datetime_bytes
    rx_data = bytearray(SPI_TRANSFER_SIZE)

    cs.value(0)
    time.sleep_us(10)
    try:
        spi.write_readinto(tx_data, rx_data)
    finally:
        time.sleep_us(10)
        cs.value(1)

    print("SET_DATE sent!:", datetime_string)

#read datetime command to/from mcxa rtc
def get_rtc_spi():
    #send command for read datetime
    tx_data = bytearray(SPI_TRANSFER_SIZE)
    tx_data[:8] = b"GET_DATE"
    rx_data = bytearray(SPI_TRANSFER_SIZE)
    
    cs.value(0)
    time.sleep_us(10)
    try:
        spi.write_readinto(tx_data, rx_data)
    finally:
        time.sleep_us(10)
        cs.value(1)
    print("GET_DATE sent!:")
    
    #wait and recieve reply from mcxa
    time.sleep_ms(50)
    tx_data = bytearray(SPI_TRANSFER_SIZE)
    rx_data = bytearray(SPI_TRANSFER_SIZE)
    
    cs.value(0)
    time.sleep_us(10)
    
    try:
        spi.write_readinto(tx_data, rx_data)
    finally:
        time.sleep_us(10)
        cs.value(1)
    
    datetime_bytes = bytes(rx_data).split(b"\x00", 1)[0]
    try:
        datetime_string = datetime_bytes.decode("ascii").strip()
        if len(datetime_string) != 19:
            raise ValueError("Invalid String length")
        
        #verify format yyyy-mm-dd hh:mm:ss
        if (
            datetime_string[4] != "-"
            or datetime_string[7] != "-"
            or datetime_string[10] != " "
            or datetime_string[13] != ":"
            or datetime_string[16] != ":"
        ):
            raise ValueError("Invalid format")

        print("Datetime received!:", datetime_string)
        return datetime_string

    except (UnicodeError, ValueError) as e:
        print("Invalid data from MCXA156:", bytes(rx_data))
        raise ValueError("no valid time, topa g") from e

#wait for mcxa156 to boot up and start running
time.sleep_ms(2000)

#connect to wifi
# SSID = input("wifi name: ")
# PASSWORD = input("Password: ")
SSID = "Stink"
PASSWORD = "69696969"

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

#udp discoveryto connect esp1 to esp2
DISCOVERY_PORT = 2001

udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
udp_socket.bind(("0.0.0.0", DISCOVERY_PORT))
udp_socket.settimeout(0)

print("UDP discovery luistert op poort:", DISCOVERY_PORT)


def check_discovery():
    try:
        data, sender = udp_socket.recvfrom(100)

        if data.strip() == b"ESP1_DISCOVER":
            response = "ESP1_HERE," + ip + "," + str(TCP_PORT)
            udp_socket.sendto(response.encode(), sender)

            print("Discovery request van:", sender)
            print("Discovery response:", response)

    except OSError:
        # als er geen packet is tijdens het wachten
        pass

#tcp server setup
TCP_PORT = 2000
address = ("0.0.0.0", TCP_PORT)

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

server.bind(address)
server.listen(1)
server.settimeout(0.1)

print("TCP Server luistert op:", ip, "port:", TCP_PORT)

#verwerk tcp commands (SET_TIME & GET_TIME)
def handle_command(request):
    request = request.strip()

    print("Request received:", request)

    if request.startswith(b"SET_DATE,"):
        try:
            datetime_string = request.split(b",", 1)[1].decode("ascii").strip()
            set_rtc_spi(datetime_string)
            return b"SENT\n"

        except Exception as e:
            print("RTC se fue rip:", e)
            return b"ERROR\n"

    elif request == b"GET_DATE":
        try:
            datetime_string = get_rtc_spi()
            return datetime_string.encode("ascii") + b"\n"
        except Exception as e:
            print("RTC READ ERROR:", e)
            return b"GET_DATE ERROR\n"

    else:
        print("Unknown command:", request)
        return b"UNKNOWN COMMAND\n"
    
#main loop
while True:
    check_discovery()
    try:
        client, client_address = server.accept()
    
    except OSError:
        #blijf checken of er clients zijn om te verbinden
        continue
    
    print("Connected to:", client_address)
    request_buffer = b""
        
    #tcp socket exchange
    try:
        while True:
            request = client.recv(100)
            
            if not request:
                print("client se fue")
                break
            request_buffer += request
            
            #verwerk tcp commandos
            while b"\n" in request_buffer:
                command, request_buffer = request_buffer.split(b"\n", 1)
                response = handle_command(command)
                client.sendall(response)
                print("response sent:", response.strip())

    except OSError as e:
        print("TCP a hode:", e)
    
    finally:
        client.close()
        print("Connection closed")
        

