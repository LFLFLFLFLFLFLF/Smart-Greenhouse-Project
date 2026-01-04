import json
import time
import threading
from pathlib import Path
import requests
import paho.mqtt.client as mqtt

CONFIG = {
    "broker_host": "test.mosquitto.org",
    "broker_port": 1883,
    "sensor_topic": "polito/iot/group8/greenhouse/sensors",
    "update_sec": 60,
    "thingspeak_enabled": False,
    "thingspeak_endpoint": "https://api.thingspeak.com/update",
    "thingspeak_api_key": "YOUR_KEY"
}

latest = None
lock = threading.Lock()

def on_connect(client, userdata, flags, rc):
    print("[MQTT] connected rc=", rc)
    client.subscribe(CONFIG["sensor_topic"])
    print("[MQTT] subscribed:", CONFIG["sensor_topic"])

def on_message(client, userdata, msg):
    global latest
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        with lock:
            latest = payload
        print("[MQTT] got:", payload)
    except Exception as e:
        print("[MQTT] parse error:", e)

def upload_loop():
    while True:
        time.sleep(CONFIG["update_sec"])
        with lock:
            data = latest
        if not data:
            print("[ThingSpeak] no data yet")
            continue

        payload = {
            "api_key": CONFIG["thingspeak_api_key"],
            "field1": data.get("temperature"),
            "field2": data.get("humidity"),
            "field3": data.get("light"),
            "field4": data.get("soil_moist")
        }

        if not CONFIG["thingspeak_enabled"]:
            print("[ThingSpeak] mock upload:", payload)
            continue

        try:
            r = requests.post(CONFIG["thingspeak_endpoint"], data=payload, timeout=10)
            print("[ThingSpeak] uploaded:", r.status_code, r.text)
        except Exception as e:
            print("[ThingSpeak] upload error:", e)

def main():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(CONFIG["broker_host"], CONFIG["broker_port"], 60)

    t = threading.Thread(target=upload_loop, daemon=True)
    t.start()

    client.loop_forever()

if __name__ == "__main__":
    main()
