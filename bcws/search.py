import os
import threading
import time
from typing import Callable

from .gossip import Gossip
from .p2p import P2PPeer
from .utils import run_in_background, safe_invoke

_SEARCH_TIMEOUT = 30

type SearchHandler = Callable[[bytes], bytes | None]
type SearchResultHandler = Callable[[bytes | None], bool]


class Search:
    def __init__(self, gossip: Gossip):
        self.gossip = gossip
        self.p2p = gossip.p2p

        self._search_handlers: dict[str, SearchHandler] = {}
        self._queries: dict[
            bytes, tuple[threading.Lock, SearchResultHandler, float]
        ] = {}
        self._return_paths: dict[bytes, tuple[P2PPeer, float]] = {}

    def start(self) -> None:
        self._stopped = threading.Event()
        self._timeout_loop_thread = run_in_background(self._timeout_loop)

    def stop(self) -> None:
        pass

    def register(self, kind: str, handler: SearchHandler):
        if kind in self._search_handlers:
            raise ValueError(f"Search handler for kind '{kind}' is already registered.")

        self._search_handlers[kind] = handler

        _gossip_msg = "search:" + kind
        _search_response_msg = "search_response:" + kind

        def _gossip_handler(peer: P2PPeer, payload: bytes):
            search_id = payload[:16]
            message_payload = payload[16:]

            response = safe_invoke(handler, message_payload)
            if response is not None:
                self.p2p.send_message(peer, _search_response_msg, search_id + response)
                return False
            else:
                self._return_paths[search_id] = (peer, time.time())
                return True

        def _response_handler(peer: P2PPeer, payload: bytes):
            search_id = payload[:16]
            message_payload = payload[16:]

            if search_id in self._queries:
                l, result_handler, _ = self._queries[search_id]
                with l:
                    if search_id not in self._queries:
                        return
                    if safe_invoke(result_handler, message_payload):
                        self._queries.pop(search_id, None)
            elif search_id in self._return_paths:
                peer2, _ = self._return_paths.pop(search_id, (None, 0.0))
                if peer2 is not None:
                    self.p2p.send_message(peer2, _search_response_msg, message_payload)

        self.gossip.register_handler(_gossip_msg, _gossip_handler)
        self.p2p.register_handler(_search_response_msg, _response_handler)

    def query(
        self,
        kind: str,
        payload: bytes,
        result_handler: SearchResultHandler,
    ) -> None:
        """Submits a query to the network.

        Args:
            kind (str): The kind of data being searched for.
            payload (bytes): The payload of the search query.
            result_handler (SearchResultHandler): The handler for processing search results. If the handler returns True, the search is considered complete.
        """
        msg_id = _make_msg_id()
        self._queries[msg_id] = (threading.Lock(), result_handler, time.time())
        self.gossip.broadcast("search:" + kind, msg_id + payload)

    def _timeout_loop(self) -> None:
        while not self._stopped.is_set():
            for k, (l, rh, ts) in list(self._queries.items()):
                if time.time() - ts > _SEARCH_TIMEOUT:
                    with l:
                        if k not in self._queries:
                            continue
                        self._queries.pop(k, None)
                        safe_invoke(rh, None)
            for k, (_, ts) in list(self._return_paths.items()):
                if time.time() - ts > _SEARCH_TIMEOUT:
                    self._return_paths.pop(k, None)

            self._stopped.wait(5)


def _make_msg_id() -> bytes:
    return os.urandom(16)
