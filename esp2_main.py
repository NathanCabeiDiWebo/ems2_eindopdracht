import network
import time
import socket
import binascii
from machine import Pin
from umqtt.simple import MQTTClient

from wifi_secrets import SSID, PASSWORD

#knop voor datum socketreq en led voor mqtt publishing
knop = Pin(10, Pin.IN, Pin.PULL_UP)
knop_last = 1
led = Pin(0, Pin.OUT)
led.off()

def toggle_led():
    for _ in range(3):
        led.on()
        time.sleep_ms(100)
        led.off()
        time.sleep_ms(100)
    

def bericht_ontvangen(topic, bericht):
    print("mqtt topic recvd:", topic.decode())
    print("mqtt bericht recvd:", bericht.decode())

    if topic == INITDATETOPIC:
        try:
            datumtijd = bericht.decode().strip()
            command = ("SET_TIME," + datumtijd).encode()

            socket_naar_server.send(command)
            print("datumtijd verzonden:", command)

            antwoord = socket_naar_server.recv(200)
            print("antwoord ESP1:", antwoord)
    
        except OSError as e:
            print("topa RTC")
    
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

#Verbind esp2 naar esp1 tcp server
ESP2_IP = "10.254.117.245" #esp1 server ip
PORT = 2000

address = (ESP2_IP, PORT)
socket_naar_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

socket_naar_server.connect(address)

print("connected to esp1 server")
print("on ip and port:", address)
    
#connect to broker
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

#main loop 
try:
    while True:
        knop_state = knop.value()
        if knop_state == 0 and knop_last == 1:
            time.sleep_ms(50)
            if knop.value() == 0:
                try:
                    socket_naar_server.send(b"GET_DATA\n")
                    print("req sent")
                    data = socket_naar_server.recv(200)
                    if data:
                        data = data.strip()
                        print("Reactie server:", data)
                        client.publish(DATUMTOPIC, data)
                        print("published on mqtt:", data)
                        toggle_led()
                    else:
                        print("connection's closed")
                        
                except OSError as e:
                    print("Communication error:", e)
                    
        knop_last = knop_state
        client.check_msg()
        
        if time.ticks_diff(time.ticks_ms(), last_ping) >= 30000:
            client.ping()
            last_ping = time.ticks_ms()
            
        time.sleep_ms(20)

finally:
    socket_naar_server.close()
    client.disconnect()
    print("topa g")
