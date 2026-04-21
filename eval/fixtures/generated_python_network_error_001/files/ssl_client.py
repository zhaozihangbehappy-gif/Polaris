import ssl


def make_client_context():
    return ssl.create_default_context()
