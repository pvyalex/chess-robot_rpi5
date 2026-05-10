# chess-robot_rpi5

Chess-playing robot arm project using a Raspberry Pi 5 for vision/logic and an ESP32 for servo control.

## What this repo contains
- `main/rpi5/`: Python code for vision, move detection, and robot control.
- `main/esp32/`: ESP32 firmware for servo motion and gripper control.
- `yolo26n/`: Trained segmentation model and dataset artifacts.
- `pcb/`: KiCad files for hardware.
- `robot_arm/`: 3D model and calibration sketch.

## High-level flow
1. Capture a reference board image and calibrate perspective.
2. Detect the human move by comparing new frames to the reference.
3. Compute the engine reply and command the robot arm to move the piece.

## Run (Raspberry Pi 5)
Open [main/rpi5/main.py](main/rpi5/main.py) and run it from that folder. The script:
- captures images,
- detects the move,
- asks the chess engine for a reply,
- and drives the robot arm over UART.

If your ESP32 is on a different serial port than `COM3`, update the port passed to `ChessRobot` in [main/rpi5/main.py](main/rpi5/main.py).

## ESP32 firmware
Upload [main/esp32/esp32_source.ino](main/esp32/esp32_source.ino) to the ESP32. It expects servo pins defined at the top of the file and listens for commands from the host.

## Notes
- The vision pipeline uses the model under `yolo26n/model/` for calibration and detection.
- Movement logic and inverse kinematics are implemented in [main/rpi5/chess_robot_ik_only.py](main/rpi5/chess_robot_ik_only.py).
