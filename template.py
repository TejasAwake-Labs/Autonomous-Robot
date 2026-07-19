import os
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)

list_of_files = [
    "requirements.txt",
    "src/main.py",
    "src/face.py",
    "src/renderer.py",
    "src/text_gen.py",
    "src/auth/token_verifier.py",
    "src/auth/activation_state.py",
    "src/auth/revocation_check.py",
    "src/comms/listener.py",
    "config/emotion.json",
    "config/text_gen.json",
    "config/auth_public_key.pem",
    "data/activation_state.dat",
    "tools/generate_token.py",
    "revocation_server/revoked_devices.json",
    ".gitignore",
]

for filepath in list_of_files:
    filepath = Path(filepath)
    filedir, filename = os.path.split(filepath)

    if filedir != "":
        os.makedirs(filedir, exist_ok=True)
        logging.info(f"Creating directory:{filedir} for the file {filename}")

    if (not os.path.exists(filepath)) or (os.path.getsize(filepath) == 0):
        with open(filepath,'w') as f:
            logging.info(f"Creating empty file: {filepath}")

    else:
        logging.info(f"{filename} already exists")
