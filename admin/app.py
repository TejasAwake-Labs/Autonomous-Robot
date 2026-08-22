import os
import json
from flask import Flask, request, jsonify, session, send_from_directory, redirect

# ---------- Paths ----------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # project root
CONFIG_DIR = os.path.join(BASE_DIR, 'config')
WWW_DIR = os.path.join(BASE_DIR, 'www')

CREDENTIALS_PATH = os.path.join(CONFIG_DIR, 'credentials.json')
WWW_CONFIG_PATH = os.path.join(CONFIG_DIR, 'www_config.json')

# ---------- App setup ----------
app = Flask(__name__)
app.secret_key = os.urandom(24)  # required for session cookies to work


def load_json(path):
    with open(path) as f:
        return json.load(f)


def load_credentials():
    return load_json(CREDENTIALS_PATH)


def load_www_config():
    return load_json(WWW_CONFIG_PATH)


# ---------- Auth ----------
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    username = data.get('username', '')
    password = data.get('password', '')

    try:
        creds = load_credentials()
    except FileNotFoundError:
        return jsonify(success=False, message='Server misconfigured'), 500
    except json.JSONDecodeError:
        return jsonify(success=False, message='Server misconfigured'), 500

    if username == creds.get('username') and password == creds.get('password'):
        session['logged_in'] = True
        return jsonify(success=True)

    return jsonify(success=False, message='Invalid credentials'), 401


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


# ---------- Gatekeeper ----------
@app.before_request
def require_login():
    public_paths = ('/login', '/api/login')
    public_prefixes = ('/css/', '/js/', '/assets/')

    if request.path in public_paths:
        return
    if any(request.path.startswith(p) for p in public_prefixes):
        return
    if not session.get('logged_in'):
        return redirect('/login')


# ---------- Static asset routes ----------
@app.route('/login')
def login_page():
    return send_from_directory(os.path.join(WWW_DIR, 'html'), 'login.html')


@app.route('/css/<path:filename>')
def css_files(filename):
    return send_from_directory(os.path.join(WWW_DIR, 'css'), filename)


@app.route('/js/<path:filename>')
def js_files(filename):
    return send_from_directory(os.path.join(WWW_DIR, 'js'), filename)


# ---------- Admin panel (protected) ----------
@app.route('/admin')
def admin_panel():
    return send_from_directory(os.path.join(WWW_DIR, 'html'), 'index.html')


@app.route('/api/upload-map', methods=['POST'])
def upload_map():
    if 'file' not in request.files:
        return jsonify(success=False, message='No file provided'), 400

    uploaded = request.files['file']
    if not uploaded.filename.endswith('.map'):
        return jsonify(success=False, message='Invalid file type'), 400

    data_dir = os.path.join(BASE_DIR, 'data')
    os.makedirs(data_dir, exist_ok=True)
    uploaded.save(os.path.join(data_dir, uploaded.filename))

    return jsonify(success=True, message='Map uploaded successfully')


@app.route('/')
def index():
    return redirect('/admin')


# ---------- Entry point ----------
if __name__ == '__main__':
    www_cfg = load_www_config()
    app.run(
        host=www_cfg.get('host', '127.0.0.1'),
        port=www_cfg.get('port', 5050),
        debug=www_cfg.get('debug', False)
    )
