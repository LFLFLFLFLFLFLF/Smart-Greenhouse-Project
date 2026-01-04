import requests
from flask import Flask, request

app = Flask(__name__)

SENSOR_URL = "http://127.0.0.1:8001/sensors/GH1/latest"
ACTUATOR_URL = "http://127.0.0.1:8002/actuators/GH1/status"
OVERRIDE_URL = "http://127.0.0.1:8002/actuators/GH1/override"

@app.get("/")
def home():
    try:
        sensor = requests.get(SENSOR_URL, timeout=2).json()
    except Exception:
        sensor = {"error": "cannot reach sensor REST"}

    try:
        actuators = requests.get(ACTUATOR_URL, timeout=2).json()
    except Exception:
        actuators = {"error": "cannot reach actuator REST"}

    return {
        "sensor_latest": sensor,
        "actuator_status": actuators,
        "how_to_override": "POST /override with json {device, action, duration(optional)}"
    }

@app.post("/override")
def override():
    payload = request.get_json(force=True)
    try:
        r = requests.post(OVERRIDE_URL, json=payload, timeout=3)
        return {"sent": payload, "status_code": r.status_code, "resp": r.text}
    except Exception as e:
        return {"error": str(e), "payload": payload}, 500

if __name__ == "__main__":
    app.run(port=5000, debug=True)
