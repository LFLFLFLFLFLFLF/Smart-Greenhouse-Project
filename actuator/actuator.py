import sys
import requests
import json
import time
from MyMQTT import MyMQTT

class GreenhouseActuator:
    def __init__(self, config_file, actuator_type):

        self.actuator_type = actuator_type
        self.clientID = None
        self.topic = None
        self.client = None

        with open(config_file, 'r') as f:
            config_data = json.load(f)
        self.catalog_url = config_data['catalog_url']

        self.setup()

    def setup(self):
        try:
            response = requests.get(self.catalog_url).json()
            # Obtain the connect information
            broker = response['broker_config']['address']
            port = response['broker_config']['port']
            base_topic = response['broker_config']['base_topic']
            prefix = response['broker_config'].get('clientID_prefix','GH_')

            # Create unique ID
            self.clientID = f"{prefix}{self.actuator_type}"
            # Determine the channel
            self.topic = f"{base_topic}/actuators/{self.actuator_type}"
            # Initialization
            self.client = MyMQTT(self.clientID, broker, port, self)

        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            exit()

    def run(self):
        self.client.start()
        self.client.mySubscribe(self.topic)
        print(f"Running {self.actuator_type}:{self.clientID}-Topic:{self.topic}")

        try:
            while True:
                time.sleep(2)
        except KeyboardInterrupt:
            self.client.stop()

    def notify(self, topic, message):
        try:
            command = json.loads(message)
            print(f"{self.clientID} received command on {topic}: {command}")
            action = command.get('action')
            if action == "ON":
                # GPIO.output(17, GPIO.HIGH)
                print(f"{command['action']} ON")
            elif action == "OFF":
                print(f"{command['action']} OFF")
            else:
                print(f"{command['action']} UNKNOWN")

        except json.JSONDecodeError:
            print(f"Error decoding JSON message: {message}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")


if __name__ == '__main__':
    a_type = sys.argv[1] if len(sys.argv) > 1 else "air_con"

    actuator = GreenhouseActuator("config.json", a_type)
    actuator.run()