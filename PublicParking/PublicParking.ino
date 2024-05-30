#include <SPI.h>
#include <Servo.h>
#include <ArduinoJson.h>

// Pin Definitions
#define PARKING_LED_1 2
#define PARKING_LED_2 3
#define PARKING_LED_3 4

#define INFRARED_1 A5
#define INFRARED_2 A4
#define INFRARED_3 A3

#define NUM_PARKING_SLOTS 3
#define ERROR_DURATION 3000 

enum ParkingState {
    PARKING_EMPTY,
    PARKING_OCCUPIED,
    PARKING_ERROR
};

struct ParkingSlot {
    int ledPin;
    int irPin;
    ParkingState currentState;
    ParkingState previousState;
    unsigned long lastTriggerTime;
    unsigned long errorStartTime; 
    bool errorDataSent; 
};

ParkingSlot parkingSlots[NUM_PARKING_SLOTS] = {
    {PARKING_LED_1, INFRARED_1, PARKING_EMPTY, PARKING_EMPTY, 0, 0, false},
    {PARKING_LED_2, INFRARED_2, PARKING_EMPTY, PARKING_EMPTY, 0, 0, false},
    {PARKING_LED_3, INFRARED_3, PARKING_EMPTY, PARKING_EMPTY, 0, 0, false}
};

void setup() {
    Serial.begin(9600);
    Serial.println("Setup Complete");
    for (int i = 0; i < NUM_PARKING_SLOTS; i++) {
        pinMode(parkingSlots[i].ledPin, OUTPUT);
        pinMode(parkingSlots[i].irPin, INPUT);
        sendSerialData("Parking", PARKING_EMPTY, i + 1);
    }
}

void loop() {
    for (int i = 0; i < NUM_PARKING_SLOTS; i++) {
        handleParkingDetection(parkingSlots[i], i + 1);
    }
    delay(100);
}

void handleParkingDetection(ParkingSlot &slot, int slotID) {
    int infraredValue = analogRead(slot.irPin);
    bool irDetected = infraredValue < 512;

    // Determine current state based on sensor readings
    if (irDetected) {
        slot.currentState = PARKING_OCCUPIED;
        slot.errorStartTime = 0;  
        slot.errorDataSent = false;  
    } else {
        slot.currentState = PARKING_EMPTY;
        slot.errorStartTime = 0;  
        slot.errorDataSent = false; 
    }

    // Handle state transitions and LED behavior
    if (slot.currentState != slot.previousState) {
        handleStateTransition(slot, slotID);
        slot.previousState = slot.currentState;  // Update the previous state
    }
}

void handleStateTransition(ParkingSlot &slot, int slotID) {
    switch (slot.currentState) {
        case PARKING_EMPTY:
            digitalWrite(slot.ledPin, LOW); 
            sendSerialData("Parking", PARKING_EMPTY, slotID);
            break;
        case PARKING_OCCUPIED:
            digitalWrite(slot.ledPin, HIGH);  
            sendSerialData("Parking", PARKING_OCCUPIED, slotID);
            break;
        case PARKING_ERROR:
            slot.errorDataSent = false;  // Reset error data sent flag
            break;
    }
}

void sendSerialData(String type, int status, int slotID) {
    // Create a JSON object
    StaticJsonDocument<200> jsonDoc;
    jsonDoc["type"] = type;
    jsonDoc["status"] = status;
    jsonDoc["slotID"] = slotID;

    String jsonString;
    serializeJson(jsonDoc, jsonString);
    Serial.println(jsonString);
}
