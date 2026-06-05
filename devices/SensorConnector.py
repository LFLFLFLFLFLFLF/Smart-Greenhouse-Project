import json
import random
import sys
import threading
import time
from pathlib import Path

import cherrypy
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mqtt.MyMQTT import MQTTclient

def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)

def get_greenhouse(catalog, greenhouse_id):
    for greenhouse in catalog["greenhouses"]:
        if greenhouse["greenhouse_id"] == greenhouse_id:
            return greenhouse
    raise ValueError(f"greenhouse_id not found: {greenhouse_id}")

class Sensor:
    def __init__(self, greenhouse_id, device, broker, port, unit, latest):
        self.greenhouse_id = greenhouse_id
        self.sensor_type = device["sensor_type"]
        self.device_id = device["device_id"]
        self.broker = broker
        self.port = port
        self.topic = device["topic"]
        self.unit = unit
        self.latest = latest
        self.client = MQTTclient(self.device_id, self.broker, self.port)
        self.active = True

    def get_value(self):
        if self.sensor_type == "temperature":
            return round(random.uniform(18, 32), 2)
        if self.sensor_type == "humidity":
            return round(random.uniform(40, 90), 2)
        if self.sensor_type == "light":
            return round(random.uniform(0, 7000), 2)
        if self.sensor_type == "co2":
            return round(random.uniform(350, 1200), 2)
        if self.sensor_type == "soil_moist":
            return round(random.uniform(20, 90), 2)
        return round(random.uniform(20, 90), 2)

    def run(self, freq):
        self.client.start()
        print(f"[Sensor] {self.greenhouse_id} {self.sensor_type} publishes to {self.topic}", flush=True)
        while self.active:
            value = self.get_value()
            message = {
                "bn": self.device_id,
                "greenhouse_id": self.greenhouse_id,
                "device_id": self.device_id,
                "sensor_type": self.sensor_type,
                "e": [
                    {
                        "n": self.sensor_type,
                        "v": value,
                        "u": self.unit,
                        "t": int(time.time())
                    }
                ]
            }
            self.latest.setdefault(self.greenhouse_id, {})[self.device_id] = message
            self.client.publish(self.topic, json.dumps(message), qos=0)
            time.sleep(freq)
        print(f"[Sensor] {self.device_id} stopped", flush=True)

    def stop(self):
        self.active = False
        self.latest.get(self.greenhouse_id, {}).pop(self.device_id, None)
        if not self.latest.get(self.greenhouse_id):
            self.latest.pop(self.greenhouse_id, None)
        try:
            self.client.finalize()
        except Exception as exc:
            print(f"[Sensor] {self.device_id} MQTT finalize failed: {exc}", flush=True)

class SensorREST:
    exposed = True

    def __init__(self, latest):
        self.latest = latest

    @cherrypy.tools.json_out()
    def GET(self, *uri, **params):
        if len(uri) == 3 and uri[0] == "sensors" and uri[2] == "latest":
            greenhouse_id = uri[1]
            return {"greenhouse_id": greenhouse_id, "latest": self.latest.get(greenhouse_id, {})}
        raise cherrypy.HTTPError(404, "resource not found")

def start_sensor(device, greenhouse, catalog, latest, running_sensors):
    device_id = device["device_id"]
    if device_id in running_sensors:
        return
    greenhouse_id = greenhouse["greenhouse_id"]
    freq = int(greenhouse.get("sampling_sec", 5))
    sensor_config = catalog["device_types"]["sensors"][device["sensor_type"]]
    sensor = Sensor(greenhouse_id, device, catalog["broker"], catalog["port"], sensor_config["unit"], latest)
    thread = threading.Thread(target=sensor.run, args=(freq,), daemon=True)
    running_sensors[device_id] = sensor
    thread.start()

def sync_sensors(catalog_url, latest, running_sensors):
    while True:
        try:
            catalog = requests.get(f"{catalog_url}/catalog", timeout=5).json()
            catalog_device_ids = set()
            for greenhouse in catalog["greenhouses"]:
                for device in greenhouse.get("sensors", []):
                    catalog_device_ids.add(device["device_id"])
                    start_sensor(device, greenhouse, catalog, latest, running_sensors)
            for device_id in list(running_sensors):
                if device_id not in catalog_device_ids:
                    running_sensors.pop(device_id).stop()
        except Exception as exc:
            print(f"[Sensor] catalog sync failed: {exc}", flush=True)
        time.sleep(10)


if __name__ == "__main__":
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "config" / "config.json"
    config = load_json(config_path)
    catalog_url = config["catalog_url"].rstrip("/")
    latest = {}
    running_sensors = {}
    threading.Thread(
        target=sync_sensors,
        args=(catalog_url, latest, running_sensors),
        daemon=True
    ).start()

    conf = {
        "/": {
            "request.dispatch": cherrypy.dispatch.MethodDispatcher(),
            "tools.response_headers.on": True,
            "tools.response_headers.headers": [("Content-Type", "application/json")]
        }
    }
    cherrypy.config.update({"server.socket_host": "127.0.0.1", "server.socket_port": 8001})
    cherrypy.tree.mount(SensorREST(latest), "/", conf)
    cherrypy.engine.start()
    cherrypy.engine.block()
