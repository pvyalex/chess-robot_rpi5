"""TCP server helper for accepting a single ESP32 client and sending commands."""
import socket
import threading
import time
from typing import Optional, Tuple


class TcpServerHelper:
    def __init__(self, host: str, port: int) -> None:
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind((host, port))
        self._server.listen(1)
        self._server.settimeout(1.0)

        self._client: Optional[socket.socket] = None
        self._client_addr: Optional[Tuple[str, int]] = None
        self._stop = threading.Event()

        self._thread = threading.Thread(
            target=self._accept_loop,
            name="tcp-accept",
            daemon=True,
        )
        self._thread.start()
        print(f"Robot server TCP pe {host}:{port}")

    def _accept_loop(self) -> None:
        while not self._stop.is_set() and self._client is None:
            try:
                client, addr = self._server.accept()
                client.settimeout(5)
                self._client = client
                self._client_addr = addr
                print(f"ESP32 conectat: {addr}")
                return
            except socket.timeout:
                continue
            except Exception as exc:
                print(f"Eroare accept TCP: {exc}")
                time.sleep(0.2)

    def send_and_recv(self, cmd: str, timeout_sec: int = 10) -> str:
        if self._client is None:
            return "Nu sunt conectat!"
        try:
            self._client.sendall(f"{cmd}\n".encode())
            return self._recv_line(timeout_sec)
        except Exception as exc:
            self._close_client()
            return f"ERR:{exc}"

    def _recv_line(self, timeout_sec: int) -> str:
        if self._client is None:
            return ""
        deadline = time.time() + timeout_sec
        data = b""
        while time.time() < deadline:
            try:
                chunk = self._client.recv(1)
            except socket.timeout:
                continue
            if not chunk:
                break
            if chunk == b"\n":
                break
            data += chunk
        return data.decode(errors="ignore").strip()

    def _close_client(self) -> None:
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
        self._client = None
        self._client_addr = None

    def close(self) -> None:
        self._stop.set()
        self._close_client()
        try:
            self._server.close()
        except Exception:
            pass
