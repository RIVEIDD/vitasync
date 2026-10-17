# VitaSync

Continuer un même jeu possédé sur PC et sur PS Vita sans transférer les sauvegardes à la main. La V1 synchronise la Vita et le PC sur le réseau local (FTP de VitaShell), sans serveur ni cloud.

Jeu pilote : **Persona 4 Golden** (Steam `1113000` ↔ PS Vita `PCSB00245`).

## État du projet

Phase 0 (préparation) : procédure manuelle PC ↔ Vita validée dans les deux sens pour P4G.

Phase 1 (squelette Python) : paquet `vitasync`, commande `vitasync --version`, outillage qualité et CI GitLab.

Phase 2 (transport FTP) : client FTP pour VitaShell (lister, télécharger, envoyer un dossier) et commande `vitasync ls`.

Phase 3 (modèle et sécurité) : fiches de jeu YAML, stockage versionné des sauvegardes, copie de sécurité avant tout écrasement, commandes `vitasync history` et `vitasync restore`.

## Procédure manuelle validée (P4G)

Outil de conversion : [p4g-saveconv](https://github.com/zarroboogs/p4g-saveconv), cloné dans `outils/` (non versionné).

| Sujet | Valeur |
|---|---|
| Sauvegardes Vita | `ux0:user/00/savedata/PCSB00245/` (EUR) |
| Sauvegardes PC | `Steam\userdata\<id>\1113000\remote\` |
| Fichier PC | `dataXXXX.bin` + `dataXXXX.binslot` ; `system.bin` + `system.binslot` |
| Fichier Vita (décrypté) | `dataXXXX.bin`, `system.bin`, `sce_sys/sdslot.dat` |

### PC → Vita

1. Copier `remote\` dans un dossier de travail et lancer `convert_pc2vita.py` dessus.
2. Envoyer la sortie par FTP vers `ux0:data/p4g_in/`.
3. Dans VitaShell : `PCSB00245` → Triangle → *Open decrypted*, puis coller `data00XX.bin`, `system.bin` et `sce_sys/sdslot.dat` à l'intérieur. Ne jamais remplacer le dossier entier.
4. Sortir du dossier avec Rond pour réécrire les données chiffrées.

### Vita → PC

1. Dans VitaShell : *Open decrypted* sur `PCSB00245`, copier le contenu dans `ux0:data/p4g_dump/`.
2. Récupérer ce dossier par FTP, puis lancer `convert_vita2pc.py` dessus (génère aussi `remotecache.vdf`).
3. Steam fermé : sauvegarder `userdata\<id>\1113000\`, puis copier les slots voulus dans `remote\` et `remotecache.vdf` dans `1113000\`.

### Observations

- Le dossier Vita copié par FTP est chiffré (présence de `sce_pfs`, entropie proche de 8 bits par octet) ; il faut passer par *Open decrypted* et `ux0:data/`.
- Les `.bin` PC font 217 937 octets, ceux produits par l'outil 216 381 : seul le nouveau slot 7 a été ajouté côté Steam, les slots 1 à 6 n'ont pas été écrasés.
- Le `remotecache.vdf` généré par l'outil (sans `ChangeNumber` ni `ostype`) a été accepté par Steam.
- Steam Cloud activé pendant le test : aucun conflit, Steam a repris la sauvegarde la plus récente.

## Développement

Prérequis : Python 3.12 ou plus et [uv](https://docs.astral.sh/uv/).

```bash
uv sync                  # crée .venv et installe les dépendances de dev
uv run vitasync --version
```

Vérifications (les mêmes que la CI GitLab) :

```bash
uv run ruff check
uv run ruff format --check
uv run mypy
uv run pytest
```

## Utilisation

Dans VitaShell, appuyer sur Select pour lancer le serveur FTP et noter l'adresse affichée. Puis :

```bash
uv run vitasync ls ux0:data --host 192.168.1.42
```

Pour ne pas répéter l'adresse, créer `%APPDATA%\vitasync\config.toml` (`~/.config/vitasync/config.toml` hors Windows) :

```toml
[vita]
host = "192.168.1.42"
port = 1337      # port de VitaShell, valeur par défaut
timeout = 10     # secondes
```

Les chemins Vita s'écrivent `ux0:data/p4g_dump` ; la forme FTP `/ux0:/data/p4g_dump` est aussi acceptée. Les tests FTP tournent contre un faux serveur local (pyftpdlib), sans console.

Chaque version d'une sauvegarde est copiée dans `%LOCALAPPDATA%\vitasync\store\<jeu>\<version>\` (`~/.local/share/vitasync/store` hors Windows), datée par l'horloge du PC. Toute écriture de VitaSync commence par y copier le dossier qu'elle va modifier.

```bash
uv run vitasync backup p4g --pc "C:\chemin\vers\remote"   # enregistre le dossier du PC
uv run vitasync backup p4g --vita ux0:data/p4g_dump       # ou celui de la Vita, par FTP
uv run vitasync history p4g
uv run vitasync restore p4g 20261017-142300-000000 --to "C:\chemin\vers\remote"
```

`restore` ne remplace que les fichiers présents dans la version restaurée, après avoir copié le dossier cible. L'option `--store` change le dossier du stockage.

Code dans `src/vitasync/`, tests dans `tests/`. Les docstrings suivent la convention Google, mypy tourne en mode strict.

## Règles

- Jamais d'écrasement sans copie de sauvegarde préalable.
- Côté Vita, ne remplacer que les fichiers de slot, jamais tout le dossier.
- Injection côté Steam uniquement avec Steam fermé.

## Arborescence locale

- `Références initiales/Pc/`, `Références initiales/Vita/` : états de base des sauvegardes (non versionné).
- `travail/` : fichiers intermédiaires de conversion et sauvegardes Steam (non versionné).
- `outils/` : outils tiers clonés (non versionné).
