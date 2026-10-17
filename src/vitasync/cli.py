"""Interface en ligne de commande de VitaSync."""

import argparse
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from vitasync import __version__, p4g_sync
from vitasync.config import (
    ConfigError,
    VitaConfig,
    default_config_path,
    load_config,
    load_steam_config,
)
from vitasync.ftp import FtpError, VitaFtpClient
from vitasync.manifest import ManifestError, find_game
from vitasync.p4g import ConversionError, parse_slots
from vitasync.p4g_sync import SyncError
from vitasync.safety import backup_pc_dir, backup_vita_dir, write_pc_files
from vitasync.store import LocalStore, StoreError, default_store_path


def build_parser() -> argparse.ArgumentParser:
    """Construit l'analyseur des arguments de la commande ``vitasync``.

    Returns:
        L'analyseur configuré avec les options globales et les sous-commandes.
    """
    parser = argparse.ArgumentParser(
        prog="vitasync",
        description="Synchronise les sauvegardes de jeux entre le PC et la PS Vita.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command")

    ls = subparsers.add_parser("ls", help="liste un dossier de la Vita par FTP")
    ls.add_argument("path", help="dossier Vita, par exemple ux0:data")
    add_connection_options(ls)

    store_help = f"dossier du stockage des versions (défaut : {default_store_path()})"

    backup = subparsers.add_parser(
        "backup", help="enregistre une version d'un dossier du PC ou de la Vita"
    )
    backup.add_argument("game", help="identifiant du jeu, par exemple p4g")
    source = backup.add_mutually_exclusive_group(required=True)
    source.add_argument("--pc", type=Path, metavar="DOSSIER", help="dossier du PC à enregistrer")
    source.add_argument("--vita", metavar="CHEMIN", help="dossier de la Vita à enregistrer")
    backup.add_argument("--store", type=Path, default=None, help=store_help)
    add_connection_options(backup)

    history = subparsers.add_parser("history", help="liste les versions enregistrées d'un jeu")
    history.add_argument("game", help="identifiant du jeu, par exemple p4g")
    history.add_argument("--store", type=Path, default=None, help=store_help)

    restore = subparsers.add_parser(
        "restore", help="restaure une version enregistrée dans un dossier du PC"
    )
    restore.add_argument("game", help="identifiant du jeu, par exemple p4g")
    restore.add_argument("version", help="identifiant de la version (voir vitasync history)")
    restore.add_argument(
        "--to",
        type=Path,
        required=True,
        dest="dest",
        metavar="DOSSIER",
        help="dossier du PC à mettre à jour",
    )
    restore.add_argument("--store", type=Path, default=None, help=store_help)

    for name, help_text in (
        ("pull", "copie des slots de la Vita vers Steam (Steam fermé)"),
        ("push", "prépare des slots de Steam pour la Vita, dans le dossier de transit"),
    ):
        transfer = subparsers.add_parser(name, help=help_text)
        transfer.add_argument("game", help="identifiant du jeu, par exemple p4g")
        transfer.add_argument(
            "--slots",
            required=True,
            help="slots à transférer : 7, 1,7, system ou all",
        )
        transfer.add_argument("--store", type=Path, default=None, help=store_help)
        add_connection_options(transfer)
    return parser


def add_connection_options(parser: argparse.ArgumentParser) -> None:
    """Ajoute les options de connexion à la Vita à une sous-commande.

    Args:
        parser: Analyseur de la sous-commande.
    """
    parser.add_argument("--host", help="adresse IP de la Vita (remplace la config)")
    parser.add_argument("--port", type=int, help="port FTP de VitaShell (remplace la config)")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help=f"fichier de configuration (défaut : {default_config_path()})",
    )


def open_store(args: argparse.Namespace) -> LocalStore:
    """Ouvre le stockage indiqué par ``--store``, ou celui par défaut.

    Args:
        args: Arguments analysés de la sous-commande.

    Returns:
        Le stockage local.
    """
    return LocalStore(args.store or default_store_path())


def run_history(args: argparse.Namespace) -> int:
    """Affiche les versions enregistrées d'un jeu, de la plus ancienne à la plus récente.

    Args:
        args: Arguments analysés de la sous-commande ``history``.

    Returns:
        0 en cas de succès, 1 si le jeu est inconnu.
    """
    try:
        game = find_game(args.game)
    except ManifestError as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    versions = open_store(args).history(game.id)
    if not versions:
        print(f"Aucune version enregistrée pour {game.name}.")
        return 0
    for version in versions:
        local_time = version.created_at.astimezone().strftime("%d/%m/%Y %H:%M:%S")
        print(f"{version.id}  {local_time}  {version.origin}")
    return 0


