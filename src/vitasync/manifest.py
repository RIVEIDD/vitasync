"""Fiches de jeu (manifestes YAML) : où trouver les sauvegardes de chaque jeu."""

from dataclasses import dataclass
from importlib import resources
from typing import Any

import yaml


class ManifestError(Exception):
    """Fiche de jeu absente ou invalide."""


@dataclass(frozen=True)
class PcSide:
    """Emplacement des sauvegardes côté PC.

    Attributes:
        path: Dossier des sauvegardes. Pour un jeu Steam, il est relatif au
            dossier ``Steam/userdata/<id>/`` de l'utilisateur.
        steam_appid: Identifiant Steam du jeu, ou ``None`` hors Steam.
    """

    path: str
    steam_appid: int | None = None


@dataclass(frozen=True)
class VitaSide:
    """Emplacement des sauvegardes côté Vita.

    Attributes:
        title_id: Identifiant du jeu sur la Vita, par exemple ``PCSB00245``.
        path: Dossier des sauvegardes, au format Vita (``ux0:...``). Vu par
            FTP, il est chiffré : on n'y lit ni n'y écrit directement.
        dump: Copie décryptée de la sauvegarde (slot de Save Manager rempli
            par *Backup*), lue par ``vitasync pull`` et ``vitasync push``.
        inbox: Dossier où ``vitasync push`` écrit une sauvegarde complète, à
            remettre en place avec *Restore* dans Save Manager.
    """

    title_id: str
    path: str
    dump: str | None = None
    inbox: str | None = None


@dataclass(frozen=True)
class GameManifest:
    """Description d'un jeu synchronisable.

    Attributes:
        id: Identifiant court utilisé en ligne de commande (``p4g``).
        name: Nom complet du jeu.
        adapter: Nom de l'adaptateur qui convertit les sauvegardes
            (``passthrough`` pour une copie directe).
        pc: Emplacement côté PC.
        vita: Emplacement côté Vita.
    """

    id: str
    name: str
    adapter: str
    pc: PcSide
    vita: VitaSide


def _require_str(data: dict[str, Any], key: str, where: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ManifestError(f"{where} : « {key} » doit être un texte non vide")
    return value


def _optional_str(data: dict[str, Any], key: str, where: str) -> str | None:
    if data.get(key) is None:
        return None
    return _require_str(data, key, where)


def _require_section(data: dict[str, Any], key: str, where: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ManifestError(f"{where} : section « {key} » manquante")
    return value


def parse_manifest(text: str, where: str = "fiche") -> GameManifest:
    """Analyse le contenu YAML d'une fiche de jeu.

    Args:
        text: Contenu YAML de la fiche.
        where: Nom de la fiche, repris dans les messages d'erreur.

    Returns:
        La fiche validée.

    Raises:
        ManifestError: Si le YAML est invalide ou qu'un champ manque.
    """
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ManifestError(f"{where} : YAML invalide ({exc})") from exc
    if not isinstance(data, dict):
        raise ManifestError(f"{where} : la fiche doit être un dictionnaire YAML")

    pc = _require_section(data, "pc", where)
    appid = pc.get("steam_appid")
    if appid is not None and (not isinstance(appid, int) or isinstance(appid, bool)):
        raise ManifestError(f"{where} : « steam_appid » doit être un entier")
    vita = _require_section(data, "vita", where)

    return GameManifest(
        id=_require_str(data, "id", where),
        name=_require_str(data, "name", where),
        adapter=_require_str(data, "adapter", where),
        pc=PcSide(path=_require_str(pc, "path", where), steam_appid=appid),
        vita=VitaSide(
            title_id=_require_str(vita, "title_id", where),
            path=_require_str(vita, "path", where),
            dump=_optional_str(vita, "dump", where),
            inbox=_optional_str(vita, "inbox", where),
        ),
    )


def builtin_manifests() -> dict[str, GameManifest]:
    """Charge les fiches livrées avec VitaSync (dossier ``vitasync/games``).

    Returns:
        Les fiches, indexées par identifiant de jeu.

    Raises:
        ManifestError: Si une fiche est invalide ou si deux fiches ont le même id.
    """
    manifests: dict[str, GameManifest] = {}
    for entry in sorted(resources.files("vitasync.games").iterdir(), key=lambda e: e.name):
        if not entry.name.endswith(".yaml"):
            continue
        manifest = parse_manifest(entry.read_text(encoding="utf-8"), where=entry.name)
        if manifest.id in manifests:
            raise ManifestError(f"{entry.name} : id « {manifest.id} » déjà utilisé")
        manifests[manifest.id] = manifest
    return manifests


def find_game(game_id: str) -> GameManifest:
    """Renvoie la fiche d'un jeu livré avec VitaSync.

    Args:
        game_id: Identifiant du jeu, par exemple ``p4g``.

    Returns:
        La fiche du jeu.

    Raises:
        ManifestError: Si aucun jeu ne porte cet identifiant.
    """
    manifests = builtin_manifests()
    try:
        return manifests[game_id]
    except KeyError:
        known = ", ".join(sorted(manifests)) or "aucun"
        raise ManifestError(f"Jeu inconnu : {game_id} (jeux connus : {known})") from None
