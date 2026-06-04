import json
import sys
from copy import deepcopy
from pathlib import Path

import cherrypy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def join_topic(*parts):
    return "/".join(str(part).strip("/") for part in parts if str(part).strip("/"))

def is_multiple(device_config):
    return device_config.get("mode") == "multiple"

def device_name(greenhouse_id, device_type, index, device_config):
    if is_multiple(device_config):
        return f"{greenhouse_id}_{device_type}_{index}"
    return f"{greenhouse_id}_{device_type}"

def topic_name(greenhouse_id, device_id):
    return device_id.removeprefix(f"{greenhouse_id}_")

def single_device_conflict(greenhouse_id, device_kind, device_type, existing):
    cherrypy.response.status = 409
    return {
        "status": "error",
        "message": f"{greenhouse_id} already has {device_type} {device_kind}. No new device was added.",
        "existing_device": existing
    }

class CatalogUtils:
    def __init__(self, file_path):
        self.file_path = file_path
        self.data = self.load()

    def load(self):
        with open(self.file_path, "r", encoding="utf-8") as file:
            return json.load(file)

    def save(self):
        with open(self.file_path, "w", encoding="utf-8") as file:
            json.dump(self.data, file, indent=4)

    def greenhouse(self, greenhouse_id):
        for greenhouse in self.data["greenhouses"]:
            if greenhouse["greenhouse_id"] == greenhouse_id:
                return greenhouse
        raise cherrypy.HTTPError(404, "greenhouse not found")

