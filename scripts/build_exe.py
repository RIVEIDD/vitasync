"""Construit dist/VitaSync.exe : la fenêtre de VitaSync en un seul fichier, sans console.

Usage (depuis la racine du dépôt) :
    uv run --group build python scripts/build_exe.py

L'exécutable embarque Python, VitaSync et ses dépendances : il se lance d'un
double-clic sur n'importe quel PC Windows, sans uv ni projet. Il lit la même
configuration que la ligne de commande (``%APPDATA%/vitasync/config.toml``).
À reconstruire après chaque modification du code.
"""

from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    """Lance PyInstaller avec les options de VitaSync."""
    PyInstaller.__main__.run(
        [
            str(ROOT / "scripts" / "vitasync_gui_entry.py"),
            "--name=VitaSync",
            "--onefile",  # un seul .exe, décompressé dans un dossier temporaire au lancement
            "--windowed",  # pas de fenêtre de console derrière la fenêtre Tkinter
            "--noconfirm",  # écrase dist/ et build/ sans poser de question
            # Les fiches de jeux (vitasync/games/*.yaml) sont lues comme fichiers de données.
            "--collect-data=vitasync",
            # __version__ vient des métadonnées du paquet installé (importlib.metadata).
            "--copy-metadata=vitasync",
            # Modules de la bibliothèque standard utilisés par p4g-saveconv, lancé
            # par « VitaSync.exe --run-script » : PyInstaller n'embarque que ce que
            # VitaSync importe lui-même, il ne voit pas les scripts externes.
            *(f"--hidden-import={m}" for m in ("argparse", "hashlib", "math", "shutil", "struct")),
            f"--distpath={ROOT / 'dist'}",
            f"--workpath={ROOT / 'build'}",
            f"--specpath={ROOT / 'build'}",
        ]
    )


if __name__ == "__main__":
    main()
