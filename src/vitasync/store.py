"""Stockage versionné des sauvegardes de jeu."""

import json
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

VERSION_FORMAT = "%Y%m%d-%H%M%S-%f"
"""Format des identifiants de version : date et heure UTC du PC, à la microseconde."""

META_FILE = "version.json"
FILES_DIR = "files"


class StoreError(Exception):
    """Erreur de base du stockage des sauvegardes."""


class VersionNotFoundError(StoreError):
    """La version demandée n'existe pas pour ce jeu."""


class VersionConflictError(StoreError):
    """La version courante n'est pas celle attendue : quelqu'un a écrit entre-temps."""


@dataclass(frozen=True)
class SaveVersion:
    """Une version enregistrée de la sauvegarde d'un jeu.

    Attributes:
        game_id: Identifiant du jeu.
        id: Identifiant de la version, dérivé de l'horloge du PC.
        created_at: Date de création (UTC, horloge du PC, jamais celle de la Vita).
        origin: Provenance, par exemple ``pc``, ``vita`` ou ``backup-pc``.
        files: Dossier qui contient les fichiers de la sauvegarde.
    """

    game_id: str
    id: str
    created_at: datetime
    origin: str
    files: Path


class SaveStore(Protocol):
    """Ce que doit savoir faire tout stockage de sauvegardes."""

    def get(self, game_id: str, version_id: str | None = None) -> SaveVersion:
        """Renvoie une version précise, ou la plus récente si ``version_id`` est ``None``."""
        ...

    def put(self, game_id: str, source: Path, origin: str, expected: str | None) -> SaveVersion:
        """Enregistre une nouvelle version si la version courante est ``expected``."""
        ...

    def snapshot(self, game_id: str, source: Path, origin: str) -> SaveVersion:
        """Enregistre une nouvelle version sans condition (copie de sécurité)."""
        ...

    def history(self, game_id: str) -> list[SaveVersion]:
        """Renvoie toutes les versions, de la plus ancienne à la plus récente."""
        ...


def default_store_path() -> Path:
    """Renvoie l'emplacement par défaut du stockage local.

    Returns:
        ``%LOCALAPPDATA%/vitasync/store`` sous Windows,
        ``~/.local/share/vitasync/store`` ailleurs.
    """
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if local else Path.home() / ".local" / "share"
    return base / "vitasync" / "store"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _version_order(version_dir: Path) -> tuple[str, int]:
    """Clé de tri : la date, puis le suffixe -2, -3... (pour que -10 vienne après -9)."""
    parts = version_dir.name.split("-")
    counter = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1
    return "-".join(parts[:3]), counter


