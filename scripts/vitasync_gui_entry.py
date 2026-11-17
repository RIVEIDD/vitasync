"""Point d'entrée de l'exécutable Windows VitaSync.exe (voir scripts/build_exe.py).

PyInstaller part d'un fichier .py qu'il exécute comme un script, pas d'une
fonction : ce fichier se contente donc d'appeler la fenêtre de VitaSync.
"""

from vitasync.gui import main

raise SystemExit(main())
