import paho.mqtt.client as mqtt


class MQTTclient:
    def __init__(self, client_id, broker, port):
        self.client_id = client_id
        self.broker = broker
        self.port = int(port)
        self.subscriptions = []
        try:
            self.client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=client_id
            )
        except AttributeError:
            self.client = mqtt.Client(client_id=client_id)
        self.client.on_connect = self._on_connect

    def register_callbacks(self, on_con=None, on_dis=None, on_pub=None, on_mes=None):
        if on_con:
            self.user_on_connect = on_con
        else:
            self.user_on_connect = None
        if on_dis:
            self.client.on_disconnect = on_dis
        if on_pub:
            self.client.on_publish = on_pub
        if on_mes:
            self.client.on_message = on_mes

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        print(f"[MQTT] {self.client_id} connected with code {reason_code}")
        for topic, qos in self.subscriptions:
            self.client.subscribe(topic, qos)
            print(f"[MQTT] {self.client_id} subscribed {topic}")
        if getattr(self, "user_on_connect", None):
            try:
                self.user_on_connect(client, userdata, flags, reason_code, properties)
            except TypeError:
                self.user_on_connect(client, userdata, flags, reason_code)

    def start(self):
        self.client.connect(self.broker, self.port)
        self.client.loop_start()

    def publish(self, topic, message, qos=0):
        self.client.publish(topic, message, qos)

    def subscribe(self, topic, qos=0):
        if (topic, qos) not in self.subscriptions:
            self.subscriptions.append((topic, qos))
        self.client.subscribe(topic, qos)

    def unsubscribe(self, topic):
        self.client.unsubscribe(topic)

    def finalize(self):
        self.client.loop_stop()
        self.client.disconnect()
