import os
import time
import threading
import urllib.request
import json
import zipfile
import tarfile
import ssl
from flask import Blueprint, request, jsonify
import app.shared as shared

llamacpp_bp = Blueprint('llamacpp', __name__)

def get_latest():
    try:
        req = urllib.request.Request("https://api.github.com/repos/ggml-org/llama.cpp/releases/latest", headers={'User-Agent': 'Omnix/1.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
            # Try to get the latest version from tag_name
            tag_name = data.get('tag_name', 'b3650')
            # Also check if there are assets available
            assets = data.get('assets', [])
            if assets:
                # Use the first asset as a reference for the correct naming pattern
                first_asset = assets[0]
                asset_name = first_asset.get('name', '')
                # Extract version from asset name if possible
                if 'llama-' in asset_name:
                    # Try to extract version from asset name pattern
                    import re
                    match = re.search(r'llama-([a-zA-Z0-9.-]+)', asset_name)
                    if match:
                        return match.group(1)
            return tag_name.lstrip('b')
    except: return "3650"

@llamacpp_bp.route('/api/llamacpp/releases', methods=['GET'])
def get_releases():
    import platform
    sys, mach = platform.system().lower(), platform.machine().lower()
    rec = "windows-cuda-13.1" if sys == "windows" else "macos-arm" if sys == "darwin" and "arm" in mach else "linux-cuda" if sys == "linux" else "windows-cpu"
    
    # Use the correct URLs based on the actual GitHub release
    tag_name = "b8209"  # Latest version
    
    rels = []
    
    # Windows releases
    if sys == "windows":
        rels = [
            {
                "id": "windows-cpu",
                "name": "Windows (CPU only)",
                "url": f"https://github.com/ggml-org/llama.cpp/releases/download/{tag_name}/llama-{tag_name}-bin-win-cpu-x64.zip",
                "extension": ".zip"
            },
            {
                "id": "windows-cuda-13.1",
                "name": "Windows (CUDA 13.1)",
                "url": f"https://github.com/ggml-org/llama.cpp/releases/download/{tag_name}/llama-{tag_name}-bin-win-cuda-13.1-x64.zip",
                "extension": ".zip"
            },
            {
                "id": "windows-cuda-12.4",
                "name": "Windows (CUDA 12.4)",
                "url": f"https://github.com/ggml-org/llama.cpp/releases/download/{tag_name}/llama-{tag_name}-bin-win-cuda-12.4-x64.zip",
                "extension": ".zip"
            }
        ]
    else:
        # Non-Windows releases
        rels = [
            {"id": "macos-arm", "name": "macOS (Apple Silicon)", "url": f"https://github.com/ggml-org/llama.cpp/releases/download/{tag_name}/llama-{tag_name}-bin-macos-arm64.tar.gz", "extension": ".tar.gz"},
            {"id": "linux-cuda", "name": "Linux (CUDA)", "url": f"https://github.com/ggml-org/llama.cpp/releases/download/{tag_name}/llama-{tag_name}-bin-ubuntu-x64-cuda-cu12.2.tar.gz", "extension": ".tar.gz"}
        ]
    
    # Mark recommended release
    for r in rels:
        r['recommended'] = (r['id'] == rec)
    
    return jsonify({"success": True, "latest_version": tag_name.lstrip('b'), "releases": rels})

@llamacpp_bp.route('/api/llamacpp/server/status', methods=['GET'])
def server_status():
    server_dir = os.path.join(shared.MODELS_DIR, 'server')
    binary = next((n for n in ["llama-server.exe", "llama-server", "llama.exe", "llama"] if os.path.exists(os.path.join(server_dir, n))), None)
    return jsonify({"success": True, "server_dir": server_dir, "binary_found": bool(binary), "binary_name": binary})

@llamacpp_bp.route('/api/llamacpp/server/start', methods=['POST'])
def start_server():
    model = request.get_json().get('model', '')
    if not model: return jsonify({"success": False, "error": "Model required"}), 400
    
    s_dir = os.path.join(shared.MODELS_DIR, 'server')
    binary = next((n for n in ["llama-server.exe", "llama-server", "llama.exe", "llama"] if os.path.exists(os.path.join(s_dir, n))), None)
    if not binary: return jsonify({"success": False, "error": "Binary not found"}), 400
    
    m_path = model if os.path.isabs(model) else next((p for p in [os.path.join(shared.MODELS_DIR, 'llm', model), os.path.join(s_dir, model)] if os.path.exists(p)), None)
    if not m_path: return jsonify({"success": False, "error": "Model file not found"}), 400
    
    port = 8080
    try: port = int(shared.load_settings().get('llamacpp', {}).get('base_url', '').split(':')[-1])
    except: pass

    try:
        import subprocess as sp
        sp.run(f'netstat -ano | findstr :{port} | findstr LISTENING | awk \'{{print $5}}\' | xargs taskkill /F /PID 2>nul', shell=True)
        time.sleep(1)
        proc = sp.Popen([os.path.join(s_dir, binary), "-m", m_path, "-c", "4096", "-ngl", "999", "--host", "0.0.0.0", "--port", str(port)], cwd=s_dir, stdout=sp.PIPE, stderr=sp.STDOUT)
        return jsonify({"success": True, "message": f"Started on port {port}", "pid": proc.pid})
    except Exception as e: return jsonify({"success": False, "error": str(e)}), 500

@llamacpp_bp.route('/api/llamacpp/server/stop', methods=['POST'])
def stop_server():
    try:
        import subprocess as sp
        port = 8080
        try: port = int(shared.load_settings().get('llamacpp', {}).get('base_url', '').split(':')[-1])
        except: pass
        sp.run(f'netstat -ano | findstr :{port} | findstr LISTENING | awk \'{{print $5}}\' | xargs taskkill /F /PID 2>nul', shell=True)
        return jsonify({"success": True, "message": f"Stopped port {port}"})
    except Exception as e: return jsonify({"success": False, "error": str(e)}), 500

@llamacpp_bp.route('/api/llamacpp/server/download', methods=['POST'])
def download_server():
    """Download and install llama-cpp-python wheel."""
    data = request.get_json()
    release_id = data.get('release_id', '')
    
    if not release_id:
        return jsonify({"success": False, "error": "Release ID required"}), 400
    
    # Generate download ID
    import uuid
    download_id = str(uuid.uuid4())[:8]
    
    # Initialize download tracking
    shared.llamacpp_server_downloads[download_id] = {
        "id": download_id,
        "release_id": release_id,
        "status": "starting",
        "progress": 0,
        "total": 0,
        "downloaded": 0,
        "filename": "llama-cpp-python wheel installation"
    }
    
    # Start installation in background thread
    def install_llamacpp_wheel():
        try:
            import subprocess
            import sys
            
            # Determine the appropriate index URL based on release_id
            if release_id == 'windows-cuda-13.1':
                index_url = "https://parisneo.github.io/llama-cpp-python-wheels/whl/cu121/"
                wheel_name = "llama-cpp-python (CUDA 13.1)"
            elif release_id == 'windows-cuda-12.4':
                index_url = "https://parisneo.github.io/llama-cpp-python-wheels/whl/cu121/"  # Use cu121 for both CUDA versions
                wheel_name = "llama-cpp-python (CUDA 12.4)"
            elif release_id == 'windows-cpu':
                index_url = "https://parisneo.github.io/llama-cpp-python-wheels/whl/cpu/"
                wheel_name = "llama-cpp-python (CPU only)"
            elif release_id == 'macos-arm':
                index_url = "https://parisneo.github.io/llama-cpp-python-wheels/whl/cpu/"
                wheel_name = "llama-cpp-python (macOS ARM)"
            elif release_id == 'linux-cuda':
                index_url = "https://parisneo.github.io/llama-cpp-python-wheels/whl/cu121/"
                wheel_name = "llama-cpp-python (Linux CUDA)"
            else:
                # Fallback to CPU version
                index_url = "https://parisneo.github.io/llama-cpp-python-wheels/whl/cpu/"
                wheel_name = "llama-cpp-python (CPU fallback)"
            
            shared.llamacpp_server_downloads[download_id]['status'] = "installing"
            shared.llamacpp_server_downloads[download_id]['filename'] = wheel_name
            
            # Install using pip with the custom index URL
            cmd = [
                sys.executable, "-m", "pip", "install", "llama-cpp-python",
                "--extra-index-url", index_url
            ]
            
            print(f"[LLAMA.CPP INSTALL] Installing with command: {' '.join(cmd)}")
            
            # Start the installation process
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            # Read output line by line to track progress
            output_lines = []
            while True:
                line = proc.stdout.readline()
                if not line and proc.poll() is not None:
                    break
                if line:
                    output_lines.append(line.strip())
                    # Update progress based on output
                    if "Requirement already satisfied" in line or "Successfully installed" in line:
                        shared.llamacpp_server_downloads[download_id]['progress'] = 100
                    elif "Collecting" in line or "Downloading" in line:
                        shared.llamacpp_server_downloads[download_id]['progress'] = 50
                    elif "Building wheel" in line:
                        shared.llamacpp_server_downloads[download_id]['progress'] = 75
            
            # Wait for completion
            proc.wait()
            
            if proc.returncode == 0:
                # Verify installation
                try:
                    import llama_cpp
                    shared.llamacpp_server_downloads[download_id]['status'] = "completed"
                    shared.llamacpp_server_downloads[download_id]['progress'] = 100
                    print(f"[LLAMA.CPP INSTALL] Successfully installed {wheel_name}")
                except ImportError:
                    shared.llamacpp_server_downloads[download_id]['status'] = "error"
                    shared.llamacpp_server_downloads[download_id]['error'] = "Installation completed but verification failed"
            else:
                shared.llamacpp_server_downloads[download_id]['status'] = "error"
                shared.llamacpp_server_downloads[download_id]['error'] = f"Installation failed with exit code {proc.returncode}"
                shared.llamacpp_server_downloads[download_id]['downloaded'] = '\n'.join(output_lines)
                
        except Exception as e:
            shared.llamacpp_server_downloads[download_id]['status'] = "error"
            shared.llamacpp_server_downloads[download_id]['error'] = str(e)
    
    # Start installation thread
    threading.Thread(target=install_llamacpp_wheel, daemon=True).start()
    
    return jsonify({
        "success": True, 
        "download_id": download_id,
        "message": f"Starting installation of {release_id.replace('-', ' ').title()}"
    })

@llamacpp_bp.route('/api/llamacpp/server/download/status', methods=['GET'])
def download_status():
    """Get download/installation status for llama.cpp server."""
    download_id = request.args.get('id')
    
    if not download_id:
        return jsonify({"success": False, "error": "Download ID required"}), 400
    
    download = shared.llamacpp_server_downloads.get(download_id)
    
    if not download:
        return jsonify({"success": False, "error": "Download not found"}), 404
    
    # Calculate download speed and ETA for downloads, or just return status for installations
    status = download.copy()
    
    if status['status'] == 'downloading' and status['downloaded'] > 0:
        # This is a simplified calculation - in a real implementation you'd track more timing data
        elapsed = time.time() - (download.get('start_time', time.time()))
        if elapsed > 0:
            speed = status['downloaded'] / elapsed
            status['speed'] = speed
            if status['total'] > 0 and speed > 0:
                remaining = (status['total'] - status['downloaded']) / speed
                status['eta'] = remaining
    elif status['status'] == 'installing':
        # For wheel installation, we don't have download speed/eta, just progress
        status['speed'] = 0
        status['eta'] = 0
    
    return jsonify({"success": True, "download": status})

@llamacpp_bp.route('/api/llamacpp/server/download/stop', methods=['POST'])
def stop_download():
    """Stop a running download or installation."""
    data = request.get_json()
    download_id = data.get('download_id')
    
    if not download_id:
        return jsonify({"success": False, "error": "Download ID required"}), 400
    
    download = shared.llamacpp_server_downloads.get(download_id)
    
    if not download:
        return jsonify({"success": False, "error": "Download not found"}), 404
    
    if download['status'] in ['downloading', 'extracting', 'installing']:
        download['status'] = 'cancelled'
        return jsonify({"success": True, "message": "Download/Installation cancelled"})
    else:
        return jsonify({"success": False, "error": "Download/Installation not in progress"}), 400
