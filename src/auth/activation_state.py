import os
import time

from auth.token_verifier import verify_token, get_robot_id
from auth.revocation_check import check_revocation

def get_data_dir():
    src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(os.path.dirname(src_dir), "data")

TOKEN_FILE = os.path.join(get_data_dir(), "activation_state.dat")
LOG_FILE = os.path.join(get_data_dir(), "audit.log")

def log_audit(action, is_authorized, reason=""):
    os.makedirs(get_data_dir(), exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    status = "GRANTED" if is_authorized else "DENIED"
    log_line = f"[{timestamp}] ACTION={action} STATUS={status} REASON={reason}\n"
    try:
        with open(LOG_FILE, "a") as f:
            f.write(log_line)
    except Exception as e:
        print(f"Failed to write audit log: {e}")

def is_authorized():
    """
    Reads token from data/activation_state.dat, verifies it, and checks revocation.
    Returns True if authorized, False otherwise. Fails closed on any error.
    """
    robot_id = get_robot_id()
    
    # Check revocation first
    if check_revocation(robot_id):
        log_audit("authorization_check", False, "device_revoked")
        return False
        
    try:
        with open(TOKEN_FILE, "r") as f:
            token_string = f.read().strip()
    except FileNotFoundError:
        log_audit("authorization_check", False, "token_file_missing")
        return False
    except Exception as e:
        log_audit("authorization_check", False, f"file_read_error_{e}")
        return False
        
    is_valid, reason = verify_token(token_string)
    
    log_audit("authorization_check", is_valid, reason)
    return is_valid

def save_token(token_string):
    """
    Writes a new token to data/activation_state.dat.
    """
    os.makedirs(get_data_dir(), exist_ok=True)
    try:
        with open(TOKEN_FILE, "w") as f:
            f.write(token_string)
        log_audit("save_token", True, "token_saved")
        return True
    except Exception as e:
        log_audit("save_token", False, f"write_error_{e}")
        return False
