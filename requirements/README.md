# Python runtime dependency inputs

Omnix supports Python 3.11. Runtime-specific inputs are compiled with pip-tools
using `--generate-hashes`. Generated `*.lock.txt` files become installation
authority only after clean-environment validation.

The legacy root `requirements.txt` remains temporarily during WP-1.3 so the
transition cannot silently change operator installs. GPU runtimes remain
separate from gateway/worker dependencies.
