"""Interface en ligne de commande de VitaSync."""

import argparse
from collections.abc import Sequence

from vitasync import __version__


def build_parser() -> argparse.ArgumentParser:
    """Construit l'analyseur des arguments de la commande ``vitasync``.

    Returns:
        L'analyseur configuré avec les options globales.
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Point d'entrée de la commande ``vitasync``.

    Args:
        argv: Arguments de la ligne de commande, sans le nom du programme.
            ``None`` utilise ``sys.argv``.

    Returns:
        Le code de sortie du programme.
    """
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0
