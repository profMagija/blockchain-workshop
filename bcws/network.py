import logging
import socket
from typing import Any


from .utils import (
    EventHandler,
    InfiniteLoop,
    recv_exact,
)

type TcpAddress = tuple[str, int]


class TcpConnection:

    def __init__(self, sock: socket.socket, addr: TcpAddress):
        self.addr = addr
        self.sock = sock
        self.connected = True
        self.listen_thread: InfiniteLoop

    def send_message(self, message: bytes) -> None:
        """Send a message to the connection."""
        if not self.connected:
            return

        length = len(message).to_bytes(4, byteorder="big")
        self.sock.sendall(length + message)

    def __hash__(self):
        return hash(self.addr)

    def __eq__(self, other: Any):
        return isinstance(other, TcpConnection) and self.addr == other.addr

    def __repr__(self) -> str:
        return f"TcpConnection(addr={self.addr}, connected={self.connected})"


class TcpServer:
    def __init__(
        self,
        addr: TcpAddress,
    ):
        self.addr = addr
        self.on_connect = EventHandler[TcpConnection, bool]()
        self.on_message = EventHandler[TcpConnection, bytes]()
        self.on_disconnect = EventHandler[TcpConnection, bool]()
        self.listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listen_socket.bind(self.addr)
        self.listen_socket.listen()
        self.conns: dict[TcpAddress, TcpConnection] = {}

    def start(self):
        self.listen_thread = InfiniteLoop(self._listen_for_conns)
        self.listen_thread.start()

    def stop(self):
        self.running = False
        self.listen_socket.close()
        self.listen_thread.stop()

    def connect(self, addr: TcpAddress):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect(addr)
            return self._create_conn(sock, addr, True)
        except Exception:
            logging.exception("Error connecting to conn %s", addr, stack_info=True)

    def disconnect(self, conn: TcpConnection):
        if not conn.connected:
            return

        self._disconnect(conn, True)

    def _disconnect(self, conn: TcpConnection, initiated: bool):
        self.conns.pop(conn.addr, None)
        conn.connected = False
        conn.sock.close()
        conn.listen_thread.stop()
        self.on_disconnect.notify(conn, initiated)

    def _listen_for_conns(self):
        try:
            sock, addr = self.listen_socket.accept()
        except Exception:
            return
        self._create_conn(sock, addr, False)

    def _create_conn(
        self, sock: socket.socket, addr: TcpAddress, initiated: bool
    ) -> TcpConnection:
        conn = TcpConnection(sock, addr)
        self.conns[addr] = conn

        conn.listen_thread = InfiniteLoop(lambda: self._recv_loop(conn))
        self.on_connect.notify(conn, initiated)
        conn.listen_thread.start()
        return conn

    def _recv_loop(self, conn: TcpConnection):
        if not conn.connected:
            conn.listen_thread.stop()

        try:
            len_bytes = recv_exact(conn.sock, 4)
            if len_bytes is None:
                raise Exception("Connection closed")

            length = int.from_bytes(len_bytes, byteorder="big")
            message = recv_exact(conn.sock, length)
            if message is None:
                raise Exception("Connection closed")

            self.on_message.notify(conn, message)
        except Exception:
            if conn.connected:
                self._disconnect(conn, False)


def parse_address(address: str) -> TcpAddress:
    host, port_str = address.split(":")
    return (host, int(port_str))


def address_to_str(addr: TcpAddress) -> str:
    return f"{addr[0]}:{addr[1]}"
