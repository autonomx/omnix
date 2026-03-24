"""
Llama.cpp Installation Manager

Handles automatic installation of precompiled llama.cpp wheels and binaries.
Provides both Python wheel installation and binary download capabilities.
"""

import os
import sys
import subprocess
import platform
import json
import urllib.request
import urllib.error
import zipfile
import tarfile
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import threading
import time

from app.shared import BASE_DIR


def detect_os():
    """Detect the operating system."""
    pf = platform.system()
    if pf == "Windows":
        return "windows"
    elif pf == "Linux":
        return "linux"
    elif pf == "Darwin":
        return "mac"
    else:
        return "unknown"


def detect_gpu():
    """Detect GPU type for appropriate wheel selection."""
    gpu_type = "cpu"

    os_name = detect_os()

    if os_name == "windows" or os_name == "linux":
        try:
            result = subprocess.run(["nvidia-smi"], capture_output=True, text=True)
            if result.returncode == 0:
                gpu_type = "nvidia"
        except Exception:
            pass

        if gpu_type == "cpu":
            try:
                result = subprocess.run(["rocminfo"], capture_output=True, text=True)
                if result.returncode == 0:
                    gpu_type = "amd"
            except Exception:
                pass

    elif os_name == "mac":
        gpu_type = "metal"

    return gpu_type


WHEEL_URLS = {
    "windows": {
        "nvidia": "https://github.com/boneylizard/llama-cpp-python-cu128-gemma3/releases/download/0.3.16/llama_cpp_python-0.3.16-cp312-cp312-win_amd64.whl",
        "amd": None,
        "cpu": "https://github.com/abetlen/llama-cpp-python/releases/download/0.3.16/llama_cpp_python-0.3.16-cp312-cp312-win_amd64.whl"
    },
    "linux": {
        "nvidia": "https://github.com/boneylizard/llama-cpp-python-cu128-gemma3/releases/download/0.3.16/llama_cpp_python-0.3.16-cp312-cp312-manylinux2014_x86_64.whl",
        "amd": None,
        "cpu": "https://github.com/abetlen/llama-cpp-python/releases/download/0.3.16/llama_cpp_python-0.3.16-cp312-cp312-manylinux2014_x86_64.whl"
    },
    "mac": {
        "metal": "https://github.com/boneylizard/llama-cpp-python/releases/download/0.3.16/llama_cpp_python-0.3.16-cp312-cp312-macosx_11_0_arm64.whl",
        "cpu": "https://github.com/abetlen/llama-cpp-python/releases/download/0.3.16/llama_cpp_python-0.3.16-cp312-cp312-macosx_11_0_arm64.whl"
    }
}


