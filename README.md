# VitaSync

Continuer un même jeu possédé sur PC et sur PS Vita sans transférer les sauvegardes à la main. La V1 synchronise la Vita et le PC sur le réseau local (FTP de VitaShell), sans serveur ni cloud.

Jeu pilote : **Persona 4 Golden** (Steam `1113000` ↔ PS Vita `PCSB00245`).

## État du projet

Phase 0 (préparation) : procédure manuelle PC ↔ Vita validée dans les deux sens pour P4G.

Phase 1 (squelette Python) : paquet `vitasync`, commande `vitasync --version`, outillage qualité et CI GitLab.

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

Code dans `src/vitasync/`, tests dans `tests/`. Les docstrings suivent la convention Google, mypy tourne en mode strict.

## Règles

- Jamais d'écrasement sans copie de sauvegarde préalable.
- Côté Vita, ne remplacer que les fichiers de slot, jamais tout le dossier.
- Injection côté Steam uniquement avec Steam fermé.

## Arborescence locale

- `Références initiales/Pc/`, `Références initiales/Vita/` : états de base des sauvegardes (non versionné).
- `travail/` : fichiers intermédiaires de conversion et sauvegardes Steam (non versionné).
- `outils/` : outils tiers clonés (non versionné).
