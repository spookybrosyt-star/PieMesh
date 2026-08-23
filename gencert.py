import datetime
import ipaddress
import socket
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

out = Path(__file__).parent / "certs"
out.mkdir(exist_ok=True)


def dump_key(p, k):
    p.write_bytes(
        k.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )


def dump_cert(p, c):
    p.write_bytes(c.public_bytes(serialization.Encoding.PEM))


ca_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Piemesh Root CA")])
now = datetime.datetime.now(datetime.timezone.utc)

ca_cert = (
    x509.CertificateBuilder()
    .subject_name(name)
    .issuer_name(name)
    .public_key(ca_key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now)
    .not_valid_after(now + datetime.timedelta(days=3650))
    .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
    .sign(ca_key, hashes.SHA256())
)

srv_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
sans = [x509.DNSName("localhost"), x509.DNSName(socket.gethostname())]
for ip in set(socket.gethostbyname_ex(socket.gethostname())[2]) | {"127.0.0.1"}:
    try:
        sans.append(x509.IPAddress(ipaddress.ip_address(ip)))
    except ValueError:
        pass

srv_cert = (
    x509.CertificateBuilder()
    .subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, socket.gethostname())])
    )
    .issuer_name(ca_cert.subject)
    .public_key(srv_key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now)
    .not_valid_after(now + datetime.timedelta(days=825))
    .add_extension(x509.SubjectAlternativeName(sans), critical=False)
    .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
    .sign(ca_key, hashes.SHA256())
)

dump_key(out / "ca.key", ca_key)
dump_cert(out / "ca.crt", ca_cert)
dump_key(out / "server.key", srv_key)
dump_cert(out / "server.crt", srv_cert)
print("done ->", out)
