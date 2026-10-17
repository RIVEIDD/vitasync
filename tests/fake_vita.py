import shutil
import threading
from pathlib import Path

from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer

from vitasync.config import VitaConfig

APP_COMMANDS = {
    name: {"perm": None, "auth": True, "arg": arg, "help": name}
    for name, arg in (("VSVR", False), ("VSBK", True), ("VSRS", True))
}


class AppHandler(FTPHandler):  # type: ignore[misc]
    """Imite le FTP de l'appli VitaSync : commandes VSVR, VSBK et VSRS.

    La sauvegarde « décryptée » d'un jeu est le dossier ``savedata/<TITLEID>``,
    ses slots sont ``savegames/<TITLEID>/SLOT<n>``, comme Save Manager.
    """

    proto_cmds = {**FTPHandler.proto_cmds, **APP_COMMANDS}
    root = Path()

    def ftp_VSVR(self, line: str) -> None:  # noqa: N802 (nom imposé par pyftpdlib)
        self.respond("200 VitaSync test")

    def _paths(self, line: str) -> tuple[Path, Path] | None:
        parts = line.split()
        if len(parts) != 2 or not parts[1].isdigit():
            self.respond("501 Usage")
            return None
        title, slot = parts
        return self.root / "savedata" / title, self.root / "savegames" / title / f"SLOT{slot}"

    def ftp_VSBK(self, line: str) -> None:  # noqa: N802
        paths = self._paths(line)
        if paths is None:
            return
        save, slot = paths
        if not save.is_dir():
            self.respond("550 Sauvegarde introuvable")
            return
        shutil.copytree(save, slot, dirs_exist_ok=True)
        self.respond("200 OK")

    def ftp_VSRS(self, line: str) -> None:  # noqa: N802
        paths = self._paths(line)
        if paths is None:
            return
        save, slot = paths
        if not slot.is_dir():
            self.respond("550 Slot vide")
            return
        shutil.copytree(slot, save, dirs_exist_ok=True)
        self.respond("200 OK")


class FakeVita:
    """Serveur FTP local qui joue le rôle de VitaShell (ou de l'appli VitaSync)."""

    def __init__(self, root: Path, app: bool = False) -> None:
        self.root = root
        authorizer = DummyAuthorizer()
        authorizer.add_anonymous(str(root), perm="elradfmw")
        base = AppHandler if app else FTPHandler
        handler = type("Handler", (base,), {"authorizer": authorizer, "root": root})
        self.server = FTPServer(("127.0.0.1", 0), handler)
        self.port: int = self.server.socket.getsockname()[1]
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"timeout": 0.05}, daemon=True
        )

    @property
    def config(self) -> VitaConfig:
        return VitaConfig(host="127.0.0.1", port=self.port, timeout=5.0)
