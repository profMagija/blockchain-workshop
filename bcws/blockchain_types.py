from typing import Any
import hashlib

from .crypto import PublicKey, PrivateKey


class Block:
    def __init__(self):
        self.number = 0
        self.nonce = 0
        self.parent_hash: bytes = b""
        self.coinbase: bytes = b""
        self.transactions: list[Transaction] = []
        self.hash: bytes = b""

    def has_difficulty(self, difficulty: int):
        self.calculate_hash()
        target = "0" * difficulty
        return self.hash.hex().startswith(target)

    def calculate_hash(self):
        data = self.serialize()
        self.hash = hashlib.sha256(data.encode()).digest()
        return self.hash

    def serialize(self):
        data = ""
        data += f"{self.number}"
        data += f":{self.nonce}"
        data += f":{self.parent_hash.hex()}"
        data += f":{self.coinbase.hex()}"
        for tx in self.transactions:
            data += f":{tx.serialize()}"
        return data

    @classmethod
    def deserialize(cls, data: str):
        block = cls()
        number, nonce, parent, coinbase, *transactions = data.split(":")
        block.number = int(number)
        block.nonce = int(nonce)
        block.parent_hash = bytes.fromhex(parent)
        block.coinbase = bytes.fromhex(coinbase)
        block.transactions = [Transaction.deserialize(tx) for tx in transactions]
        block.calculate_hash()
        return block

    def to_json(self) -> dict[str, Any]:
        self.calculate_hash()
        return {
            "number": self.number,
            "nonce": self.nonce,
            "parent_hash": self.parent_hash.hex(),
            "coinbase": self.coinbase.hex(),
            "transactions": [tx.to_json() for tx in self.transactions],
            "hash": self.hash.hex(),
        }

    def __repr__(self):
        return f"<Block {self.number} 0x..{self.hash.hex()[-8:]}>"


class Transaction:
    def __init__(self):
        self.sender = b""
        self.receiver = b""
        self.nonce = 0
        self.amount = 0
        self.sig = b""

    def data_to_sign(self):
        sender = self.sender.hex()
        receiver = self.receiver.hex()
        return f"{sender},{receiver},{self.nonce},{self.amount}"

    def serialize(self):
        assert self.sig, "Transaction not signed"

        data_to_sign = self.data_to_sign()
        sig = self.sig.hex()
        return f"{data_to_sign},{sig}"

    @classmethod
    def deserialize(cls, data: str):
        tx = cls()
        sender, receiver, nonce, amount, sig = data.split(",")
        tx.sender = bytes.fromhex(sender)
        tx.receiver = bytes.fromhex(receiver)
        tx.nonce = int(nonce)
        tx.amount = int(amount)
        tx.sig = bytes.fromhex(sig)
        return tx

    def sign(self, key: PrivateKey):
        data = self.data_to_sign().encode()
        self.sig = key.sign(data)

    def validate_signature(self):
        assert self.sig, "Transaction not signed"
        key = PublicKey.from_bytes(self.sender)
        return key.verify(self.data_to_sign().encode(), self.sig)

    def hash(self):
        return hashlib.sha256(self.serialize().encode()).digest()

    def to_json(self) -> dict[str, Any]:
        return {
            "hash": self.hash().hex(),
            "sender": self.sender.hex(),
            "receiver": self.receiver.hex(),
            "nonce": self.nonce,
            "amount": self.amount,
            "sig": self.sig.hex(),
        }

    def __repr__(self):
        return (
            f"<Transaction {self.sender.hex()} -> {self.receiver.hex()} {self.amount}>"
        )
