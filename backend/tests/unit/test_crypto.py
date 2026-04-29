import pytest
from cryptography.fernet import InvalidToken

from app.crypto import decrypt, encrypt, generate_key


def test_roundtrip():
    key = generate_key()
    ct = encrypt("hello", key)
    assert ct != "hello"
    assert decrypt(ct, key) == "hello"


def test_decrypt_wrong_key_raises():
    ct = encrypt("hello", generate_key())
    with pytest.raises(InvalidToken):
        decrypt(ct, generate_key())
