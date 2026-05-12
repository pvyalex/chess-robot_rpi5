import math
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple

import serial


class ServoName(Enum):
    BASE = "base"
    SHOULDER = "shoulder"
    ELBOW = "elbow"


@dataclass
class RobotConfig:
    L1: float = 240.0
    L2: float = 126.78
    L3: float = 130.0
    L3_angle: float = 68.51
    H_shoulder: float = 90.0
    H_piece: float = 50.0
    square_size: float = 35.0
    distance_to_row8: float = 140.0

    # 64-point least-squares fitted parameters
    base_scale: float = 1.1043
    base_offset: float = 5.809
    shoulder_scale: float = 0.7910
    shoulder_offset: float = 10.0883
    elbow_scale: float = -0.7949
    elbow_offset: float = 163.923


class ChessRobot:
    MOVE_WAYPOINT_DELAY_SEC = 0.12

    def __init__(
        self,
        port: str = "COM3",
        baudrate: int = 115200,
    ):
        self.cfg = RobotConfig()

        angle_rad = math.radians(self.cfg.L3_angle)
        self.eff_h = self.cfg.L3 * math.cos(angle_rad)
        self.eff_v = self.cfg.L3 * math.sin(angle_rad)

        self.serial = None

        try:
            self.serial = serial.Serial(port, baudrate, timeout=5)
            print(f"Astept ESP32 boot pe {port}...")
            time.sleep(3)
            self.serial.reset_input_buffer()
            print("Robot conectat!")
        except Exception as e:
            print(f"Eroare conexiune: {e}")
            self.serial = None

    @staticmethod
    def _normalize_square(pos: str) -> str:
        pos = pos.strip().lower()
        if len(pos) != 2 or pos[0] not in "abcdefgh" or pos[1] not in "12345678":
            raise ValueError(f"Invalid square: {pos!r} (expected like 'e2')")
        return pos

    def chess_to_xy(self, pos: str) -> Tuple[float, float]:
        pos = self._normalize_square(pos)
        col = ord(pos[0]) - ord("a")
        row = int(pos[1])
        x = (col - 3.5) * self.cfg.square_size
        y = self.cfg.distance_to_row8 + (8 - row) * self.cfg.square_size
        return x, y

    def get_column(self, pos: str) -> int:
        pos = self._normalize_square(pos)
        return ord(pos[0]) - ord("a")

    def solve_ik(self, x: float, y: float, h_target: Optional[float] = None) -> Optional[Dict[ServoName, int]]:
        cfg = self.cfg
        if h_target is None:
            h_target = cfg.H_piece

        base_geom = 90.0 + math.degrees(math.atan2(x, y))
        base_angle = cfg.base_scale * base_geom + cfg.base_offset

        r_xy = math.sqrt(x**2 + y**2)
        r_target = r_xy - self.eff_h
        z_rel = (h_target + self.eff_v) - cfg.H_shoulder
        distance = math.sqrt(r_target**2 + z_rel**2)

        if distance > cfg.L1 + cfg.L2 or distance < abs(cfg.L1 - cfg.L2):
            return None

        cos_elbow = (cfg.L1**2 + cfg.L2**2 - distance**2) / (2 * cfg.L1 * cfg.L2)
        cos_elbow = max(-1.0, min(1.0, cos_elbow))
        elbow_geom = math.degrees(math.acos(cos_elbow))
        elbow_angle = cfg.elbow_scale * elbow_geom + cfg.elbow_offset

        alpha = math.degrees(math.atan2(z_rel, r_target))
        cos_beta = (cfg.L1**2 + distance**2 - cfg.L2**2) / (2 * cfg.L1 * distance)
        cos_beta = max(-1.0, min(1.0, cos_beta))
        beta = math.degrees(math.acos(cos_beta))
        shoulder_geom = alpha + beta
        shoulder_angle = cfg.shoulder_scale * shoulder_geom + cfg.shoulder_offset

        return {
            ServoName.BASE: int(round(base_angle)),
            ServoName.SHOULDER: int(round(shoulder_angle)),
            ServoName.ELBOW: int(round(elbow_angle)),
        }

    def _max_reachable_height(self, x: float, y: float) -> float:
        """Gaseste cea mai mare inaltime la care bratul ajunge la (x,y)."""
        cfg = self.cfg
        r_xy = math.sqrt(x**2 + y**2)
        r_target = r_xy - self.eff_h
        max_dist = cfg.L1 + cfg.L2 - 1.0  # mic marja
        max_z_rel = math.sqrt(max(0, max_dist**2 - r_target**2))
        return max_z_rel + cfg.H_shoulder - self.eff_v

    def _interpolate_path(self, from_pos: str, to_pos: str, steps: int = 5) -> list:
        """
        Genereaza puncte intermediare intre from si to, la inaltime maxima
        sigura. Bratul urca -> traverseaza arc -> coboara.
        """
        x1, y1 = self.chess_to_xy(from_pos)
        x2, y2 = self.chess_to_xy(to_pos)

        waypoints = []

        # 1) Ridica la sursa - cat de sus poate
        h_up_src = min(self._max_reachable_height(x1, y1), 150.0)
        h_up_src = max(h_up_src, self.cfg.H_piece + 20)
        lift = self.solve_ik(x1, y1, h_target=h_up_src)
        if lift:
            waypoints.append(lift)

        # 2) Puncte intermediare de-a lungul arcului, la inaltime safe
        for i in range(1, steps + 1):
            t = i / (steps + 1)
            xi = x1 + (x2 - x1) * t
            yi = y1 + (y2 - y1) * t
            h_max = min(self._max_reachable_height(xi, yi), 150.0)
            h_max = max(h_max, self.cfg.H_piece + 20)
            pt = self.solve_ik(xi, yi, h_target=h_max)
            if pt:
                waypoints.append(pt)

        # 3) Sus deasupra destinatiei
        h_up_dst = min(self._max_reachable_height(x2, y2), 150.0)
        h_up_dst = max(h_up_dst, self.cfg.H_piece + 20)
        hover = self.solve_ik(x2, y2, h_target=h_up_dst)
        if hover:
            waypoints.append(hover)

        return waypoints

    def _move_between_squares_arc(self, from_pos: str, to_pos: str, steps: int = 5) -> bool:
        waypoints = self._interpolate_path(from_pos, to_pos, steps=steps)
        if not waypoints:
            return False

        for waypoint in waypoints:
            if not self.send_angles_to_esp32(waypoint):
                return False
            time.sleep(self.MOVE_WAYPOINT_DELAY_SEC)

        return True

    def send_command(self, cmd: str) -> str:
        if self.serial is None:
            return "Nu sunt conectat!"

        self.serial.reset_input_buffer()
        self.serial.write(f"{cmd}\n".encode())

        time.sleep(0.1)
        response = ""
        timeout = time.time() + 10
        while time.time() < timeout:
            if self.serial.in_waiting:
                response = self.serial.readline().decode(errors="ignore").strip()
                break
            time.sleep(0.1)
        return response

    def calculate_servo_angles(self, pos: str) -> Optional[Dict[ServoName, int]]:
        pos = self._normalize_square(pos)
        x, y = self.chess_to_xy(pos)
        angles = self.solve_ik(x, y)

        if angles is None:
            print(f"{pos.upper()} - Inaccesibil!")
            return None

        return angles

    def send_angles_to_esp32(self, angles: Dict[ServoName, int]) -> bool:
        if self.serial is None:
            print("Nu sunt conectat!")
            return False

        base = angles[ServoName.BASE]
        shoulder = angles[ServoName.SHOULDER]
        elbow = angles[ServoName.ELBOW]

        cmd = f"B{base},S{shoulder},E{elbow}"
        response = self.send_command(cmd)
        print(f"   Robot: {response}")
        return True

    def _move_to_square(self, pos: str) -> bool:
        pos = self._normalize_square(pos)
        angles = self.calculate_servo_angles(pos)
        if angles is None:
            return False

        col = self.get_column(pos)
        side = "(stanga)" if col < 3 else "(dreapta)" if col > 3 else "(centru)"
        print(
            f"{pos.upper()} {side}:  Baza={angles[ServoName.BASE]} "
            f"Umar={angles[ServoName.SHOULDER]} Cot={angles[ServoName.ELBOW]}"
        )
        return self.send_angles_to_esp32(angles)

    def move_piece_between_squares(self, from_pos: str, to_pos: str) -> bool:
        from_pos = self._normalize_square(from_pos)
        to_pos = self._normalize_square(to_pos)

        print(f"\n{'='*40}")
        print(f"MUTARE:  {from_pos.upper()} -> {to_pos.upper()}")
        print(f"{'='*40}")

        print("\n[1] Merg la piesa...")
        if not self._move_to_square(from_pos):
            return False
        time.sleep(0.2)

        print("\n[2] Prind piesa...")
        response = self.send_command("GRIP")
        print(f"   Robot: {response}")
        time.sleep(0.2)

        print("\n[3] Ridic si traversez...")
        if not self._move_between_squares_arc(from_pos, to_pos):
            response = self.send_command("MIDDLE")
            print(f"   Robot:  {response}")
            time.sleep(0.1)

        print("\n[4] Merg la destinatie...")
        if not self._move_to_square(to_pos):
            return False
        time.sleep(0.2)

        print("\n[5] Las piesa...")
        response = self.send_command("LASA")
        print(f"   Robot:  {response}")
        time.sleep(0.2)

        print("\n[6] Revenire base...")
        response = self.send_command("BASE")
        print(f"   Robot:  {response}")

        print(f"\nMUTARE COMPLETA: {from_pos.upper()} -> {to_pos.upper()}")
        return True

    def take_piece_and_move(self, from_pos: str, capture_pos: str) -> bool:
        from_pos = self._normalize_square(from_pos)
        capture_pos = self._normalize_square(capture_pos)

        print(f"\n{'='*40}")
        print(f"CAPTURA: {from_pos.upper()} x {capture_pos.upper()}")
        print(f"{'='*40}")

        print("\n[1] Merg la piesa capturata...")
        if not self._move_to_square(capture_pos):
            return False
        time.sleep(0.2)

        print("\n[2] Prind piesa capturata...")
        response = self.send_command("GRIP")
        print(f"   Robot: {response}")
        time.sleep(0.2)

        print("\n[3] Ridic...")
        response = self.send_command("MIDDLE")
        print(f"   Robot: {response}")
        time.sleep(0.1)

        print("\n[4] Duc piesa capturata in afara tablei...")
        cmd = "B150,S45,E90"
        response = self.send_command(cmd)
        print(f"   Robot: {response}")
        time.sleep(0.2)

        print("\n[5] Las piesa capturata...")
        response = self.send_command("LASA")
        print(f"   Robot: {response}")
        time.sleep(0.2)

        print("\n[6] Revenire safe...")
        response = self.send_command("MIDDLE")
        print(f"   Robot: {response}")
        time.sleep(0.1)

        print("\n[7] Mutam piesa atacatoare...")
        return self.move_piece_between_squares(from_pos, capture_pos)

    def close(self) -> None:
        if self.serial:
            self.serial.close()
            print("Deconectat")


__all__ = ["ChessRobot", "RobotConfig", "ServoName"]
