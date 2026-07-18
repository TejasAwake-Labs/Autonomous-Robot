import json
import os
import time
import requests

REVOCATION_URL = "http://example.com/revoked_devices.json" # Placeholder URL
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "revocation_cache.json")

def check_revocation(device_id):
    """
    Returns True if the device has been marked stolen (revoked), False otherwise.
    Uses local cache if network is unreachable or to avoid flapping.
    """
    now = time.time()
    
    # Try fetching online first
    try:
        response = requests.get(REVOCATION_URL, timeout=3.0)
        if response.status_code == 200:
            revoked_list = response.json().get("revoked_devices", [])
            is_revoked = device_id in revoked_list
            
            # Cache the result
            with open(CACHE_FILE, "w") as f:
                json.dump({
                    "timestamp": now,
                    "is_revoked": is_revoked
                }, f)
                
            return is_revoked
    except (requests.RequestException, ValueError):
        # Network error or bad JSON, fallback to cache
        pass
        
    # Read from cache if network fails
    try:
        with open(CACHE_FILE, "r") as f:
            cache = json.load(f)
            return cache.get("is_revoked", False)
    except (FileNotFoundError, json.JSONDecodeError):
        # No cache, network failed -> assume not revoked (fail open for revocation, rely on token expiry)
        return False
