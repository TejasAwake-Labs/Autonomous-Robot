import base64
import json
import os
import time
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.exceptions import InvalidSignature

def get_public_key_path():
    src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(os.path.dirname(src_dir), "config", "auth_public_key.pem")

def get_robot_id():
    # In a real system, this might come from a hardware secure enclave or an immutable config file.
    return os.environ.get("ROBOT_ID", "robot_001")

def verify_token(token_string):
    """
    Checks if a token is genuine, unexpired, and for the expected device.
    Returns (bool, reason)
    """
    if not token_string or "." not in token_string:
        return False, "malformed"
        
    parts = token_string.split(".")
    if len(parts) != 2:
        return False, "malformed"
        
    payload_b64, signature_b64 = parts
    
    # Add padding back if necessary
    def add_padding(s):
        return s + "=" * (-len(s) % 4)
        
    try:
        payload_bytes = base64.urlsafe_b64decode(add_padding(payload_b64))
        signature = base64.urlsafe_b64decode(add_padding(signature_b64))
        payload = json.loads(payload_bytes.decode('utf-8'))
    except Exception:
        return False, "malformed"

    # Load public key
    key_path = get_public_key_path()
    try:
        with open(key_path, "rb") as f:
            public_key = load_pem_public_key(f.read())
    except FileNotFoundError:
        return False, "missing_public_key"

    # Verify signature
    try:
        public_key.verify(
            signature,
            payload_bytes,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
    except InvalidSignature:
        return False, "invalid_signature"

    # Verify device id
    expected_device_id = get_robot_id()
    if payload.get("device_id") != expected_device_id:
        return False, "wrong_device"
        
    # Verify expiration
    now = int(time.time())
    expires_at = payload.get("expires_at", 0)
    if now > expires_at:
        return False, "expired"
        
    return True, "valid"