def run_backup(args: argparse.Namespace) -> int:
    """Enregistre une version d'un dossier du PC (``--pc``) ou de la Vita (``--vita``).

    Args:
        args: Arguments analysés de la sous-commande ``backup``.

    Returns:
        0 en cas de succès, 1 en cas d'erreur.
    """
    try:
        game = find_game(args.game)
        store = open_store(args)
        if args.pc is not None:
            source = str(args.pc)
            version = backup_pc_dir(store, game.id, args.pc, origin="pc")
        else:
            source = args.vita
            with VitaFtpClient(resolve_config(args)) as ftp:
                version = backup_vita_dir(store, game.id, ftp, args.vita, origin="vita")
    except (ManifestError, StoreError, ConfigError, FtpError, OSError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    if version is None:
        print(f"Erreur : dossier introuvable : {source}", file=sys.stderr)
        return 1
    count = sum(1 for path in version.files.rglob("*") if path.is_file())
    print(f"Version {version.id} enregistrée ({count} fichiers) depuis {source}")
    return 0


def run_transfer(args: argparse.Namespace) -> int:
    """Lance ``pull`` (Vita vers Steam) ou ``push`` (Steam vers la Vita).

    Args:
        args: Arguments analysés de la sous-commande ``pull`` ou ``push``.

    Returns:
        0 en cas de succès, 1 en cas d'erreur (rien n'est alors écrit à la
        destination).
    """
    try:
        slots = parse_slots(args.slots)
        game = find_game(args.game)
        if game.adapter != "p4g":
            raise SyncError(f"{game.name} : adaptateur {game.adapter} pas encore pris en charge")
        steam = load_steam_config(args.config or default_config_path())
        store = open_store(args)
        with VitaFtpClient(resolve_config(args)) as ftp:
            if args.command == "pull":
                result = p4g_sync.pull(store, ftp, steam, game, slots)
            else:
                result = p4g_sync.push(store, ftp, steam, game, slots)
    except (
        ValueError,
        ManifestError,
        StoreError,
        ConfigError,
        FtpError,
        ConversionError,
        SyncError,
        OSError,
    ) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1

    files = ", ".join(result.files)
    print(f"Version d'origine enregistrée : {result.source.id}")
    if result.backup is not None:
        print(f"Copie de sécurité de la destination : {result.backup.id}")
    if args.command == "pull":
        print(f"Copié dans Steam : {files} (+ .binslot), remotecache.vdf régénéré.")
    else:
        slot = (game.vita.inbox or "").rstrip("/").rsplit("/", 1)[-1]
        print(f"Sauvegarde complète prête dans {game.vita.inbox} (slots remplacés : {files})")
        print(f"Dans Save Manager : {game.name} > {slot} > Restore.")
    return 0


def run_restore(args: argparse.Namespace) -> int:
    """Restaure une version dans un dossier du PC, après une copie de sécurité.

    Args:
        args: Arguments analysés de la sous-commande ``restore``.

    Returns:
        0 en cas de succès, 1 en cas d'erreur.
    """
    try:
        game = find_game(args.game)
        store = open_store(args)
        version = store.get(game.id, args.version)
        backup = write_pc_files(store, game.id, version.files, args.dest)
    except (ManifestError, StoreError, OSError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    if backup is not None:
        print(f"Copie de sécurité de {args.dest} : version {backup.id}")
    print(f"Version {version.id} restaurée dans {args.dest}")
    return 0


def resolve_config(args: argparse.Namespace) -> VitaConfig:
    """Détermine la configuration de connexion à partir des options et du fichier.

    ``--host`` suffit à se passer du fichier de configuration ; sinon le fichier
    est lu et ``--port`` remplace éventuellement le port qu'il indique.

    Args:
        args: Arguments analysés de la sous-commande.

    Returns:
        La configuration de connexion à utiliser.

    Raises:
        ConfigError: Si aucune adresse n'est fournie et que le fichier est absent
            ou invalide.
    """
    if args.host:
        config = VitaConfig(host=args.host)
    else:
        config = load_config(args.config or default_config_path())
    if args.port is not None:
        config = replace(config, port=args.port)
    return config


def run_ls(args: argparse.Namespace) -> int:
    """Affiche le contenu d'un dossier de la Vita.

    Args:
        args: Arguments analysés de la sous-commande ``ls``.

    Returns:
        0 en cas de succès, 1 en cas d'erreur de configuration ou réseau.
    """
    try:
        config = resolve_config(args)
        with VitaFtpClient(config) as ftp:
            entries = ftp.list_dir(args.path)
    except (ConfigError, FtpError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    for entry in entries:
        if entry.is_dir:
            print(f"{'<dir>':>12}  {entry.name}/")
        else:
            print(f"{entry.size:>12}  {entry.name}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Point d'entrée de la commande ``vitasync``.

    Args:
        argv: Arguments de la ligne de commande, sans le nom du programme.
            ``None`` utilise ``sys.argv``.

    Returns:
        Le code de sortie du programme.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "ls":
        return run_ls(args)
    if args.command == "backup":
        return run_backup(args)
    if args.command == "history":
        return run_history(args)
    if args.command == "restore":
        return run_restore(args)
    if args.command in ("pull", "push"):
        return run_transfer(args)
    parser.print_help()
    return 0
