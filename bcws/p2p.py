from typing import Callable
from .network import TcpAddress, TcpServer, TcpConnection, address_to_str
from .messaging import Messaging

# --------8<--------
import logging
from .network import parse_address
from .messaging import MessageHandler, MessageResponseHandler
from .utils import InfiniteLoop
import random
import itertools

_P2P_HELLO = "p2p:hello"
_P2P_GET_PEERS = "p2p:get_peers"
# --------8<--------


class P2PPeer:
    def __init__(self, conn: TcpConnection, addr: TcpAddress):
        self.conn = conn
        self.addr = addr

    def __repr__(self) -> str:
        return f"<P2PPeer {address_to_str(self.addr)}>"

    def __hash__(self):
        return hash(self.addr)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, P2PPeer) and self.addr == other.addr


type P2PMessageHandler = Callable[[P2PPeer, bytes], bytes | None]
type P2PMessageResponseHandler = Callable[[P2PPeer, bytes | None], None]


class P2PNode:
    def __init__(
        self,
        net: TcpServer,
        msg: Messaging,
        max_peers: int = 40,
        bootstrap_nodes: list[TcpAddress] = [],
    ):
        """Create a P2P node."""
        self.net = net
        self.msg = msg
        self.min_peers = max_peers // 2
        self.max_peers = max_peers
        self.bootstrap_nodes = bootstrap_nodes

        # --------8<--------
        self.peers: set[P2PPeer] = set()
        self._peers_addr: dict[TcpAddress, P2PPeer] = {}
        self._peers_conn: dict[TcpConnection, P2PPeer] = {}
        self.msg.register_handler(_P2P_HELLO, self._handle_hello)
        self.msg.register_handler(_P2P_GET_PEERS, self._handle_get_peers)
        self.net.on_disconnect.register(self._on_disconnect)
        # --------8<--------

    def start(self) -> None:
        """Start the P2P node.

        This will start the necessary background tasks to manage peers. The node
        will attempt to maintain a number of connected peers between min_peers
        and max_peers. If there are too few peers, it will request peer addresses
        from existing peers. If there are too many peers, it will disconnect
        from some peers.
        """
        # <<raise NotImplementedError
        # --------8<--------
        self._peer_loop_thread = InfiniteLoop(self._peer_loop, 1)
        self._peer_loop_thread.start()

        for addr in self.bootstrap_nodes:
            self.connect_to_peer(addr)
        # --------8<--------

    def stop(self) -> None:
        """Stop the P2P node.

        This will stop all background tasks and disconnect from all peers.
        """
        # <<raise NotImplementedError
        # --------8<--------
        for peer in list(self.peers):
            self.disconnect_peer(peer)
        # --------8<--------

    def register_handler(self, kind: str, handler: P2PMessageHandler) -> None:
        """Register a message handler for a specific kind of message."""
        # <<raise NotImplementedError
        # --------8<--------
        self.msg.register_handler(kind, self._make_handler(handler))
        # --------8<--------

    def connect_to_peer(self, addr: TcpAddress) -> None:
        """Connect to a peer at the given address.

        Thos method should do nothing if already connected to the peer. If not,
        we should initiate a connection and send the HELLO message.
        """
        # <<raise NotImplementedError
        # --------8<--------
        assert addr != self.net.addr

        if addr in self._peers_addr:
            return

        new_conn = self.net.connect(addr)
        if new_conn is None:
            return

        self.msg.send_message(
            new_conn,
            _P2P_HELLO,
            address_to_str(self.net.addr).encode(),
            self._handle_hello_response,
        )
        # --------8<--------

    def disconnect_peer(self, peer: P2PPeer) -> None:
        """Disconnect from a peer, removing it from our peer list, and closing
        the underlying connection.
        """
        # <<raise NotImplementedError
        # --------8<--------
        self._remove_peer(peer)
        self.net.disconnect(peer.conn)
        # --------8<--------

    def send_message(
        self,
        peer: P2PPeer,
        kind: str,
        payload: bytes,
        response_handler: P2PMessageResponseHandler | None = None,
        response_timeout: float | None = None,
    ) -> None:
        """Send a message to a specific peer.

        If a response handler is provided, it will be called when a response is
        received, or if a timeout occurs.
        """
        # <<raise NotImplementedError
        # --------8<--------
        if peer not in self.peers:
            return

        self.msg.send_message(
            peer.conn,
            kind,
            payload,
            self._make_response_handler(response_handler),
            response_timeout,
        )
        # --------8<--------

    def broadcast_message(
        self,
        kind: str,
        payload: bytes,
        response_handler: P2PMessageResponseHandler | None = None,
        response_timeout: float | None = None,
        except_peers: set[P2PPeer] = set(),
    ) -> None:
        """Broadcast a message to all connected peers."""
        # <<raise NotImplementedError
        # --------8<--------
        for peer in list(self.peers):
            if peer in except_peers:
                continue
            self.send_message(peer, kind, payload, response_handler, response_timeout)

    def _insert_peer(self, peer: P2PPeer) -> None:
        self.peers.add(peer)
        self._peers_conn[peer.conn] = peer
        self._peers_addr[peer.addr] = peer

    def _remove_peer(self, peer: P2PPeer) -> None:
        self.peers.discard(peer)
        self._peers_conn.pop(peer.conn, None)
        self._peers_addr.pop(peer.addr, None)

    def _handle_hello(self, conn: TcpConnection, payload: bytes) -> bytes | None:
        addr = parse_address(payload.decode())

        if addr in self.peers:
            logging.error("Received hello from existing peer %s", addr)
            return None

        peer_list = _make_peer_list([p.addr for p in self.peers])
        if len(self.peers) < self.max_peers * 2:
            self._insert_peer(P2PPeer(conn, addr))
            return b"\x01" + peer_list
        else:
            return b"\x00" + peer_list

    def _handle_hello_response(self, conn: TcpConnection, resp: bytes | None):
        if resp is None or len(resp) == 0:
            self.net.disconnect(conn)
            return

        accepted = resp[0] == 1
        addrs = _parse_peer_list(resp[1:])

        if accepted:
            peer = P2PPeer(conn, conn.addr)
            self._insert_peer(peer)

        self._connect_to_peers(addrs)

    def _handle_get_peers(self, conn: TcpConnection, payload: bytes) -> bytes | None:
        peer_addrs = [address_to_str(peer.addr) for peer in self.peers]
        data = ",".join(peer_addrs).encode()
        return data

    def _handle_get_peers_response(self, conn: TcpConnection, resp: bytes | None):
        if resp is None:
            return

        addrs = _parse_peer_list(resp)
        self._connect_to_peers(addrs)

    def _peer_loop(self):
        if len(self.peers) == 0:
            # re-bootstrap
            self._connect_to_peers(self.bootstrap_nodes)
        elif len(self.peers) < self.min_peers:
            for peer in list(self.peers):
                self.msg.send_message(
                    peer.conn,
                    _P2P_GET_PEERS,
                    b"",
                    self._handle_get_peers_response,
                )
        elif len(self.peers) > self.max_peers:
            peer = random.choice(list(self.peers))
            self.disconnect_peer(peer)

    def _connect_to_peers(self, addrs: list[TcpAddress]) -> None:
        addrs = addrs.copy()
        random.shuffle(addrs)
        for addr in addrs:
            if len(self.peers) >= self.max_peers:
                break
            if addr == self.net.addr:
                continue
            self.connect_to_peer(addr)

    def _make_handler(
        self,
        handler: P2PMessageHandler,
    ) -> MessageHandler:
        def wrapped(conn: TcpConnection, data: bytes) -> bytes | None:
            peer = self._peers_conn.get(conn)
            if peer is not None:
                return handler(peer, data)
            return None

        return wrapped

    def _make_response_handler(
        self,
        handler: P2PMessageResponseHandler | None,
    ) -> MessageResponseHandler | None:
        if handler is None:
            return None

        def wrapped(conn: TcpConnection, resp: bytes | None) -> None:
            peer = self._peers_conn.get(conn)
            if peer is not None:
                handler(peer, resp)

        return wrapped

    def _on_disconnect(self, conn: TcpConnection, initiated: bool) -> None:
        if initiated:
            return

        peer = self._peers_conn.get(conn)
        if peer is not None:
            self._remove_peer(peer)


