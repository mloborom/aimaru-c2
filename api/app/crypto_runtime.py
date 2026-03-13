# api/app/crypto_runtime.py
from __future__ import annotations

from typing import Dict, Tuple, Optional
from dataclasses import dataclass
from time import time
import os, base64, hmac, hashlib

from Crypto.Cipher import AES  # pycryptodome

# ------------------------------
# In-RAM keyring
# ------------------------------
@dataclass
class ClientKeys:
    kid: str
    enc_key: bytes  # 32 bytes (AES-256)
    mac_key: bytes  # 32 bytes (HMAC-SHA256)
    updated_at: float

class KeyRing:
    def __init__(self):
        self._by_client: Dict[str, ClientKeys] = {}

    def put(self, client_id: str, kid: str, enc_key: bytes, mac_key: bytes):
        self._by_client[client_id] = ClientKeys(kid, enc_key, mac_key, time())
        print(f"[RING] Stored keys for client_id={client_id}, kid={kid}")

    def get_enc(self, client_id: str) -> Optional[Tuple[str, bytes]]:
        """(kid, enc_key) — kept for legacy callers."""
        k = self._by_client.get(client_id)
        if not k: 
            print(f"[RING] No enc key found for client_id={client_id}")
            return None
        return (k.kid, k.enc_key)

    def get_all(self, client_id: str) -> Optional[Tuple[str, bytes, bytes]]:
        """(kid, enc_key, mac_key) for CBC+HMAC flows."""
        k = self._by_client.get(client_id)
        if not k:
            print(f"[RING] No keys found for client_id={client_id}. Available clients: {list(self._by_client.keys())}")
            return None
        print(f"[RING] Retrieved keys for client_id={client_id}, kid={k.kid}")
        return (k.kid, k.enc_key, k.mac_key)

    def info(self) -> Dict[str, dict]:
        """Debug info about stored keys"""
        out = {}
        for cid, k in self._by_client.items():
            out[cid] = {
                "kid": k.kid,
                "enc_fp": base64.b64encode(hashlib.sha256(k.enc_key).digest()[:8]).decode(),
                "mac_fp": base64.b64encode(hashlib.sha256(k.mac_key).digest()[:8]).decode(),
                "age_s": int(time() - k.updated_at),
            }
        return out
    
    def remove(self, client_id: str) -> bool:
        """Remove keys for a client"""
        if client_id in self._by_client:
            del self._by_client[client_id]
            print(f"[RING] Removed keys for client_id={client_id}")
            return True
        return False
    
    def clear(self):
        """Clear all keys"""
        count = len(self._by_client)
        self._by_client.clear()
        print(f"[RING] Cleared {count} client key(s)")

# Global instance
RING = KeyRing()

# ------------------------------
# AES-256-CBC with PKCS#7
# (matches your PowerShell client)
# ------------------------------
_BLOCK = 16

def _pkcs7_pad(data: bytes, block: int = _BLOCK) -> bytes:
    padlen = block - (len(data) % block)
    return data + bytes([padlen]) * padlen

def _pkcs7_unpad(b: bytes) -> bytes:
    if not b:
        raise ValueError("bad padding: empty")
    pad = b[-1]
    if pad < 1 or pad > 16:
        raise ValueError("bad padding length")
    if b[-pad:] != bytes([pad]) * pad:
        raise ValueError("bad padding bytes")
    return b[:-pad]

def encrypt_cbc_b64(key: bytes, plaintext: bytes) -> str:
    """
    Returns base64( IV(16) || ciphertext )
    """
    if len(key) != 32:
        raise ValueError("AES-256 key must be 32 bytes")
    iv = os.urandom(16)
    cipher = AES.new(key, AES.MODE_CBC, iv=iv)
    ct = cipher.encrypt(_pkcs7_pad(plaintext))
    return base64.b64encode(iv + ct).decode("ascii")

def decrypt_cbc_b64(cipher_b64: str, enc_key: bytes) -> bytes:
    raw = base64.b64decode(cipher_b64)
    if len(raw) < 16 + 1:
        raise ValueError("ciphertext too short")
    iv = raw[:16]
    ct = raw[16:]
    c = AES.new(enc_key, AES.MODE_CBC, iv=iv)
    pt = c.decrypt(ct)
    return _pkcs7_unpad(pt)

# ------------------------------
# HMAC-SHA256 (base64)
# ------------------------------
def hmac_sha256_b64(key: bytes, message: bytes) -> str:
    mac = hmac.new(key, message, hashlib.sha256).digest()
    return base64.b64encode(mac).decode("ascii")

# ------------------------------
# Existing GCM decrypt (kept for compatibility)
# ------------------------------
def decrypt_gcm_b64(cipher_b64: str, enc_key: bytes, aad: bytes = b"") -> bytes:
    """
    Expects base64( iv(12) || ciphertext || tag(16) )
    Not used by the current PS client (CBC+HMAC), but retained for old data.
    """
    raw = base64.b64decode(cipher_b64)
    if len(raw) < 12 + 16:
        raise ValueError("cipher too short")
    iv   = raw[:12]
    tag  = raw[-16:]
    body = raw[12:-16]
    c = AES.new(enc_key, AES.MODE_GCM, nonce=iv)
    if aad:
        c.update(aad)
    pt = c.decrypt_and_verify(body, tag)
    return pt

# ---- CBC helper (what the PS client uses) ----
def decrypt_cbc_raw(raw: bytes, enc_key: bytes) -> bytes:
    """raw = 16-byte IV + ciphertext; AES-256-CBC; PKCS7 unpad."""
    if len(raw) < 17:
        raise ValueError("ciphertext too short")
    iv = raw[:16]
    body = raw[16:]
    c = AES.new(enc_key, AES.MODE_CBC, iv=iv)
    pt = c.decrypt(body)
    pad = pt[-1]
    if pad < 1 or pad > 16:
        raise ValueError("bad PKCS7 padding")
    return pt[:-pad]

# ------------------------------
# Debug helpers
# ------------------------------
def debug_ring():
    """Print current RING contents for debugging"""
    info = RING.info()
    if not info:
        print("[RING] No clients stored")
    else:
        print(f"[RING] Stored clients: {len(info)}")
        for client_id, data in info.items():
            print(f"  {client_id}: kid={data['kid']}, enc_fp={data['enc_fp']}, mac_fp={data['mac_fp']}, age={data['age_s']}s")

def test_encryption_roundtrip(client_id: str, test_message: str = "Hello World") -> bool:
    """Test encryption/decryption for a client"""
    try:
        keys = RING.get_all(client_id)
        if not keys:
            print(f"[TEST] No keys for client {client_id}")
            return False
        
        kid, enc_key, mac_key = keys
        
        # Test encryption
        plaintext_bytes = test_message.encode('utf-8')
        encrypted_b64 = encrypt_cbc_b64(enc_key, plaintext_bytes)
        
        # Test HMAC
        hmac_b64 = hmac_sha256_b64(mac_key, plaintext_bytes)
        
        # Test decryption
        decrypted_bytes = decrypt_cbc_b64(encrypted_b64, enc_key)
        decrypted_text = decrypted_bytes.decode('utf-8')
        
        success = decrypted_text == test_message
        print(f"[TEST] Encryption test for {client_id}: {'PASS' if success else 'FAIL'}")
        if not success:
            print(f"[TEST] Expected: {test_message}, Got: {decrypted_text}")
        
        return success
        
    except Exception as e:
        print(f"[TEST] Encryption test failed for {client_id}: {e}")
        return False