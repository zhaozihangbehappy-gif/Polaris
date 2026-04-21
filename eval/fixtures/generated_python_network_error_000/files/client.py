import socket


def fetch_banner(host, port):
    with socket.create_connection((host, port), timeout=0.2) as sock:
        return sock.recv(64).decode("ascii")
