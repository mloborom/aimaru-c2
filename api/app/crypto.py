import base64, hmac, hashlib
import os
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes

# ===== Existing MCP encryption functions =====

def hkdf_sha256(ikm: bytes, salt: bytes, info: bytes, length: int = 32) -> bytes:
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    out = b""
    t = b""
    block = 0
    while len(out) < length:
        block += 1
        t = hmac.new(prk, t + info + bytes([block]), hashlib.sha256).digest()
        out += t
    return out[:length]

def derive_keys_from_access_token(access_token: str):
    ikm = access_token.encode("utf-8")
    salt = b"mcp-hkdf-salt-v1"
    aes = hkdf_sha256(ikm, salt, b"mcp-aes-256-cbc", 32)
    mac = hkdf_sha256(ikm, salt, b"mcp-hmac-sha256", 32)
    return aes, mac

def encrypt_cbc(plain: str, aes_key: bytes) -> str:
    iv = get_random_bytes(16)
    cipher = AES.new(aes_key, AES.MODE_CBC, iv)
    data = plain.encode("utf-8")
    pad = 16 - (len(data) % 16)
    data += bytes([pad]) * pad
    ct = cipher.encrypt(data)
    return base64.b64encode(iv + ct).decode("ascii")

def hmac_sig_b64(plain: str, mac_key: bytes) -> tuple[str, str]:
    mac = hmac.new(mac_key, plain.encode("utf-8"), hashlib.sha256).digest()
    return "v1", base64.b64encode(mac).decode("ascii")

# ===== API Key Encryption Functions (for LLM configs) =====

def get_api_encryption_key() -> bytes:
    """
    Get or derive a consistent encryption key for API keys.
    Uses environment variable or falls back to a derived key.
    """
    # Try to get from environment
    key_str = os.environ.get('API_ENCRYPTION_KEY')
    
    if key_str:
        # If provided as base64, decode it
        try:
            return base64.b64decode(key_str)
        except:
            # If not base64, use HKDF to derive a proper key
            return hkdf_sha256(
                key_str.encode('utf-8'),
                b"api-key-encryption-salt",
                b"api-key-aes-256",
                32
            )
    else:
        # Fall back to deriving from SECRET_KEY or a default
        secret = os.environ.get('SECRET_KEY', 'default-dev-key-change-in-production')
        return hkdf_sha256(
            secret.encode('utf-8'),
            b"api-key-encryption-salt",
            b"api-key-aes-256",
            32
        )

def encrypt_api_key(plaintext: str) -> str:
    """
    Encrypt an API key for storage in the database.
    Returns a base64-encoded string containing IV + ciphertext.
    Uses the same AES-CBC method as the MCP encryption.
    """
    if not plaintext:
        return ""
    
    aes_key = get_api_encryption_key()
    
    # Reuse the existing encrypt_cbc function for consistency
    return encrypt_cbc(plaintext, aes_key)

def decrypt_api_key(ciphertext: str) -> str:
    """
    Decrypt an API key from database storage.
    Expects a base64-encoded string containing IV + ciphertext.
    """
    if not ciphertext:
        return ""
    
    try:
        aes_key = get_api_encryption_key()
        
        # Decode from base64
        encrypted_data = base64.b64decode(ciphertext)
        
        # Extract IV (first 16 bytes) and ciphertext
        iv = encrypted_data[:16]
        ct = encrypted_data[16:]
        
        # Decrypt
        cipher = AES.new(aes_key, AES.MODE_CBC, iv)
        decrypted = cipher.decrypt(ct)
        
        # Remove PKCS7 padding
        pad_len = decrypted[-1]
        decrypted = decrypted[:-pad_len]
        
        return decrypted.decode('utf-8')
    except Exception as e:
        # Log the error in production
        print(f"Error decrypting API key: {e}")
        raise ValueError("Failed to decrypt API key")