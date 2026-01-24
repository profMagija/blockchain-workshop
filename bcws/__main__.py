import json
import logging
import random
import time

import click

from .blockchain import BlockchainNode, Transaction
from .crypto import PrivateKey
from .gossip import Gossip
from .messaging import Messaging
from .network import TcpConnection, TcpServer, parse_address
from .p2p import P2PNode, P2PPeer, network_discovery_loop
from .search import Search
from .storage import StorageMaster
from .utils import run_in_background

logging.basicConfig(level=logging.INFO)

_host: str
_port: int
_peers: list[str]


@click.group()
@click.option("--host", default="127.0.0.1", help="Host to listen on")
@click.option("--port", default=15151, help="Port to listen on")
@click.option(
    "--peer", multiple=True, help="Peer address to connect to (format: host:port)"
)
def main(host: str, port: int, peer: list[str]):
    global _host, _port, _peers
    _host = host
    _port = port
    _peers = peer


def _add_node_logging(node: TcpServer) -> None:
    def on_connect(conn: TcpConnection, initiated: bool) -> None:
        logging.info("Connected to %s (initiated=%s)", conn.addr, initiated)

    def on_message(conn: TcpConnection, message: bytes) -> None:
        logging.info("Received message from %s: %s", conn.addr, message)

    def on_disconnect(conn: TcpConnection, initiated: bool) -> None:
        logging.info("Disconnected from %s (initiated=%s)", conn.addr, initiated)

    node.on_connect.register(on_connect)
    node.on_message.register(on_message)
    node.on_disconnect.register(on_disconnect)


def _connect_to_peers(node: TcpServer, peer_addresses: list[str]) -> None:
    for p in peer_addresses:
        host, port_str = p.split(":")
        addr = (host, int(port_str))
        node.connect(addr)


@main.command()
def networking(port: int, peer: list[str]):

    node = TcpServer((_host, port))
    _add_node_logging(node)

    node.start()
    logging.info("Node started on port %d", port)

    _connect_to_peers(node, peer)

    try:
        while True:
            message = input()
            if message.lower() == "exit":
                break

            for conn in node.conns.values():
                conn.send_message(message.encode())
    except KeyboardInterrupt:
        logging.info("Shutting down node...")

    node.stop()


@main.command()
def messaging():
    node = TcpServer((_host, _port))
    messaging = Messaging(node)

    # _add_node_logging(node)

    def on_message(conn: TcpConnection, payload: bytes) -> bytes | None:
        logging.info("Received message from %s: %s", conn.addr, payload)
        response = b"Echo: " + payload
        return response

    def on_response(conn: TcpConnection, payload: bytes | None) -> None:
        if payload is None:
            logging.info("No response from %s", conn.addr)
        else:
            logging.info("Received response from %s: %s", conn.addr, payload)

    messaging.register_handler("echo", on_message)

    node.start()
    messaging.start()

    logging.info("Messaging node started on port %d", _port)

    _connect_to_peers(node, _peers)

    try:
        while True:
            message = "this is a test message"
            for conn in node.conns.values():
                messaging.send_message(conn, "echo", message.encode(), on_response)
            time.sleep(5)
    except KeyboardInterrupt:
        logging.info("Shutting down messaging node...")

    node.stop()


@main.command()
@click.option("--nd", is_flag=True, help="Enable network discovery background task")
def p2p(nd: bool):
    bootstrap_nodes = [parse_address(p) for p in _peers]

    node = TcpServer((_host, _port))
    messaging = Messaging(node)
    p2p_node = P2PNode(node, messaging, 4, bootstrap_nodes=bootstrap_nodes)

    node.start()
    messaging.start()
    p2p_node.start()

    if nd:
        run_in_background(network_discovery_loop, p2p_node)

    for p in _peers:
        addr = parse_address(p)
        p2p_node.connect_to_peer(addr)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Shutting down P2P node...")

    node.stop()


