"""Đếm byte thật ở tầng socket bằng cách bọc socket của Python.

Vì sao cần: nếu chỉ đo len(json) thì ta bỏ qua toàn bộ header giao thức —
mà header CHÍNH LÀ thứ phân biệt HTTP với MQTT/CoAP. HTTP request có
~150-250B header text; MQTT chỉ 2-4B. Không đếm header thì so sánh vô nghĩa.

Cách làm: monkey-patch tạm thời socket.socket.send/recv trong một
context manager, cộng dồn số byte đi qua. Bỏ patch ngay khi xong.

CẢNH BÁO QUAN TRỌNG (đã gặp thật khi phát triển):
    Patch này là TOÀN CỤC trong tiến trình. Nếu server chạy chung tiến
    trình với client thì byte của server CŨNG bị đếm -> số liệu sai gấp đôi.
    Vì vậy mọi server trong bộ demo này đều chạy ở TIẾN TRÌNH RIÊNG
    (xem protocols/*_server.py). Cách này còn đúng với thực tế hơn:
    thiết bị và máy chủ vốn là hai máy khác nhau.
"""
from __future__ import annotations

import socket
import threading
from contextlib import contextmanager
from typing import Iterator

from .metrics import ByteCounter


class _CountingSocket(socket.socket):
    """Socket ghi lại số byte gửi/nhận vào bộ đếm dùng chung."""

    _counter: ByteCounter | None = None

    def send(self, data, *args, **kwargs):  # type: ignore[override]
        n = super().send(data, *args, **kwargs)
        if _CountingSocket._counter is not None:
            _CountingSocket._counter.add_sent(n)
        return n

    def sendall(self, data, *args, **kwargs):  # type: ignore[override]
        result = super().sendall(data, *args, **kwargs)
        if _CountingSocket._counter is not None:
            _CountingSocket._counter.add_sent(len(data))
        return result

    def recv(self, bufsize, *args, **kwargs):  # type: ignore[override]
        data = super().recv(bufsize, *args, **kwargs)
        if _CountingSocket._counter is not None:
            _CountingSocket._counter.add_recv(len(data))
        return data

    def recv_into(self, buffer, nbytes=0, *args, **kwargs):  # type: ignore[override]
        n = super().recv_into(buffer, nbytes, *args, **kwargs)
        if _CountingSocket._counter is not None:
            _CountingSocket._counter.add_recv(n)
        return n


_patch_lock = threading.Lock()


@contextmanager
def count_socket_bytes(counter: ByteCounter) -> Iterator[ByteCounter]:
    """Đếm mọi byte đi qua socket trong khối ``with``.

    Dùng::

        counter = ByteCounter()
        with count_socket_bytes(counter):
            requests.post(...)
        print(counter.bytes_sent, counter.bytes_recv)

    Lưu ý: chỉ đếm socket TCP/UDP do Python tạo trong khối này. Header
    TCP/IP do kernel thêm KHÔNG thấy được ở đây — chúng được ước lượng
    riêng qua ``ProtocolReport.l3_bytes_per_packet``.
    """
    with _patch_lock:
        original = socket.socket
        _CountingSocket._counter = counter
        socket.socket = _CountingSocket  # type: ignore[misc,assignment]
        try:
            yield counter
        finally:
            socket.socket = original  # type: ignore[misc]
            _CountingSocket._counter = None


class UDPByteTracker:
    """Đếm byte cho UDP (CoAP) — đơn giản hơn vì mỗi datagram là 1 gói."""

    def __init__(self) -> None:
        self.counter = ByteCounter()

    def sent(self, data: bytes) -> None:
        self.counter.add_sent(len(data))

    def received(self, data: bytes) -> None:
        self.counter.add_recv(len(data))
