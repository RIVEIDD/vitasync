"""Client FTP pour le serveur intégré à VitaShell."""

import ftplib
import posixpath
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Self

from vitasync.config import VitaConfig


class FtpError(Exception):
    """Erreur de base des échanges FTP avec la Vita."""


class VitaUnreachableError(FtpError):
    """La Vita ne répond pas (FTP de VitaShell non lancé, mauvaise IP, Wi-Fi coupé)."""


class TransferError(FtpError):
    """Une commande ou un transfert FTP a échoué en cours de route."""


@dataclass(frozen=True)
class RemoteEntry:
    """Entrée d'un dossier distant.

    Attributes:
        name: Nom du fichier ou du dossier.
        is_dir: ``True`` pour un dossier.
        size: Taille en octets (0 pour un dossier).
    """

    name: str
    is_dir: bool
    size: int


def to_ftp_path(path: str) -> str:
    """Convertit un chemin Vita en chemin FTP de VitaShell.

    VitaShell expose chaque partition comme un dossier de la racine :
    ``ux0:data/p4g_dump`` devient ``/ux0:/data/p4g_dump``. Un chemin qui
    commence déjà par ``/`` est renvoyé tel quel.

    Args:
        path: Chemin au format Vita (``ux0:data``) ou FTP (``/ux0:/data``).

    Returns:
        Le chemin FTP absolu correspondant.
    """
    if path.startswith("/"):
        return path
    device, sep, rest = path.partition(":")
    if not sep:
        return "/" + path
    return posixpath.join(f"/{device}:", rest.lstrip("/"))


def parse_list_line(line: str) -> RemoteEntry | None:
    """Analyse une ligne de réponse ``LIST`` au format Unix.

    Args:
        line: Ligne du type ``drwxrwxrwx 1 vita vita 0 Jan 01 00:00 nom``.

    Returns:
        L'entrée décrite, ou ``None`` pour une ligne vide ou ``.``/``..``.
    """
    parts = line.split(None, 8)
    if len(parts) < 9:
        return None
    name = parts[8]
    if name in (".", ".."):
        return None
    is_dir = parts[0].startswith("d")
    size = int(parts[4]) if not is_dir and parts[4].isdigit() else 0
    return RemoteEntry(name=name, is_dir=is_dir, size=size)


