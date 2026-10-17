"""Transferts de Hotline Miami entre la Vita et le PC (``pull``, ``push``, ``status``).

Hotline Miami n'a qu'une sauvegarde (``SaveData.sav``), sans slots : les
transferts portent sur tout le fichier, mais seuls les fichiers internes
communs changent (voir :mod:`vitasync.hotline_miami`).
"""

import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from vitasync import hotline_miami as hm
from vitasync.config import SteamConfig
from vitasync.ftp import VitaFtpClient
from vitasync.manifest import GameManifest
from vitasync.p4g_sync import (
    BACKUP_HINT,
    SlotState,
    SyncError,
    TransferResult,
    _app_slot,
    _slot_number,
    _vita_dir,
)
from vitasync.paths import resolve_pc_path
from vitasync.safety import backup_pc_dir, backup_vita_dir, copy_file
from vitasync.steam import is_steam_running
from vitasync.store import SaveStore

SAVE_SLOT = 1
"""Numéro affiché par ``status`` pour l'unique sauvegarde du jeu."""


def _fresh_dump(ftp: VitaFtpClient, game: GameManifest) -> tuple[str, int | None]:
    """Fait faire le Backup par l'appli VitaSync si elle est là ; renvoie (dossier, slot)."""
    dump = _vita_dir(game.vita.dump, "dump", game)
    dump_slot = _app_slot(ftp, dump)
    if dump_slot is not None:
        ftp.save_backup(game.vita.title_id, dump_slot)
    if not ftp.dir_exists(dump):
        raise SyncError(f"{dump} introuvable sur la Vita : {BACKUP_HINT}")
    return dump, dump_slot


def _read_vita_save(ftp: VitaFtpClient, dump: str, tmp: Path) -> bytes:
    local = tmp / hm.SAVE_FILE
    ftp.download_file(f"{dump.rstrip('/')}/{hm.SAVE_FILE}", local)
    return local.read_bytes()


def status(ftp: VitaFtpClient, steam: SteamConfig | None, game: GameManifest) -> list[SlotState]:
    """Compare l'avancement (niveaux débloqués) entre le PC et la Vita.

    Args:
        ftp: Connexion ouverte à la Vita.
        steam: Configuration Steam, ou ``None``.
        game: Fiche du jeu.

    Returns:
        Un seul état, numéroté 1, avec le nombre de niveaux débloqués de chaque côté.

    Raises:
        SyncError: Si la copie de la Vita est absente.
        SaveFormatError: Si une sauvegarde est illisible.
    """
    dump, _ = _fresh_dump(ftp, game)
    with tempfile.TemporaryDirectory(prefix="vitasync-hm-") as tmp:
        vita = hm.progress(_read_vita_save(ftp, dump, Path(tmp)))
    pc_file = resolve_pc_path(game.pc.path, steam) / hm.SAVE_FILE
    pc = hm.progress(pc_file.read_bytes()) if pc_file.is_file() else None
    return [SlotState(SAVE_SLOT, pc, vita)]


def pull(
    store: SaveStore,
    ftp: VitaFtpClient,
    steam: SteamConfig | None,
    game: GameManifest,
    steam_running: Callable[[], bool] | None = None,
) -> TransferResult:
    """Copie la progression de la Vita dans la sauvegarde PC.

    Args:
        store: Stockage des versions et des copies de sécurité.
        ftp: Connexion ouverte à la Vita.
        steam: Configuration Steam, ou ``None``.
        game: Fiche du jeu.
        steam_running: Détection de Steam, remplaçable dans les tests.

    Returns:
        Le résultat du transfert.

    Raises:
        SyncError: Si Steam est ouvert ou si la copie de la Vita est absente.
        SaveFormatError: Si une sauvegarde est illisible.
    """
    steam_running = steam_running or is_steam_running
    if steam_running():
        raise SyncError("Steam est ouvert : ferme-le complètement avant un pull")
    pc_dir = resolve_pc_path(game.pc.path, steam)
    pc_file = pc_dir / hm.SAVE_FILE
    if not pc_file.is_file():
        raise SyncError(f"{pc_file} introuvable : lance le jeu une fois sur PC")
    dump, dump_slot = _fresh_dump(ftp, game)
    with tempfile.TemporaryDirectory(prefix="vitasync-hm-") as tmp:
        vita_copy = Path(tmp) / "vita"
        ftp.download_dir(dump, vita_copy)
        source = store.snapshot(game.id, vita_copy, origin="vita")
        merged = hm.transfer((source.files / hm.SAVE_FILE).read_bytes(), pc_file.read_bytes())
        if steam_running():
            raise SyncError("Steam a été ouvert pendant le pull : rien n'a été écrit")
        backup = backup_pc_dir(store, game.id, pc_dir)
        new_file = Path(tmp) / hm.SAVE_FILE
        new_file.write_bytes(merged)
        copy_file(new_file, pc_file)
    return TransferResult(
        files=[hm.SAVE_FILE], source=source, backup=backup, automatic=dump_slot is not None
    )


def push(
    store: SaveStore,
    ftp: VitaFtpClient,
    steam: SteamConfig | None,
    game: GameManifest,
) -> TransferResult:
    """Copie la progression du PC dans la sauvegarde Vita.

    Args:
        store: Stockage des versions et des copies de sécurité.
        ftp: Connexion ouverte à la Vita.
        steam: Configuration Steam, ou ``None``.
        game: Fiche du jeu.

    Returns:
        Le résultat du transfert ; ``backup`` est la copie de la sauvegarde Vita.

    Raises:
        SyncError: Si une sauvegarde manque.
        SaveFormatError: Si une sauvegarde est illisible.
    """
    inbox = _vita_dir(game.vita.inbox, "inbox", game)
    pc_dir = resolve_pc_path(game.pc.path, steam)
    if not (pc_dir / hm.SAVE_FILE).is_file():
        raise SyncError(f"{pc_dir / hm.SAVE_FILE} introuvable : lance le jeu une fois sur PC")
    source = store.snapshot(game.id, pc_dir, origin="pc")
    dump, dump_slot = _fresh_dump(ftp, game)
    backup = backup_vita_dir(store, game.id, ftp, dump)
    if backup is None or not (backup.files / hm.SAVE_FILE).is_file():
        raise SyncError(f"{hm.SAVE_FILE} absent de {dump} : {BACKUP_HINT}")
    inbox_slot = _slot_number(inbox) if dump_slot is not None else None

    with tempfile.TemporaryDirectory(prefix="vitasync-hm-") as tmp:
        prepared = Path(tmp) / "vita"
        shutil.copytree(backup.files, prepared)
        merged = hm.transfer(
            (source.files / hm.SAVE_FILE).read_bytes(),
            (backup.files / hm.SAVE_FILE).read_bytes(),
        )
        (prepared / hm.SAVE_FILE).write_bytes(merged)
        backup_vita_dir(store, game.id, ftp, inbox)
        if ftp.dir_exists(inbox):
            ftp.remove_tree(inbox)
        ftp.upload_dir(prepared, inbox)
    if inbox_slot is not None:
        ftp.save_restore(game.vita.title_id, inbox_slot)
    return TransferResult(
        files=[hm.SAVE_FILE], source=source, backup=backup, automatic=inbox_slot is not None
    )