class LocalStore:
    """Stockage sur le disque du PC, un dossier par version.

    Organisation sur le disque::

        <racine>/<jeu>/<version>/version.json   métadonnées
        <racine>/<jeu>/<version>/files/...      copie des fichiers

    Une version n'est jamais modifiée ni supprimée après sa création.
    """

    def __init__(self, root: Path, clock: Callable[[], datetime] = _utc_now) -> None:
        """Prépare le stockage, sans rien créer sur le disque.

        Args:
            root: Dossier racine du stockage.
            clock: Horloge du PC, remplaçable dans les tests. Doit renvoyer
                une date avec fuseau horaire.
        """
        self.root = root
        self._clock = clock

    def _game_dir(self, game_id: str) -> Path:
        return self.root / game_id

    def _read(self, game_id: str, version_dir: Path) -> SaveVersion:
        meta = json.loads((version_dir / META_FILE).read_text(encoding="utf-8"))
        return SaveVersion(
            game_id=game_id,
            id=version_dir.name,
            created_at=datetime.fromisoformat(meta["created_at"]),
            origin=meta["origin"],
            files=version_dir / FILES_DIR,
        )

    def history(self, game_id: str) -> list[SaveVersion]:
        """Renvoie toutes les versions d'un jeu, de la plus ancienne à la plus récente.

        Args:
            game_id: Identifiant du jeu.

        Returns:
            Les versions complètes (les copies interrompues sont ignorées).
        """
        game_dir = self._game_dir(game_id)
        if not game_dir.is_dir():
            return []
        dirs = sorted(
            (
                d
                for d in game_dir.iterdir()
                if not d.name.startswith(".") and (d / META_FILE).is_file()
            ),
            key=_version_order,
        )
        return [self._read(game_id, d) for d in dirs]

    def get(self, game_id: str, version_id: str | None = None) -> SaveVersion:
        """Renvoie une version d'un jeu.

        Args:
            game_id: Identifiant du jeu.
            version_id: Version voulue, ou ``None`` pour la plus récente.

        Returns:
            La version demandée.

        Raises:
            VersionNotFoundError: Si le jeu n'a aucune version, ou pas celle-ci.
        """
        versions = self.history(game_id)
        if not versions:
            raise VersionNotFoundError(f"Aucune version enregistrée pour {game_id}")
        if version_id is None:
            return versions[-1]
        for version in versions:
            if version.id == version_id:
                return version
        raise VersionNotFoundError(f"Version {version_id} introuvable pour {game_id}")

    def current_id(self, game_id: str) -> str | None:
        """Renvoie l'identifiant de la version la plus récente.

        Args:
            game_id: Identifiant du jeu.

        Returns:
            L'identifiant, ou ``None`` si le jeu n'a encore aucune version.
        """
        versions = self.history(game_id)
        return versions[-1].id if versions else None

    def put(self, game_id: str, source: Path, origin: str, expected: str | None) -> SaveVersion:
        """Enregistre une nouvelle version, seulement si personne n'a écrit entre-temps.

        Args:
            game_id: Identifiant du jeu.
            source: Dossier à copier dans la nouvelle version.
            origin: Provenance de la sauvegarde (``pc``, ``vita``...).
            expected: Version courante attendue, ou ``None`` si le jeu ne doit
                encore avoir aucune version.

        Returns:
            La version créée.

        Raises:
            VersionConflictError: Si la version courante n'est pas ``expected``.
        """
        current = self.current_id(game_id)
        if current != expected:
            raise VersionConflictError(
                f"{game_id} : version courante {current}, attendue {expected}"
            )
        return self.snapshot(game_id, source, origin)

    def snapshot(self, game_id: str, source: Path, origin: str) -> SaveVersion:
        """Enregistre une nouvelle version sans vérifier la version courante.

        La copie est faite dans un dossier temporaire, puis renommée : une
        copie interrompue n'apparaît jamais dans l'historique.

        Args:
            game_id: Identifiant du jeu.
            source: Dossier à copier.
            origin: Provenance de la sauvegarde (``backup-pc``, ``backup-vita``...).

        Returns:
            La version créée.

        Raises:
            StoreError: Si ``source`` n'est pas un dossier.
        """
        if not source.is_dir():
            raise StoreError(f"Dossier à sauvegarder introuvable : {source}")
        game_dir = self._game_dir(game_id)
        game_dir.mkdir(parents=True, exist_ok=True)

        created_at = self._clock()
        base_id = created_at.astimezone(UTC).strftime(VERSION_FORMAT)
        version_id, counter = base_id, 1
        while (game_dir / version_id).exists():
            # Deux copies dans la même microseconde : suffixe -2, -3...
            counter += 1
            version_id = f"{base_id}-{counter}"

        tmp_dir = game_dir / f".tmp-{version_id}"
        shutil.rmtree(tmp_dir, ignore_errors=True)
        try:
            shutil.copytree(source, tmp_dir / FILES_DIR)
            meta = {"created_at": created_at.isoformat(), "origin": origin}
            (tmp_dir / META_FILE).write_text(json.dumps(meta, indent=2), encoding="utf-8")
            tmp_dir.rename(game_dir / version_id)
        except BaseException:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise
        return self._read(game_id, game_dir / version_id)
