"""Interface en ligne de commande de VitaSync."""

import argparse
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from vitasync import __version__
from vitasync.config import ConfigError, VitaConfig, default_config_path, load_config
from vitasync.ftp import FtpError, VitaFtpClient
from vitasync.manifest import ManifestError, find_game
from vitasync.safety import write_pc_files
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
    ls.add_argument("--host", help="adresse IP de la Vita (remplace la config)")
    ls.add_argument("--port", type=int, help="port FTP de VitaShell (remplace la config)")
    ls.add_argument(
        "--config",
        type=Path,
        default=None,
        help=f"fichier de configuration (défaut : {default_config_path()})",
    )

    store_help = f"dossier du stockage des versions (défaut : {default_store_path()})"

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
    return parser


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
    if args.command == "history":
        return run_history(args)
    if args.command == "restore":
        return run_restore(args)
    parser.print_help()
    return 0
