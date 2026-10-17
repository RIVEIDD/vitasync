# Origine du code

Cette appli est un fork de [vita-savemgr](https://github.com/d3m3vilurr/vita-savemgr) (GPLv3),
commit `63cfa4ba3f3e00712804c45d7f677ac8a2295692`, avec ses dépendances copiées telles quelles :

- `extern/inih` : [inih](https://github.com/benhoyt/inih), commit `60b5ad398a89462b33bae327cd8e7761b882dc9f`
- `extern/vitashell` : [VitaShell](https://github.com/TheOfficialFloW/VitaShell) (GPLv3), commit `680dd6008067d155c19c2d5942fc158a7fd0c59a`

Licence : GPLv3 (voir `LICENSE`). Le reste du dépôt VitaSync n'est pas concerné.

## Modifications par rapport à l'original

- Identifiant `VSYNC0001` et titre « VitaSync », pour cohabiter avec Save Manager.
- Compilation avec VitaSDK 2026 (GCC 15) : `-std=gnu99`, include `psp2/io/stat.h`,
  `mkdir`/`rmdir` renommés `mkdir_p`/`rmdir_r` (conflit avec la libc), et erreurs
  `int-conversion` / `incompatible-pointer-types` ramenées à des avertissements.
- `extern/libftpvita` : [libftpvita](https://github.com/xerpi/libftpvita) (MIT), commit
  `77a1d39`, sans l'exemple ; port rendu configurable (`FTP_PORT`) et include
  `psp2/io/stat.h` ajouté.
- `src/remote.c` : serveur FTP intégré (port `VITASYNC_FTP_PORT`, 1337 par défaut) avec
  les commandes `VSVR`, `VSBK <TITLEID> <slot>` (Backup) et `VSRS <TITLEID> <slot>`
  (Restore), et affichage de son état en haut de l'écran.
