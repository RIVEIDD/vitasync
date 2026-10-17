"""Transferts de Persona 4 Golden entre la Vita et Steam (``pull`` et ``push``)."""

import re
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from vitasync import p4g
from vitasync.config import SteamConfig
from vitasync.ftp import VitaFtpClient
from vitasync.manifest import GameManifest
from vitasync.paths import resolve_pc_path
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
        automatic: ``True`` si l'appli VitaSync a fait elle-même le Backup
            (``pull``) ou le Restore (``push``) sur la Vita.
    """

    files: list[str]
    source: SaveVersion
    backup: SaveVersion | None
    automatic: bool = False


def _saveconv(steam: SteamConfig) -> Path:
    if steam.p4g_saveconv is None:
        raise SyncError("p4g-saveconv non configuré : ajoute p4g_saveconv dans [steam]")
    return steam.p4g_saveconv


def _vita_dir(value: str | None, key: str, game: GameManifest) -> str:
    if value is None:
        raise SyncError(f"La fiche {game.id} n'indique pas de dossier vita.{key}")
    return value


def _slot_number(path: str) -> int | None:
    match = re.search(r"SLOT(\d)$", path.rstrip("/"))
    return int(match.group(1)) if match else None


def _app_slot(ftp: VitaFtpClient, path: str) -> int | None:
    """Slot de Save Manager à piloter, si l'appli VitaSync est au bout du FTP."""
    slot = _slot_number(path)
    if slot is None or not ftp.is_vitasync_app():
        return None
    return slot


def pull(
    store: SaveStore,
    ftp: VitaFtpClient,
    steam: SteamConfig,
    game: GameManifest,
    slots: list[int],
    steam_running: Callable[[], bool] | None = None,
) -> TransferResult:
    """Copie des slots de la Vita vers Steam.

    Si l'appli VitaSync est ouverte sur la Vita, elle fait d'abord elle-même
    le Backup de la sauvegarde vers ``vita.dump``. Étapes suivantes :
    télécharger la copie décryptée (``vita.dump``) et l'enregistrer,
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
    remote = resolve_pc_path(game.pc.path, steam)
    app_dir = remote.parent

    dump_slot = _app_slot(ftp, dump)
    if dump_slot is not None:
        ftp.save_backup(game.vita.title_id, dump_slot)
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
    return TransferResult(
        files=files, source=source, backup=backup, automatic=dump_slot is not None
    )


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
    entrées de ``sdslot.dat``), puis vider et remplir ``vita.inbox``.

    Si l'appli VitaSync est ouverte sur la Vita, elle fait elle-même le Backup
    vers ``vita.dump`` au début et le Restore de ``vita.inbox`` à la fin.
    Sinon, il reste à faire ce Restore avec Save Manager.

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
    remote = resolve_pc_path(game.pc.path, steam)
    if not remote.is_dir():
        raise SyncError(f"Dossier Steam introuvable : {remote}")

    source = store.snapshot(game.id, remote, origin="pc")
    dump_slot = _app_slot(ftp, dump)
    inbox_slot = _slot_number(inbox) if dump_slot is not None else None
    if dump_slot is not None:
        ftp.save_backup(game.vita.title_id, dump_slot)
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
    if inbox_slot is not None:
        ftp.save_restore(game.vita.title_id, inbox_slot)
    return TransferResult(
        files=files, source=source, backup=backup, automatic=inbox_slot is not None
    )


@dataclass(frozen=True)
class SlotState:
    """Avancement d'un slot de chaque côté.

    Attributes:
        slot: Numéro du slot (1 à 16).
        pc: Temps de jeu côté Steam en secondes, ou ``None`` si le slot est vide.
        vita: Temps de jeu côté Vita en secondes, ou ``None`` si le slot est vide.
    """

    slot: int
    pc: int | None
    vita: int | None

    @property
    def newer(self) -> str:
        """``pc``, ``vita`` ou ``same`` selon le côté le plus avancé."""
        if self.pc == self.vita:
            return "same"
        if self.vita is None or (self.pc is not None and self.pc > self.vita):
            return "pc"
        return "vita"


def status(ftp: VitaFtpClient, steam: SteamConfig, game: GameManifest) -> list[SlotState]:
    """Compare le temps de jeu de chaque slot entre Steam et la Vita.

    Le temps de jeu ne fait qu'augmenter au fil d'une partie : le côté qui en
    a le plus est le plus récent. Les dates des fichiers ne servent pas,
    l'horloge de la Vita n'étant pas fiable. Avec l'appli VitaSync, la copie
    du slot 0 est d'abord rafraîchie par un Backup.

    Args:
        ftp: Connexion ouverte à la Vita.
        steam: Emplacements côté PC.
        game: Fiche du jeu.

    Returns:
        Un état par slot présent d'un côté ou de l'autre, trié par numéro.

    Raises:
        SyncError: Si la copie décryptée de la Vita est absente.
        TransferError: Si le téléchargement échoue.
    """
    dump = _vita_dir(game.vita.dump, "dump", game)
    dump_slot = _app_slot(ftp, dump)
    if dump_slot is not None:
        ftp.save_backup(game.vita.title_id, dump_slot)
    if not ftp.dir_exists(dump):
        raise SyncError(f"{dump} introuvable sur la Vita : {BACKUP_HINT}")
    with tempfile.TemporaryDirectory(prefix="vitasync-status-") as tmp:
        sdslot = Path(tmp) / "sdslot.dat"
        ftp.download_file(f"{dump.rstrip('/')}/{p4g.SDSLOT.as_posix()}", sdslot)
        vita = p4g.vita_play_times(sdslot.read_bytes())
    pc = p4g.pc_play_times(resolve_pc_path(game.pc.path, steam))
    return [
        SlotState(slot, pc.get(slot), vita.get(slot)) for slot in sorted(pc.keys() | vita.keys())
    ]


def plan_sync(states: list[SlotState]) -> tuple[str | None, list[int]]:
    """Choisit le sens de la synchronisation et les slots à copier.

    Args:
        states: Résultat de :func:`status`.

    Returns:
        ``("push", slots)`` si seul le PC a des slots plus avancés,
        ``("pull", slots)`` si seule la Vita en a, ``(None, [])`` si tout est
        déjà identique.

    Raises:
        SyncError: Si certains slots sont plus avancés sur PC et d'autres sur
            la Vita : c'est à l'utilisateur de trancher.
    """
    pc = [state.slot for state in states if state.newer == "pc"]
    vita = [state.slot for state in states if state.newer == "vita"]
    if pc and vita:
        raise SyncError(
            "Conflit : slots plus avancés sur PC "
            f"({', '.join(map(str, pc))}) et sur Vita ({', '.join(map(str, vita))}). "
            f"Choisis toi-même : vitasync push --slots {','.join(map(str, pc))} "
            f"et/ou vitasync pull --slots {','.join(map(str, vita))}"
        )
    if pc:
        return "push", pc
    if vita:
        return "pull", vita
    return None, []
