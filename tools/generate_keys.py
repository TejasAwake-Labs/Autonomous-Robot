import os
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

def generate_keys():
    tools_dir = os.path.dirname(os.path.abspath(__file__))
    config_dir = os.path.join(os.path.dirname(tools_dir), "config")
    
    os.makedirs(tools_dir, exist_ok=True)
    os.makedirs(config_dir, exist_ok=True)
    
    private_key_path = os.path.join(tools_dir, "private_key.pem")
    public_key_path = os.path.join(config_dir, "auth_public_key.pem")

    print("Generating RSA key pair...")
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    with open(private_key_path, "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))
    
    public_key = private_key.public_key()
    with open(public_key_path, "wb") as f:
        f.write(public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ))

    print(f"Private key saved to {private_key_path}")
    print(f"Public key saved to {public_key_path}")

if __name__ == "__main__":
    generate_keys()
