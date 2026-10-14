"""WireGuard key generation (Curve25519 / X25519, RFC 7748) without external dependencies.

Keys are only generated offline on the admin machine, so a straightforward
Montgomery ladder is sufficient here. If the `wg` binary is installed you can
cross-check with `wg pubkey`.
"""

import base64
import secrets

_P = 2**255 - 19
_A24 = 121665
_BASEPOINT = (9).to_bytes(32, "little")


def _decode_scalar(k: bytes) -> int:
    b = bytearray(k)
    b[0] &= 248
    b[31] &= 127
    b[31] |= 64
    return int.from_bytes(b, "little")


def _decode_u(u: bytes) -> int:
    b = bytearray(u)
    b[31] &= 127
    return int.from_bytes(b, "little") % _P


def x25519(scalar: bytes, u: bytes) -> bytes:
    if len(scalar) != 32 or len(u) != 32:
        raise ValueError("x25519 erwartet 32-Byte-Eingaben")
    k = _decode_scalar(scalar)
    x1 = _decode_u(u)
    x2, z2, x3, z3 = 1, 0, x1, 1
    swap = 0
    for t in reversed(range(255)):
        kt = (k >> t) & 1
        swap ^= kt
        if swap:
            x2, x3 = x3, x2
            z2, z3 = z3, z2
        swap = kt
        a = (x2 + z2) % _P
        aa = a * a % _P
        b = (x2 - z2) % _P
        bb = b * b % _P
        e = (aa - bb) % _P
        c = (x3 + z3) % _P
        d = (x3 - z3) % _P
        da = d * a % _P
        cb = c * b % _P
        x3 = (da + cb) ** 2 % _P
        z3 = x1 * (da - cb) ** 2 % _P
        x2 = aa * bb % _P
        z2 = e * (aa + _A24 * e) % _P
    if swap:
        x2, x3 = x3, x2
        z2, z3 = z3, z2
    return (x2 * pow(z2, _P - 2, _P) % _P).to_bytes(32, "little")


def generate_private_key() -> str:
    raw = bytearray(secrets.token_bytes(32))
    # clamp like `wg genkey` does
    raw[0] &= 248
    raw[31] &= 127
    raw[31] |= 64
    return base64.b64encode(bytes(raw)).decode()


def public_key(private_key_b64: str) -> str:
    priv = base64.b64decode(private_key_b64, validate=True)
    return base64.b64encode(x25519(priv, _BASEPOINT)).decode()


def generate_preshared_key() -> str:
    return base64.b64encode(secrets.token_bytes(32)).decode()


def generate_keypair() -> tuple[str, str]:
    priv = generate_private_key()
    return priv, public_key(priv)


def is_valid_key(key_b64: str) -> bool:
    try:
        return len(base64.b64decode(key_b64, validate=True)) == 32
    except (ValueError, TypeError):
        return False
