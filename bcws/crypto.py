# type: ignore
import ecdsa


class PrivateKey:
    def __init__(self, key: ecdsa.SigningKey):
        self._key = key

    @classmethod
    def generate(cls):
        return cls(ecdsa.SigningKey.generate())

    @classmethod
    def from_bytes(cls, data: bytes):
        return cls(ecdsa.SigningKey.from_string(data))

    def to_bytes(self) -> bytes:
        return self._key.to_string()

    def to_public(self):
        return PublicKey(self._key.get_verifying_key())

    def sign(self, data: bytes) -> bytes:
        return self._key.sign_deterministic(data)


class PublicKey:
    def __init__(self, key: ecdsa.VerifyingKey):
        self._key = key

    @classmethod
    def from_bytes(cls, data: bytes):
        return cls(ecdsa.VerifyingKey.from_string(data))

    def to_bytes(self) -> bytes:
        return self._key.to_string(encoding="compressed")

    def verify(self, data: bytes, sig: bytes) -> bool:
        try:
            self._key.verify(sig, data)
            return True
        except ecdsa.BadSignatureError:
            return False
