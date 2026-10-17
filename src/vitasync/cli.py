"""Interface en ligne de commande de VitaSync."""

import argparse
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from vitasync import __version__, hotline_miami_sync, p4g_sync
from vitasync.config import (
    ConfigError,
    SteamConfig,
    VitaConfig,
    default_config_path,
    load_config,
    load_steam_config,
)
from vitasync.ftp import FtpError, VitaFtpClient
from vitasync.hotline_miami import SaveFormatError
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
            default=None,
            help="slots à transférer (P4G) : 7, 1,7, system ou all",
        )
        transfer.add_argument("--store", type=Path, default=None, help=store_help)
        add_connection_options(transfer)

    status = subparsers.add_parser(
        "status", help="compare le temps de jeu de chaque slot entre Steam et la Vita"
    )
    status.add_argument("game", help="identifiant du jeu, par exemple p4g")
    add_connection_options(status)

    sync = subparsers.add_parser(
        "sync", help="copie les slots les plus avancés dans le bon sens (pull ou push)"
    )
    sync.add_argument("game", help="identifiant du jeu, par exemple p4g")
    sync.add_argument("--store", type=Path, default=None, help=store_help)
    add_connection_options(sync)
    return parser


def format_play_time(seconds: int | None) -> str:
    """Formate un temps de jeu en ``h:mm:ss``, ou ``-`` pour un slot vide.

    Args:
        seconds: Temps de jeu en secondes.

    Returns:
        Le texte à afficher.
    """
    if seconds is None:
        return "-"
    return f"{seconds // 3600}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"


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
    command = args.command
    try:
        game = find_game(args.game)
        if game.adapter not in ("p4g", "hotline_miami"):
            raise SyncError(f"{game.name} : adaptateur {game.adapter} pas encore pris en charge")
        is_p4g = game.adapter == "p4g"
        # Les slots sont vérifiés d'abord : une faute de frappe ne coûte pas de connexion.
        slots: list[int] = []
        if is_p4g and command in ("pull", "push"):
            if args.slots is None:
                raise ValueError("--slots est obligatoire pour ce jeu (7, 1,7, system ou all)")
            slots = parse_slots(args.slots)
        try:
            steam: SteamConfig | None = load_steam_config(args.config or default_config_path())
        except ConfigError:
            if is_p4g:
                raise
            steam = None  # Hotline Miami n'a pas besoin de Steam
        with VitaFtpClient(resolve_config(args)) as ftp:
            if command in ("status", "sync"):
                if is_p4g:
                    assert steam is not None
                    states = p4g_sync.status(ftp, steam, game)
                else:
                    states = hotline_miami_sync.status(ftp, steam, game)
                if command == "status":
                    print_status(states, as_time=is_p4g)
                    return 0
                direction, slots = p4g_sync.plan_sync(states)
                if direction is None:
                    print("Déjà synchronisé : le PC et la Vita sont au même point.")
                    return 0
                command = direction
                where = "PC" if command == "push" else "Vita"
                detail = f" des slots {','.join(map(str, slots))}" if is_p4g else ""
                print(f"Plus avancé sur {where} : {command}{detail}.")
            store = open_store(args)
            if is_p4g:
                assert steam is not None
                if command == "pull":
                    result = p4g_sync.pull(store, ftp, steam, game, slots)
                else:
                    result = p4g_sync.push(store, ftp, steam, game, slots)
            elif command == "pull":
                result = hotline_miami_sync.pull(store, ftp, steam, game)
            else:
                result = hotline_miami_sync.push(store, ftp, steam, game)
    except (
        SaveFormatError,
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
    if command == "pull":
        if result.automatic:
            print("Backup fait par l'appli VitaSync sur la Vita.")
        if game.adapter == "p4g":
            print(f"Copié dans Steam : {files} (+ .binslot), remotecache.vdf régénéré.")
        else:
            print(f"Copié sur le PC : {files}.")
    elif result.automatic:
        print(f"Restauré sur la Vita par l'appli VitaSync (slots remplacés : {files}).")
    else:
        slot = (game.vita.inbox or "").rstrip("/").rsplit("/", 1)[-1]
        print(f"Sauvegarde complète prête dans {game.vita.inbox} (slots remplacés : {files})")
        print(f"Dans Save Manager : {game.name} > {slot} > Restore.")
    return 0


def print_status(states: list[p4g_sync.SlotState], as_time: bool = True) -> None:
    """Affiche le tableau de ``vitasync status``.

    Args:
        states: Avancement de chaque slot.
        as_time: ``True`` si l'avancement est un temps de jeu en secondes
            (P4G), ``False`` si c'est un nombre de niveaux (Hotline Miami).
    """
    labels = {"same": "identiques", "pc": "PC", "vita": "Vita"}
    if not as_time:
        for state in states:
            pc = "-" if state.pc is None else f"{state.pc} niveaux"
            vita = "-" if state.vita is None else f"{state.vita} niveaux"
            print(f"PC : {pc}  |  Vita : {vita}  |  plus avancé : {labels[state.newer]}")
        return
    print(f"{'Slot':>4}  {'PC':>9}  {'Vita':>9}  Plus avancé")
    for state in states:
        print(
            f"{state.slot:>4}  {format_play_time(state.pc):>9}  "
            f"{format_play_time(state.vita):>9}  {labels[state.newer]}"
        )


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
    if args.command in ("pull", "push", "status", "sync"):
        return run_transfer(args)
    parser.print_help()
    return 0
