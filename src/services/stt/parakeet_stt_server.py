"""Compatibility entrypoint for the optimized Omnix Parakeet runtime."""
from parakeet_stt_runtime import app, main

__all__ = ["app", "main"]

if __name__ == "__main__":
    main()
