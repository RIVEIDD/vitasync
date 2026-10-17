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
    try:
        with path.open("rb") as file:
            data = tomllib.load(file)
    except FileNotFoundError as exc:
        raise ConfigError(f"Fichier de configuration introuvable : {path}") from exc
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"Fichier de configuration illisible : {path} ({exc})") from exc

    vita = data.get("vita")
    if not isinstance(vita, dict):
        raise ConfigError(f"Section [vita] manquante dans {path}")

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