def _make_peer_list(addrs: list[TcpAddress]) -> bytes:
    return ",".join([address_to_str(a) for a in addrs]).encode()


def _parse_peer_list(data: bytes) -> list[TcpAddress]:
    if len(data) == 0:
        return []

    addr_strs = data.decode().split(",")
    return [parse_address(addr_str) for addr_str in addr_strs]


# --------8<--------


def network_discovery_loop(p2p: P2PNode):
    # <<"""You are not supposed to implement this function."""
    # <<raise NotImplementedError
    # --------8<--------
    import time, json

    msg = p2p.msg
    net = p2p.net

    known_peers: set[TcpAddress] = set()
    peer_map: dict[TcpAddress, list[TcpAddress]] = {}

    def _response_handler(conn: TcpConnection, resp: bytes | None):
        if resp is None:
            peer_map.pop(conn.addr, None)
            known_peers.discard(conn.addr)
            return

        if len(resp) == 0:
            return

        addrs = [parse_address(a) for a in resp.decode().split(",")]
        peer_map[conn.addr] = addrs
        known_peers.update(addrs)

    while True:
        for my_peer in list(p2p.peers):
            if my_peer.addr not in known_peers:
                known_peers.add(my_peer.addr)

        for peer in list(known_peers):
            conn = net.connect(peer)

            if conn is None:
                known_peers.discard(peer)
                continue

            msg.send_message(conn, _P2P_GET_PEERS, b"", _response_handler, 10.0)

        with open("network_layout.json", "w") as f:
            json.dump(
                [
                    [
                        address_to_str(k),
                        [address_to_str(a) for a in sorted(peer_map.get(k, []))],
                    ]
                    for k in set(itertools.chain(*peer_map.values()))
                ],
                f,
                indent=2,
            )

        time.sleep(5)
