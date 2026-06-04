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

def get_greenhouse(catalog, greenhouse_id):
    for greenhouse in catalog["greenhouses"]:
        if greenhouse["greenhouse_id"] == greenhouse_id:
            return greenhouse
    raise ValueError(f"greenhouse_id not found: {greenhouse_id}")

NPK_DEVICE_LABELS = {
    "nitrogen_pump": "nitrogen_pump (N)",
    "phosphorus_pump": "phosphorus_pump (P)",
    "potassium_pump": "potassium_pump (K)"
}

def device_label(device):
    return NPK_DEVICE_LABELS.get(device, device)

class Controller:
    def __init__(self, catalog_url):
        self.catalog_url = catalog_url.rstrip("/")
        self.memory = {}
        self.thresholds = {}
        self.command_topics = {}
        self.actuators = {}
        self.control_sec = 5
        self.client = None
        self.sensor_topic = None
        self.load_config()

    def load_config(self):
        catalog = requests.get(f"{self.catalog_url}/catalog", timeout=5).json()
        base_topic = catalog["base_topic"]
        self.sensor_topic = join_topic(base_topic, "+", "sensors", "#")
        self.thresholds = {}
        self.command_topics = {}
        self.actuators = {}
        for greenhouse in catalog["greenhouses"]:
            greenhouse_id = greenhouse["greenhouse_id"]
            self.thresholds[greenhouse_id] = greenhouse["thresholds"]
            self.control_sec = int(greenhouse.get("control_sec", self.control_sec))
            self.command_topics.setdefault(greenhouse_id, {})
            self.actuators.setdefault(greenhouse_id, [])
            for actuator in greenhouse.get("actuators", []):
                device_id = actuator["device_id"]
                self.command_topics[greenhouse_id][device_id] = actuator["topic"]
                self.actuators[greenhouse_id].append(actuator)

        if self.client is None:
            self.client = MQTTclient("greenhouse_controller", catalog["broker"], catalog["port"])
            self.client.register_callbacks(on_mes=self.trigger)

    def start(self):
        self.client.start()
        self.client.subscribe(self.sensor_topic, qos=0)
        print(f"[Controller] subscribes {self.sensor_topic}")

    def trigger(self, client, userdata, msg):
        payload = json.loads(msg.payload.decode("utf-8"))
        greenhouse_id = payload.get("greenhouse_id")
        if not greenhouse_id:
            return
        for event in payload.get("e", []):
            name = event["n"]
            value = float(event["v"])
            self.memory.setdefault(greenhouse_id, {}).setdefault(name, []).append(value)

    def publish_command(self, greenhouse_id, device_id, action, priority=1, duration=None):
        topic = self.command_topics[greenhouse_id][device_id]
        command = {
            "greenhouse_id": greenhouse_id,
            "device_id": device_id,
            "action": action,
            "source": "controller",
            "priority": priority,
            "timestamp": int(time.time())
        }
        if duration is not None:
            command["duration"] = duration
        self.client.publish(topic, json.dumps(command), qos=0)
        print(f"[Controller] {greenhouse_id} {device_id} <- {action}")

    def publish_to_type(self, greenhouse_id, actuator_type, action, priority=1, duration=None):
        for actuator in self.actuators.get(greenhouse_id, []):
            if actuator["actuator_type"] == actuator_type:
                self.publish_command(
                    greenhouse_id,
                    actuator["device_id"],
                    action,
                    priority=priority,
                    duration=duration
                )

    def average_values(self, greenhouse_id):
        avg = {}
        for name, values in self.memory.get(greenhouse_id, {}).items():
            if values:
                avg[name] = sum(values) / len(values)
        self.memory[greenhouse_id] = {}
        return avg

    def greenhouse_ids(self):
        return list(self.thresholds.keys())

    def apply_rules(self, greenhouse_id, avg):
        thresholds = self.thresholds[greenhouse_id]
        if "temperature" in avg:
            temp = avg["temperature"]
            threshold = thresholds["temperature"]
            if temp > threshold["max"]:
                self.publish_to_type(greenhouse_id, "air_con", "ON", priority=4)
                self.publish_to_type(greenhouse_id, "heater", "OFF", priority=4)
            elif temp < threshold["min"]:
                self.publish_to_type(greenhouse_id, "heater", "ON", priority=4)
                self.publish_to_type(greenhouse_id, "air_con", "OFF", priority=4)
            else:
                self.publish_to_type(greenhouse_id, "air_con", "OFF", priority=4)
                self.publish_to_type(greenhouse_id, "heater", "OFF", priority=4)

        if "light" in avg:
            light = avg["light"]
            threshold = thresholds["light"]
            if light > threshold["shade_cloth_threshold"]:
                self.publish_to_type(greenhouse_id, "shade_cloth", "ON", priority=3)
                self.publish_to_type(greenhouse_id, "grow_light", "OFF", priority=3)
            elif light < threshold["min"]:
                self.publish_to_type(greenhouse_id, "grow_light", "ON", priority=2)
            else:
                self.publish_to_type(greenhouse_id, "grow_light", "OFF", priority=2)
                self.publish_to_type(greenhouse_id, "shade_cloth", "OFF", priority=2)

        if "soil_moist" in avg:
            soil = avg["soil_moist"]
            threshold = thresholds["soil_moist"]
            if soil < threshold["min"]:
                self.publish_to_type(greenhouse_id, "irrigation", "RUN_FOR_N_SECONDS", priority=3, duration=5)

        fert = thresholds["fertility"]
        if "fertility_n" in avg and avg["fertility_n"] < fert["min_n"]:
            self.publish_to_type(greenhouse_id, "nitrogen_pump", "RUN_FOR_N_SECONDS", priority=3, duration=5)
        if "fertility_p" in avg and avg["fertility_p"] < fert["min_p"]:
            self.publish_to_type(greenhouse_id, "phosphorus_pump", "RUN_FOR_N_SECONDS", priority=3, duration=5)
        if "fertility_k" in avg and avg["fertility_k"] < fert["min_k"]:
            self.publish_to_type(greenhouse_id, "potassium_pump", "RUN_FOR_N_SECONDS", priority=3, duration=5)

    def run(self):
        self.start()
        while True:
            self.load_config()
            for greenhouse_id in self.greenhouse_ids():
                avg = self.average_values(greenhouse_id)
                if avg:
                    print(f"[Controller] {greenhouse_id} average values: {avg}")
                    self.apply_rules(greenhouse_id, avg)
            time.sleep(self.control_sec)


if __name__ == "__main__":
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "config" / "config.json"
    config = load_json(config_path)
    controller = Controller(config["catalog_url"])
    controller.run()
