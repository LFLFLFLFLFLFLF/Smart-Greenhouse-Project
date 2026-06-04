import json
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

class Actuator:
    def __init__(self, greenhouse_id, device, broker, port, label, states):
        self.greenhouse_id = greenhouse_id
        self.actuator_type = device["actuator_type"]
        self.device_id = device["device_id"]
        self.broker = broker
        self.port = port
        self.label = label
        self.topic = device["topic"]
        self.states = states
        self.client = MQTTclient(self.device_id, self.broker, self.port)
        self.client.register_callbacks(on_mes=self.notify)
        self.states.setdefault(self.greenhouse_id, {})[self.device_id] = {
            "device_id": self.device_id,
            "actuator_type": self.actuator_type,
            "state": "OFF",
            "source": "startup",
            "priority": 0,
            "updated_at": int(time.time())
        }

    def start(self):
        self.client.start()
        self.client.subscribe(self.topic, qos=0)
        print(f"[Actuator] {self.greenhouse_id} {self.label} subscribes {self.topic}")

    def notify(self, client, userdata, msg):
        command = json.loads(msg.payload.decode("utf-8"))
        target_device = command.get("device_id", command.get("device"))
        if target_device != self.device_id:
            return
        action = command.get("action")
        if action not in ["ON", "OFF", "RUN_FOR_N_SECONDS"]:
            return
        incoming_priority = int(command.get("priority", 0))
        current_priority = int(self.states.get(self.greenhouse_id, {}).get(self.device_id, {}).get("priority", 0))
        if incoming_priority < current_priority:
            print(
                f"[Actuator] ignored lower priority command for "
                f"{self.device_id}: {incoming_priority} < {current_priority}"
            )
            return

        if action == "RUN_FOR_N_SECONDS":
            state = "ON"
            duration = int(command.get("duration", 5))
            threading.Thread(target=self.auto_off, args=(duration, command.get("source", "unknown")), daemon=True).start()
        else:
            state = action

        self.states.setdefault(self.greenhouse_id, {})[self.device_id] = {
            "device_id": self.device_id,
            "actuator_type": self.actuator_type,
            "state": state,
            "source": command.get("source", "unknown"),
            "priority": incoming_priority,
            "updated_at": int(time.time())
        }
        print(f"[Actuator] {self.device_id} -> {state}")

    def auto_off(self, duration, source):
        time.sleep(duration)
        self.states.setdefault(self.greenhouse_id, {})[self.device_id] = {
            "device_id": self.device_id,
            "actuator_type": self.actuator_type,
            "state": "OFF",
            "source": f"{source}_auto_stop",
            "priority": 0,
            "updated_at": int(time.time())
        }
        print(f"[Actuator] {self.device_id} -> OFF")

class ActuatorREST:
    exposed = True

    def __init__(self, states, command_topics, mqtt_client, token):
        self.states = states
        self.command_topics = command_topics
        self.mqtt_client = mqtt_client
        self.token = token

    @cherrypy.tools.json_out()
    def GET(self, *uri, **params):
        if len(uri) == 3 and uri[0] == "actuators" and uri[2] == "status":
            greenhouse_id = uri[1]
            return {"greenhouse_id": greenhouse_id, "states": self.states.get(greenhouse_id, {})}
        raise cherrypy.HTTPError(404, "resource not found")

    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def POST(self, *uri, **params):
        if len(uri) != 3 or uri[0] != "actuators" or uri[2] != "override":
            raise cherrypy.HTTPError(404, "resource not found")

        auth = cherrypy.request.headers.get("Authorization", "")
        if auth != "Bearer " + self.token:
            raise cherrypy.HTTPError(401, "Unauthorized")

        body = cherrypy.request.json
        greenhouse_id = body.get("greenhouse_id", uri[1])
        device_id = body.get("device_id", body.get("device"))
        if device_id not in self.command_topics.get(greenhouse_id, {}):
            raise cherrypy.HTTPError(404, "device_id not found")
        command = {
            "greenhouse_id": greenhouse_id,
            "device_id": device_id,
            "action": body["action"],
            "source": "manual_override",
            "priority": 10,
            "timestamp": int(time.time())
        }
        if "duration" in body:
            command["duration"] = body["duration"]
        topic = self.command_topics[greenhouse_id][device_id]
        self.mqtt_client.publish(topic, json.dumps(command), qos=0)
        return {"status": "sent", "topic": topic, "command": command}

def start_actuator(device, greenhouse, catalog, states, command_topics, actuators):
    device_id = device["device_id"]
    greenhouse_id = greenhouse["greenhouse_id"]
    command_topics.setdefault(greenhouse_id, {})[device_id] = device["topic"]
    if device_id in actuators:
        return
    actuator_config = catalog["device_types"]["actuators"][device["actuator_type"]]
    label = actuator_config.get("label", device["actuator_type"])
    actuator = Actuator(greenhouse_id, device, catalog["broker"], catalog["port"], label, states)
    actuator.start()
    actuators[device_id] = actuator

def sync_actuators(catalog_url, states, command_topics, actuators):
    while True:
        try:
            catalog = requests.get(f"{catalog_url}/catalog", timeout=5).json()
            for greenhouse in catalog["greenhouses"]:
                for device in greenhouse.get("actuators", []):
                    start_actuator(device, greenhouse, catalog, states, command_topics, actuators)
        except requests.RequestException as exc:
            print(f"[Actuator] catalog sync failed: {exc}")
        time.sleep(10)


if __name__ == "__main__":
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "config" / "config.json"
    config = load_json(config_path)
    catalog_url = config["catalog_url"].rstrip("/")
    catalog = requests.get(f"{catalog_url}/catalog", timeout=5).json()

    states = {}
    command_topics = {}
    actuators = {}

    rest_client = MQTTclient("actuator_rest_client", catalog["broker"], catalog["port"])
    rest_client.start()
    threading.Thread(
        target=sync_actuators,
        args=(catalog_url, states, command_topics, actuators),
        daemon=True
    ).start()

    conf = {
        "/": {
            "request.dispatch": cherrypy.dispatch.MethodDispatcher(),
            "tools.response_headers.on": True,
            "tools.response_headers.headers": [("Content-Type", "application/json")]
        }
    }
    cherrypy.config.update({"server.socket_host": "127.0.0.1", "server.socket_port": 8002})
    cherrypy.tree.mount(
        ActuatorREST(states, command_topics, rest_client, config["admin_token"]),
        "/",
        conf
    )
    cherrypy.engine.start()
    cherrypy.engine.block()
