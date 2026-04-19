import os
import json
import datetime
from typing import Any, Dict, Optional
from app.shared import LOGS_DIR


def _get_log_file_path(log_name: str) -> str:
    """Get full path for log file, ensures directory exists"""
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    filename = f"{log_name}_{date_str}.log"
    return os.path.join(LOGS_DIR, filename)


def write_rpg_log(message: str, level: str = "INFO", extra: Optional[Dict[str, Any]] = None) -> None:
    """Write RPG system logs to file, no console output"""
    timestamp = datetime.datetime.now().isoformat()
    log_entry = {
        "timestamp": timestamp,
        "level": level,
        "message": message,
        "category": "rpg"
    }
    if extra:
        log_entry.update(extra)
    
    log_path = _get_log_file_path("rpg")
    try:
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + '\n')
    except Exception:
        # Fail silently, never break application for logging
        pass


def write_backend_log(message: str, level: str = "INFO", extra: Optional[Dict[str, Any]] = None) -> None:
    """Write backend application logs to file, no console output"""
    timestamp = datetime.datetime.now().isoformat()
    log_entry = {
        "timestamp": timestamp,
        "level": level,
        "message": message,
        "category": "backend"
    }
    if extra:
        log_entry.update(extra)
    
    log_path = _get_log_file_path("backend")
    try:
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + '\n')
    except Exception:
        # Fail silently, never break application for logging
        pass


def write_debug_log(message: str, extra: Optional[Dict[str, Any]] = None) -> None:
    """Write debug/trace logs to separate file"""
    timestamp = datetime.datetime.now().isoformat()
    log_entry = {
        "timestamp": timestamp,
        "message": message,
        "category": "debug"
    }
    if extra:
        log_entry.update(extra)
    
    log_path = _get_log_file_path("debug")
    try:
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + '\n')
    except Exception:
        pass