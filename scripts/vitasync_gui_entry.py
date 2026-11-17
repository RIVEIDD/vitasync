"""Point d'entrée de l'exécutable Windows VitaSync.exe (voir scripts/build_exe.py).

PyInstaller part d'un fichier .py qu'il exécute comme un script, pas d'une
fonction. Par défaut, ce fichier ouvre la fenêtre de VitaSync. Avec l'option
``--run-script``, il exécute à la place un script Python externe (p4g-saveconv),
car dans l'exécutable il n'y a pas d'autre interpréteur Python à appeler
(voir :mod:`vitasync.frozen`).
"""

import sys

from vitasync.frozen import RUN_SCRIPT, run_script

if len(sys.argv) >= 3 and sys.argv[1] == RUN_SCRIPT:
    raise SystemExit(run_script(sys.argv[2:]))

from vitasync.gui import main  # noqa: E402  (inutile de charger Tkinter pour un script)

raise SystemExit(main())
