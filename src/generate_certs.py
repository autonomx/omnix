"""Generate a self-signed certificate for local HTTPS (WP-11.4).

    python src/generate_certs.py --host omnix.local --ip 192.168.1.20 [--out DIR] [--days 365]

Writes cert.pem and key.pem (the key readable by the owner only). Each --host
and --ip becomes a subject alternative name; the first one is the common name.
"""
from __future__ import annotations

import argparse
import datetime
import ipaddress
import os
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def build(hosts: list[str], ips: list[str], days: int) -> tuple[bytes, bytes]:
    names: list[x509.GeneralName] = [x509.DNSName(host) for host in hosts]
    names += [x509.IPAddress(ipaddress.ip_address(value)) for value in ips]
    if not names:
        raise ValueError("name at least one --host or --ip")
    common_name = hosts[0] if hosts else ips[0]
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName(names), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return cert.public_bytes(serialization.Encoding.PEM), key_pem


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", action="append", default=[], help="DNS name (repeatable)")
    parser.add_argument("--ip", action="append", default=[], help="IP address (repeatable)")
    parser.add_argument("--out", type=Path, default=Path.cwd(), help="output directory (default: current)")
    parser.add_argument("--days", type=int, default=365)
    args = parser.parse_args(argv)
    try:
        cert_pem, key_pem = build(args.host, args.ip, args.days)
    except ValueError as exc:
        parser.error(str(exc))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "cert.pem").write_bytes(cert_pem)
    key_path = args.out / "key.pem"
    key_path.write_bytes(key_pem)
    os.chmod(key_path, 0o600)
    print(f"Wrote {args.out / 'cert.pem'} and {key_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