class Catalog:
    exposed = True

    def __init__(self, catalog):
        self.catalog = catalog

    @cherrypy.tools.json_out()
    def GET(self, *uri, **params):
        self.catalog.data = self.catalog.load()
        if not uri or uri[0] == "catalog":
            return self.catalog.data

        if uri[0] == "greenhouses":
            greenhouse_id = params.get("greenhouse_id")
            if greenhouse_id:
                return self.catalog.greenhouse(greenhouse_id)
            return {"ids": [g["greenhouse_id"] for g in self.catalog.data["greenhouses"]]}

        if uri[0] == "devices":
            greenhouse_id = params.get("greenhouse_id")
            if not greenhouse_id:
                return self.catalog.data["greenhouses"]
            greenhouse = self.catalog.greenhouse(greenhouse_id)
            return {
                "sensors": greenhouse["sensors"],
                "actuators": greenhouse["actuators"]
            }

        raise cherrypy.HTTPError(404, "resource not found")

    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def POST(self, *uri, **params):
        if not uri:
            raise cherrypy.HTTPError(404, "resource not found")

        self.catalog.data = self.catalog.load()
        body = deepcopy(cherrypy.request.json)

        if uri[0] == "greenhouses":
            greenhouse_id = body.get("greenhouse_id", "").strip()
            if not greenhouse_id:
                raise cherrypy.HTTPError(400, "greenhouse_id is required")
            for greenhouse in self.catalog.data["greenhouses"]:
                if greenhouse["greenhouse_id"] == greenhouse_id:
                    return {"status": "already_registered", "greenhouse": greenhouse}

            defaults = self.catalog.data.get("greenhouse_defaults", {})
            greenhouse = {
                "greenhouse_id": greenhouse_id,
                "plant_type": body.get("plant_type", "unknown"),
                "sampling_sec": int(body.get("sampling_sec", defaults.get("sampling_sec", 5))),
                "control_sec": int(body.get("control_sec", defaults.get("control_sec", 5))),
                "thresholds": deepcopy(body.get("thresholds", defaults.get("thresholds", {}))),
                "sensors": [],
                "actuators": []
            }
            self.catalog.data["greenhouses"].append(greenhouse)
            channels = self.catalog.data.get("thingspeak", {}).setdefault("channels", {})
            if greenhouse_id not in channels:
                channels[greenhouse_id] = {"api_key": body.get("thingspeak_api_key", "PUT_WRITE_API_KEY_HERE")}
            self.catalog.save()
            return {"status": "registered", "greenhouse": greenhouse}

        if uri[0] != "devices":
            raise cherrypy.HTTPError(404, "resource not found")

        greenhouse_id = body.get("greenhouse_id", "").strip()
        if not greenhouse_id:
            raise cherrypy.HTTPError(400, "greenhouse_id is required")
        greenhouse = self.catalog.greenhouse(greenhouse_id)
        broker = self.catalog.data["broker"]
        port = self.catalog.data["port"]
        base_topic = self.catalog.data["base_topic"]
        device_types = self.catalog.data.get("device_types", {})

        if body["type"] == "sensor":
            sensor_type = body["sensor_type"]
            sensor_config = device_types.get("sensors", {}).get(sensor_type)
            if sensor_config is None:
                raise cherrypy.HTTPError(400, "unknown sensor_type")
            if not is_multiple(sensor_config):
                existing = next(
                    (s for s in greenhouse["sensors"] if s["sensor_type"] == sensor_type),
                    None
                )
                if existing:
                    return single_device_conflict(greenhouse_id, "sensor", sensor_type, existing)
            index = len([s for s in greenhouse["sensors"] if s["sensor_type"] == sensor_type])
            device_id = device_name(greenhouse_id, sensor_type, index, sensor_config)
            topic = join_topic(base_topic, greenhouse_id, "sensors", topic_name(greenhouse_id, device_id))
            device = {
                "device_id": device_id,
                "type": "sensor",
                "sensor_type": sensor_type,
                "topic": topic
            }
            greenhouse["sensors"].append(device)
        elif body["type"] == "actuator":
            actuator_type = body["actuator_type"]
            actuator_config = device_types.get("actuators", {}).get(actuator_type)
            if actuator_config is None:
                raise cherrypy.HTTPError(400, "unknown actuator_type")
            if not is_multiple(actuator_config):
                existing = next(
                    (a for a in greenhouse["actuators"] if a["actuator_type"] == actuator_type),
                    None
                )
                if existing:
                    return single_device_conflict(greenhouse_id, "actuator", actuator_type, existing)
            index = len([a for a in greenhouse["actuators"] if a["actuator_type"] == actuator_type])
            device_id = device_name(greenhouse_id, actuator_type, index, actuator_config)
            topic = join_topic(base_topic, greenhouse_id, "commands", topic_name(greenhouse_id, device_id))
            device = {
                "device_id": device_id,
                "type": "actuator",
                "actuator_type": actuator_type,
                "topic": topic
            }
            greenhouse["actuators"].append(device)
        else:
            raise cherrypy.HTTPError(400, "type must be sensor or actuator")

        self.catalog.save()
        return {
            "broker": broker,
            "port": port,
            "topic": topic,
            "device_id": device_id,
            "device": device,
            "status": "registered"
        }

    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def PUT(self, *uri, **params):
        if not uri or uri[0] != "greenhouses":
            raise cherrypy.HTTPError(404, "resource not found")
        greenhouse_id = params.get("greenhouse_id")
        if not greenhouse_id:
            raise cherrypy.HTTPError(400, "greenhouse_id is required")
        greenhouse = self.catalog.greenhouse(greenhouse_id)
        greenhouse.update(deepcopy(cherrypy.request.json))
        self.catalog.save()
        return {"status": "ok", "greenhouse_id": greenhouse_id}


if __name__ == "__main__":
    catalog = CatalogUtils(ROOT / "config" / "catalog.json")
    conf = {
        "/": {
            "request.dispatch": cherrypy.dispatch.MethodDispatcher(),
            "tools.response_headers.on": True,
            "tools.response_headers.headers": [("Content-Type", "application/json")]
        }
    }
    cherrypy.config.update({"server.socket_host": "127.0.0.1", "server.socket_port": 8080})
    cherrypy.tree.mount(Catalog(catalog), "/", conf)
    cherrypy.engine.start()
    cherrypy.engine.block()
