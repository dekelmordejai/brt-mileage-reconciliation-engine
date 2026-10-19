import hashlib
import hmac
import secrets


def password_hash(password):
    if len(password) < 12:
        raise ValueError("Contraseña: mínimo 12 caracteres")
    salt = secrets.token_hex(16)
    return (
        salt + ":" + hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    )


def verify(password, encoded):
    salt, expected = encoded.split(":")
    actual = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return hmac.compare_digest(actual, expected)
