"""Chargement de la configuration de VitaSync."""

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PORT = 1337
"""Port FTP par défaut de VitaShell."""

DEFAULT_TIMEOUT = 10.0
"""Délai d'attente réseau par défaut, en secondes."""


class ConfigError(Exception):
    """Configuration absente ou invalide."""


@dataclass(frozen=True)
class VitaConfig:
    """Paramètres de connexion au serveur FTP de VitaShell.

    Attributes:
        host: Adresse IP ou nom d'hôte de la Vita.
        port: Port FTP affiché par VitaShell.
        timeout: Délai d'attente réseau, en secondes.
    """

    host: str
    port: int = DEFAULT_PORT
    timeout: float = DEFAULT_TIMEOUT


def default_config_path() -> Path:
    """Renvoie l'emplacement par défaut du fichier de configuration.

    Returns:
        ``%APPDATA%/vitasync/config.toml`` sous Windows,
        ``~/.config/vitasync/config.toml`` ailleurs.
    """
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / ".config"
    return base / "vitasync" / "config.toml"


def load_config(path: Path) -> VitaConfig:
    """Lit la section ``[vita]`` d'un fichier de configuration TOML.

    Exemple de fichier::

        [vita]
        host = "192.168.1.42"
        port = 1337

    Args:
        path: Chemin du fichier TOML.

    Returns:
        La configuration de connexion à la Vita.

    Raises:
        ConfigError: Si le fichier est absent, illisible ou invalide.
    """
    vita = _read_toml(path).get("vita")
    if not isinstance(vita, dict):
        raise ConfigError(f"Section [vita] manquante dans {path}")
    return _parse_vita(vita)


@dataclass(frozen=True)
class SteamConfig:
    """Emplacements côté PC.

    Attributes:
        userdata: Dossier ``Steam/userdata/<id>`` du compte Steam.
        p4g_saveconv: Dossier de l'outil p4g-saveconv, ou ``None`` s'il n'est
            pas configuré.
    """

    userdata: Path
    p4g_saveconv: Path | None = None


def load_steam_config(path: Path) -> SteamConfig:
    """Lit la section ``[steam]`` d'un fichier de configuration TOML.

    Exemple de fichier::

        [steam]
        userdata = 'C:/Program Files (x86)/Steam/userdata/125320760'
        p4g_saveconv = 'F:/Projets/VitaPcSynchro/outils/p4g-saveconv'

    Args:
        path: Chemin du fichier TOML.

    Returns:
        Les emplacements côté PC.

    Raises:
        ConfigError: Si le fichier est absent, illisible ou invalide.
    """
    steam = _read_toml(path).get("steam")
    if not isinstance(steam, dict):
        raise ConfigError(f"Section [steam] manquante dans {path}")
    userdata = steam.get("userdata")
    if not isinstance(userdata, str) or not userdata:
        raise ConfigError("[steam] userdata doit être un chemin non vide")
    saveconv = steam.get("p4g_saveconv")
    if saveconv is not None and (not isinstance(saveconv, str) or not saveconv):
        raise ConfigError("[steam] p4g_saveconv doit être un chemin non vide")
    return SteamConfig(
        userdata=Path(userdata),
        p4g_saveconv=Path(saveconv) if saveconv else None,
    )


def _read_toml(path: Path) -> dict[str, object]:
    try:
        with path.open("rb") as file:
            return tomllib.load(file)
    except FileNotFoundError as exc:
        raise ConfigError(f"Fichier de configuration introuvable : {path}") from exc
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"Fichier de configuration illisible : {path} ({exc})") from exc


def _parse_vita(vita: dict[str, object]) -> VitaConfig:
    host = vita.get("host")
    if not isinstance(host, str) or not host:
        raise ConfigError("[vita] host doit être une adresse non vide")

    port = vita.get("port", DEFAULT_PORT)
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise ConfigError("[vita] port doit être un entier entre 1 et 65535")

    timeout = vita.get("timeout", DEFAULT_TIMEOUT)
    if not isinstance(timeout, int | float) or isinstance(timeout, bool) or timeout <= 0:
        raise ConfigError("[vita] timeout doit être un nombre positif")

    return VitaConfig(host=host, port=port, timeout=float(timeout))
