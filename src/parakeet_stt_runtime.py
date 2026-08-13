"""Compatibility entrypoint for the Omnix Nemotron + Parakeet EOU runtime.

The historic Parakeet launcher imports this module, so keep the filename stable
while replacing the transcriber architecture underneath it.
"""
from nemotron_eou_stt_server import app, main

__all__ = ["app", "main"]

if __name__ == "__main__":
    main()
