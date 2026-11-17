"""Détection de Steam : on n'écrit jamais dans ses sauvegardes pendant qu'il tourne."""

import subprocess
import sys

from vitasync.frozen import no_window_flags


def is_steam_running() -> bool:
    """Indique si le client Steam est lancé sur ce PC.

    Returns:
        ``True`` si un processus Steam est trouvé. En cas de doute (commande
        de détection indisponible), renvoie ``True`` par prudence.
    """
    if sys.platform == "win32":
        command = ["tasklist", "/FI", "IMAGENAME eq steam.exe", "/NH"]
    else:
        command = ["pgrep", "-x", "steam"]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            creationflags=no_window_flags(),
        )
    except OSError:
        return True
    if sys.platform == "win32":
        return "steam.exe" in result.stdout.lower()
    return result.returncode == 0
