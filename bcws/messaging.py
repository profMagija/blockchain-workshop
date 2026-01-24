import threading
import time
from typing import Callable

from .utils import run_in_background, safe_invoke
from .network import TcpServer, TcpConnection


type MessageHandler = Callable[[TcpConnection, bytes], bytes | None]
type MessageResponseHandler = Callable[[TcpConnection, bytes | None], None]

DEFAULT_TIMEOUT = 10.0


_MESSAGE_TYPE_STANDARD = 0
_MESSAGE_TYPE_STANDARD_WITH_RESPONSE = 1
_MESSAGE_TYPE_RESPONSE = 2


class MessagingMessage:
    def __init__(self, message_type: int, message_id: int, kind: str, payload: bytes):
        self.message_type = message_type
        self.message_id = message_id
        self.kind = kind
        self.payload = payload

    def serialize(self) -> bytes:
        ba = bytearray()
        ba.append(self.message_type)
        ba.extend(self.message_id.to_bytes(4, byteorder="big"))
        ba.extend(self.kind.encode("utf-8"))
        ba.append(0)
        ba.extend(self.payload)
        return bytes(ba)

    @staticmethod
    def deserialize(data: bytes) -> "MessagingMessage":
        message_type = data[0]
        message_id = int.from_bytes(data[1:5], byteorder="big")
        null_index = data.index(0, 5)
        kind = data[5:null_index].decode("utf-8")
        payload = data[null_index + 1 :]
        return MessagingMessage(message_type, message_id, kind, payload)

    def __repr__(self) -> str:
        return f"MessagingMessage(type={self.message_type}, id={self.message_id}, kind={self.kind!r}, payload={self.payload!r})"


class Messaging:
    def __init__(self, net: TcpServer):
        net.on_message.register(self._handle_message)

        self._message_handlers: dict[str, MessageHandler] = {}
        self._last_message_id = 0
        self._response_handlers: dict[
            tuple[TcpConnection, int], tuple[float, MessageResponseHandler]
        ] = {}

    def start(self):
        self._stopped = threading.Event()
        self._process_thread = run_in_background(self._process_timeouts)

    def stop(self):
        self._stopped.set()
        if self._process_thread is not threading.current_thread():
            self._process_thread.join()

    def register_handler(self, kind: str, handler: MessageHandler):
        if kind in self._message_handlers:
            raise ValueError(f"Handler for kind '{kind}' is already registered")
        self._message_handlers[kind] = handler

    def send_message(
        self,
        conn: TcpConnection,
        kind: str,
        payload: bytes,
        response_handler: MessageResponseHandler | None = None,
        response_timeout: float | None = None,
    ) -> None:
        message_id = self._next_message_id()
        if response_handler is not None:
            response_timeout = response_timeout or DEFAULT_TIMEOUT
            expire_at = time.time() + response_timeout
            self._response_handlers[(conn, message_id)] = (expire_at, response_handler)
            message_type = _MESSAGE_TYPE_STANDARD_WITH_RESPONSE
        else:
            message_type = _MESSAGE_TYPE_STANDARD

        message = MessagingMessage(
            message_type=message_type,
            message_id=message_id,
            kind=kind,
            payload=payload,
        )
        conn.send_message(message.serialize())

    def _handle_message(self, conn: TcpConnection, data: bytes) -> None:
        message = MessagingMessage.deserialize(data)
        if message.message_type == _MESSAGE_TYPE_RESPONSE:
            return self._handle_response(conn, message)

        handler = self._message_handlers.get(message.kind)
        if handler is None:
            return  # Unknown message kind; ignore

        response_payload = handler(conn, message.payload)
        if (
            message.message_type == _MESSAGE_TYPE_STANDARD_WITH_RESPONSE
            and response_payload is not None
        ):
            response_message = MessagingMessage(
                message_type=_MESSAGE_TYPE_RESPONSE,
                message_id=message.message_id,
                kind="",
                payload=response_payload,
            )
            conn.send_message(response_message.serialize())

    def _handle_response(self, conn: TcpConnection, message: MessagingMessage) -> None:
        key = (conn, message.message_id)
        _, response_handler = self._response_handlers.pop(key, (0.0, None))
        if response_handler is not None:
            safe_invoke(response_handler, conn, message.payload)

    def _next_message_id(self) -> int:
        self._last_message_id += 1
        return self._last_message_id

    def _process_timeouts(self) -> None:
        while not self._stopped.is_set():
            now = time.time()
            handlers_to_invoke: list[tuple[TcpConnection, MessageResponseHandler]] = []
            for key, (expire_at, handler) in list(self._response_handlers.items()):
                if now >= expire_at:
                    handlers_to_invoke.append((key[0], handler))
                    del self._response_handlers[key]

            for peer, handler in handlers_to_invoke:
                safe_invoke(handler, peer, None)

            self._stopped.wait(1.0)