@main.command()
@click.option("--nd", is_flag=True, help="Enable network discovery background task")
def gossip(nd: bool):
    bootstrap_nodes = [parse_address(p) for p in _peers]

    node = TcpServer((_host, _port))
    messaging = Messaging(node)
    p2p_node = P2PNode(node, messaging, 4, bootstrap_nodes=bootstrap_nodes)
    gossip = Gossip(p2p_node)

    def _print_message(peer: P2PPeer, payload: bytes):
        sender, message = payload.decode().split("\0", 1)
        print(f"[{sender}] {message}")
        return True

    gossip.register_handler("chat", _print_message)

    node.start()
    messaging.start()
    p2p_node.start()
    gossip.start()

    if nd:
        run_in_background(network_discovery_loop, p2p_node)

    for p in _peers:
        addr = parse_address(p)
        p2p_node.connect_to_peer(addr)

    try:
        while True:
            msg = "hello world"
            sender = f"{_host}:{_port}"
            payload = f"{sender}\0{msg}".encode()
            gossip.broadcast("chat", payload)

            time.sleep(5 * random.random())

    except KeyboardInterrupt:
        logging.info("Shutting down Gossip node...")

    gossip.stop()
    node.stop()


@main.command()
@click.option("--nd", is_flag=True, help="Enable network discovery.")
@click.option("--ds", is_flag=True, help="Dump blockchain state periodically.")
@click.option(
    "--state-dir", default=":memory:", help="Directory to store blockchain state."
)
def blockchain(nd: bool, ds: bool, state_dir: str):

    net = TcpServer((_host, _port))
    msg = Messaging(net)
    network = P2PNode(net, msg, bootstrap_nodes=[parse_address(p) for p in _peers])
    gossip = Gossip(network)
    search = Search(gossip)
    sm = StorageMaster(state_dir)
    blockchain_node = BlockchainNode(sm, gossip, search)

    pk_storage = sm.get_storage("privkey")
    pk = pk_storage.load("privkey")
    if pk is None:
        pk = PrivateKey.generate()
        pk_storage.save("privkey", pk.to_bytes())
    else:
        pk = PrivateKey.from_bytes(pk)

    my_address = pk.to_public().to_bytes()

    blockchain_node.coinbase = my_address

    net.start()
    msg.start()
    network.start()
    gossip.start()
    search.start()
    blockchain_node.start()

    if nd:
        run_in_background(network_discovery_loop, network)

    if ds:

        def _do_state_dump():
            try:
                while True:
                    transactions = [
                        tx.to_json()
                        for block in blockchain_node.canonicaliser.iter_blocks()
                        for tx in block.transactions
                    ]
                    latest_block = blockchain_node.canonicaliser.get_block_by_number(-1)
                    latest_state = (
                        blockchain_node.canonicaliser.get_latest_state().to_json()
                    )
                    with open("state.json", "w") as f:
                        json.dump(
                            {
                                "transactions": transactions,
                                "latest_state": latest_state,
                                "latest_block": latest_block.to_json(),
                            },
                            f,
                        )
                    time.sleep(1)
            except Exception as e:
                logging.exception("Error in state dump thread: %s", e)

        run_in_background(_do_state_dump)

    while True:
        time.sleep(10)

    while True:
        action = input("[s]end, [b]alance, [n]once, [l]atest, [q]uit: ").lower()
        if action == "s":
            receiver = input("Enter recipient: ")
            amount = int(input("Enter amount: "))

            tx = Transaction()
            tx.nonce = blockchain_node.get_nonce(my_address)
            tx.sender = my_address
            tx.receiver = bytes.fromhex(receiver)
            tx.amount = amount
            tx.sign(pk)

            blockchain_node.send_transaction(tx)

        elif action == "b":
            address = input("Enter address: ")
            if address == "":
                address = my_address.hex()
            print(blockchain_node.get_balance(bytes.fromhex(address)))
        elif action == "n":
            address = input("Enter address: ")
            if address == "":
                address = my_address.hex()
            print(blockchain_node.get_nonce(bytes.fromhex(address)))
        elif action == "l":
            state = blockchain_node.canonicaliser.get_latest_state()
            print("Latest state:")
            print("  Block number:", state.block_number)
            print("  Block hash:", state.block_hash.hex())
            print("  Accounts:")
            for address, balance in state.balances.items():
                print("    ", address.hex(), balance, state.nonces.get(address, 0))
            print()

        elif action == "q":
            break
        else:
            print("Invalid action. Try again.")


main()
