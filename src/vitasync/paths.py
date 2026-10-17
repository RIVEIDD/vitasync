"""Résolution des dossiers de sauvegarde côté PC indiqués dans les fiches de jeu."""

import os
import re
from pathlib import Path

from vitasync.config import SteamConfig

PLACEHOLDER = re.compile(r"\{(\w+)\}")


class PathError(Exception):
    """Chemin de fiche de jeu impossible à résoudre."""


def known_folders(steam: SteamConfig | None) -> dict[str, Path]:
    """Dossiers que les fiches de jeu peuvent utiliser entre accolades.

    Args:
        steam: Configuration Steam, pour ``{steam_userdata}`` ; ``None`` si absente.

    Returns:
        Les dossiers connus, par nom : ``documents``, ``appdata``,
        ``localappdata``, ``home`` et, si Steam est configuré, ``steam_userdata``.
    """
    home = Path.home()
    folders = {
        "home": home,
        "documents": home / "Documents",
        "appdata": Path(os.environ.get("APPDATA", home / "AppData" / "Roaming")),
        "localappdata": Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local")),
    }
    if steam is not None:
        folders["steam_userdata"] = steam.userdata
    return folders


def resolve_pc_path(path: str, steam: SteamConfig | None) -> Path:
    """Transforme le chemin PC d'une fiche de jeu en vrai dossier.

    Exemples : ``{steam_userdata}/1113000/remote`` ou
    ``{documents}/My Games/HotlineMiami``. Un chemin sans accolades reste,
    comme avant, relatif au dossier ``Steam/userdata/<id>``.

    Args:
        path: Chemin tel qu'écrit dans la fiche.
        steam: Configuration Steam, ou ``None`` si absente.

    Returns:
        Le dossier correspondant sur ce PC.

    Raises:
        PathError: Si un nom entre accolades est inconnu, ou si le chemin a
            besoin de Steam alors qu'il n'est pas configuré.
    """
    folders = known_folders(steam)
    if not PLACEHOLDER.search(path):
        path = "{steam_userdata}/" + path

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in folders:
            if name == "steam_userdata":
                raise PathError("Ce jeu a besoin de la section [steam] de la configuration")
            raise PathError(f"Dossier inconnu dans la fiche : {{{name}}}")
        return folders[name].as_posix()

    return Path(PLACEHOLDER.sub(replace, path))
