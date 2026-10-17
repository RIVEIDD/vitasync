import threading
from pathlib import Path

from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer

from vitasync.config import VitaConfig


class FakeVita:
    """Serveur FTP local qui joue le rôle de VitaShell pendant les tests."""

    def __init__(self, root: Path) -> None:
        self.root = root
        authorizer = DummyAuthorizer()
        authorizer.add_anonymous(str(root), perm="elradfmw")
        handler = type("Handler", (FTPHandler,), {"authorizer": authorizer})
        self.server = FTPServer(("127.0.0.1", 0), handler)
        self.port: int = self.server.socket.getsockname()[1]
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"timeout": 0.05}, daemon=True
        )

    @property
    def config(self) -> VitaConfig:
        return VitaConfig(host="127.0.0.1", port=self.port, timeout=5.0)
