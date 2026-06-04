import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mqtt.MyMQTT import MQTTclient

def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)

def join_topic(*parts):
    return "/".join(str(part).strip("/") for part in parts if str(part).strip("/"))

class ThingSpeakAdaptor:
    def __init__(self, catalog_url):
        self.catalog_url = catalog_url.rstrip("/")
        self.pool = {}
        self.client = None
        self.load_config()

    def load_config(self):
        catalog = requests.get(f"{self.catalog_url}/catalog", timeout=5).json()
        self.thingspeak = catalog["thingspeak"]
        self.field_map = {
            sensor_type: config.get("thingspeak_field")
            for sensor_type, config in catalog.get("device_types", {}).get("sensors", {}).items()
        }
        self.update_sec = max(int(self.thingspeak.get("update_sec", 60)), 15)
        self.sensor_topic = join_topic(catalog["base_topic"], "+", "sensors", "#")
        if self.client is None:
            self.client = MQTTclient("thingspeak_adaptor", catalog["broker"], catalog["port"])
            self.client.register_callbacks(on_mes=self.notify)

    def start(self):
        self.client.start()
        self.client.subscribe(self.sensor_topic, qos=0)
        print(f"[ThingSpeak] subscribes {self.sensor_topic}")

    def notify(self, client, userdata, msg):
        payload = json.loads(msg.payload.decode("utf-8"))
        greenhouse_id = payload.get("greenhouse_id")
        if not greenhouse_id:
            return
        for event in payload.get("e", []):
            name = event["n"]
            value = float(event["v"])
            self.pool.setdefault(greenhouse_id, {}).setdefault(name, []).append(value)

    def average_payload(self, greenhouse_id, values_by_name):
        channel = self.thingspeak.get("channels", {}).get(greenhouse_id)
        if not channel:
            print(f"[ThingSpeak] no channel configured for {greenhouse_id}")
            return None
        payload = {"api_key": channel["api_key"]}
        for name, values in values_by_name.items():
            field = self.field_map.get(name)
            if field and values:
                payload[field] = sum(values) / len(values)
        return payload

    def upload(self, greenhouse_id, payload):
        if payload is None:
            return
        if len(payload) <= 1:
            print(f"[ThingSpeak] no data to upload for {greenhouse_id}")
            return
        if payload["api_key"].startswith("PUT_"):
            print(f"[ThingSpeak] api_key placeholder for {greenhouse_id}, skipped upload")
            return
        if not self.thingspeak.get("enabled", False):
            print(f"[ThingSpeak] mock upload for {greenhouse_id}: {payload}")
            return
        try:
            response = requests.post(self.thingspeak["endpoint"], data=payload, timeout=10)
            print(f"[ThingSpeak] {greenhouse_id} uploaded: {response.status_code} {response.text}")
        except requests.RequestException as exc:
            print(f"[ThingSpeak] {greenhouse_id} upload failed, will retry next cycle: {exc}")

    def run(self):
        self.start()
        while True:
            time.sleep(self.update_sec)
            self.load_config()
            snapshot = self.pool
            self.pool = {}
            for greenhouse_id, values_by_name in snapshot.items():
                payload = self.average_payload(greenhouse_id, values_by_name)
                self.upload(greenhouse_id, payload)


if __name__ == "__main__":
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "config" / "config.json"
    config = load_json(config_path)
    adaptor = ThingSpeakAdaptor(config["catalog_url"])
    adaptor.run()
