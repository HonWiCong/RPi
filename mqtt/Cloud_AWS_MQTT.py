import mysql.connector
import time
import json
from awscrt import io, mqtt, auth, http
from awsiot import mqtt_connection_builder

database = mysql.connector.connect(
    host="database.ckozhfjjzal0.us-east-1.rds.amazonaws.com",
    user="admin",
    password="aRHnjDuknZhPZc4",
    database="parking"
)

endpoint = "a27eliy2xg4c5e-ats.iot.us-east-1.amazonaws.com"
cert_filepath = r"D:\Users\User\Programming\Swinburne Project\IOT\Hardware Program\mqtt\44bdbb017ed61e3180473d7562a7219625694010abfe0315ab96632a7fe8402b-certificate.pem.crt"
pri_key_filepath = r"D:\Users\User\Programming\Swinburne Project\IOT\Hardware Program\mqtt\44bdbb017ed61e3180473d7562a7219625694010abfe0315ab96632a7fe8402b-private.pem.key"
ca_filepath = r"D:\Users\User\Programming\Swinburne Project\IOT\Hardware Program\mqtt\AmazonRootCA1.pem"
client_id = "MyCloudComputer"

event_loop_group = io.EventLoopGroup(1)
host_resolver = io.DefaultHostResolver(event_loop_group)
client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)


# Initiate AWS CRT resources
io.init_logging(getattr(io.LogLevel.NoLogs, 'NoLogs'), 'stderr')

# Build an MQTT connection object
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
print("Connected!")


def sendData(topic, payload, dup, qos, retain, **kwargs):
    payload = payload.decode('utf-8')
    data = json.loads(payload)

    if "request" in data and data["request"] == "control_data":
        print("Sending data to RPI")
        cursor = database.cursor(dictionary=True)
        cursor.execute("SELECT * FROM variables")
        result = cursor.fetchall()
        database.commit()
        response_data = {}
        for row in result:
            response_data[row["name"]] = row["value"]

        print(response_data)
        try:
            mqtt_connection.publish(
                topic="rpi/get_response", payload=json.dumps(response_data), qos=mqtt.QoS.AT_LEAST_ONCE)
            mqtt_connection.publish(
                topic="rpi/get_response", payload=json.dumps(response_data), qos=mqtt.QoS.AT_LEAST_ONCE)
            
        except Exception as e:
            print("Publish timed out, retrying...", e)
            time.sleep(1)

        return


def saveData(topic, payload, dup, qos, retain, **kwargs):
    print("Saving data to database")
    payload = payload.decode('utf-8')
    data = json.loads(payload)

    if "sql" in data:
        cursor = database.cursor()
        cursor.execute(data["sql"])
        database.commit()
        return

    elif "type" in data and "status" in data and "rfidTag" in data and "distance" in data and "slotID" in data:
        cursor = database.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users")
        result = cursor.fetchone()
        print(result)

        exist = False

        print("Data: ", data["rfidTag"])
        print("Result: ", result["rfid_tag"])
        if int(result["rfid_tag"]) == int(data["rfidTag"]):
            cursor.execute(
                f"INSERT INTO access_logs (user_id, event_type, timestamp) VALUES ({result['id']}, 'enter', NOW())")
            exist = True
            database.commit()

        print("Exist: ", exist)
        if not exist:
            cursor.execute(
                f"INSERT INTO system_alarms (type, description, timestamp) VALUES ('{data['type']}', 'error at private gate', NOW())")
            database.commit()
            response = {
                "status": "error",
                "message": "RFID not found"
            }
            mqtt_connection.publish(topic="rpi/post_response", payload=json.dumps(response), qos=mqtt.QoS.AT_LEAST_ONCE)
            return
        if exist:
            response = {"status": 'success', "message": 'RFID found'}
            mqtt_connection.publish(topic="rpi/post_response", payload=json.dumps(response), qos=mqtt.QoS.AT_LEAST_ONCE)
            # myMQTTClient.publish("rpi/post_response", bytes(response, 'utf-8'), 2)
            # myMQTTClient.publish("rpi/post_response", response.encode('utf-8'), 2)
            return

        return

print("Subscribing to topic 'rpi/get_request'...")
subscribe_future, packet_id = mqtt_connection.subscribe(
    topic="rpi/get_request",
    qos=mqtt.QoS.AT_LEAST_ONCE,
    callback=sendData)

# Wait for the subscribe to succeed
subscribe_result = subscribe_future.result()
print("Subscribed with {}".format(str(subscribe_result['qos'])))

print("Subscribing to topic 'rpi/post_request'...")
subscribe_future, packet_id = mqtt_connection.subscribe(
    topic="rpi/post_request",
    qos=mqtt.QoS.AT_LEAST_ONCE,
    callback=saveData)

# Wait for the subscribe to succeed
subscribe_result = subscribe_future.result()
print("Subscribed with {}".format(str(subscribe_result['qos'])))

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Interrupted by user, disconnecting...")
    mqtt_connection.disconnect()
    print("Disconnected")
