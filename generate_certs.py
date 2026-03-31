import os

cwd = os.getcwd()
print('Current dir:', cwd)

import datetime

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

print('Generating key...')
key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())

print('Generating certificate...')
subject = issuer = x509.Name([
    x509.NameAttribute(NameOID.COUNTRY_NAME, 'US'),
    x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, 'CA'),
    x509.NameAttribute(NameOID.LOCALITY_NAME, 'SF'),
    x509.NameAttribute(NameOID.COMMON_NAME, '192.168.1.71')
])

cert = x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(
    key.public_key()
).serial_number(
    x509.random_serial_number()
).not_valid_before(
    datetime.datetime.utcnow()
).not_valid_after(
    datetime.datetime.utcnow() + datetime.timedelta(days=365)
).add_extension(
    x509.SubjectAlternativeName([x509.DNSName('192.168.1.71')]),
    critical=False
).sign(key, hashes.SHA256(), default_backend())

cert_path = os.path.join(cwd, 'cert.pem')
key_path = os.path.join(cwd, 'key.pem')

print('Writing cert to:', cert_path)
with open(cert_path, 'wb') as f:
    f.write(cert.public_bytes(serialization.Encoding.PEM))

print('Writing key to:', key_path)
with open(key_path, 'wb') as f:
    f.write(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    ))

print('Done!')
print('Cert exists:', os.path.exists(cert_path))
print('Key exists:', os.path.exists(key_path))
