from typing import Callable

from .p2p import P2PNode, P2PPeer

# --------8<--------
import time
import threading
import os

from .utils import run_in_background, safe_invoke

# --------8<--------

type GossipHandler = Callable[[P2PPeer, bytes], bool]

_MESSAGE_ID_LEN = 16
_EXPIRY_TIME = 300


class Gossip:
    def __init__(self, p2p: P2PNode):
        self.p2p = p2p
        # --------8<--------
        self.seen_messages: dict[bytes, float] = {}
        # --------8<--------

    def start(self) -> None:
        # <<raise NotImplementedError
        # --------8<--------
        self._stopped = threading.Event()
        self._cleanup_thread = run_in_background(self._cleanup_loop)
        # --------8<--------

    def stop(self) -> None:
        # <<raise NotImplementedError
        # --------8<--------
        self._stopped.set()
        if self._cleanup_thread is not threading.current_thread():
            self._cleanup_thread.join()
        # --------8<--------

    def broadcast(self, kind: str, payload: bytes) -> None:
        """Broadcast a message to all peers using gossip protocol."""
        # <<raise NotImplementedError
        # --------8<--------
        message_id = _make_msg_id()
        if message_id not in self.seen_messages:
            self.seen_messages[message_id] = time.time()
            message = message_id + payload
            self.p2p.broadcast_message("gossip:" + kind, message)
        # --------8<--------

    def register_handler(self, kind: str, handler: GossipHandler) -> None:
        """Register a handler for a gossip message type.

        The handler should return True if the message is valid and should be
        re-gossiped to other peers, or False otherwise.
        """
        # <<raise NotImplementedError
        # --------8<--------

        def gossip_handler(peer: P2PPeer, payload: bytes):

            message_id = payload[:_MESSAGE_ID_LEN]
            message_payload = payload[_MESSAGE_ID_LEN:]

            if message_id in self.seen_messages:
                return

            if not safe_invoke(handler, peer, message_payload):
                return

            self.seen_messages[message_id] = time.time()
            self.p2p.broadcast_message(
                "gossip:" + kind,
                payload,
                except_peers={peer},
            )

        self.p2p.register_handler("gossip:" + kind, gossip_handler)

    def _cleanup_loop(self) -> None:
        """Periodically remove expired messages."""
        while True:
            now = time.time()
            expired_keys = [
                key for key, ts in self.seen_messages.items() if now - ts > _EXPIRY_TIME
            ]
            for key in expired_keys:
                del self.seen_messages[key]
            self._stopped.wait(60)


def _make_msg_id() -> bytes:
    return os.urandom(_MESSAGE_ID_LEN)
