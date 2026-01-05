import json
import time
import threading
import os
import requests
import paho.mqtt.client as mqtt

CATALOG_URL = os.getenv("CATALOG_URL", "http://127.0.0.1:8080/catalog")

THINGSPEAK_ENABLED = os.getenv("THINGSPEAK_ENABLED", "0") == "1"  # 默认 mock
THINGSPEAK_ENDPOINT = os.getenv("THINGSPEAK_ENDPOINT", "https://api.thingspeak.com/update")
THINGSPEAK_API_KEY = os.getenv("THINGSPEAK_API_KEY", "YOUR_KEY")

FIELD_TO_THINGSPEAK = {
    "temperature": "field1",
    "humidity": "field2",
    "light": "field3",
    "soil_moist": "field4",
    "co2": "field5",
    "fertility_n": "field6",
    "fertility_p": "field7",
    "fertility_k": "field8",
}

ALIASES = {
    "moisture": "soil_moist",
}

#状态
latest = {}  # 累积各传感器最新值
lock = threading.Lock()

BROKER_HOST = None
BROKER_PORT = None
SUBSCRIBE_TOPIC = None
UPLOAD_SEC = 60#时间间隔60s


def load_catalog():
    """
    从 Catalog REST 拿到 broker/topic/update_sec 等配置
    Catalog REST 返回的 JSON 结构应与 catalog/catalog.json 一致
    """
    r = requests.get(CATALOG_URL, timeout=5)
    r.raise_for_status()
    cfg = r.json()

    broker = cfg["broker_config"]
    base_topic = broker["base_topic"].rstrip("/")
    sensors_topic = cfg["field_devices"]["sensors"]["topic"].lstrip("/")

    global BROKER_HOST, BROKER_PORT, SUBSCRIBE_TOPIC, UPLOAD_SEC
    BROKER_HOST = broker["address"]
    BROKER_PORT = int(broker["port"])
    SUBSCRIBE_TOPIC = f"{base_topic}/{sensors_topic}/#"

    # 从 catalog 的 services.thingspeak_adaptor.update_sec 读取
    UPLOAD_SEC = int(cfg.get("services", {})
                       .get("thingspeak_adaptor", {})
                       .get("update_sec", 60))

    return cfg


def senml_to_flat(payload: dict) -> dict:
    """
    把 SenML 风格：
      {"bn":"...", "e":[{"n":"temperature","v":23.1,"t":...}, ...]}
    转成扁平：
      {"temperature": 23.1, ...}
    """
    flat = {}

    # 如果本身就是扁平的，就直接返回
    if "e" not in payload and isinstance(payload, dict):
        # 过滤掉明显不是测量值的字段
        for k, v in payload.items():
            if k in ("bn", "bt", "ver"):
                continue
            flat[k] = v
        return flat

    events = payload.get("e", [])
    for ev in events:
        name = ev.get("n")
        value = ev.get("v")
        if not name:
            continue
        name = ALIASES.get(name, name)
        flat[name] = value

    return flat


#  MQTT callbacks 
def on_connect(client, userdata, flags, rc):
    print("[MQTT] connected rc=", rc)
    client.subscribe(SUBSCRIBE_TOPIC)
    print("[MQTT] subscribed:", SUBSCRIBE_TOPIC)


def on_message(client, userdata, msg):
    global latest
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        flat = senml_to_flat(payload)

        if not flat:
            print("[MQTT] got empty/unknown payload:", payload)
            return

        with lock:
            latest.update(flat)  # 累积各传感器最新值
        print("[MQTT] updated:", flat)

    except Exception as e:
        print("[MQTT] parse error:", e)


def build_thingspeak_payload(data: dict) -> dict:
    """
    将 latest(dict) 映射为 ThingSpeak 的 field1..field8
    """
    out = {"api_key": THINGSPEAK_API_KEY}
    for k, field in FIELD_TO_THINGSPEAK.items():
        if k in data:
            out[field] = data[k]
    return out


def upload_loop():
    while True:
        time.sleep(UPLOAD_SEC)

        with lock:
            snapshot = dict(latest)

        if not snapshot:
            print("[ThingSpeak] no data yet")
            continue

        payload = build_thingspeak_payload(snapshot)

        # 如果没映射到任何 field，就不上传
        if len(payload.keys()) <= 1:
            print("[ThingSpeak] no mapped fields in data:", snapshot)
            continue

        if not THINGSPEAK_ENABLED:
            print("[ThingSpeak] mock upload:", payload)
            continue

        try:
            r = requests.post(THINGSPEAK_ENDPOINT, data=payload, timeout=10)
            print("[ThingSpeak] uploaded:", r.status_code, r.text)
        except Exception as e:
            print("[ThingSpeak] upload error:", e)


def main():
    cfg = load_catalog()
    print("[Catalog] loaded OK. broker:", BROKER_HOST, BROKER_PORT, "topic:", SUBSCRIBE_TOPIC, "upload_sec:", UPLOAD_SEC)

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER_HOST, BROKER_PORT, 60)

    t = threading.Thread(target=upload_loop, daemon=True)
    t.start()

    client.loop_forever()


if __name__ == "__main__":
    main()
