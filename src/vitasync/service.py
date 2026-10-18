"""Actions de haut niveau partagées par la ligne de commande et la fenêtre.

``cli.py`` et ``gui.py`` ne parlent qu'à ce module : il choisit le bon
module de jeu (``p4g_sync`` ou ``hotline_miami_sync``), décide du sens d'une
synchronisation et rédige les messages pour l'utilisateur.
"""

from dataclasses import dataclass, replace
from pathlib import Path

from vitasync import hotline_miami_sync, p4g_sync
from vitasync.config import (
    ConfigError,
    SteamConfig,
    VitaConfig,
    default_config_path,
    load_config,
    load_steam_config,
)
from vitasync.ftp import FtpError, VitaFtpClient
from vitasync.hotline_miami import SaveFormatError
from vitasync.manifest import GameManifest, ManifestError
from vitasync.p4g import ConversionError
from vitasync.p4g_sync import SlotState, SyncError, TransferResult
from vitasync.store import LocalStore, StoreError, default_store_path

USER_ERRORS = (
    SaveFormatError,
    ValueError,
    ManifestError,
    StoreError,
    ConfigError,
    FtpError,
    ConversionError,
    SyncError,
    OSError,
)
"""Erreurs prévues, à montrer telles quelles à l'utilisateur (sans trace Python)."""

SUPPORTED_ADAPTERS = ("p4g", "hotline_miami")


@dataclass(frozen=True)
class Session:
    """Tout ce qu'il faut pour travailler : Vita, Steam et stockage.

    Attributes:
        vita: Connexion à la Vita.
        steam: Emplacements Steam, ou ``None`` si la section ``[steam]`` manque.
        store: Stockage des versions et des copies de sécurité.
    """

    vita: VitaConfig
    steam: SteamConfig | None
    store: LocalStore


def open_session(
    config_path: Path | None = None,
    host: str | None = None,
    port: int | None = None,
    store_path: Path | None = None,
) -> Session:
    """Lit la configuration et prépare une session.

    Args:
        config_path: Fichier de configuration, ou ``None`` pour celui par défaut.
        host: Adresse de la Vita qui remplace celle du fichier.
        port: Port qui remplace celui du fichier.
        store_path: Dossier du stockage, ou ``None`` pour celui par défaut.

    Returns:
        La session.

    Raises:
        ConfigError: Si la Vita n'est configurée ni par ``host`` ni par le fichier.
    """
    path = config_path or default_config_path()
    vita = VitaConfig(host=host) if host else load_config(path)
    if port is not None:
        vita = replace(vita, port=port)
    try:
        steam: SteamConfig | None = load_steam_config(path)
    except ConfigError:
        steam = None
    return Session(vita=vita, steam=steam, store=LocalStore(store_path or default_store_path()))


def check_supported(game: GameManifest) -> None:
    """Vérifie que VitaSync sait synchroniser ce jeu.

    Raises:
        SyncError: Si l'adaptateur du jeu n'est pas encore pris en charge.
    """
    if game.adapter not in SUPPORTED_ADAPTERS:
        raise SyncError(f"{game.name} : adaptateur {game.adapter} pas encore pris en charge")


def _steam_for(session: Session, game: GameManifest) -> SteamConfig:
    if session.steam is None:
        raise SyncError(f"{game.name} a besoin de la section [steam] de la configuration")
    return session.steam


@dataclass(frozen=True)
class GameStatus:
    """État d'un jeu et synchronisation proposée.

    Attributes:
        game: Fiche du jeu.
        states: Avancement de chaque slot.
        in_levels: ``True`` si l'avancement se compte en niveaux (Hotline
            Miami), ``False`` s'il s'agit d'un temps de jeu en secondes (P4G).
        direction: ``"pull"``, ``"push"`` ou ``None`` si rien à faire ou conflit.
        slots: Slots à copier dans ce sens.
        conflict: Explication du conflit, ou ``None``.
    """

    game: GameManifest
    states: list[SlotState]
    in_levels: bool
    direction: str | None
    slots: list[int]
    conflict: str | None = None

    @property
    def summary(self) -> str:
        """Résumé d'une ligne : ce qu'il faut faire pour ce jeu."""
        if self.conflict is not None:
            return "Conflit : à trancher à la main"
        if self.direction is None:
            return "Identiques"
        return "Plus avancé sur PC" if self.direction == "push" else "Plus avancé sur Vita"


