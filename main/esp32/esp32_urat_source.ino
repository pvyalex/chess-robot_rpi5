#include <ESP32Servo.h>

// SERVO PINS
#define PIN_BASE     18
#define PIN_SHOULDER 33
#define PIN_ELBOW    21
#define PIN_WRIST    32
#define PIN_GRIPPER  19

Servo servoBase;
Servo servoShoulder;
Servo servoElbow;
Servo servoWrist;
Servo servoGripper;

// Tracked positions (must stay in sync with physical servos)
int currentBase     = 90;
int currentShoulder = 90;
int currentElbow    = 90;
int currentGripper  = 180;

// Wrist is held constant throughout all movement
const int WRIST_ANGLE = 47;

// Backlash overshoot for base servo (degrees)
const int BACKLASH_COMP = 3;

// Shoulder landmarks — 130 = arm folded back at rest, 80 = arm just over board edge
const int SHOULDER_BASE_REST   = 130;
const int SHOULDER_BOARD_ENTRY = 80;

// ─────────────────────────────────────────────────────
//  Velocity ramp
// ─────────────────────────────────────────────────────

// Trapezoidal profile: slow start → fast cruise → slow stop.
// Uses the distance from the nearest end (start or finish) to compute delay.
//   MAX_D ms at the edges, MIN_D ms in the cruise zone.
//   RAMP = how many steps to spend accelerating / decelerating (≤ 10, ≤ 33% of travel).
int rampDelay(int stepsDone, int stepsTotal) {
    const int MAX_D = 4;  // ms — slow (start / end)
    const int MIN_D = 1;  // ms — fast (cruise)
    int ramp = min(10, stepsTotal / 3);
    if (ramp < 2) return MIN_D;  // move too short to bother ramping

    // Distance from the nearer end (0 at the very first/last step)
    int fromEnd = min(stepsDone, stepsTotal - 1 - stepsDone);
    if (fromEnd >= ramp) return MIN_D;
    return MAX_D - (MAX_D - MIN_D) * fromEnd / ramp;
}

void setup() {
    Serial.begin(115200);

    servoBase.attach(PIN_BASE);
    servoShoulder.attach(PIN_SHOULDER);
    servoElbow.attach(PIN_ELBOW);
    servoWrist.attach(PIN_WRIST);
    servoGripper.attach(PIN_GRIPPER);

    servoWrist.write(WRIST_ANGLE);
    servoGripper.write(180);

    moveToBase();

    delay(1000);
    Serial.println("READY");
}

// ─────────────────────────────────────────────────────
//  Primitives
// ─────────────────────────────────────────────────────

// Move a single servo with a trapezoidal velocity profile.
// applyBacklash: overshoot by BACKLASH_COMP then pull back (positive direction only).
//   Backlash correction runs at fixed 1 ms — no ramp needed for a 3-degree nudge.
void smoothMoveSingle(int* current, int target, Servo* servo,
                      bool applyBacklash = false) {
    if (*current == target) return;

    int dir        = (*current < target) ? 1 : -1;
    int stepsTotal = abs(target - *current);
    int stepsDone  = 0;

    if (applyBacklash && dir > 0) {
        int overshoot = min(target + BACKLASH_COMP, 180);
        while (*current < overshoot) {
            *current += 1;
            servo->write(*current);
            servoWrist.write(WRIST_ANGLE);
            delay(1);
        }
        delay(5);  // let servo settle at overshoot
        while (*current > target) {
            *current -= 1;
            servo->write(*current);
            servoWrist.write(WRIST_ANGLE);
            delay(1);
        }
    } else {
        while (*current != target) {
            delay(rampDelay(stepsDone, stepsTotal));
            *current += dir;
            servo->write(*current);
            servoWrist.write(WRIST_ANGLE);
            stepsDone++;
        }
    }

    // Hard-set to guarantee exact landing position
    *current = target;
    servo->write(target);
}

