"""Transferts de Persona 4 Golden entre la Vita et Steam (``pull`` et ``push``)."""

import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from vitasync import p4g
from vitasync.config import SteamConfig
from vitasync.ftp import VitaFtpClient
from vitasync.manifest import GameManifest
from vitasync.safety import backup_pc_dir, backup_vita_dir, copy_file
from vitasync.steam import is_steam_running
from vitasync.store import SaveStore, SaveVersion

BACKUP_HINT = "fais d'abord un Backup de la sauvegarde vers le slot 0 dans Save Manager"


class SyncError(Exception):
    """Un transfert ne peut pas avoir lieu sans risque."""


@dataclass(frozen=True)
class TransferResult:
    """Ce qu'un transfert a fait.

    Attributes:
        files: Noms des ``.bin`` transférés.
        source: Version enregistrée de la sauvegarde d'origine.
        backup: Copie de sécurité de la destination, ou ``None`` si elle
            n'existait pas encore.
    """

    files: list[str]
    source: SaveVersion
    backup: SaveVersion | None


def _saveconv(steam: SteamConfig) -> Path:
    if steam.p4g_saveconv is None:
        raise SyncError("p4g-saveconv non configuré : ajoute p4g_saveconv dans [steam]")
    return steam.p4g_saveconv


def _vita_dir(value: str | None, key: str, game: GameManifest) -> str:
    if value is None:
        raise SyncError(f"La fiche {game.id} n'indique pas de dossier vita.{key}")
    return value


def pull(
    store: SaveStore,
    ftp: VitaFtpClient,
    steam: SteamConfig,
    game: GameManifest,
    slots: list[int],
    steam_running: Callable[[], bool] | None = None,
) -> TransferResult:
    """Copie des slots de la Vita vers Steam.

    Étapes : télécharger la copie décryptée (``vita.dump``) et l'enregistrer,
    la convertir au format PC, copier tout le dossier Steam du jeu dans le
    stockage, puis écrire uniquement les slots demandés et régénérer
    ``remotecache.vdf``.

    Args:
        store: Stockage des versions et des copies de sécurité.
        ftp: Connexion ouverte à la Vita.
        steam: Emplacements côté PC.
        game: Fiche du jeu.
        slots: Numéros des slots à copier.
        steam_running: Détection de Steam, remplaçable dans les tests
            (``None`` : :func:`vitasync.steam.is_steam_running`).

    Returns:
        Le résultat du transfert.

    Raises:
        SyncError: Si Steam est ouvert, si la configuration est incomplète ou
            si la copie décryptée est absente.
        ConversionError: Si la conversion échoue.
        TransferError: Si le téléchargement échoue.
    """
    steam_running = steam_running or is_steam_running
    if steam_running():
        raise SyncError("Steam est ouvert : ferme-le complètement avant un pull")
    saveconv = _saveconv(steam)
    dump = _vita_dir(game.vita.dump, "dump", game)
    remote = steam.userdata / game.pc.path
    app_dir = remote.parent

    if not ftp.dir_exists(dump):
        raise SyncError(f"{dump} introuvable sur la Vita : {BACKUP_HINT}")
    with tempfile.TemporaryDirectory(prefix="vitasync-pull-") as tmp:
        vita_copy = Path(tmp) / "vita"
        ftp.download_dir(dump, vita_copy)
        source = store.snapshot(game.id, vita_copy, origin="vita")
        converted = Path(tmp) / "pc"
        files = p4g.vita_to_pc(saveconv, source.files, converted, slots)

        if steam_running():
            raise SyncError("Steam a été ouvert pendant le pull : rien n'a été écrit")
        backup = backup_pc_dir(store, game.id, app_dir)
        for file in sorted(converted.iterdir()):
            copy_file(file, remote / file.name)
    p4g.write_remotecache(remote, app_dir / "remotecache.vdf")
    return TransferResult(files=files, source=source, backup=backup)


def push(
    store: SaveStore,
    ftp: VitaFtpClient,
    steam: SteamConfig,
    game: GameManifest,
    slots: list[int],
) -> TransferResult:
    """Prépare pour la Vita une sauvegarde complète, dans le dossier ``vita.inbox``.

    Étapes : enregistrer le dossier Steam, télécharger la copie décryptée
    actuelle de la Vita (``vita.dump``) comme copie de sécurité, partir de
    cette copie et y remplacer uniquement les slots demandés (``.bin`` et
    entrées de ``sdslot.dat``), puis vider et remplir ``vita.inbox``. Il
    reste à restaurer ce dossier avec Save Manager.

    Args:
        store: Stockage des versions et des copies de sécurité.
        ftp: Connexion ouverte à la Vita.
        steam: Emplacements côté PC.
        game: Fiche du jeu.
        slots: Numéros des slots à envoyer.

    Returns:
        Le résultat du transfert ; ``backup`` est la copie de la sauvegarde Vita.

    Raises:
        SyncError: Si la configuration est incomplète, ou si la copie
            décryptée de la Vita est absente (pas de copie de sécurité possible).
        ConversionError: Si la conversion échoue.
        TransferError: Si un transfert échoue.
    """
    saveconv = _saveconv(steam)
    dump = _vita_dir(game.vita.dump, "dump", game)
    inbox = _vita_dir(game.vita.inbox, "inbox", game)
    remote = steam.userdata / game.pc.path
    if not remote.is_dir():
        raise SyncError(f"Dossier Steam introuvable : {remote}")

    source = store.snapshot(game.id, remote, origin="pc")
    backup = backup_vita_dir(store, game.id, ftp, dump)
    if backup is None:
        raise SyncError(
            f"{dump} introuvable sur la Vita : {BACKUP_HINT}, pour garder une copie "
            "de la sauvegarde Vita avant de la remplacer"
        )
    sdslot = backup.files / p4g.SDSLOT
    if not sdslot.is_file():
        raise SyncError(f"{p4g.SDSLOT.as_posix()} manquant dans {dump} : la copie est incomplète")

    with tempfile.TemporaryDirectory(prefix="vitasync-push-") as tmp:
        # Sauvegarde complète : la copie actuelle de la Vita (param.sfo, clés...),
        # dans laquelle on ne remplace que les slots demandés.
        converted = Path(tmp) / "vita"
        shutil.copytree(backup.files, converted)
        files = p4g.pc_to_vita(saveconv, source.files, converted, slots, sdslot.read_bytes())
        backup_vita_dir(store, game.id, ftp, inbox)
        if ftp.dir_exists(inbox):
            ftp.remove_tree(inbox)
        ftp.upload_dir(converted, inbox)
    return TransferResult(files=files, source=source, backup=backup)
