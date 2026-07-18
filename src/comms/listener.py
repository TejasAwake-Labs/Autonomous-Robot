import threading
import logging
from flask import Flask, request, jsonify

from auth.token_verifier import verify_token
from auth.activation_state import save_token, log_audit

app = Flask(__name__)
# Suppress flask default logging to avoid clutter
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

@app.route('/upload_token', methods=['POST'])
def upload_token():
    data = request.get_json()
    if not data or 'token' not in data:
        return jsonify({"error": "Missing 'token' in JSON body"}), 400
        
    token_string = data['token']
    
    # Validate token
    is_valid, reason = verify_token(token_string)
    if is_valid:
        success = save_token(token_string)
        if success:
            return jsonify({"status": "success", "message": "Token accepted and saved."}), 200
        else:
            return jsonify({"error": "Token valid but failed to save."}), 500
    else:
        log_audit("token_upload", False, reason)
        return jsonify({"error": f"Token rejected: {reason}"}), 403

def start_listener(port=5000):
    """
    Starts the Flask listener in a background thread.
    """
    def run_server():
        # run on 0.0.0.0 to allow external network access
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    return server_thread
