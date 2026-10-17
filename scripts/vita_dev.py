"""Boucle de développement de l'appli Vita, via vitacompanion (FTP 1337, commandes 1338).

Usage (depuis la racine du dépôt) :
    python -m uv run python scripts/vita_dev.py deploy vita/build/vitasync.vpk
    python -m uv run python scripts/vita_dev.py cmd "launch VSYNC0001"
    python -m uv run python scripts/vita_dev.py crashes
    python -m uv run python scripts/vita_dev.py get ux0:data/vitasync/screen.bmp travail/screen.bmp

Outil de développement uniquement : il suppose vitacompanion chargé sous *main.
"""

import argparse
import socket
import sys
import tempfile
import zipfile
from pathlib import Path

from vitasync.config import VitaConfig
from vitasync.ftp import VitaFtpClient

HOST = "192.168.1.5"
CMD_PORT = 1338
STAGING = "ux0:data/vitasync_dev/app"
TITLE_ID = "VSYNC0001"


def send_command(command: str, timeout: float = 30.0) -> str:
    """Envoie une commande au port de commandes de vitacompanion et renvoie sa réponse."""
    with socket.create_connection((HOST, CMD_PORT), timeout=timeout) as sock:
        sock.sendall(command.encode() + b"\n")
        sock.shutdown(socket.SHUT_WR)
        chunks = []
        while data := sock.recv(4096):
            chunks.append(data)
    return b"".join(chunks).decode(errors="replace").strip()


def deploy(vpk: Path) -> None:
    """Décompresse le VPK, l'envoie sur la Vita, l'installe et le lance."""
    print(send_command(f"quit {TITLE_ID}"))
    with tempfile.TemporaryDirectory() as tmp:
        app = Path(tmp) / "app"
        with zipfile.ZipFile(vpk) as archive:
            archive.extractall(app)
        with VitaFtpClient(VitaConfig(host=HOST)) as ftp:
            if ftp.dir_exists(STAGING):
                ftp.remove_tree(STAGING)
            ftp.make_dir("ux0:data/vitasync_dev")
            sent = ftp.upload_dir(app, STAGING)
    print(f"{len(sent)} fichiers envoyés dans {STAGING}")
    print(send_command(f"promote {STAGING}", timeout=120))
    print(send_command(f"launch {TITLE_ID}"))


def crashes() -> None:
    """Liste les rapports de plantage (psp2dmp) présents sur la Vita."""
    with VitaFtpClient(VitaConfig(host=HOST)) as ftp:
        for entry in ftp.list_dir("ux0:data"):
            if "psp2dmp" in entry.name:
                print(entry.size, entry.name)


def get(remote: str, local: Path) -> None:
    """Télécharge un fichier de la Vita."""
    with VitaFtpClient(VitaConfig(host=HOST)) as ftp:
        ftp.download_file(remote, local)
    print(f"{remote} -> {local}")


def main() -> int:
    """Point d'entrée."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("deploy").add_argument("vpk", type=Path)
    sub.add_parser("cmd").add_argument("command")
    sub.add_parser("crashes")
    get_parser = sub.add_parser("get")
    get_parser.add_argument("remote")
    get_parser.add_argument("local", type=Path)
    args = parser.parse_args()
    if args.action == "deploy":
        deploy(args.vpk)
    elif args.action == "cmd":
        print(send_command(args.command))
    elif args.action == "crashes":
        crashes()
    else:
        get(args.remote, args.local)
    return 0


if __name__ == "__main__":
    sys.exit(main())
