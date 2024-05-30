import time
import json
from datetime import datetime
from awscrt import io, mqtt, auth, http
from awsiot import mqtt_connection_builder

from SerialInterface import SerialInterface
from Controller import Controller
from Database import Database

localDatabase = Database.get_instance()
controller = Controller()
data_received = False
iface = SerialInterface()

post_response_data = {
    "status": None,
    "message": None
}

current_parking_status = {}

endpoint = "a27eliy2xg4c5e-ats.iot.us-east-1.amazonaws.com"
cert_filepath = "/home/pi/RPi-clone/mqtt/44bdbb017ed61e3180473d7562a7219625694010abfe0315ab96632a7fe8402b-certificate.pem.crt"
pri_key_filepath = "/home/pi/RPi-clone/mqtt/44bdbb017ed61e3180473d7562a7219625694010abfe0315ab96632a7fe8402b-private.pem.key"
ca_filepath = "/home/pi/RPi-clone/mqtt/AmazonRootCA1.pem"
client_id = "rpi_public_parking"

event_loop_group = io.EventLoopGroup(1)
host_resolver = io.DefaultHostResolver(event_loop_group)
client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)

io.init_logging(getattr(io.LogLevel, 'NoLogs'), 'stderr')

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

print("Connecting to {} with client ID '{}'...".format(endpoint, client_id))
connected_future = mqtt_connection.connect()
connected_future.result()
if connected_future.done():
    print("Connected!")
else:
    print("Connection failed")

def retrieveData(topic, payload, dup, qos, retain, **kwargs):
    print("New message received")
    global controller, localDatabase, data_received
    payload = payload.decode('utf-8')
    data = json.loads(payload)
    print(data)

    # Update controller variables based on received data
    for key, value in data.items():
        setattr(controller, key, value)

    # Update all the variables in the database that match the name
    for key in data:
        localDatabase.query(f"UPDATE variables SET value = {data[key]} WHERE name = '{key}'", False)
    
    data_received = True
    print(controller.toJson())
    iface.write_msg(controller.toJson())
    # Repeat 5 times if the response is invalid
    response = iface.read_msg()
    i = 5
    while response is None or response.startswith("Error") or response.startswith("InvalidInput") and i > 0:
        print(f"Response: {response}")
        iface.write_msg(controller.toJson())
        response = iface.read_msg()
        i -= 1

def handleResponseData(topic, payload, dup, qos, retain, **kwargs):
    print("Response received")
    global post_response_data
    payload = payload.decode('utf-8')
    data = json.loads(payload)

    if "status" in data and "message" in data:
        post_response_data["status"] = data["status"]
        post_response_data["message"] = data["message"]

mqtt_connection.publish(topic="rpi/get_public_parking", payload=json.dumps({"request": "control_data"}), qos=mqtt.QoS.AT_LEAST_ONCE)
subscribe_future, packet_id = mqtt_connection.subscribe(topic="rpi/get_public_parking", qos=mqtt.QoS.AT_LEAST_ONCE, callback=retrieveData)
subscribe_result = subscribe_future.result()
if subscribe_future.done():
    print("Subscribed to rpi/get_public_parking")

subscribe_future, packet_id = mqtt_connection.subscribe(topic="rpi/post_public_parking", qos=mqtt.QoS.AT_LEAST_ONCE, callback=handleResponseData)
subscribe_result = subscribe_future.result()
if subscribe_future.done():
    print("Subscribed to rpi/post_public_parking")

def publish_to_cloud(data):
    try:
        publish_future, packet_id = mqtt_connection.publish("rpi/post_public_parking", json.dumps(data), mqtt.QoS.AT_LEAST_ONCE)
        publish_result = publish_future.result()
    except Exception as e:
        print(f"Error publishing to cloud: {e}")

def handle_parking_event(slot_id, status):
    current_status = current_parking_status.get(slot_id, None)
    if status == 0 and current_status == 1:
        end_parking_session(slot_id)
    elif status == 1 and current_status != 1:
        start_parking_session(slot_id)
    current_parking_status[slot_id] = status
    update_public_carpark_slot(slot_id, status)

