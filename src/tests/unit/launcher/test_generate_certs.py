"""Local certificates name the hosts and addresses given, not a fixed LAN address (WP-11.4)."""
from __future__ import annotations

import importlib.util
import ipaddress
from pathlib import Path

import pytest
from cryptography import x509

ROOT = Path(__file__).resolve().parents[4]


def _module():
    spec = importlib.util.spec_from_file_location("generate_certs", ROOT / "src/generate_certs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_certificate_carries_every_requested_name(tmp_path):
    assert _module().main(["--host", "omnix.local", "--ip", "10.0.0.5", "--out", str(tmp_path)]) == 0
    cert = x509.load_pem_x509_certificate((tmp_path / "cert.pem").read_bytes())
    names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert names.get_values_for_type(x509.DNSName) == ["omnix.local"]
    assert names.get_values_for_type(x509.IPAddress) == [ipaddress.ip_address("10.0.0.5")]
    assert (tmp_path / "key.pem").read_bytes().startswith(b"-----BEGIN PRIVATE KEY-----")


def test_a_name_is_required():
    with pytest.raises(SystemExit):
        _module().main([])
