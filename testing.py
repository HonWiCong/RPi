import time
import json
from awscrt import io, mqtt, auth, http
from awsiot import mqtt_connection_builder

from SerialInterface import SerialInterface
from Controller import Controller
from Database import Database

# localDatabase = Database.get_instance()
controller = Controller()
data_received = False
# iface = SerialInterface()

post_response_data = {
    "status": None,
    "message": None
}

def retrieveData(topic, payload, dup, qos, retain, **kwargs):
    print("New message received")
    global controller, data_received
    payload = payload.decode('utf-8')
    data = json.loads(payload)
    print(data)

    if "public_always_open_gate" in data:
        controller.public_always_open_gate = data["public_always_open_gate"]
    if "public_always_close_gate" in data:
        controller.public_always_close_gate = data["public_always_close_gate"]
    if "public_current_car_number" in data:
        controller.public_current_car_number = data["public_current_car_number"]
    if "public_max_car_number" in data:
        controller.public_max_car_number = data["public_max_car_number"]

    if "private_always_open_gate" in data:
        controller.private_always_open_gate = data["private_always_open_gate"]
    if "private_always_close_gate" in data:
        controller.private_always_close_gate = data["private_always_close_gate"]
    if "private_current_car_number" in data:
        controller.private_current_car_number = data["private_current_car_number"]
    if "private_max_car_number" in data:
        controller.private_max_car_number = data["private_max_car_number"]

    data_received = True
    # combine 2 object class into 1 object
    print(controller.toJson())
    # iface.write_msg(controller.toJson())
    # response = iface.read_msg()
    # i = 5
    # while response is None or response.startswith("Error") or response.startswith("InvalidInput") and i > 0:
    #     print(f"Response: {response}")
    #     iface.write_msg(controller.toJson())
    #     response = iface.read_msg()
    #     i -= 1

def handleResponseData(topic, payload, dup, qos, retain, **kwargs):
    print("Response received")
    payload = payload.decode('utf-8')
    data = json.loads(payload)

    if "status" in data and "message" in data:
        post_response_data["status"] = data["status"]
        post_response_data["message"] = data["message"]

endpoint = "a27eliy2xg4c5e-ats.iot.us-east-1.amazonaws.com"
cert_filepath = r"D:\Users\User\Programming\Swinburne Project\IOT\Hardware Program\mqtt\44bdbb017ed61e3180473d7562a7219625694010abfe0315ab96632a7fe8402b-certificate.pem.crt"
pri_key_filepath = r"D:\Users\User\Programming\Swinburne Project\IOT\Hardware Program\mqtt\44bdbb017ed61e3180473d7562a7219625694010abfe0315ab96632a7fe8402b-private.pem.key"
ca_filepath = r"D:\Users\User\Programming\Swinburne Project\IOT\Hardware Program\mqtt\AmazonRootCA1.pem"
client_id = "rpi_public"

# RPi
# cert_filepath = r"/home/pi/RPi/mqtt/44bdbb017ed61e3180473d7562a7219625694010abfe0315ab96632a7fe8402b-certificate.pem.crt"
# pri_key_filepath = r"/home/pi/RPi/mqtt/44bdbb017ed61e3180473d7562a7219625694010abfe0315ab96632a7fe8402b-private.pem.key"
# ca_filepath = r"/home/pi/RPi/mqtt/AmazonRootCA1.pem"

event_loop_group = io.EventLoopGroup(1)
host_resolver = io.DefaultHostResolver(event_loop_group)
client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)

io.init_logging(getattr(io.LogLevel.NoLogs, 'NoLogs'), 'stderr')

mqtt_connection = mqtt_connection_builder.mtls_from_path(
    endpoint=endpoint,
    cert_filepath=cert_filepath,
    pri_key_filepath=pri_key_filepath,
    client_bootstrap=client_bootstrap,
    ca_filepath=ca_filepath,
    client_id=client_id,
    clean_session=False,
    keep_alive_secs=6
)

request = {
    "request": "control_data"
}

print("Connecting to {} with client ID '{}'...".format(endpoint, client_id))
connected_future = mqtt_connection.connect()
connected_future.result()
if connected_future.done():
    print("Connected!")
else:
    print("Connection failed")

# myMQTTClient.publish("rpi/get_request", json.dumps(request), 1)
# myMQTTClient.subscribe("rpi/get_response", 1, retrieveData)
# myMQTTClient.subscribe("rpi/post_response", 1, handleResponseData)

mqtt_connection.publish(topic="rpi/get_response", payload=json.dumps(request), qos=mqtt.QoS.AT_LEAST_ONCE)
subscribe_future, packet_id = mqtt_connection.subscribe(topic="rpi/get_response", qos=mqtt.QoS.AT_LEAST_ONCE, callback=retrieveData)
subscribe_result = subscribe_future.result()
if subscribe_future.done():
    print("Subscribed to rpi/get_response")

subscribe_future, packet_id = mqtt_connection.subscribe(topic="rpi/post_response", qos=mqtt.QoS.AT_LEAST_ONCE, callback=handleResponseData)
subscribe_result = subscribe_future.result()
if subscribe_future.done():
    print("Subscribed to rpi/post_response")

if __name__ == "__main__":
    response = {
        "id": 1,
		"rfidTag": 13851605,
        "type": "public",
        "slotID": 1,
        "distance": 0,
        "status": "in",
        "type": "enter"
	}
    publish_future, packet_id = mqtt_connection.publish(
        topic="rpi/post_request",
        payload=json.dumps(response),
        qos=mqtt.QoS.AT_LEAST_ONCE)
    publish_result = publish_future.result()
    while post_response_data["status"] is None and post_response_data["message"] is None:
        print("Waiting for response...")
        time.sleep(1)
        print(post_response_data)