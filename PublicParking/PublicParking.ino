#include <SPI.h>
#include <MFRC522.h>
#include <Servo.h>
#include <ArduinoJson.h>
#include <HCSR04.h>

// Pin Definitions
#define PARKING_LED_1 2
#define PARKING_LED_2 3
#define PARKING_LED_3 4

#define TRIG_PARKING_1 8
#define ECHO_PARKING_1 9
#define TRIG_PARKING_2 10
#define ECHO_PARKING_2 11
#define TRIG_PARKING_3 12
#define ECHO_PARKING_3 13

#define INFRARED_1 A5
#define INFRARED_2 A4
#define INFRARED_3 A3

#define NUM_PARKING_SLOTS 3

HCSR04 slot_1_ultrasonic(TRIG_PARKING_1, ECHO_PARKING_1);
HCSR04 slot_2_ultrasonic(TRIG_PARKING_2, ECHO_PARKING_2);
HCSR04 slot_3_ultrasonic(TRIG_PARKING_3, ECHO_PARKING_3);

struct ParkingSlot {
    int ultrasonicPin;
    int ledPin;
    int irPin;
    int currentState;
    int previousState;
    unsigned long lastTriggerTime;
    unsigned long lastSendTime;
};

ParkingSlot parkingSlots[NUM_PARKING_SLOTS] = {
    {slot_1_ultrasonic, PARKING_LED_1, INFRARED_1, 0, 0, 0, 0},
    {slot_2_ultrasonic, PARKING_LED_2, INFRARED_2, 0, 0, 0, 0},
    {slot_3_ultrasonic, PARKING_LED_3, INFRARED_3, 0, 0, 0, 0}
};

void handleParkingDetection(ParkingSlot &slot, int slotID);
void sendSerialData(String type, int status, int distance, int slotID);

void setup() {
    Serial.begin(9600);
    for (int i = 0; i < NUM_PARKING_SLOTS; i++) {
        pinMode(parkingSlots[i].ultrasonicPin, INPUT);
        pinMode(parkingSlots[i].ledPin, OUTPUT);
        pinMode(parkingSlots[i].irPin, INPUT);
    }
}

void loop() {
    for (int i = 0; i < NUM_PARKING_SLOTS; i++) {
        handleParkingDetection(parkingSlots[i], i + 1);
    }
    delay(100);  
}

const int PARKING_EMPTY = 0;
const int PARKING_OCCUPIED = 1;
const int PARKING_EXITING = 2;

void handleParkingDetection(ParkingSlot &slot, int slotID) {
    const long delayThreshold = 1000; // Minimum time to consider a change in parking status stable
    const long sendInterval = 3000; // Minimum interval between sends
    unsigned long currentTime = millis();

    int distanceParking = slot.ultrasonicPin.dist();
    int infraredValue = analogRead(slot.irPin);
    int inFraredThreshold = 512;
    bool irDetected = infraredValue < inFraredThreshold;
    bool parkingClose = distanceParking < 6;

    // Determine current state based on sensor readings
    if (irDetected && parkingClose) {
        slot.currentState = PARKING_OCCUPIED;
    } else if (irDetected || parkingClose) {
        slot.currentState = PARKING_EXITING;
    } else {
        slot.currentState = PARKING_EMPTY;
    }

    // Handle state transitions and LED behavior
    if (slot.previousState != slot.currentState) {
        slot.lastTriggerTime = currentTime;  
    }

    if (currentTime - slot.lastTriggerTime >= delayThreshold) {
        switch (slot.currentState) {
            case PARKING_EMPTY:
                digitalWrite(slot.ledPin, LOW); // Turn LED off
                if (currentTime - slot.lastSendTime >= sendInterval) {
                    slot.lastSendTime = currentTime;
                    sendSerialData("Parking", PARKING_EMPTY, distanceParking, slotID);
                }
                break;
            case PARKING_OCCUPIED:
                digitalWrite(slot.ledPin, HIGH); // Turn LED on
                if (currentTime - slot.lastSendTime >= sendInterval) {
                    slot.lastSendTime = currentTime;
                    sendSerialData("Parking", PARKING_OCCUPIED, distanceParking, slotID);
                }
                break;
            case PARKING_EXITING:
                // Blink LED
                sendSerialData("Parking", PARKING_EXITING, distanceParking, slotID);
                for (int i = 0; i < 10; i++) {
                    digitalWrite(slot.ledPin, HIGH);
                    delay(200);
                    digitalWrite(slot.ledPin, LOW);
                    delay(200);
                }
                break;
        }
    }

    slot.previousState = slot.currentState;
}

void sendSerialData(String type, int status, int distance, int slotID) {
    // Create a JSON object
    StaticJsonDocument<200> jsonDoc;
    jsonDoc["type"] = type;
    jsonDoc["status"] = status;
    jsonDoc["distance"] = distance;
    jsonDoc["slotID"] = slotID;

    String jsonString;
    serializeJson(jsonDoc, jsonString);
    Serial.println(jsonString);
}
