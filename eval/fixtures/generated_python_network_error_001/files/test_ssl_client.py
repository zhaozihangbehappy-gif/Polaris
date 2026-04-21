import ssl
import unittest
from pathlib import Path

import ssl_client

CERT = Path(__file__).with_name("server_cert.pem")
KEY = Path(__file__).with_name("server_key.pem")


def complete_memory_tls_handshake(client_context):
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(CERT, KEY)

    client_in = ssl.MemoryBIO()
    client_out = ssl.MemoryBIO()
    server_in = ssl.MemoryBIO()
    server_out = ssl.MemoryBIO()

    client = client_context.wrap_bio(
        client_in, client_out, server_side=False, server_hostname="localhost"
    )
    server = server_context.wrap_bio(server_in, server_out, server_side=True)

    client_done = False
    server_done = False
    for _ in range(10):
        if not client_done:
            try:
                client.do_handshake()
                client_done = True
            except ssl.SSLWantReadError:
                pass

        data = client_out.read()
        if data:
            server_in.write(data)

        if not server_done:
            try:
                server.do_handshake()
                server_done = True
            except ssl.SSLWantReadError:
                pass

        data = server_out.read()
        if data:
            client_in.write(data)

        if client_done and server_done:
            return True

    return False


class TestSSLClient(unittest.TestCase):
    def test_client_context_trusts_local_server_certificate(self):
        context = ssl_client.make_client_context()
        self.assertTrue(complete_memory_tls_handshake(context))


if __name__ == "__main__":
    unittest.main()
