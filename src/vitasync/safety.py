"""Écritures protégées : toujours une copie de sécurité avant d'écraser."""

import shutil
import tempfile
from pathlib import Path

from vitasync.ftp import VitaFtpClient
from vitasync.store import SaveStore, SaveVersion

BACKUP_PC = "backup-pc"
BACKUP_VITA = "backup-vita"


def backup_pc_dir(store: SaveStore, game_id: str, path: Path) -> SaveVersion | None:
    """Copie un dossier du PC dans le stockage avant qu'il soit modifié.

    Args:
        store: Stockage qui reçoit la copie.
        game_id: Identifiant du jeu.
        path: Dossier du PC qui va être modifié.

    Returns:
        La copie créée, ou ``None`` si le dossier n'existe pas encore
        (il n'y a alors rien à protéger).
    """
    if not path.exists():
        return None
    return store.snapshot(game_id, path, origin=BACKUP_PC)


def backup_vita_dir(
    store: SaveStore, game_id: str, ftp: VitaFtpClient, remote: str
) -> SaveVersion | None:
    """Télécharge un dossier de la Vita dans le stockage avant qu'il soit modifié.

    Args:
        store: Stockage qui reçoit la copie.
        game_id: Identifiant du jeu.
        ftp: Connexion ouverte à la Vita.
        remote: Dossier de la Vita qui va être modifié.

    Returns:
        La copie créée, ou ``None`` si le dossier n'existe pas encore.

    Raises:
        TransferError: Si le téléchargement échoue. Dans ce cas, rien ne doit
            être écrit sur la Vita.
    """
    if not ftp.dir_exists(remote):
        return None
    with tempfile.TemporaryDirectory(prefix="vitasync-") as tmp:
        files = Path(tmp) / "files"
        ftp.download_dir(remote, files)
        return store.snapshot(game_id, files, origin=BACKUP_VITA)


def _copy_file(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".part")
    try:
        shutil.copy2(source, partial)
        partial.replace(dest)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise


def write_pc_files(store: SaveStore, game_id: str, source: Path, dest: Path) -> SaveVersion | None:
    """Copie les fichiers de ``source`` dans ``dest``, après une copie de sécurité.

    Seuls les fichiers présents dans ``source`` sont remplacés : les autres
    fichiers de ``dest`` (par exemple d'autres slots) ne sont pas touchés.

    Args:
        store: Stockage qui reçoit la copie de sécurité.
        game_id: Identifiant du jeu.
        source: Dossier contenant les fichiers à écrire.
        dest: Dossier du PC à mettre à jour.

    Returns:
        La copie de sécurité de ``dest``, ou ``None`` s'il n'existait pas.
    """
    backup = backup_pc_dir(store, game_id, dest)
    for file in sorted(source.rglob("*")):
        if file.is_file():
            _copy_file(file, dest / file.relative_to(source))
    return backup


def write_vita_files(
    store: SaveStore, game_id: str, ftp: VitaFtpClient, source: Path, remote: str
) -> SaveVersion | None:
    """Envoie les fichiers de ``source`` sur la Vita, après une copie de sécurité.

    Seuls les fichiers présents dans ``source`` sont remplacés, jamais le
    dossier entier.

    Args:
        store: Stockage qui reçoit la copie de sécurité.
        game_id: Identifiant du jeu.
        ftp: Connexion ouverte à la Vita.
        source: Dossier local contenant les fichiers à envoyer.
        remote: Dossier de la Vita à mettre à jour.

    Returns:
        La copie de sécurité du dossier Vita, ou ``None`` s'il n'existait pas.

    Raises:
        TransferError: Si la copie de sécurité ou l'envoi échoue.
    """
    backup = backup_vita_dir(store, game_id, ftp, remote)
    ftp.upload_dir(source, remote)
    return backup