// Move shoulder and elbow simultaneously with a trapezoidal profile.
// shoulderStep / elbowStep control how many degrees each joint moves per tick:
//   Going DOWN to a piece  → shoulderStep=1, elbowStep=4  (elbow leads, lifts fast)
//   Rising to SAFE/BASE    → shoulderStep=4, elbowStep=1  (shoulder leads, clears pieces fast)
// Timing (ramp) is keyed to the SLOWER joint so the profile is always smooth.
void moveShoulderElbowTogether(int targetShoulder, int targetElbow,
                               int shoulderStep = 1, int elbowStep = 4) {
    int dirS        = (currentShoulder < targetShoulder) ? 1 : -1;
    int dirE        = (currentElbow    < targetElbow)    ? 1 : -1;
    int degsS       = abs(targetShoulder - currentShoulder);
    int degsE       = abs(targetElbow    - currentElbow);
    // Total ticks driven by whichever joint takes longer (= master axis for ramp)
    int totalTicks  = max(max(degsS / max(shoulderStep, 1),
                              degsE / max(elbowStep,    1)), 1);
    int ticksDone   = 0;

    while (currentShoulder != targetShoulder || currentElbow != targetElbow) {
        if (currentShoulder != targetShoulder) {
            int step = min(shoulderStep, abs(targetShoulder - currentShoulder));
            currentShoulder += dirS * step;
            servoShoulder.write(currentShoulder);
        }
        if (currentElbow != targetElbow) {
            int step = min(elbowStep, abs(targetElbow - currentElbow));
            currentElbow += dirE * step;
            servoElbow.write(currentElbow);
        }
        servoWrist.write(WRIST_ANGLE);
        delay(rampDelay(ticksDone, totalTicks));
        ticksDone++;
    }
}

// ─────────────────────────────────────────────────────
//  High-level moves
// ─────────────────────────────────────────────────────

// Move to a board square.
// If arm is folded at BASE rest (shoulder=130), move to board entry (80) before
// swinging the base — avoids sweeping a dangerously wide arc at full extension.
void smoothMove(int targetBase, int targetShoulder, int targetElbow) {
    if (currentShoulder == SHOULDER_BASE_REST) {
        smoothMoveSingle(&currentShoulder, SHOULDER_BOARD_ENTRY, &servoShoulder, false);
    }

    smoothMoveSingle(&currentBase, targetBase, &servoBase, true);
    // Elbow first so the arm reaches the right height, then shoulder positions
    smoothMoveSingle(&currentElbow,    targetElbow,    &servoElbow);
    smoothMoveSingle(&currentShoulder, targetShoulder, &servoShoulder);
}

// Lift piece to safe transit height after gripping, centered over board.
void moveToMiddle() {
    // Shoulder first to clear nearby pieces, then elbow folds
    smoothMoveSingle(&currentShoulder, SHOULDER_BOARD_ENTRY, &servoShoulder);
    smoothMoveSingle(&currentElbow,    110,                  &servoElbow);
    smoothMoveSingle(&currentBase, 110, &servoBase, true);
    Serial.println("OK:MIDDLE");
}

// Return to fully folded rest position between moves.
void moveToBase() {
    // Shoulder first to clear nearby pieces, then elbow folds
    smoothMoveSingle(&currentShoulder, SHOULDER_BOARD_ENTRY, &servoShoulder);
    smoothMoveSingle(&currentElbow,    110,                  &servoElbow);
    smoothMoveSingle(&currentBase, 110, &servoBase, true);
    smoothMoveSingle(&currentShoulder, SHOULDER_BASE_REST, &servoShoulder);
    Serial.println("OK:BASE");
}

void grip() {
    for (int angle = currentGripper; angle >= 130; angle--) {
        servoGripper.write(angle);
        delay(10);
    }
    currentGripper = 130;
    Serial.println("OK:GRIP:130");
}

void release() {
    for (int angle = currentGripper; angle <= 170; angle++) {
        servoGripper.write(angle);
        delay(10);
    }
    currentGripper = 170;
    Serial.println("OK:LASA:170");
}

// ─────────────────────────────────────────────────────
//  Main loop
// ─────────────────────────────────────────────────────

void loop() {
    servoWrist.write(WRIST_ANGLE);

    if (!Serial.available()) return;

    String cmd = Serial.readStringUntil('\n');
    cmd.trim();

    if (cmd == "MIDDLE") { moveToMiddle(); return; }
    if (cmd == "GRIP")   { grip();         return; }
    if (cmd == "LASA")   { release();      return; }
    if (cmd == "BASE")   { moveToBase();   return; }

    if (cmd.startsWith("B")) {
        int base_angle = 0, shoulder_angle = 0, elbow_angle = 0;
        if (sscanf(cmd.c_str(), "B%d,S%d,E%d", &base_angle, &shoulder_angle, &elbow_angle) != 3) {
            Serial.println("ERR:BAD_CMD");
            return;
        }

        base_angle     = constrain(base_angle,     0, 180);
        shoulder_angle = constrain(shoulder_angle, 0, 180);
        elbow_angle    = constrain(elbow_angle,    0, 180);

        smoothMove(base_angle, shoulder_angle, elbow_angle);

        Serial.print("OK:");
        Serial.print(base_angle);
        Serial.print(",");
        Serial.print(shoulder_angle);
        Serial.print(",");
        Serial.println(elbow_angle);
    }
}
