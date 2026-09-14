"""Khởi chạy / dừng server ở tiến trình riêng.

Mọi server (HTTP, MQTT broker, CoAP) đều chạy tách tiến trình để:
  1. Bộ đếm byte chỉ tính phía thiết bị (xem common/wire.py)
  2. Giống thực tế: thiết bị và máy chủ là hai máy khác nhau
"""
from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def wait_for_tcp(host: str, port: int, timeout: float = 15.0) -> bool:
    """Chờ tới khi cổng TCP mở. Trả về False nếu quá hạn."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def wait_for_udp(host: str, port: int, timeout: float = 15.0) -> bool:
    """Chờ server UDP (CoAP). UDP không bắt tay nên ta thử gửi rồi chờ.

    Cách đơn giản: thử bind vào cổng đó — nếu bind được nghĩa là CHƯA
    có ai nghe, tiếp tục chờ.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.bind((host, port))
            probe.close()
            time.sleep(0.15)        # còn bind được -> server chưa lên
        except OSError:
            probe.close()
            return True             # cổng đã bị chiếm -> server đang nghe
    return False


class ServerProcess:
    """Quản lý vòng đời một server con.

    Dùng như context manager::

        with ServerProcess("protocols/http_server.py", port=5001):
            ...  # server đang chạy
        # tự tắt khi ra khỏi khối
    """

    def __init__(
        self,
        script: str,
        host: str = "127.0.0.1",
        port: int = 0,
        udp: bool = False,
        args: list[str] | None = None,
        quiet: bool = True,
    ) -> None:
        self.script = script
        self.host = host
        self.port = port
        self.udp = udp
        self.args = args or []
        self.quiet = quiet
        self.proc: subprocess.Popen | None = None

    def start(self) -> "ServerProcess":
        cmd = [sys.executable, str(PROJECT_ROOT / self.script), *self.args]
        self.proc = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.DEVNULL if self.quiet else None,
            stderr=subprocess.PIPE if self.quiet else None,
            text=True,
        )
        ok = (wait_for_udp if self.udp else wait_for_tcp)(self.host, self.port)
        if not ok:
            err = ""
            if self.proc.poll() is not None and self.proc.stderr:
                err = self.proc.stderr.read()[:800]
            self.stop()
            raise RuntimeError(
                f"Server {self.script} khong khoi dong duoc tren "
                f"{self.host}:{self.port}\n{err}"
            )
        return self

    def stop(self) -> None:
        if self.proc is None:
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=3)
        self.proc = None

    def __enter__(self) -> "ServerProcess":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()
