import json
import os
import sys
from pathlib import Path

import cherrypy
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SENSOR_TYPES = [
    "temperature",
    "humidity",
    "light",
    "co2",
    "soil_moist",
    "fertility_n",
    "fertility_p",
    "fertility_k"
]

def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)

class Dashboard:
    exposed = True

    def __init__(self, catalog_url, default_greenhouse_id, sensor_url, actuator_url, token):
        self.catalog_url = catalog_url.rstrip("/")
        self.default_greenhouse_id = default_greenhouse_id
        self.sensor_url = sensor_url.rstrip("/")
        self.actuator_url = actuator_url.rstrip("/")
        self.token = token
        self.actions = ["ON", "OFF", "RUN_FOR_N_SECONDS"]

    def catalog(self):
        return requests.get(f"{self.catalog_url}/catalog", timeout=5).json()

    def greenhouse(self, catalog, greenhouse_id):
        for greenhouse in catalog["greenhouses"]:
            if greenhouse["greenhouse_id"] == greenhouse_id:
                return greenhouse
        return catalog["greenhouses"][0]

    def index(self):
        cherrypy.response.headers["Content-Type"] = "text/html"
        with open(Path(__file__).resolve().parent / "index.html", "r", encoding="utf-8") as file:
            return file.read().encode("utf-8")

    def GET(self, *uri, **params):
        if not uri:
            return self.index()
        if len(uri) == 2 and uri[0] == "api" and uri[1] == "state":
            greenhouse_id = params.get("greenhouse_id", self.default_greenhouse_id)
            try:
                sensors = requests.get(f"{self.sensor_url}/sensors/{greenhouse_id}/latest", timeout=2).json()
            except Exception as exc:
                sensors = {"error": str(exc)}
            try:
                actuators = requests.get(f"{self.actuator_url}/actuators/{greenhouse_id}/status", timeout=2).json()
            except Exception as exc:
                actuators = {"error": str(exc)}
            cherrypy.response.headers["Content-Type"] = "application/json"
            return json.dumps({"sensors": sensors, "actuators": actuators}).encode("utf-8")
        if len(uri) == 2 and uri[0] == "api" and uri[1] == "options":
            catalog = self.catalog()
            greenhouse_id = params.get("greenhouse_id", self.default_greenhouse_id)
            greenhouse = self.greenhouse(catalog, greenhouse_id)
            cherrypy.response.headers["Content-Type"] = "application/json"
            return json.dumps({
                "greenhouses": [
                    {
                        "greenhouse_id": greenhouse["greenhouse_id"],
                        "plant_type": greenhouse.get("plant_type", "unknown")
                    }
                    for greenhouse in catalog["greenhouses"]
                ],
                "default_greenhouse_id": self.default_greenhouse_id,
                "sensor_types": SENSOR_TYPES,
                "actuator_types": catalog.get("actuator_types", []),
                "device_labels": catalog.get("actuator_labels", {}),
                "sensors": greenhouse.get("sensors", []),
                "actuators": greenhouse.get("actuators", []),
                "actions": self.actions
            }).encode("utf-8")
        raise cherrypy.HTTPError(404, "resource not found")

    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def POST(self, *uri, **params):
        if len(uri) == 2 and uri[0] == "api" and uri[1] == "override":
            body = cherrypy.request.json
            greenhouse_id = body.get("greenhouse_id", params.get("greenhouse_id", self.default_greenhouse_id))
            body["greenhouse_id"] = greenhouse_id
            response = requests.post(
                f"{self.actuator_url}/actuators/{greenhouse_id}/override",
                json=body,
                headers={"Authorization": "Bearer " + self.token},
                timeout=3
            )
            return {"status_code": response.status_code, "response": response.text}
        if len(uri) == 2 and uri[0] == "api" and uri[1] == "greenhouses":
            body = cherrypy.request.json
            response = requests.post(f"{self.catalog_url}/greenhouses", json=body, timeout=5)
            return {"status_code": response.status_code, "response": response.json()}
        if len(uri) == 2 and uri[0] == "api" and uri[1] == "devices":
            body = cherrypy.request.json
            response = requests.post(f"{self.catalog_url}/devices", json=body, timeout=5)
            return {"status_code": response.status_code, "response": response.json()}
        raise cherrypy.HTTPError(404, "resource not found")


if __name__ == "__main__":
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "config" / "config.json"
    config = load_json(config_path)
    catalog_url = config["catalog_url"].rstrip("/")
    catalog = requests.get(f"{catalog_url}/catalog", timeout=5).json()
    services = catalog["services"]

    conf = {
        "/": {
            "request.dispatch": cherrypy.dispatch.MethodDispatcher(),
            "tools.staticdir.root": os.path.dirname(__file__)
        },
        "/css": {
            "tools.staticdir.on": True,
            "tools.staticdir.dir": "css"
        },
        "/js": {
            "tools.staticdir.on": True,
            "tools.staticdir.dir": "js"
        }
    }
    cherrypy.config.update({"server.socket_host": "127.0.0.1", "server.socket_port": 5000})
    cherrypy.tree.mount(
        Dashboard(
            catalog_url,
            config["greenhouse_id"],
            services["sensor"],
            services["actuator"],
            config["admin_token"]
        ),
        "/",
        conf
    )
    cherrypy.engine.start()
    cherrypy.engine.block()