class VitaFtpClient:
    """Connexion FTP à VitaShell, à utiliser comme gestionnaire de contexte.

    Example::

        with VitaFtpClient(VitaConfig(host="192.168.1.42")) as ftp:
            entries = ftp.list_dir("ux0:data")
    """

    def __init__(self, config: VitaConfig) -> None:
        """Prépare le client sans ouvrir la connexion.

        Args:
            config: Paramètres de connexion à la Vita.
        """
        self._config = config
        self._ftp: ftplib.FTP | None = None

    def connect(self) -> None:
        """Ouvre la connexion et s'authentifie en anonyme.

        Raises:
            VitaUnreachableError: Si la Vita ne répond pas.
        """
        ftp = ftplib.FTP(timeout=self._config.timeout)
        try:
            ftp.connect(self._config.host, self._config.port)
            ftp.login()
        except ftplib.all_errors as exc:
            ftp.close()
            raise VitaUnreachableError(
                f"Vita injoignable sur {self._config.host}:{self._config.port} ({exc}). "
                "Vérifie que le FTP de VitaShell est lancé (Select) et l'adresse IP."
            ) from exc
        self._ftp = ftp

    def close(self) -> None:
        """Ferme la connexion, même si la Vita ne répond plus."""
        if self._ftp is None:
            return
        try:
            self._ftp.quit()
        except ftplib.all_errors:
            self._ftp.close()
        self._ftp = None

    def __enter__(self) -> Self:
        """Ouvre la connexion en entrant dans le bloc ``with``."""
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Ferme la connexion en sortant du bloc ``with``."""
        self.close()

    @property
    def _conn(self) -> ftplib.FTP:
        if self._ftp is None:
            raise FtpError("Client FTP non connecté")
        return self._ftp

    def list_dir(self, path: str) -> list[RemoteEntry]:
        """Liste le contenu d'un dossier de la Vita.

        Args:
            path: Dossier distant, au format Vita ou FTP.

        Returns:
            Les entrées du dossier, triées par nom.

        Raises:
            TransferError: Si le dossier est introuvable ou la connexion coupée.
        """
        lines: list[str] = []
        ftp_path = to_ftp_path(path)
        try:
            self._conn.cwd(ftp_path)
            self._conn.retrlines("LIST", lines.append)
        except ftplib.all_errors as exc:
            raise TransferError(f"Impossible de lister {ftp_path} ({exc})") from exc
        entries = [entry for line in lines if (entry := parse_list_line(line))]
        return sorted(entries, key=lambda entry: entry.name)

    def download_file(self, remote: str, local: Path) -> None:
        """Télécharge un fichier de la Vita.

        Le fichier est d'abord écrit en ``.part`` puis renommé : un transfert
        interrompu ne laisse jamais un fichier tronqué à la place du bon.

        Args:
            remote: Fichier distant, au format Vita ou FTP.
            local: Fichier local à créer ou remplacer.

        Raises:
            TransferError: Si le transfert échoue.
        """
        ftp_path = to_ftp_path(remote)
        local.parent.mkdir(parents=True, exist_ok=True)
        partial = local.with_name(local.name + ".part")
        try:
            with partial.open("wb") as file:
                self._conn.retrbinary(f"RETR {ftp_path}", file.write)
        except ftplib.all_errors as exc:
            partial.unlink(missing_ok=True)
            raise TransferError(f"Échec du téléchargement de {ftp_path} ({exc})") from exc
        partial.replace(local)

    def download_dir(self, remote: str, local: Path) -> list[Path]:
        """Télécharge récursivement un dossier de la Vita.

        Args:
            remote: Dossier distant, au format Vita ou FTP.
            local: Dossier local de destination, créé si besoin.

        Returns:
            Les fichiers locaux écrits.

        Raises:
            TransferError: Si un listage ou un transfert échoue.
        """
        ftp_path = to_ftp_path(remote)
        local.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for entry in self.list_dir(ftp_path):
            child_remote = posixpath.join(ftp_path, entry.name)
            child_local = local / entry.name
            if entry.is_dir:
                written.extend(self.download_dir(child_remote, child_local))
            else:
                self.download_file(child_remote, child_local)
                written.append(child_local)
        return written

    def upload_file(self, local: Path, remote: str) -> None:
        """Envoie un fichier vers la Vita.

        Args:
            local: Fichier local à envoyer.
            remote: Fichier distant à créer ou remplacer.

        Raises:
            TransferError: Si le transfert échoue.
        """
        ftp_path = to_ftp_path(remote)
        try:
            with local.open("rb") as file:
                self._conn.storbinary(f"STOR {ftp_path}", file)
        except ftplib.all_errors as exc:
            raise TransferError(f"Échec de l'envoi de {local} vers {ftp_path} ({exc})") from exc

    def make_dir(self, remote: str) -> None:
        """Crée un dossier sur la Vita s'il n'existe pas déjà.

        Args:
            remote: Dossier distant, au format Vita ou FTP.

        Raises:
            TransferError: Si le dossier ne peut pas être créé.
        """
        ftp_path = to_ftp_path(remote)
        try:
            self._conn.cwd(ftp_path)
            return
        except ftplib.error_perm:
            pass
        except ftplib.all_errors as exc:
            raise TransferError(f"Impossible d'accéder à {ftp_path} ({exc})") from exc
        try:
            self._conn.mkd(ftp_path)
        except ftplib.all_errors as exc:
            raise TransferError(f"Impossible de créer {ftp_path} ({exc})") from exc

    def upload_dir(self, local: Path, remote: str) -> list[str]:
        """Envoie récursivement un dossier local vers la Vita.

        Args:
            local: Dossier local à envoyer.
            remote: Dossier distant de destination, créé si besoin.

        Returns:
            Les chemins FTP des fichiers envoyés.

        Raises:
            TransferError: Si une création de dossier ou un transfert échoue.
        """
        ftp_path = to_ftp_path(remote)
        self.make_dir(ftp_path)
        sent: list[str] = []
        for child in sorted(local.iterdir()):
            child_remote = posixpath.join(ftp_path, child.name)
            if child.is_dir():
                sent.extend(self.upload_dir(child, child_remote))
            else:
                self.upload_file(child, child_remote)
                sent.append(child_remote)
        return sent
