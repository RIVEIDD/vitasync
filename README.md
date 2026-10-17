# VitaSync

Continuer un même jeu possédé sur PC et sur PS Vita sans transférer les sauvegardes à la main. La V1 synchronise la Vita et le PC sur le réseau local (FTP de VitaShell), sans serveur ni cloud.

Jeu pilote : **Persona 4 Golden** (Steam `1113000` ↔ PS Vita `PCSB00245`).

## État du projet

Phase 0 (préparation) : procédure manuelle PC ↔ Vita validée dans les deux sens pour P4G.

Phase 1 (squelette Python) : paquet `vitasync`, commande `vitasync --version`, outillage qualité et CI GitLab.

Phase 2 (transport FTP) : client FTP pour VitaShell (lister, télécharger, envoyer un dossier) et commande `vitasync ls`.

Phase 3 (modèle et sécurité) : fiches de jeu YAML, stockage versionné des sauvegardes, copie de sécurité avant tout écrasement, commandes `vitasync history` et `vitasync restore`.

Phase 4 (jeu en copie directe) : reportée, P4G passe en premier.

Phase 5 (Persona 4 Golden) : commandes `vitasync pull` et `vitasync push`, conversion via p4g-saveconv, vérification des MD5 et régénération de `remotecache.vdf`. Côté Vita, deux manipulations dans Save Manager (*Backup* slot 0, *Restore* slot 1) remplacent la navigation dans VitaShell.

Appli Vita VitaSync : fork de Save Manager avec un FTP intégré, actif seulement quand l'appli est ouverte. `pull` et `push` lui font faire le *Backup* et le *Restore* : plus aucune manipulation sur la console. Validé dans les deux sens sur P4G.

Phase 6 (en cours) : `vitasync status` compare le temps de jeu de chaque slot entre Steam et la Vita, et `vitasync sync` copie les slots les plus avancés dans le bon sens.

Phase 4 (deuxième jeu) : **Hotline Miami** (Steam 219150 ↔ Vita PCSB00318), sauvegarde `Documents\My Games\HotlineMiami\SaveData.sav`. Les fiches de jeu peuvent désormais viser des dossiers PC hors Steam.

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

[steam]          # nécessaire pour pull et push
userdata = 'C:/Program Files (x86)/Steam/userdata/125320760'
p4g_saveconv = 'F:/Projets/VitaPcSynchro/outils/p4g-saveconv'
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

### Persona 4 Golden : pull et push

`--slots` est obligatoire : `7`, `1,7`, `system` (pour `system.bin`) ou `all`.

Côté Vita, VitaSync range ses copies dans les slots de [Save Manager](https://github.com/d3m3vilurr/vita-savemgr) : le slot 0 reçoit la copie décryptée de la sauvegarde, le slot 1 la sauvegarde préparée par `push`.

**Avec l'appli VitaSync (recommandé)**

Ouvrir VitaSync sur la Vita (le haut de l'écran affiche « FTP pret : IP:port »), puis sur le PC :

```bash
uv run vitasync pull p4g --slots 7   # Steam fermé ; l'appli fait le Backup, VitaSync copie vers Steam
uv run vitasync push p4g --slots 7   # l'appli fait le Backup, VitaSync prépare le slot 1, l'appli fait le Restore
```

Le plus simple est de laisser VitaSync choisir le sens :

```bash
uv run vitasync status p4g   # temps de jeu de chaque slot, côté PC et côté Vita
uv run vitasync sync p4g     # pull ou push des slots les plus avancés (Steam fermé pour un pull)
```

`sync` compare le temps de jeu inscrit dans chaque slot (il ne fait qu'augmenter au fil d'une partie ; les dates de fichiers ne servent pas, l'horloge de la Vita n'étant pas fiable). Si certains slots sont plus avancés sur PC et d'autres sur Vita, il s'arrête et indique les `push` et `pull` à lancer à la main.

`pull` télécharge le slot 0, l'enregistre, le convertit avec p4g-saveconv, vérifie les MD5, copie le dossier Steam `1113000` dans le stockage, puis n'écrit que les slots demandés et régénère `remotecache.vdf`. Il refuse de tourner si Steam est ouvert.

`push` part de la copie du slot 0, y remplace uniquement les slots demandés (`.bin` convertis et entrées de `sce_sys/sdslot.dat`), écrit le résultat complet dans le slot 1, puis le remet dans la sauvegarde.

**Sans l'appli (FTP de VitaShell ou de vitacompanion)**

VitaSync le détecte et ne pilote rien : faire *Backup* vers le slot 0 dans Save Manager avant `pull` ou `push`, et *Restore* du slot 1 après `push`.

### Hotline Miami

Mêmes commandes, sans `--slots` (le jeu n'a qu'une sauvegarde) :

```bash
uv run vitasync status hotline_miami   # niveaux débloqués de chaque côté
uv run vitasync sync hotline_miami
```

`SaveData.sav` est un conteneur de petits fichiers texte, presque identique des deux côtés (52 octets d'en-tête en plus sur Vita, non vérifiés par le jeu). Un transfert reprend les fichiers communs (progression, succès, statistiques) et garde l'en-tête et les fichiers propres à la destination (trophées sur Vita, réglages sur PC).

### Persona 4 Golden : langue

Les slots Steam doivent avoir été sauvegardés avec le jeu PC en anglais : la Vita européenne n'affiche plus aucune sauvegarde si un slot a des métadonnées en français, et `push` refuse ce cas.

### Appli Vita (`vita/`)

Fork de vita-savemgr sous GPLv3 (origine et modifications : `vita/UPSTREAM.md`). Compilation sous WSL avec VitaSDK installé dans `~/vitasdk` :

```bash
wsl -d Ubuntu-24.04 -- bash vita/build.sh                          # FTP sur 1337 -> vita/build/vitasync.vpk
VITASYNC_FTP_PORT=1340 wsl -d Ubuntu-24.04 -- bash vita/build.sh   # FTP sur 1340 (développement)
```

Pendant le développement, [vitacompanion](https://github.com/devnoname120/vitacompanion) est chargé sous `*main` dans `ur0:tai/config.txt` (FTP 1337, commandes 1338) : il occupe le port 1337, d'où le port 1340 de l'appli. `scripts/vita_dev.py` s'en sert pour installer et lancer l'appli (`deploy`), envoyer une commande (`cmd`), prendre une capture d'écran (`screenshot`) et lister les plantages (`crashes`). vitacompanion est à retirer une fois l'appli terminée.

Code dans `src/vitasync/`, tests dans `tests/`. Les docstrings suivent la convention Google, mypy tourne en mode strict.

## Règles

- Jamais d'écrasement sans copie de sauvegarde préalable.
- Côté Vita, ne jamais toucher au dossier chiffré directement (FTP, copier-coller hors *Open decrypted*) : passer par Save Manager. Seuls les slots demandés changent, le reste de la sauvegarde est repris tel quel de la copie Vita.
- Injection côté Steam uniquement avec Steam fermé.

## Arborescence locale

- `Références initiales/Pc/`, `Références initiales/Vita/` : états de base des sauvegardes (non versionné).
- `travail/` : fichiers intermédiaires de conversion et sauvegardes Steam (non versionné).
- `outils/` : outils tiers clonés (non versionné).
