#!/usr/bin/env python3
"""
Build llama.cpp from source for Docker

This script clones the llama.cpp repository and builds the server binary
with CUDA support. This is more reliable than downloading pre-built
binaries which may not be available for all platforms.
"""
import os
import platform
import subprocess
import sys
import tempfile

# Set paths based on platform
if platform.system() == 'Windows':
    DEST_DIR = os.path.join(os.getcwd(), 'models', 'server')
    LLAMA_DIR = os.path.join(tempfile.gettempdir(), 'llama.cpp')
else:
    DEST_DIR = '/app/models/server'
    LLAMA_DIR = '/tmp/llama.cpp'

def run_cmd(cmd, cwd=None, env=None, timeout=900):  # 15 minutes for build
    """Run a shell command and return the result"""
    import platform
    print(f'Running: {" ".join(cmd)}')
    
    # On Windows, use shell=True for better compatibility
    shell = platform.system() == 'Windows'
    
    # On Linux Docker, use python3 instead of python
    cmd = [c.replace('python ', 'python3 ') for c in cmd]
    
    try:
        result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, 
                               shell=shell, timeout=timeout)
        if result.returncode != 0:
            print(f'Error: {result.stderr[:500] if result.stderr else "Unknown error"}')
            return False
        if result.stdout:
            print(result.stdout[:500])
        return True
    except subprocess.TimeoutExpired:
        print(f'Command timed out after {timeout} seconds')
        return False

def install_build_deps():
    """Install build dependencies"""
    import platform
    
    # Skip on Windows - this script is meant to run in Linux Docker container
    if platform.system() == 'Windows':
        print('Skipping build deps install on Windows (this runs in Docker Linux container)')
        return
    
    print('Installing build dependencies...')
    # These should already be in the Docker image, but just in case
    deps = ['cmake', 'build-essential', 'curl', 'python3']
    cmd = ['apt-get', 'update'] + ['apt-get', 'install', '-y'] + deps
    subprocess.run(cmd, check=False)  # Continue even if fails - deps may exist
    
def build_llama_cpp():
    """Clone and build llama.cpp from source"""
    import platform
    import shutil
    
    # Clean up any previous build
    if os.path.exists(LLAMA_DIR):
        print('Removing previous build directory...')
        if platform.system() == 'Windows':
            shutil.rmtree(LLAMA_DIR, ignore_errors=True)
        else:
            subprocess.run(['rm', '-rf', LLAMA_DIR])
    
    # Clone llama.cpp
    print('Cloning llama.cpp repository...')
    if not run_cmd(['git', 'clone', '--depth', '1', 'https://github.com/ggml-org/llama.cpp.git', LLAMA_DIR]):
        print('Failed to clone llama.cpp')
        return False
    
    # Create build directory
    build_dir = os.path.join(LLAMA_DIR, 'build')
    os.makedirs(build_dir, exist_ok=True)
    
    # Configure with CMake - try with CUDA first, fallback to CPU
    print('Configuring with CMake (trying CUDA first)...')
    cmake_cmd = [
        'cmake',
        '..',
        '-DCMAKE_BUILD_TYPE:STRING=Release',
        '-DGGML_CUDA=ON',  # Enable CUDA (new option name)
        '-DLLAMA_SERVER=ON',   # Build server
    ]
    
    env = os.environ.copy()
    env['CUDA_VISIBLE_DEVICES'] = ''  # Hide CUDA devices for initial configure
    
    if not run_cmd(cmake_cmd, cwd=build_dir, env=env):
        print('CMake configuration failed with CUDA, trying CPU-only...')
        # Clean the build directory and try without CUDA
        import shutil
        shutil.rmtree(build_dir, ignore_errors=True)
        os.makedirs(build_dir, exist_ok=True)
        
        # Try without CUDA - explicitly disable it
        cmake_cmd = [
            'cmake',
            '..',
            '-DCMAKE_BUILD_TYPE:STRING=Release',
            '-DGGML_CUDA=OFF',  # Explicitly disable CUDA
            '-DLLAMA_SERVER=ON',
        ]
        if not run_cmd(cmake_cmd, cwd=build_dir, env=env):
            print('CMake configuration failed')
            return False
    
    # Build - use single thread to avoid Docker resource issues
    print('Building llama.cpp server (this may take a while)...')
    build_cmd = ['cmake', '--build', '.', '-j1']
    if not run_cmd(build_cmd, cwd=build_dir):
        print('Build failed')
        return False
    
    # Find the server binary
    server_bin = os.path.join(build_dir, 'bin', 'llama-server')
    if not os.path.exists(server_bin):
        # Try alternative location
        server_bin = os.path.join(build_dir, 'llama-server')
    
    if os.path.exists(server_bin):
        dest_bin = os.path.join(DEST_DIR, 'llama-server')
        print(f'Copying server to {dest_bin}...')
        if platform.system() == 'Windows':
            shutil.copy(server_bin, dest_bin)
        else:
            subprocess.run(['cp', server_bin, dest_bin])
            os.chmod(dest_bin, 0o755)  # Make executable
        return True
    else:
        print('Server binary not found!')
        # List what was built
        print('Build output:')
        if platform.system() == 'Windows':
            for root, dirs, files in os.walk(build_dir):
                for f in files:
                    if 'llama' in f.lower():
                        print(f'  {os.path.join(root, f)}')
        else:
            subprocess.run(['find', build_dir, '-name', 'llama*', '-type', 'f'], cwd=build_dir)
        return False

def main():
    import platform
    
    os.makedirs(DEST_DIR, exist_ok=True)
    
    # On Windows, just verify the clone exists and inform user to run in Docker
    if platform.system() == 'Windows':
        print('=== Windows detected ===')
        print('This script is designed to run inside the Docker Linux container.')
        print('On Windows, it just verifies the setup is ready.')
        
        if os.path.exists(LLAMA_DIR):
            print(f'llama.cpp repository already cloned at: {LLAMA_DIR}')
            print('\nTo build the Docker image, run:')
            print('  docker build -t omnix .')
            return 0
        else:
            print('llama.cpp not cloned yet - will be cloned during Docker build.')
            return 0
    
    # Install build dependencies (Linux only)
    install_build_deps()
    
    # Build llama.cpp
    if build_llama_cpp():
        print('\n=== BUILD SUCCESSFUL ===')
        print('llama.cpp server built and installed!')
        
        # List installed files
        print('\nInstalled files:')
        for f in os.listdir(DEST_DIR):
            fpath = os.path.join(DEST_DIR, f)
            size = os.path.getsize(fpath) / 1024 / 1024
            print(f'  {f} ({size:.1f} MB)')
        return 0
    else:
        print('\n=== BUILD FAILED ===')
        print('Could not build llama.cpp from source')
        return 1

if __name__ == '__main__':
    sys.exit(main())
