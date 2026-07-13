"""Omnix user customization hook.

Persistence startup is intentionally not installed through Python's implicit
``usercustomize`` mechanism. The supported application launcher calls the
explicit PostgreSQL bootstrap before importing feature modules. Keeping this
module inert prevents test collection, package installation, and unrelated
operator scripts from contacting the authoritative database unexpectedly.
"""

from __future__ import annotations
