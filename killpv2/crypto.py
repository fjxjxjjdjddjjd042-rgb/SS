"""AES-256-GCM vault encryption with scrypt key derivation.
Blob: b"KPV2" | ver(1) | salt(16) | nonce(12) | ciphertext+tag
"""
import json
import zlib
import hashlib
import hmac
import secrets

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _HAVE_CRYPTO = True
except Exception:  # pragma: no cover
    _HAVE_CRYPTO = False

MAGIC = b"KPV2"
VERSION = 1
_key_cache = {}
_MAXMEM = 128 * 1024 * 1024


def _derive(material: str, salt: bytes) -> bytes:
    ck = (material, salt)
    if ck not in _key_cache:
        _key_cache[ck] = hashlib.scrypt(material.encode("utf-8"), salt=salt, n=2 ** 15, r=8, p=1, dklen=32, maxmem=_MAXMEM)
    return _key_cache[ck]


def encrypt_bytes(data: bytes, material: str) -> bytes:
    if not material:
        raise ValueError("encryption key material is empty")
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    key = _derive(material, salt)
    comp = zlib.compress(data, 6)
    ct = AESGCM(key).encrypt(nonce, comp, MAGIC) if _HAVE_CRYPTO else _fallback_encrypt(key, nonce, comp)
    return MAGIC + bytes([VERSION]) + salt + nonce + ct


def decrypt_bytes(blob: bytes, material: str) -> bytes:
    if not blob.startswith(MAGIC):
        raise ValueError("not a kill_pv2 vault blob")
    salt, nonce, ct = blob[5:21], blob[21:33], blob[33:]
    key = _derive(material, salt)
    comp = AESGCM(key).decrypt(nonce, ct, MAGIC) if _HAVE_CRYPTO else _fallback_decrypt(key, nonce, ct)
    return zlib.decompress(comp)


def encrypt_json(obj, material: str) -> bytes:
    return encrypt_bytes(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), material)


def decrypt_json(blob: bytes, material: str):
    return json.loads(decrypt_bytes(blob, material).decode("utf-8"))


def hash_password(password: str, salt: bytes = None) -> str:
    salt = salt or secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1, dklen=32, maxmem=_MAXMEM)
    return salt.hex() + "$" + h.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, h_hex = stored.split("$", 1)
        calc = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex), n=2 ** 14, r=8, p=1, dklen=32, maxmem=_MAXMEM)
        return hmac.compare_digest(calc.hex(), h_hex)
    except Exception:
        return False


def _keystream(key, nonce, length):
    out, counter = bytearray(), 0
    while len(out) < length:
        out += hashlib.sha256(key + nonce + counter.to_bytes(8, "big")).digest()
        counter += 1
    return bytes(out[:length])


def _fallback_encrypt(key, nonce, data):
    ct = bytes(a ^ b for a, b in zip(data, _keystream(key, nonce, len(data))))
    return ct + hmac.new(key, nonce + ct, hashlib.sha256).digest()


def _fallback_decrypt(key, nonce, blob):
    ct, tag = blob[:-32], blob[-32:]
    if not hmac.compare_digest(hmac.new(key, nonce + ct, hashlib.sha256).digest(), tag):
        raise ValueError("vault authentication failed")
    return bytes(a ^ b for a, b in zip(ct, _keystream(key, nonce, len(ct))))