def game_status(session: Session, ftp: VitaFtpClient, game: GameManifest) -> GameStatus:
    """Compare l'avancement du jeu des deux côtés et propose un sens.

    Args:
        session: Session en cours.
        ftp: Connexion ouverte à la Vita.
        game: Fiche du jeu.

    Returns:
        L'état du jeu. Un conflit n'est pas une erreur : il est décrit dans
        ``conflict``.
    """
    check_supported(game)
    if game.adapter == "p4g":
        states = p4g_sync.status(ftp, _steam_for(session, game), game)
    else:
        states = hotline_miami_sync.status(ftp, session.steam, game)
    in_levels = game.adapter == "hotline_miami"
    try:
        direction, slots = p4g_sync.plan_sync(states)
    except SyncError as exc:
        return GameStatus(game, states, in_levels, None, [], conflict=str(exc))
    return GameStatus(game, states, in_levels, direction, slots)


def transfer(
    session: Session,
    ftp: VitaFtpClient,
    game: GameManifest,
    direction: str,
    slots: list[int],
) -> TransferResult:
    """Lance un ``pull`` (Vita vers PC) ou un ``push`` (PC vers Vita).

    Args:
        session: Session en cours.
        ftp: Connexion ouverte à la Vita.
        game: Fiche du jeu.
        direction: ``"pull"`` ou ``"push"``.
        slots: Slots à copier (P4G seulement).

    Returns:
        Le résultat du transfert.
    """
    check_supported(game)
    if game.adapter == "p4g":
        steam = _steam_for(session, game)
        if direction == "pull":
            return p4g_sync.pull(session.store, ftp, steam, game, slots)
        return p4g_sync.push(session.store, ftp, steam, game, slots)
    if direction == "pull":
        return hotline_miami_sync.pull(session.store, ftp, session.steam, game)
    return hotline_miami_sync.push(session.store, ftp, session.steam, game)


def describe_plan(status: GameStatus) -> str:
    """Annonce le sens choisi par ``sync`` (``Plus avancé sur PC : push des slots 7.``)."""
    where = "PC" if status.direction == "push" else "Vita"
    detail = "" if status.in_levels else f" des slots {','.join(map(str, status.slots))}"
    return f"Plus avancé sur {where} : {status.direction}{detail}."


def describe_result(game: GameManifest, direction: str, result: TransferResult) -> list[str]:
    """Rédige le compte rendu d'un transfert, une phrase par ligne.

    Args:
        game: Fiche du jeu.
        direction: ``"pull"`` ou ``"push"``.
        result: Résultat du transfert.

    Returns:
        Les lignes à afficher.
    """
    files = ", ".join(result.files)
    lines = [f"Version d'origine enregistrée : {result.source.id}"]
    if result.backup is not None:
        lines.append(f"Copie de sécurité de la destination : {result.backup.id}")
    if direction == "pull":
        if result.automatic:
            lines.append("Backup fait par l'appli VitaSync sur la Vita.")
        if game.adapter == "p4g":
            lines.append(f"Copié dans Steam : {files} (+ .binslot), remotecache.vdf régénéré.")
        else:
            lines.append(f"Copié sur le PC : {files}.")
    elif result.automatic:
        lines.append(f"Restauré sur la Vita par l'appli VitaSync (slots remplacés : {files}).")
    else:
        slot = (game.vita.inbox or "").rstrip("/").rsplit("/", 1)[-1]
        lines.append(
            f"Sauvegarde complète prête dans {game.vita.inbox} (slots remplacés : {files})"
        )
        lines.append(f"Dans Save Manager : {game.name} > {slot} > Restore.")
    return lines
