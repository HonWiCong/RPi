import time
import json
from datetime import datetime
from SerialInterface import SerialInterface
from Controller import Controller
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient
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

def handle_parking_event(slot_id, status, distance):
    current_status = current_parking_status.get(slot_id, None)
    if status == 0 and current_status == 1:
        end_parking_session(slot_id)
    elif status == 1 and current_status != 1:
        start_parking_session(slot_id)
    elif status == 2:
        log_system_alarm(slot_id, "Error at parking slot", "Parking sensor error detected")
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

def log_system_alarm(slot_id, alarm_type, description):
    try:
        localDatabase.query(
            'INSERT INTO system_alarms (type, description, timestamp) VALUES (%s, %s, %s)',
            params=(alarm_type, description, datetime.now())
        )
        # Publish to cloud
        publish_to_cloud({"slot_id": slot_id, "type": alarm_type, "description": description, "timestamp": datetime.now().isoformat()})
    except Exception as e:
        print(f"Error logging system alarm: {e}")

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

        # Update public_max_car_number if needed
        max_car_number = localDatabase.query(
            'SELECT value FROM variables WHERE name = "public_max_car_number"', fetch_results=True
        )
        current_car_number = localDatabase.query(
            'SELECT value FROM variables WHERE name = "public_current_car_number"', fetch_results=True
        )
        if current_car_number['value'] > max_car_number['value']:
            localDatabase.query(
                'UPDATE variables SET value = %s WHERE name = "public_max_car_number"',
                params=(current_car_number['value'],)
            )

        # Publish to cloud
        publish_to_cloud({"slot_id": slot_id, "status": status})
    except Exception as e:
        print(f"Error updating public carpark slot: {e}")


def publish_to_cloud(data):
    myMQTTClient.publish("rpi/get_request", json.dumps(data), 1)

def retrieveData(client, userdata, message):
    print("New message received")
    global controller, localDatabase, data_received
    payload = message.payload.decode('utf-8')
    data = json.loads(payload)
    print(data)
    data_received = True
    print(controller.toJson())
    iface.write_msg(controller.toJson())

def handleResponseData(client, userdata, message):
    print("Response received")
    global post_response_data
    payload = message.payload.decode('utf-8')
    data = json.loads(payload)

    if "status" in data and "message" in data:
        post_response_data["status"] = data["status"]
        post_response_data["message"] = data["message"]

myMQTTClient = AWSIoTMQTTClient("rpi_public")
myMQTTClient.configureEndpoint(
    "a27eliy2xg4c5e-ats.iot.us-east-1.amazonaws.com", 8883)
myMQTTClient.configureCredentials(
    r"/home/pi/RPi-clone/mqtt/AmazonRootCA1.pem",
    r"/home/pi/RPi-clone/mqtt/44bdbb017ed61e3180473d7562a7219625694010abfe0315ab96632a7fe8402b-private.pem.key",
    r"/home/pi/RPi-clone/mqtt/44bdbb017ed61e3180473d7562a7219625694010abfe0315ab96632a7fe8402b-certificate.pem.crt"
)
myMQTTClient.configureOfflinePublishQueueing(-1)
myMQTTClient.configureDrainingFrequency(2)
myMQTTClient.configureConnectDisconnectTimeout(10)
myMQTTClient.configureMQTTOperationTimeout(5)

request = {
    "request": "control_data"
}

myMQTTClient.connect()
myMQTTClient.publish("rpi/get_request", json.dumps(request), 1)
myMQTTClient.subscribe("rpi/get_response", 1, retrieveData)
myMQTTClient.subscribe("rpi/post_response", 1, handleResponseData)

if __name__ == "__main__":
    try:
        while True:
            response = iface.read_msg()
            if response:
                print(f"Response: {response}")
                # Process the response (e.g., update the database, send MQTT messages, etc.)
                try:
                    data = json.loads(response)
                    slot_id = data["slotID"]
                    status = data["status"]
                    distance = data["distance"]

                    handle_parking_event(slot_id, status, distance)
                    update_public_carpark_slot(slot_id, status)

                    myMQTTClient.publish("rpi/post_request", f'{response}', 1)
                    # Reset post_response_data
                    post_response_data["status"] = None
                    post_response_data["message"] = None

                    # Example: Send an MQTT message if the status changes
                    if status == 1:
                        myMQTTClient.publish("parking/occupied", json.dumps(data), 1)
                    elif status == 0:
                        myMQTTClient.publish("parking/empty", json.dumps(data), 1)

                except json.JSONDecodeError:
                    print(f"Received non-JSON response: {response}")

            time.sleep(0.1)
    except KeyboardInterrupt:
        print("Interrupted by user, disconnecting...")
    finally:
        myMQTTClient.disconnect()
        iface.close()
