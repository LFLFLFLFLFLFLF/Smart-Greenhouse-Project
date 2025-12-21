import paho
import paho.mqtt.client as PahoMQTT

class MyMQTT:
    def __init__(self, clientID, broker, port, notifier):
        self.broker = broker
        self.port = port
        self.notifier = notifier
        self.client = clientID
        self._isSubscriber = False
        self._subscribedTopics = []

        # create an instance of paho.mqtt.client
        self._paho_mqtt = PahoMQTT.Client(clientID, True)
        # register the callback
        self._paho_mqtt.on_connect = self.myOnConnect
        self._paho_mqtt.on_message = self.myOnMessageReceived


    def myOnConnect(self, paho_mqtt, userdata, flags, rc):
        if rc == 0:
            print(f"Connected to {self.broker} with result code: {rc}")
        else:
            print(f"Connection failed with result code: {rc}")
                
    def myOnMessageReceived(self, paho_mqtt, userdata, msg):
        self.notifier.notify(msg.topic, msg.payload.decode("utf-8"))

    def myPublish(self, topic, msg):
        if not isinstance(msg, (str, bytes)):
            print("Error: Message must be a string or bytes.")
            return
        if not (topic and msg):
            print("Error: Topic or Message is missing.")
            return
        self._paho_mqtt.publish(topic, msg, 2)
        print(f"publishing {msg} with topic {topic}")

    def mySubscribe(self, topic):
        if topic not in self._subscribedTopics:
            self._paho_mqtt.subscribe(topic, 2)
            self._isSubscriber = True
            self._subscribedTopics.append(topic)
            print(f"Subscribed to {topic}")

    def start(self):
        self._paho_mqtt.connect(self.broker, self.port)
        self._paho_mqtt.loop_start()

    def stop(self):
        if self._isSubscriber:
            for i in self._subscribedTopics:
                self._paho_mqtt.unsubscribe(i)
                print(f"unsubscribed to {i}")
        self._paho_mqtt.loop_stop()
        self._paho_mqtt.disconnect()