class LlamaCppInstaller:
    """Manages installation of llama.cpp Python wheel and server binaries."""
    
    def __init__(self):
        self.base_dir = Path(BASE_DIR)
        self.models_dir = self.base_dir / "models"
        self.server_dir = self.models_dir / "server"
        self.llm_dir = self.models_dir / "llm"
        self.installation_status = {}
        self.installation_lock = threading.Lock()
        
        # Ensure directories exist
        self.server_dir.mkdir(parents=True, exist_ok=True)
        self.llm_dir.mkdir(parents=True, exist_ok=True)
    
    def get_system_info(self) -> Dict[str, str]:
        """Get system information for determining appropriate downloads."""
        sys_name = platform.system().lower()
        machine = platform.machine().lower()
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
        
        # Determine OS
        if sys_name == "windows":
            os_type = "windows"
        elif sys_name == "darwin":
            os_type = "macos"
        elif sys_name == "linux":
            os_type = "linux"
        else:
            os_type = "unknown"
        
        # Determine architecture
        if "arm" in machine or "aarch64" in machine:
            arch = "arm64" if os_type == "macos" else "arm64"
        elif "64" in machine or machine in ["x86_64", "amd64"]:
            arch = "x64"
        else:
            arch = "x86"
        
        # Determine CUDA support
        cuda_available = self._check_cuda_availability()
        
        return {
            "os": os_type,
            "arch": arch,
            "python_version": python_version,
            "cuda_available": cuda_available,
            "full_machine": machine
        }
    
    def _check_cuda_availability(self) -> bool:
        """Check if CUDA is available on the system."""
        try:
            # Try to run nvidia-smi to check for CUDA
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0 and len(result.stdout.strip()) > 0
        except:
            return False
    
    def get_python_wheel_url(self) -> Tuple[str, str]:
        """Get the appropriate Python wheel URL based on system configuration."""
        sys_info = self.get_system_info()
        python_version = sys_info["python_version"]
        
        # Check if CUDA is available for GPU acceleration
        if sys_info["cuda_available"]:
            # Use CUDA wheel
            wheel_url = f"https://parisneo.github.io/llama-cpp-python-wheels/whl/cu121/llama_cpp_python-0.3.16-cp{python_version.replace('.', '')}-cp{python_version.replace('.', '')}-win_amd64.whl"
            wheel_name = f"llama_cpp_python-0.3.16-cp{python_version.replace('.', '')}-cp{python_version.replace('.', '')}-win_amd64.whl"
        else:
            # Use CPU wheel
            wheel_url = f"https://parisneo.github.io/llama-cpp-python-wheels/whl/cpu/llama_cpp_python-0.3.16-cp{python_version.replace('.', '')}-cp{python_version.replace('.', '')}-win_amd64.whl"
            wheel_name = f"llama_cpp_python-0.3.16-cp{python_version.replace('.', '')}-cp{python_version.replace('.', '')}-win_amd64.whl"
        
        return wheel_url, wheel_name
    
    def is_python_wheel_installed(self) -> bool:
        """Check if llama-cpp-python is installed."""
        try:
            import llama_cpp
            return True
        except ImportError:
            return False
    
    def install_python_wheel(self) -> Dict[str, Any]:
        """Install the llama-cpp-python wheel using pip."""
        with self.installation_lock:
            if self.is_python_wheel_installed():
                return {"success": True, "message": "llama-cpp-python is already installed"}
            
            wheel_url = self.get_wheel_url()
            
            if not wheel_url:
                return {"success": False, "error": "No compatible wheel found for your system"}
            
            wheel_name = wheel_url.split("/")[-1]
            
            try:
                print(f"Downloading {wheel_url}")
                temp_wheel = self.llm_dir / wheel_name
                temp_wheel.parent.mkdir(parents=True, exist_ok=True)
                
                urllib.request.urlretrieve(wheel_url, temp_wheel)
                
                cmd = [sys.executable, "-m", "pip", "install", str(temp_wheel)]
                print(f"Installing llama-cpp-python: {' '.join(cmd)}")
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                
                temp_wheel.unlink(missing_ok=True)
                
                if result.returncode == 0:
                    if self.is_python_wheel_installed():
                        return {"success": True, "message": "llama-cpp-python installed successfully"}
                    else:
                        return {"success": False, "error": "Installation completed but verification failed"}
                else:
                    return {"success": False, "error": f"Installation failed: {result.stderr}"}
                    
            except subprocess.TimeoutExpired:
                return {"success": False, "error": "Installation timed out"}
            except Exception as e:
                return {"success": False, "error": f"Installation error: {str(e)}"}
    
    def get_server_binary_url(self) -> Tuple[str, str, str]:
        """Get the appropriate server binary URL based on system configuration."""
        sys_info = self.get_system_info()
        os_type = sys_info["os"]
        arch = sys_info["arch"]
        cuda_available = sys_info["cuda_available"]
        
        # Get latest version
        latest_version = self.get_latest_version()
        
        if os_type == "windows":
            if cuda_available:
                url = f"https://github.com/ggml-org/llama.cpp/releases/download/b{latest_version}/llama-b{latest_version}-bin-win-cuda-cu12.2-x64.zip"
                extension = ".zip"
                binary_name = "llama-server.exe"
            else:
                url = f"https://github.com/ggml-org/llama.cpp/releases/download/b{latest_version}/llama-b{latest_version}-bin-win-x64.zip"
                extension = ".zip"
                binary_name = "llama-server.exe"
        elif os_type == "macos":
            if arch == "arm64":
                url = f"https://github.com/ggml-org/llama.cpp/releases/download/b{latest_version}/llama-b{latest_version}-bin-macos-arm64.tar.gz"
                extension = ".tar.gz"
                binary_name = "llama-server"
            else:
                url = f"https://github.com/ggml-org/llama.cpp/releases/download/b{latest_version}/llama-b{latest_version}-bin-macos-x64.tar.gz"
                extension = ".tar.gz"
                binary_name = "llama-server"
        elif os_type == "linux":
            if cuda_available:
                url = f"https://github.com/ggml-org/llama.cpp/releases/download/b{latest_version}/llama-b{latest_version}-bin-ubuntu-x64-cuda-cu12.2.tar.gz"
                extension = ".tar.gz"
                binary_name = "llama-server"
            else:
                url = f"https://github.com/ggml-org/llama.cpp/releases/download/b{latest_version}/llama-b{latest_version}-bin-ubuntu-x64.tar.gz"
                extension = ".tar.gz"
                binary_name = "llama-server"
        else:
            raise ValueError(f"Unsupported operating system: {os_type}")
        
        return url, extension, binary_name
    
    def get_latest_version(self) -> str:
        """Get the latest llama.cpp version from GitHub API."""
        try:
            req = urllib.request.Request(
                "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest",
                headers={'User-Agent': 'Omnix/1.0'}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read())
                return data.get('tag_name', 'b3650').lstrip('b')
        except Exception:
            return "b3650"  # Fallback version
    
    def is_server_binary_available(self) -> bool:
        """Check if the server binary is available."""
        binary_names = ["llama-server.exe", "llama-server", "llama.exe", "llama"]
        for binary_name in binary_names:
            if (self.server_dir / binary_name).exists():
                return True
        return False
    
    def download_and_extract_server(self, progress_callback=None) -> Dict[str, Any]:
        """Download and extract the llama.cpp server binary."""
        import io
        import sys
        
        with self.installation_lock:
            if self.is_server_binary_available():
                return {"success": True, "message": "Server binary already available"}
            
            url, extension, binary_name = self.get_server_binary_url()
            temp_file = self.server_dir / f"llama-cpp-download{extension}"
            
            try:
                print(f"Downloading llama.cpp server from: {url}")
                
                class ProgressTracker:
                    def __init__(self, callback):
                        self.callback = callback
                        self.downloaded = 0
                        self.total = 0
                        self.last_percent = -1
                    
                    def update(self, block_num, block_size, total_size):
                        self.downloaded = block_num * block_size
                        self.total = total_size
                        if total_size > 0:
                            percent = int(self.downloaded * 100 / total_size)
                            if percent != self.last_percent:
                                self.last_percent = percent
                                if self.callback:
                                    self.callback({
                                        "type": "download",
                                        "progress": percent,
                                        "message": f"Downloading... {percent}%"
                                    })
                                print(f"\rDownloading: {percent}%", end="", flush=True)
                
                tracker = ProgressTracker(progress_callback)
                
                with urllib.request.urlopen(url) as response:
                    total_size = int(response.headers.get('Content-Length', 0))
                    chunk_size = 8192
                    
                    with open(temp_file, 'wb') as f:
                        downloaded = 0
                        while True:
                            chunk = response.read(chunk_size)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                percent = int(downloaded * 100 / total_size)
                                if percent != tracker.last_percent:
                                    tracker.last_percent = percent
                                    if progress_callback:
                                        progress_callback({
                                            "type": "download",
                                            "progress": percent,
                                            "message": f"Downloading... {percent}%"
                                        })
                                    print(f"\rDownloading: {percent}%", end="", flush=True)
                
                print()
                
                if progress_callback:
                    progress_callback({
                        "type": "extract",
                        "progress": 0,
                        "message": "Extracting files..."
                    })
                
                print("Extracting files...")
                if extension == ".zip":
                    with zipfile.ZipFile(temp_file, 'r') as zip_ref:
                        zip_ref.extractall(self.server_dir)
                elif extension == ".tar.gz":
                    with tarfile.open(temp_file, 'r:gz') as tar_ref:
                        tar_ref.extractall(self.server_dir)
                
                if binary_name != "llama-server.exe":
                    binary_path = self.server_dir / binary_name
                    if binary_path.exists():
                        os.chmod(binary_path, 0o755)
                
                temp_file.unlink(missing_ok=True)
                
                if progress_callback:
                    progress_callback({
                        "type": "complete",
                        "progress": 100,
                        "message": "Installation complete!"
                    })
                
                return {"success": True, "message": "Server binary downloaded and extracted successfully"}
                
            except urllib.error.HTTPError as e:
                temp_file.unlink(missing_ok=True)
                return {"success": False, "error": f"HTTP error {e.code}: {e.reason}"}
            except urllib.error.URLError as e:
                temp_file.unlink(missing_ok=True)
                return {"success": False, "error": f"Network error: {e.reason}"}
            except Exception as e:
                temp_file.unlink(missing_ok=True)
                return {"success": False, "error": f"Download/extract failed: {str(e)}"}
    
    def get_installation_status(self) -> Dict[str, Any]:
        """Get comprehensive installation status."""
        sys_info = self.get_system_info()
        python_wheel_installed = self.is_python_wheel_installed()
        server_binary_available = self.is_server_binary_available()
        
        # Check if server is running
        server_running = self.is_server_running()
        
        return {
            "python_wheel": {
                "installed": python_wheel_installed,
                "version": self.get_python_wheel_version() if python_wheel_installed else None
            },
            "server_binary": {
                "available": server_binary_available,
                "binary_name": self.get_server_binary_name() if server_binary_available else None
            },
            "server_status": {
                "running": server_running
            },
            "system_info": sys_info,
            "recommended_action": self.get_recommended_action()
        }
    
    def get_python_wheel_version(self) -> Optional[str]:
        """Get the installed llama-cpp-python version."""
        try:
            import llama_cpp
            return getattr(llama_cpp, '__version__', 'unknown')
        except ImportError:
            return None
    
    def get_server_binary_name(self) -> Optional[str]:
        """Get the name of the available server binary."""
        binary_names = ["llama-server.exe", "llama-server", "llama.exe", "llama"]
        for binary_name in binary_names:
            if (self.server_dir / binary_name).exists():
                return binary_name
        return None
    
    def is_server_running(self) -> bool:
        """Check if the llama.cpp server is running."""
        try:
            import requests
            response = requests.get("http://localhost:8080/v1/models", timeout=2)
            return response.status_code == 200
        except:
            return False
    
    def get_recommended_action(self) -> str:
        """Get the recommended installation action based on current status."""
        python_installed = self.is_python_wheel_installed()
        binary_available = self.is_server_binary_available()
        
        if not python_installed and not binary_available:
            return "Install both Python wheel and server binary"
        elif not python_installed:
            return "Install Python wheel"
        elif not binary_available:
            return "Download server binary"
        else:
            return "All components installed - ready to use!"
    
    def install_complete(self, progress_callback=None) -> Dict[str, Any]:
        """Install both Python wheel and server binary."""
        results = {}
        
        # Install Python wheel
        print("Installing Python wheel...")
        wheel_result = self.install_python_wheel()
        results["python_wheel"] = wheel_result
        
        if progress_callback:
            progress_callback({
                "type": "python_wheel",
                "success": wheel_result["success"],
                "message": wheel_result.get("message", wheel_result.get("error", ""))
            })
        
        # Download server binary
        print("Downloading server binary...")
        binary_result = self.download_and_extract_server(progress_callback)
        results["server_binary"] = binary_result
        
        # Overall success
        overall_success = wheel_result["success"] and binary_result["success"]
        
        return {
            "success": overall_success,
            "message": "Complete installation finished" if overall_success else "Some components failed to install",
            "results": results
        }
    
    def get_wheel_url(self) -> Optional[str]:
        """Get the appropriate wheel URL based on OS and GPU detection."""
        os_name = detect_os()
        gpu_type = detect_gpu()
        
        wheel_url = WHEEL_URLS.get(os_name, {}).get(gpu_type)
        
        if not wheel_url:
            wheel_url = WHEEL_URLS.get(os_name, {}).get("cpu")
        
        return wheel_url
    
    def download_model_from_huggingface(
        self,
        repo_id: str,
        filename: str,
        progress_callback=None
    ) -> Dict[str, Any]:
        """Download a GGUF model from HuggingFace."""
        try:
            from huggingface_hub import hf_hub_download
        except ImportError:
            return {"success": False, "error": "huggingface_hub not installed. Install with: pip install huggingface_hub"}
        
        try:
            if progress_callback:
                progress_callback({
                    "type": "download",
                    "progress": 0,
                    "message": f"Downloading {filename} from HuggingFace..."
                })
            
            file_path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=str(self.llm_dir),
                local_dir_use_symlinks=False
            )
            
            if progress_callback:
                progress_callback({
                    "type": "complete",
                    "progress": 100,
                    "message": "Download complete!"
                })
            
            return {
                "success": True,
                "message": f"Model downloaded to {file_path}",
                "path": file_path
            }
            
        except Exception as e:
            return {"success": False, "error": f"Download failed: {str(e)}"}
    
    def download_model_from_url(
        self,
        url: str,
        filename: Optional[str] = None,
        progress_callback=None
    ) -> Dict[str, Any]:
        """Download a model from a direct URL with progress tracking."""
        if not filename:
            filename = url.split("/")[-1]
        
        dest_path = self.llm_dir / filename
        
        try:
            print(f"Downloading {url}")
            
            with urllib.request.urlopen(url) as response:
                total_size = int(response.headers.get('Content-Length', 0))
                chunk_size = 8192
                
                with open(dest_path, 'wb') as f:
                    downloaded = 0
                    last_percent = -1
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = int(downloaded * 100 / total_size)
                            if percent != last_percent:
                                last_percent = percent
                                if progress_callback:
                                    progress_callback({
                                        "type": "download",
                                        "progress": percent,
                                        "message": f"Downloading... {percent}%"
                                    })
                                print(f"\rDownloading: {percent}%", end="", flush=True)
            
            print()
            
            if progress_callback:
                progress_callback({
                    "type": "complete",
                    "progress": 100,
                    "message": "Download complete!"
                })
            
            return {
                "success": True,
                "message": f"Model downloaded to {dest_path}",
                "path": str(dest_path)
            }
            
        except urllib.error.HTTPError as e:
            if dest_path.exists():
                dest_path.unlink(missing_ok=True)
            return {"success": False, "error": f"HTTP error {e.code}: {e.reason}"}
        except urllib.error.URLError as e:
            if dest_path.exists():
                dest_path.unlink(missing_ok=True)
            return {"success": False, "error": f"Network error: {e.reason}"}
        except Exception as e:
            if dest_path.exists():
                dest_path.unlink(missing_ok=True)
            return {"success": False, "error": f"Download failed: {str(e)}"}
    
    def get_available_models(self) -> List[Dict[str, Any]]:
        """Get list of locally available GGUF models."""
        models = []
        
        if not self.llm_dir.exists():
            return models
        
        for gguf_file in self.llm_dir.rglob("*.gguf"):
            try:
                size = gguf_file.stat().st_size
                models.append({
                    "name": gguf_file.name,
                    "path": str(gguf_file),
                    "size": size,
                    "size_formatted": self._format_size(size)
                })
            except Exception:
                continue
        
        return models
    
    def _format_size(self, bytes_size: int) -> str:
        """Format bytes to human-readable size."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.1f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.1f} PB"


# Global installer instance
_installer = LlamaCppInstaller()


def get_installer() -> LlamaCppInstaller:
    """Get the global installer instance."""
    return _installer