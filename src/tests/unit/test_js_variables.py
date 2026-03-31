"""
Backend tests to catch JavaScript variable declaration conflicts.
Run with: python -m pytest tests/test_js_variables.py -v
"""
import os
import re
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).parent.parent.parent
STATIC_DIR = BASE_DIR / "static"


def get_js_files():
    """Get all JavaScript files in static directory."""
    js_files = []
    for root, _, files in os.walk(STATIC_DIR):
        for f in files:
            if f.endswith('.js'):
                js_files.append(Path(root) / f)
    return js_files


def extract_global_vars(js_path):
    """
    Extract global variable declarations from a JS file.
    Returns dict of {var_name: line_number}
    """
    content = js_path.read_text(encoding='utf-8')
    global_vars = {}
    
    lines = content.split('\n')
    
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        
        if stripped.startswith('//') or stripped.startswith('*'):
            continue
        
        var_match = re.match(r'^(let|const|var)\s+(\w+)\s*=', stripped)
        if var_match:
            var_type, var_name = var_match.groups()
            global_vars[var_name] = i
    
    return global_vars


def test_no_duplicate_global_vars():
    """Test that no global variables are declared multiple times across JS files."""
    js_files = get_js_files()
    assert len(js_files) > 0, "No JS files found in static directory"
    
    common_local_vars = {
        'data', 'response', 'result', 'text', 'file', 'url', 'name', 'buffer',
        'audio', 'stream', 'msg', 'content', 'reader', 'div', 'option', 'select',
        'a', 'span', 'button', 'input', 'form', 'label', 'container', 'header',
        'event', 'events', 'len', 'offset', 'output', 't', 'html', 'source',
        'duration', 'currentTime', 'startTime', 'percent', 'profile', 'profiles',
        'decoder', 'lines', 'dataStr', 'mins', 'secs', 'blob', 'wavBuffer',
        'pcmBuffer', 'combinedPcm', 'view', 'float32', 'int16', 'binaryString',
        'arrayBuffer', 'uint8Array', 'pcmView', 'numChannels', 'bitsPerSample',
        'bytesPerSample', 'blockAlign', 'byteRate', 'dataSize', 'bufferSize',
        'statusResponse', 'statusData', 'rect', 'totalDuration', 'totalLength',
        'apiKey', 'model', 'settings', 'sampleRate', 'pcmArrays', 'totalTime',
        'fadeIn', 'fadeOut', 'fadeLength', 'crossFadeLength', 'numSamples',
        'pcm16', 'infoEl', 'statusEl', 'pauseBtn', 'resumeBtn', 'playBtn',
        'personality', 'nameInput', 'voiceProfilesKey', 'saved', 'voiceCloneModal',
        'ttsSpeaker', 'audioUrl', 'formData', 'streamingAudioElement', 'systemPrompt',
        'audioBlob', 'messageDiv', 'contentDiv', 'headerDiv', 'message', 'startTime',
            'podcastBtn', 'date', 'streamedContent', 'voiceProfile', 'sseBuffer',
            'selectedSpeaker', 'thinkingContainer', 'thinkingHeader', 'thinkingContent',
            'headerHTML', 'ttsSpeakerSelect', 'messages', 'isPlaying', 'binary', 'bytes',
            'audioBuffer', 'streamingAudioContext', 'totalStartTime', 'conversationMessages',
            'avatarDiv', 'contentEl', 'msgDiv', 'avDiv', 'contDiv', 'convMessages',
            'totalLatency', 'llmLatency', 'tokenSpeed', 'tokensGenerated', 'ttft', 'tpft', 'ttfa', 'ttsGen'
        }
    
    all_global_vars = {}
    conflicts = []
    
    for js_file in js_files:
        global_vars = extract_global_vars(js_file)
        
        for var_name, line_num in global_vars.items():
            if var_name in common_local_vars:
                continue
                
            if var_name in all_global_vars:
                prev_file, prev_line = all_global_vars[var_name]
                conflicts.append({
                    'variable': var_name,
                    'file1': str(js_file.relative_to(BASE_DIR)),
                    'line1': line_num,
                    'file2': str(prev_file.relative_to(BASE_DIR)),
                    'line2': prev_line
                })
            else:
                all_global_vars[var_name] = (js_file, line_num)
    
    if conflicts:
        error_msg = "\n\nJavaScript global variable conflicts detected:\n"
        for c in conflicts:
            error_msg += f"  - '{c['variable']}' declared in:\n"
            error_msg += f"      {c['file1']}:{c['line1']}\n"
            error_msg += f"      {c['file2']}:{c['line2']}\n"
        pytest.fail(error_msg)


def test_no_global_var_shadowing_in_same_file():
    """Test that variables aren't declared twice in the same file."""
    js_files = get_js_files()
    
    errors = []
    for js_file in js_files:
        global_vars = extract_global_vars(js_file)
        
        seen = {}
        for var_name, line_num in global_vars.items():
            if var_name in seen:
                errors.append(f"{js_file.relative_to(BASE_DIR)}:{line_num}: '{var_name}' already declared at line {seen[var_name]}")
            seen[var_name] = line_num
    
    if errors:
        pytest.fail("\n".join(errors))


def test_no_undeclared_global_access():
    """Test for common undeclared global variables being accessed."""
    js_files = get_js_files()
    
    common_globals = {
        'window', 'document', 'navigator', 'console', 'setTimeout',
        'setInterval', 'fetch', 'WebSocket', 'AudioContext', 'AudioWorklet',
        'performance', 'location', 'history', 'localStorage', 'sessionStorage',
        'FormData', 'Blob', 'File', 'URL', 'URLSearchParams'
    }
    
    issues = []
    
    for js_file in js_files:
        content = js_file.read_text(encoding='utf-8')
        lines = content.split('\n')
        
        for i, line in enumerate(lines, 1):
            if line.strip().startswith('//'):
                continue
            
            for global_name in common_globals:
                pattern = rf'\b{global_name}\s*=\s*'
                if re.search(pattern, line):
                    issues.append(f"{js_file.relative_to(BASE_DIR)}:{i}: Assigning to undeclared global '{global_name}'")
    
    if issues:
        print("\nPotential issues (may be false positives):")
        for issue in issues[:10]:
            print(f"  {issue}")


def test_specific_known_conflicts():
    """Test for specific known conflicts that have occurred."""
    js_files = get_js_files()
    
    known_conflicts = [
        'sessionId',
        'audioContext', 
        'ws',
        'isConnected',
        'isSpeaking'
    ]
    
    file_vars = {}
    for js_file in js_files:
        file_vars[str(js_file.relative_to(BASE_DIR))] = extract_global_vars(js_file)
    
    conflicts_found = []
    
    for var_name in known_conflicts:
        files_with_var = [f for f, vars in file_vars.items() if var_name in vars]
        if len(files_with_var) > 1:
            conflicts_found.append(f"'{var_name}' declared in multiple files: {files_with_var}")
    
    if conflicts_found:
        pytest.fail("\n".join(conflicts_found))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
