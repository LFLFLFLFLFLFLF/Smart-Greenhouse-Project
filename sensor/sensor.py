import sys
import requests
import json
import time
import random
from MyMQTT import MyMQTT

class GreenhouseSensor:
    def __init__(self, config_file, sensor_type):
        self.sensor_type = sensor_type
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
            self.clientID = f"{prefix}{self.sensor_type}"
            # Determine the channel
            self.topic = f"{base_topic}/sensors/{self.sensor_type}"
            # Initialization
            self.client = MyMQTT(self.clientID, broker, port, None)


        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            exit()

    def run(self):
        self.client.start()
        print(f"Running {self.sensor_type}:{self.clientID}-Topic:{self.topic}")
        try:
            while True:
                val = self.get_value()
                message = json.dumps({
                    "bn": self.clientID,
                    "e": [{"n": self.sensor_type, "v": val, "t": time.time(), "u":"unit"}],
                })
                self.client.myPublish(self.topic, message)
                time.sleep(10)
        except KeyboardInterrupt:
            self.client.stop()


    def get_value(self):
        if self.sensor_type == "temperature": return round(random.uniform(20, 30), 2)
        if self.sensor_type == "light": return round(random.uniform(100, 1000), 2)
        if self.sensor_type == "humidity": return round(random.uniform(40, 70), 2)
        if self.sensor_type == "moisture": return round(random.uniform(10, 50), 2)
        return random.randint(0, 100)



if __name__ == "__main__":
    s_type = sys.argv[1] if len(sys.argv) > 1 else "air_con"

    sensor = GreenhouseSensor("../actuator/config.json", s_type)
    sensor.run()
