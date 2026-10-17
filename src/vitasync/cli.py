"""Interface en ligne de commande de VitaSync."""

import argparse
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from vitasync import __version__
from vitasync.config import ConfigError, VitaConfig, default_config_path, load_config
from vitasync.ftp import FtpError, VitaFtpClient


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
    return parser


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
    parser.print_help()
    return 0
