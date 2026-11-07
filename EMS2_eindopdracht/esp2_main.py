import network
import time
import socket
import binascii
from machine import Pin
from umqtt.simple import MQTTClient

# knop voor datum socketreq
knop = Pin(10, Pin.IN, Pin.PULL_UP)
knop_last = 1

# mqtt command function
def bericht_ontvangen(topic, bericht):
    print("mqtt topic recvd:", topic.decode())
    print("mqtt bericht recvd:", bericht.decode())

    if topic == INITDATETOPIC:
        try:
            datumtijd = bericht.decode().strip()
            if len(datumtijd) != 19:
                print("invalid format")
                return

            command = "SET_DATE," + datumtijd
            antwoord = tcp_request(command)
            print("datumtijd verzonden:", command)
            print("antwoord ESP1:", antwoord)

        except OSError as e:
            print("topa RTC:", e)

# tcp command function
def tcp_request(command):
    message = (command + "\n").encode()
    socket_naar_server.sendall(message)
    print("TCP Req. sent!:", command)

    response = bytearray()
    while True:
        data = socket_naar_server.recv(100)
        if not data:
            raise OSError("ESP TCP a hode")
        response.extend(data)

        if b"\n" in response:
            break

    antwoord = bytes(response).split(b"\n", 1)[0].decode().strip()
    return antwoord

# wait for mcxa156 to boot up and start running
time.sleep_ms(3000)

# connect to wifi
# SSID = input("wifi name: ")
# PASSWORD = input("Password: ")
SSID = "Stink"
PASSWORD = "69696969"

wlan = network.WLAN(network.STA_IF)
wlan.active(True)

wlan.connect(SSID, PASSWORD)

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

# Zoek ESP1 via UDP discovery
DISCOVERY_PORT = 2001
TCP_PORT = 2000

ESP1_IP = None

udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
udp_socket.settimeout(2)

try:
    print("Zoeken naar ESP1...")

    while ESP1_IP is None:
        udp_socket.sendto(
            b"ESP1_DISCOVER",
            ("255.255.255.255", DISCOVERY_PORT)
        )

        try:
            response, address = udp_socket.recvfrom(100)

            message = response.decode().strip()
            print("UDP antwoord:", message)

            parts = message.split(",")

            if len(parts) == 3 and parts[0] == "ESP1_HERE":
                ESP1_IP = parts[1]
                TCP_PORT = int(parts[2])

        except OSError:
            print("ESP1 niet gevonden. Opnieuw zoeken...")
            time.sleep_ms(2000)

finally:
    udp_socket.close()

# Verbind ESP2 naar ESP1 TCP server
socket_naar_server = None

while socket_naar_server is None:
    try:
        address = (ESP1_IP, TCP_PORT)

        tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_socket.settimeout(3)
        tcp_socket.connect(address)

        socket_naar_server = tcp_socket

    except OSError:
        print("TCP verbinding mislukt. Opnieuw proberen...")
        tcp_socket.close()
        time.sleep_ms(2000)

print("connected to esp1 tcp server")
print("on ip and port:", address)

# mqtt and connect to broker
BROKER = "broker.hivemq.com"
MQTTPORT = 1883
STUDNR = "1070608"

ESP2_ID = binascii.hexlify(wlan.config('mac')).decode()
CLIENT_ID = ("ESP2" + ESP2_ID).encode()
print("ClientID:", CLIENT_ID)

BASISTOPIC = "/ems2/" + STUDNR
INITDATETOPIC = (BASISTOPIC + "/initdatetime").encode()
DATUMTOPIC = (BASISTOPIC + "/datetime").encode()

print("Wi-Fi connected:", wlan.isconnected())
print("Broker:", BROKER, "Port:", MQTTPORT)

client = MQTTClient(CLIENT_ID, BROKER, MQTTPORT, keepalive=60)
client.set_callback(bericht_ontvangen)
client.connect()
client.subscribe(INITDATETOPIC)

print("verbonden met MQTT BROKER:", BROKER)
print("Subbed topic:", INITDATETOPIC.decode())
print("Publish topic:", DATUMTOPIC.decode())

last_ping = time.ticks_ms()

print("Node-RED editor: http://localhost:1880")
print("EMS2 Dashboard: http://localhost:1880/dashboard")

# main loop
try:
    while True:
        knop_state = knop.value()

        # ask for current datetime from rtc and upload to broker
        if knop_state == 0 and knop_last == 1:
            time.sleep_ms(50)

            if knop.value() == 0:
                try:
                    data = tcp_request("GET_DATE")
                    if len(data) == 19 and data[4] == "-":
                        client.publish(DATUMTOPIC, data.encode())
                        print("published time to dashboard:", data)
                    else:
                        print("invalid RTC time.")

                except OSError as e:
                    print("communication a hode:", e)

        knop_last = knop_state

        # receive setdate from node red
        client.check_msg()

        if time.ticks_diff(time.ticks_ms(), last_ping) >= 30000:
            client.ping()
            last_ping = time.ticks_ms()

        time.sleep_ms(20)

finally:
    if socket_naar_server is not None:
        socket_naar_server.close()

    client.disconnect()
    print("topa g")
