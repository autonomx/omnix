"""Phase 12.10 — Visual generation layer.

Provides provider-agnostic image generation, asset storage,
and background worker processing for pending visual requests.
"""
from __future__ import annotations

# Fix Windows multiprocessing sys.path inheritance issue
# This must run BEFORE any imports or process creation
import os
import sys

# Propagate current sys.path to all child processes
os.environ['PYTHONPATH'] = os.pathsep.join(sys.path)