def start_parking_session(slot_id):
    try:
        localDatabase.query(
            'INSERT INTO parking_sessions (slot_id, start_time, status) VALUES (%s, %s, %s)',
            params=(slot_id, datetime.now(), 'active')
        )
        localDatabase.query(
            'UPDATE public_carpark_slot SET status = 1 WHERE id = %s',
            params=(slot_id,)
        )
        # Publish to cloud
        publish_to_cloud({"slot_id": slot_id, "status": 1, "start_time": datetime.now().isoformat()})
    except Exception as e:
        print(f"Error starting parking session: {e}")

def end_parking_session(slot_id):
    try:
        localDatabase.query(
            'UPDATE parking_sessions SET end_time = %s, status = %s WHERE slot_id = %s AND end_time IS NULL',
            params=(datetime.now(), 'completed', slot_id)
        )
        localDatabase.query(
            'UPDATE public_carpark_slot SET status = 0 WHERE id = %s',
            params=(slot_id,)
        )
        # Publish to cloud
        publish_to_cloud({"slot_id": slot_id, "status": 0, "end_time": datetime.now().isoformat()})
    except Exception as e:
        print(f"Error ending parking session: {e}")

def update_public_carpark_slot(slot_id, status):
    try:
        # Update the public_carpark_slot table
        localDatabase.query(
            'UPDATE public_carpark_slot SET status = %s WHERE id = %s',
            params=(status, slot_id)
        )

        # Update the variables table
        if status == 1:  # If a car is occupying a slot
            localDatabase.query(
                'UPDATE variables SET value = value + 1 WHERE name = "public_current_car_number"'
            )
        elif status == 0:  # If a car is leaving a slot
            localDatabase.query(
                'UPDATE variables SET value = value - 1 WHERE name = "public_current_car_number"'
            )

        # Update public_max_car_number and public_current_car_number
        update_variables()
        
        # Publish to cloud
        publish_to_cloud({"slot_id": slot_id, "status": status})
    except Exception as e:
        print(f"Error updating public carpark slot: {e}")

def update_variables():
    try:
        cursor = localDatabase.connection.cursor()
        # Update public_current_car_number
        cursor.execute(
            'SELECT COUNT(*) FROM public_carpark_slot WHERE status = 1'
        )
        current_car_number = cursor.fetchone()[0]
        cursor.execute(
            'UPDATE variables SET value = %s WHERE name = "public_current_car_number"',
            (current_car_number,)
        )
        
        # Update public_max_car_number
        cursor.execute(
            'SELECT COUNT(*) FROM public_carpark_slot'
        )
        max_car_number = cursor.fetchone()[0]
        cursor.execute(
            'UPDATE variables SET value = %s WHERE name = "public_max_car_number"',
            (max_car_number,)
        )

        localDatabase.connection.commit()
        cursor.close()
    except Exception as e:
        print(f"Error updating variables: {e}")

if __name__ == "__main__":
    try:
        while True:
            response = iface.read_msg()
            if response:
                print(f"Response: {response}")
                try:
                    data = json.loads(response)
                    slot_id = data["slotID"]
                    status = data["status"]

                    handle_parking_event(slot_id, status)
                    update_public_carpark_slot(slot_id, status)

                    publish_to_cloud(data)

                    # Example: Send an MQTT message if the status changes
                    if status == 1:
                        publish_to_cloud({"slot_id": slot_id, "status": "occupied"})
                    elif status == 0:
                        publish_to_cloud({"slot_id": slot_id, "status": "empty"})

                except json.JSONDecodeError:
                    print(f"Received non-JSON response: {response}")

            time.sleep(0.1)
    except KeyboardInterrupt:
        print("Interrupted by user, disconnecting...")
    finally:
        mqtt_connection.disconnect()
        iface.close()
