import argparse
import base64
import json
import os
import time
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key

def generate_token(device_id, hours):
    # Load private key
    tools_dir = os.path.dirname(os.path.abspath(__file__))
    key_path = os.path.join(tools_dir, "private_key.pem")
    
    try:
        with open(key_path, "rb") as f:
            private_key = load_pem_private_key(f.read(), password=None)
    except FileNotFoundError:
        print(f"Error: Private key not found at {key_path}")
        print("Please run generate_keys.py first to create a key pair.")
        return

    # Build payload
    now = int(time.time())
    expires_at = now + int(hours * 3600)
    
    payload = {
        "device_id": device_id,
        "issued_at": now,
        "expires_at": expires_at
    }
    
    payload_bytes = json.dumps(payload).encode('utf-8')
    
    # Sign payload
    signature = private_key.sign(
        payload_bytes,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH
        ),
        hashes.SHA256()
    )
    
    # Combine payload + signature (e.g. payload_base64.signature_base64)
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode('utf-8').rstrip("=")
    signature_b64 = base64.urlsafe_b64encode(signature).decode('utf-8').rstrip("=")
    
    token = f"{payload_b64}.{signature_b64}"
    
    # Save token
    out_path = os.path.join(tools_dir, "output_token.txt")
    with open(out_path, "w") as f:
        f.write(token)
        
    print(f"Token generated successfully for device: {device_id}")
    print(f"Token valid for {hours} hours (expires {expires_at})")
    print("-" * 40)
    print(token)
    print("-" * 40)
    print(f"Saved to {out_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a signed activation token.")
    parser.add_argument("--device", required=True, help="Device ID this token is for")
    parser.add_argument("--hours", type=float, required=True, help="Validity period in hours")
    
    args = parser.parse_args()
    generate_token(args.device, args.hours)
