"""Lancement de scripts Python externes, aussi depuis l'exécutable VitaSync.exe.

Sous ``uv run``, ``sys.executable`` est l'interpréteur Python : on lui passe le
script à exécuter. Dans l'exécutable construit par PyInstaller (« gelé »),
``sys.executable`` est VitaSync.exe lui-même : le relancer avec un script
rouvrirait la fenêtre. VitaSync.exe reconnaît donc l'option :data:`RUN_SCRIPT`,
qui lui fait exécuter le script avec le Python qu'il embarque, sans fenêtre.
"""

import runpy
import subprocess
import sys
import traceback
from pathlib import Path

RUN_SCRIPT = "--run-script"
"""Option de VitaSync.exe : ``VitaSync.exe --run-script script.py args...``."""


def is_frozen() -> bool:
    """Indique si VitaSync tourne depuis l'exécutable PyInstaller.

    Returns:
        ``True`` dans VitaSync.exe, ``False`` sous un interpréteur Python.
    """
    return bool(getattr(sys, "frozen", False))


def python_command(script: Path) -> list[str]:
    """Début de ligne de commande qui exécute un script Python.

    Args:
        script: Script à exécuter.

    Returns:
        ``[python, script]``, ou ``[VitaSync.exe, --run-script, script]`` dans
        l'exécutable.
    """
    if is_frozen():
        return [sys.executable, RUN_SCRIPT, str(script)]
    return [sys.executable, str(script)]


def no_window_flags() -> int:
    """Options de :func:`subprocess.run` qui évitent une console qui clignote.

    Une commande console (``tasklist``...) lancée depuis la fenêtre, qui n'a
    pas de console, en ouvrirait une le temps de son exécution.

    Returns:
        ``CREATE_NO_WINDOW`` sous Windows, 0 ailleurs.
    """
    if sys.platform == "win32":
        return subprocess.CREATE_NO_WINDOW
    return 0


def run_script(argv: list[str]) -> int:
    """Exécute un script comme ``python script.py args...`` (côté VitaSync.exe).

    Le dossier du script est placé en tête de ``sys.path``, comme le fait
    Python, pour qu'il puisse importer ses modules voisins.

    Args:
        argv: Chemin du script suivi de ses arguments.

    Returns:
        Le code de sortie du script : 0 s'il se termine normalement, 1 s'il
        lève une exception (dont la trace est écrite sur la sortie d'erreur).
    """
    script = Path(argv[0]).resolve()
    sys.argv = [str(script), *argv[1:]]
    sys.path.insert(0, str(script.parent))
    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as exc:
        if exc.code is None or isinstance(exc.code, int):
            return exc.code or 0
        if sys.stderr is not None:
            print(exc.code, file=sys.stderr)
        return 1
    except Exception:
        if sys.stderr is not None:
            traceback.print_exc()
        return 1
    return 0
