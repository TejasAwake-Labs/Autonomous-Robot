import os
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)

list_of_files=[
    "requirements.txt",
    "src/main.py",
    "src/face.py",
    "src/renderer.py",
    "src/main.py",
    "assets/preview_happy",
    "assets/preview_sad",
    "assets/preview_angry",
    "assets/preview_happy",
    "assets/preview_surprised",
    "config/emotion.json"
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
        logging.info(f"{filename} is already exists")
