# Guide du code VitaSync

Ce guide passe en revue chaque fichier écrit pendant les phases 1, 2, 3 et 5 : ce qu'il fait, pourquoi il existe et comment le faire évoluer. Il reflète l'état du dépôt à la fin de la phase 5 (la phase 4 est reportée).

## Vue d'ensemble

```
VitaPcSynchro/
├── pyproject.toml        identité du paquet + réglages de tous les outils
├── uv.lock               versions exactes des dépendances (généré)
├── .gitignore            ce que git ne doit pas suivre
├── .gitlab-ci.yml        vérifications automatiques à chaque push
├── README.md             documentation utilisateur et développeur
├── src/vitasync/         le code de l'application
│   ├── __init__.py       expose la version
│   ├── __main__.py       permet « python -m vitasync »
│   ├── py.typed          marqueur « ce paquet est typé »
│   ├── cli.py            la commande vitasync et ses sous-commandes
│   ├── config.py         lecture du fichier de configuration
│   ├── ftp.py            dialogue FTP avec VitaShell
│   ├── manifest.py       lecture des fiches de jeu
│   ├── games/            les fiches de jeu YAML (p4g.yaml)
│   ├── store.py          stockage versionné des sauvegardes
│   ├── safety.py         écritures précédées d'une copie de sécurité
│   ├── steam.py          détection de Steam ouvert
│   ├── p4g.py            format P4G et conversion via p4g-saveconv
│   └── p4g_sync.py       pull et push de P4G
└── tests/                les tests automatiques (pytest)
    ├── conftest.py       « fixtures » partagées entre tests
    ├── fake_vita.py      faux serveur FTP qui imite la Vita
    ├── test_cli.py       tests de la commande
    ├── test_config.py    tests de la configuration
    ├── test_ftp.py       tests du client FTP
    ├── test_manifest.py  tests des fiches de jeu
    ├── test_store.py     tests du stockage
    ├── test_safety.py    tests des copies de sécurité
    ├── fake_saveconv.py  faux p4g-saveconv et fausses sauvegardes P4G
    ├── test_p4g.py       tests du format et de la conversion
    └── test_p4g_sync.py  tests de pull et push
```

Le chemin d'une commande, de haut en bas : `vitasync ls ux0:data` → `cli.py` lit les arguments → `config.py` fournit l'IP et le port → `ftp.py` se connecte à la Vita et liste le dossier → `cli.py` affiche le résultat.

Et pour `vitasync restore p4g <version> --to <dossier>` : `cli.py` → `manifest.py` vérifie que le jeu existe → `store.py` retrouve la version → `safety.py` copie d'abord le dossier cible dans le stockage, puis y écrit les fichiers de la version.

Et pour `vitasync pull p4g --slots 7` : `cli.py` → `config.py` (Vita et Steam) → `p4g_sync.py` vérifie que Steam est fermé (`steam.py`), télécharge la copie décryptée (`ftp.py`), l'enregistre (`store.py`), la convertit (`p4g.py`), copie le dossier Steam (`safety.py`), puis écrit les slots et `remotecache.vdf`.

Chaque module a une seule responsabilité. `ftp.py` ne sait rien de la ligne de commande et `cli.py` ne sait rien du protocole FTP. C'est ce qui permettra, plus tard, de réutiliser le client FTP dans `vitasync sync` sans rien réécrire.

Ordre de lecture conseillé : `config.py`, `ftp.py`, `manifest.py`, `store.py`, `safety.py`, `p4g.py`, `p4g_sync.py`, puis `cli.py` et les tests.

---

## Fichiers de configuration du projet

### `pyproject.toml`

**Ce qu'il fait.** C'est la carte d'identité du projet, au format standard Python. Il contient :

- `[project]` : nom, version (`0.1.0`), version minimale de Python (3.12) et dépendances d'exécution. Une seule : PyYAML, pour lire les fiches de jeu. Le reste utilise la bibliothèque standard (`ftplib`, `tomllib`, `argparse`, `shutil`, `hashlib`, `subprocess`). `types-pyyaml`, dans les outils de dev, donne à mypy les types de PyYAML.
- `[project.scripts]` : la ligne `vitasync = "vitasync.cli:main"` crée la commande `vitasync`. Quand tu la tapes, Python appelle la fonction `main` du fichier `cli.py`.
- `[build-system]` : l'outil qui fabrique le paquet (hatchling). Tu n'as pas à y toucher.
- `[dependency-groups] dev` : les outils de développement (ruff, mypy, pytest, pyftpdlib). Ils sont installés pour toi, mais pas pour quelqu'un qui installerait seulement VitaSync.
- `[tool.ruff]` : le linter et formateur. `select` liste les familles de règles : erreurs de style (E, W), bugs probables (F, B), tri des imports (I), syntaxe moderne (UP), simplifications (SIM) et docstrings au format Google (D). Les tests sont dispensés de docstrings.
- `[tool.mypy]` : le vérificateur de types, en mode `strict`. Chaque fonction doit déclarer le type de ses paramètres et de son retour. La section `overrides` tolère pyftpdlib, qui ne fournit pas de types.
- `[tool.pytest.ini_options]` : où trouver les tests, et un avertissement de pyftpdlib à ignorer (il signale que l'utilisateur anonyme du faux serveur a le droit d'écrire, ce qui est voulu).

**Pourquoi.** Un seul fichier remplace `setup.py`, `requirements.txt`, `setup.cfg`, `mypy.ini` et compagnie.

**Comment le maintenir.**
- Ajouter une dépendance d'exécution : `python -m uv add <paquet>`. Pour un outil de dev : `python -m uv add --dev <paquet>`. Ne modifie pas les listes à la main : uv met à jour `uv.lock` en même temps.
- Changer de version : modifie `version`. La commande `vitasync --version` la lit automatiquement (voir `__init__.py`).
- Assouplir une règle ruff qui te gêne : ajoute son code dans une liste `ignore = [...]` sous `[tool.ruff.lint]`, plutôt que de retirer toute une famille.

### `uv.lock`

**Ce qu'il fait.** Il enregistre la version exacte de chaque dépendance, y compris les dépendances des dépendances, avec leurs empreintes de sécurité.

**Pourquoi.** Ton PC et la CI installent ainsi exactement les mêmes versions. La CI échoue d'ailleurs si le fichier n'est pas à jour (`uv sync --locked`).

**Comment le maintenir.** Ne jamais l'éditer à la main. uv le régénère à chaque `uv add` ou `uv remove`. `python -m uv lock --upgrade` passe tout aux dernières versions. Commite-le toujours avec `pyproject.toml`.

### `.gitignore`

**Ce qu'il fait.** Il dit à git d'ignorer tes données personnelles (`Références initiales/`, `travail/`, `outils/`), les fichiers générés par Python et les outils (`__pycache__/`, `.venv/`, les caches de mypy, ruff et pytest, `.uv-cache/`) et les fichiers d'éditeur.

**Pourquoi.** Tes sauvegardes de jeu et les fichiers temporaires ne doivent jamais partir sur GitLab.

**Comment le maintenir.** Ajoute une ligne par motif. `git status` doit rester propre après un `uv run pytest`. Si un nouveau dossier ou fichier généré apparaît, il a sa place ici.

### `.gitlab-ci.yml`

**Ce qu'il fait.** À chaque push, GitLab lance un conteneur avec Python 3.12 et uv préinstallés, installe les dépendances (`uv sync --locked`), puis lance trois tâches en parallèle :
- `lint` : `ruff check` (règles) et `ruff format --check` (mise en forme) ;
- `typecheck` : `mypy` ;
- `test` : `pytest`.

Le cache `.uv-cache` évite de retélécharger les paquets à chaque fois.

**Pourquoi.** Il teste sur Python 3.12, la version minimale annoncée, alors que ton PC a la 3.13. Et il garantit que `main` reste toujours vert.

**Comment le maintenir.** Si tu ajoutes une vérification, ajoute une tâche sur le même modèle. Si un pipeline échoue, clique sur la tâche rouge dans GitLab : la sortie est la même que celle de la commande lancée en local.

### `README.md`, section « Développement » et « Utilisation »

Les commandes à connaître et le format du fichier de configuration. Mets à jour la section « État du projet » à chaque phase terminée.

---

## Le code : `src/vitasync/`

Le dossier `src/` (« src layout ») empêche Python d'importer le code par accident depuis le dossier courant. Les tests utilisent donc le paquet réellement installé, comme un utilisateur.

### `__init__.py`

**Ce qu'il fait.** Il fait de `vitasync` un paquet Python et définit `__version__`, lue depuis les métadonnées installées (donc depuis `pyproject.toml`).

**Pourquoi.** La version n'est écrite qu'à un seul endroit.

**Comment le maintenir.** N'y mets pas de logique : ce fichier s'exécute à chaque import du paquet.

### `__main__.py`

**Ce qu'il fait.** Il permet de lancer `python -m vitasync` en plus de la commande `vitasync`. `raise SystemExit(main())` transmet le code de retour de `main` (0 = succès, 1 = erreur) au système.

**Comment le maintenir.** Rien à faire, il restera tel quel.

### `py.typed`

Fichier vide qui signale à mypy et aux éditeurs que le paquet fournit ses types. Ne pas le supprimer.

### `config.py`

**Ce qu'il fait.** Il lit le fichier `config.toml` et renvoie un objet `VitaConfig` avec `host`, `port` et `timeout`.

- `VitaConfig` est une `dataclass` `frozen=True` : une petite structure de données non modifiable. On ne peut pas changer le port par erreur au milieu d'un transfert ; pour une variante, on en crée une nouvelle avec `dataclasses.replace` (c'est ce que fait `cli.py` pour `--port`).
- `default_config_path()` renvoie `%APPDATA%\vitasync\config.toml` sous Windows, `~/.config/vitasync/config.toml` ailleurs.
- `load_config(path)` lit le fichier avec `tomllib` (standard depuis Python 3.11), puis vérifie chaque valeur : host non vide, port entre 1 et 65535, timeout positif. À la moindre anomalie, elle lève `ConfigError` avec un message en français.

Un détail : `isinstance(port, bool)` est exclu exprès, parce qu'en Python `True` est aussi un `int`, et `port = true` serait sinon accepté comme port 1.

La section `[steam]` est lue à part, par `load_steam_config(path)`, qui renvoie un `SteamConfig` : `userdata` (le dossier `Steam\userdata\<id>` de ton compte) et `p4g_saveconv` (le dossier de l'outil, facultatif). Les deux sections partagent `_read_toml`, qui lit le fichier et traduit les erreurs. `ls` n'a donc besoin que de `[vita]`, et `pull`/`push` des deux.

**Pourquoi.** Valider tôt, avec un message clair, plutôt que d'obtenir plus tard une erreur réseau incompréhensible. Les fiches de jeu vivent dans un module à part (`manifest.py`) : la config décrit *ta* machine, les fiches décrivent *les jeux*.

**Comment le maintenir.** Pour un nouveau réglage :
1. ajoute un attribut à la dataclass de sa section (ou crée une dataclass et une fonction `load_..._config` pour une nouvelle section) ;
2. lis-le et valide-le dans la fonction de chargement ;
3. ajoute un cas valide et un cas invalide dans `tests/test_config.py`.

### `ftp.py`

**Ce qu'il fait.** C'est tout le dialogue avec le serveur FTP de VitaShell. Il s'appuie sur `ftplib`, le client FTP de la bibliothèque standard.

**Les erreurs**, du plus général au plus précis :
- `FtpError` : la classe parente. `cli.py` attrape celle-ci pour couvrir tous les cas.
- `VitaUnreachableError` : la connexion initiale échoue (mauvaise IP, FTP non lancé, autre client déjà connecté).
- `TransferError` : la connexion est établie, mais une opération échoue (dossier introuvable, Wi-Fi coupé en cours de route).

Chaque erreur de `ftplib` est rattrapée (`except ftplib.all_errors`) et traduite en l'une de celles-ci avec un message lisible. `from exc` conserve l'erreur d'origine pour le débogage.

**Les fonctions utilitaires** :
- `to_ftp_path("ux0:data/p4g_dump")` renvoie `"/ux0:/data/p4g_dump"`. VitaShell présente chaque partition comme un dossier de la racine ; tu écris les chemins comme dans VitaShell, la conversion est automatique. Validé sur ta Vita.
- `parse_list_line(...)` découpe une ligne de la réponse `LIST` (format Unix `drwxrwxrwx 1 vita vita 0 Oct 17 12:00 nom`) en `RemoteEntry(name, is_dir, size)`. `split(None, 8)` coupe en 9 morceaux au maximum, pour qu'un nom contenant des espaces reste entier. `.` et `..` sont ignorés.

**La classe `VitaFtpClient`** s'utilise avec `with`, ce qui garantit que la connexion est fermée même en cas d'erreur :

```python
with VitaFtpClient(config) as ftp:
    ftp.list_dir("ux0:data")
```

- `connect()` se connecte et s'authentifie en anonyme (VitaShell accepte n'importe quel identifiant). `close()` envoie `QUIT` poliment, ou coupe brutalement si la Vita ne répond plus.
- `_conn` (propriété privée, d'où le `_`) renvoie la connexion, ou lève une erreur si on a oublié de se connecter.
- `list_dir(path)` se place dans le dossier (`CWD`), demande `LIST` et renvoie les entrées triées par nom.
- `download_file(remote, local)` écrit d'abord dans `fichier.part`, puis renomme une fois le transfert complet. Si le transfert est coupé, le `.part` est supprimé et l'ancien fichier local reste intact. C'est l'application de la règle « jamais d'écrasement sans filet ».
- `download_dir` et `upload_dir` parcourent un dossier récursivement : pour chaque entrée, un fichier est transféré et un sous-dossier provoque un nouvel appel de la même fonction.
- `dir_exists(remote)` teste si un dossier existe en essayant d'y entrer (`CWD`). `make_dir(remote)` s'en sert pour ne créer le dossier (`MKD`) que si besoin : on peut donc renvoyer deux fois le même dossier.
- `remove_tree(remote)` supprime un dossier et tout son contenu. Il ne sert qu'à vider `ux0:data/p4g_in`, le dossier de transit de `push`, après en avoir fait une copie : sinon, des fichiers d'un ancien `push` y traîneraient et seraient collés par erreur.

**Pourquoi.** Toute la complexité réseau reste dans ce fichier. Les phases suivantes appelleront `download_dir` et `upload_dir` sans se soucier du FTP.

**Comment le maintenir.**
- Une nouvelle opération (supprimer un fichier, par exemple) devient une nouvelle méthode sur le même modèle : convertir le chemin avec `to_ftp_path`, appeler `self._conn.<commande>` dans un `try`, et traduire `ftplib.all_errors` en `TransferError`.
- Ajoute toujours un test dans `tests/test_ftp.py`, contre le faux serveur.
- Retiens que VitaShell ne sert qu'un client à la fois : ne jamais ouvrir deux `VitaFtpClient` en même temps.

### `manifest.py` et `games/`

**Ce qu'il fait.** Chaque jeu synchronisable est décrit par une fiche YAML dans `src/vitasync/games/`. La première est `p4g.yaml` :

```yaml
id: p4g                       # nom court, utilisé en ligne de commande
name: Persona 4 Golden
adapter: p4g                  # convertisseur à utiliser (phase 5)
pc:
  steam_appid: 1113000
  path: 1113000/remote        # relatif à Steam\userdata\<id>\
vita:
  title_id: PCSB00245
  path: ux0:user/00/savedata/PCSB00245
```

`manifest.py` transforme ce texte en objets Python :
- `GameManifest`, `PcSide` et `VitaSide` sont des dataclasses figées, comme `VitaConfig`.
- `parse_manifest(text)` lit le YAML avec `yaml.safe_load` (jamais `yaml.load`, qui peut exécuter du code) et vérifie chaque champ. Une erreur lève `ManifestError` avec le nom de la fiche.
- `builtin_manifests()` charge toutes les fiches du dossier `games/` grâce à `importlib.resources`. Cela fonctionne aussi une fois le paquet installé, où les fichiers ne sont pas forcément à l'endroit attendu. Deux fiches avec le même `id` sont refusées.
- `find_game("p4g")` renvoie une fiche, ou une erreur qui liste les jeux connus.

**Pourquoi.** Ajouter un jeu doit se faire en écrivant une fiche, pas en modifiant du code. Le plan prévoit Balatro ou Cuphead en phase 4.

**Comment le maintenir.**
- Nouveau jeu : copie `p4g.yaml`, change les valeurs, et ajoute un test dans `tests/test_manifest.py`. La fiche est prise en compte automatiquement.
- Nouveau champ : ajoute-le à la dataclass concernée, lis-le dans `parse_manifest` et teste le cas invalide.
- Les fiches ne sont pas encore utilisées pour trouver les dossiers réels : il faudra d'abord connaître ton dossier `Steam\userdata\<id>`. Ce sera fait quand on branchera la synchronisation.

### `store.py`

**Ce qu'il fait.** Il garde un historique de chaque sauvegarde. Chaque version est une copie complète d'un dossier, rangée ainsi :

```
%LOCALAPPDATA%\vitasync\store\
└── p4g\
    ├── 20261017-142300-000000\
    │   ├── version.json      {"created_at": "...", "origin": "backup-pc"}
    │   └── files\            copie des fichiers
    └── 20261017-150812-532114\
```

- `SaveVersion` décrit une version : jeu, identifiant, date, provenance (`origin`) et dossier des fichiers.
- `SaveStore` est un `Protocol` : la liste des méthodes que tout stockage doit avoir (`get`, `put`, `snapshot`, `history`). `LocalStore` en est la version sur disque. Un autre stockage (sur la Vita, sur un NAS...) pourra respecter le même contrat, et le reste du code n'y verra aucune différence.
- L'identifiant d'une version est la date et l'heure UTC **du PC**, à la microseconde (`AAAAMMJJ-HHMMSS-µµµµµµ`). L'horloge de la Vita n'est jamais utilisée, conformément au plan. L'UTC évite les surprises au changement d'heure ; `history` réaffiche l'heure locale. Si deux copies tombent dans la même microseconde, la seconde reçoit le suffixe `-2`, et `_version_order` trie correctement `-10` après `-9`.
- `snapshot(jeu, dossier, origin)` copie le dossier d'abord dans `.tmp-<version>`, écrit `version.json`, puis renomme. Si la copie plante (disque plein, coupure), le dossier temporaire est supprimé et rien n'apparaît dans l'historique. Les dossiers qui commencent par `.` sont ignorés par `history`.
- `put(jeu, dossier, origin, expected)` fait la même chose, mais seulement si la version courante est bien `expected`. Sinon, il lève `VersionConflictError`. C'est un verrou « optimiste » : on note la version qu'on a lue, et on refuse d'écrire si quelqu'un a enregistré une autre version entre-temps. Ça servira à détecter les conflits (phase 6).
- `get(jeu)` renvoie la plus récente, `get(jeu, id)` une version précise ; `history(jeu)` les renvoie toutes, de la plus ancienne à la plus récente.
- L'horloge est un paramètre (`clock`) : les tests lui passent une fausse horloge pour obtenir des dates prévisibles.

**Pourquoi.** C'est le filet de sécurité de tout le projet : aucune version n'est jamais modifiée ni supprimée par VitaSync.

**Comment le maintenir.**
- Ne jamais écrire dans un dossier de version existant.
- Le stockage grossit à chaque copie. Une commande de nettoyage (garder les N dernières versions, par exemple) pourra venir plus tard ; elle devra être explicite.
- Pour une nouvelle information sur les versions, ajoute une clé dans `version.json` avec une valeur par défaut à la lecture, pour que les anciennes versions restent lisibles.

### `safety.py`

**Ce qu'il fait.** Il applique la règle « jamais d'écrasement sans copie de sauvegarde préalable ». Toute écriture de VitaSync doit passer par ces fonctions :
- `backup_pc_dir` et `backup_vita_dir` copient un dossier (du PC, ou de la Vita via FTP) dans le stockage, avec l'origine `backup-pc` ou `backup-vita`. Si le dossier n'existe pas encore, il n'y a rien à protéger et elles renvoient `None`.
- `write_pc_files(store, jeu, source, dest)` copie d'abord `dest`, puis y écrit les fichiers de `source`. Chaque fichier passe par un `.part` renommé à la fin, comme pour les téléchargements FTP.
- `write_vita_files(store, jeu, ftp, source, remote)` télécharge d'abord le dossier Vita dans le stockage, puis envoie les fichiers. Si le téléchargement échoue, l'exception remonte avant l'envoi : rien n'est écrit sur la console.

Dans les deux cas, **seuls les fichiers présents dans `source` sont remplacés**. Les autres fichiers du dossier cible (d'autres slots, `sce_sys`...) restent en place, ce qui respecte la règle « côté Vita, ne remplacer que les fichiers de slot ».

**Pourquoi.** La règle est écrite une fois, ici, au lieu d'être répétée (et oubliée un jour) dans chaque commande.

**Comment le maintenir.** Si une future commande doit écrire quelque part, elle appelle `write_pc_files` ou `write_vita_files`, jamais `shutil.copy` ou `upload_file` directement. Une nouvelle destination (un autre appareil) se traite avec le même schéma : d'abord la copie, ensuite l'écriture.

### `steam.py`

**Ce qu'il fait.** `is_steam_running()` regarde si `steam.exe` tourne (avec `tasklist` sous Windows, `pgrep` ailleurs). Si la commande de détection échoue, elle répond « oui » par prudence.

**Pourquoi.** La règle « injection côté Steam uniquement avec Steam fermé » : Steam garde ses fichiers ouverts et pourrait écraser les nôtres, ou les envoyer de travers sur Steam Cloud.

**Comment le maintenir.** Si un jour la détection se trompe (Steam installé sous un autre nom), c'est ici qu'on corrige.

### `p4g.py`

**Ce qu'il fait.** Tout ce qui est propre au format de Persona 4 Golden. Le README de p4g-saveconv documente le format ; ce module s'en sert.

- **Les slots.** Un slot est un numéro : 0 pour `system.bin` (données communes), 1 à 16 pour `data0001.bin` à `data0016.bin`. `bin_name(7)` donne `data0007.bin`. `parse_slots("1,7,system")` lit l'option `--slots` et renvoie `[0, 1, 7]` ; `all` renvoie tout.
- **`check_binslot(bin, binslot)`** vérifie un `.binslot` PC. Ce fichier commence par `SAVE0001`, puis le MD5 de ses propres métadonnées suivies du mot `P4GOLDEN`, puis le MD5 du `.bin`. Si l'une des deux empreintes est fausse, le jeu refuserait la sauvegarde : on s'arrête avant d'écrire quoi que ce soit.
- **`merge_sdslot(base, new, slots)`.** Côté Vita, les métadonnées de tous les slots sont dans un seul fichier, `sce_sys/sdslot.dat` : un octet « actif » par slot à l'adresse `0x200 + slot`, et un bloc de `0x400` octets par slot à partir de `0x400`. La fonction part du `sdslot.dat` actuel de la Vita et ne remplace que les blocs des slots envoyés. Sans elle, envoyer le slot 7 remplacerait aussi l'affichage des slots 1 à 6 par celui du PC.
- **`run_saveconv(dossier_outil, script, dossier)`** lance un script de p4g-saveconv avec le même Python que VitaSync (`sys.executable`) et récupère le dossier `<dossier>_conv` qu'il produit. Si le script échoue, son message d'erreur est remonté dans une `ConversionError`.
- **`vita_to_pc(...)`** copie la sauvegarde Vita dans un dossier temporaire (l'outil écrit à côté de son entrée, et on ne veut rien salir), lance `convert_vita2pc.py`, vérifie chaque `.binslot` produit, puis ne garde que les slots demandés.
- **`pc_to_vita(...)`** fait l'inverse avec `convert_pc2vita.py`. Il convertit tous les slots, parce que l'outil a besoin de tous les `.binslot` pour construire `sdslot.dat`, mais ne garde que les `.bin` demandés et fusionne `sdslot.dat` avec celui de la Vita.
- **`write_remotecache(remote, vdf)`** réécrit `remotecache.vdf`, la liste des fichiers que Steam connaît pour le jeu, avec la taille, la date et le SHA-1 de chaque fichier. Le jeu n'affiche que les sauvegardes listées dedans. Le fichier est réécrit pour **tout** le dossier `remote`, pas seulement les slots copiés, pour que les autres restent visibles.

**Pourquoi p4g-saveconv est appelé de l'extérieur.** Son dépôt n'a pas de licence : on n'a pas le droit d'en recopier le code dans VitaSync. On l'appelle donc tel quel, depuis le dossier indiqué dans la config, et on écrit nous-mêmes le reste (choix des slots, vérifications, `remotecache.vdf`) d'après le format documenté.

**Comment le maintenir.**
- Si p4g-saveconv change sa façon de nommer ses sorties, c'est `run_saveconv` qu'il faut adapter.
- Les adresses (`0x200`, `0x400`...) sont des constantes en haut du fichier : ne les écris jamais en dur ailleurs.
- Pour un autre jeu avec conversion, crée un module à son nom sur le même modèle.

### `p4g_sync.py`

**Ce qu'il fait.** Il enchaîne les étapes de `pull` et `push`, en respectant les règles du projet. Chaque fonction renvoie un `TransferResult` : les fichiers transférés, la version d'origine enregistrée et la copie de sécurité de la destination.

`pull(store, ftp, steam, jeu, slots)`, de la Vita vers Steam :
1. refuse si Steam est ouvert ;
2. télécharge `ux0:data/p4g_dump` (la copie *Open decrypted*) et l'enregistre dans le stockage (origine `vita`) ;
3. convertit au format PC et vérifie les MD5 ;
4. revérifie que Steam est toujours fermé ;
5. copie tout le dossier Steam `1113000` (avec `remote` et `remotecache.vdf`) dans le stockage (origine `backup-pc`) ;
6. écrit uniquement les slots demandés dans `remote`, puis régénère `remotecache.vdf`.

`push(store, ftp, steam, jeu, slots)`, de Steam vers la Vita :
1. enregistre le dossier Steam `remote` (origine `pc`) ;
2. télécharge `ux0:data/p4g_dump` comme copie de sécurité de la sauvegarde Vita (origine `backup-vita`), et refuse s'il n'existe pas ;
3. convertit au format Vita, en fusionnant `sdslot.dat` avec celui de la copie Vita ;
4. copie puis vide `ux0:data/p4g_in`, et y dépose les fichiers convertis.

Il te reste ensuite à coller le contenu de `p4g_in` dans la sauvegarde avec VitaShell. VitaSync ne peut pas le faire : par FTP, la sauvegarde est chiffrée.

Le paramètre `steam_running` de `pull` permet aux tests de simuler un Steam ouvert ou fermé.

**Pourquoi.** L'ordre des étapes est la partie la plus importante : la conversion et toutes les vérifications ont lieu **avant** la première écriture, et la copie de sécurité juste avant elle. Si quelque chose échoue en route, la destination n'a pas été touchée.

**Comment le maintenir.** Garde cet ordre : lire, convertir, vérifier, copier la destination, écrire. Une limite à connaître : `push` fait confiance à `p4g_dump`. Si cette copie est ancienne, la sauvegarde de sécurité et les métadonnées des autres slots le seront aussi. D'où la consigne de rafraîchir `p4g_dump` avant chaque `push`.

### `cli.py`

**Ce qu'il fait.** C'est la ligne de commande, construite avec `argparse` (standard).

- `build_parser()` déclare l'option `--version` et la sous-commande `ls` avec ses options `path`, `--host`, `--port` et `--config`. C'est aussi ce qui produit l'aide de `vitasync -h` et `vitasync ls -h`.
- `resolve_config(args)` choisit la configuration : si `--host` est donné, le fichier est ignoré ; sinon le fichier est lu. `--port` remplace le port dans les deux cas.
- `run_ls(args)` se connecte, liste, puis affiche une ligne par entrée (taille alignée à droite, ou `<dir>`). Une `ConfigError` ou une `FtpError` est affichée sur la sortie d'erreur avec le code 1, sans trace Python effrayante.
- `add_connection_options(parser)` ajoute `--host`, `--port` et `--config` à une sous-commande ; `ls` et `backup` s'en servent.
- `run_backup(args)` enregistre une version, soit d'un dossier du PC (`--pc`), soit d'un dossier de la Vita téléchargé par FTP (`--vita`). Les deux options sont exclusives (`add_mutually_exclusive_group`). La provenance enregistrée est `pc` ou `vita`, pour la distinguer des copies automatiques `backup-pc` et `backup-vita`.
- `run_history(args)` affiche une ligne par version : identifiant, date en heure locale, provenance.
- `run_restore(args)` vérifie le jeu, retrouve la version, puis appelle `write_pc_files` pour l'écrire dans le dossier `--to`. Le dossier de destination est obligatoire pour l'instant : la fiche ne suffit pas encore à trouver ton dossier Steam. La restauration vers la Vita viendra avec les adaptateurs, puisque P4G demande une conversion.
- `open_store(args)` ouvre le stockage de `--store`, ou celui par défaut.
- `run_transfer(args)` sert à `pull` et `push` : il lit `--slots`, la fiche, les sections `[vita]` et `[steam]` de la config, ouvre la connexion FTP et appelle `p4g_sync`. Après un `push`, il affiche la manipulation à faire dans VitaShell.
- `main(argv)` analyse les arguments et aiguille vers la bonne sous-commande. Sans sous-commande, elle affiche l'aide. Le paramètre `argv` permet aux tests d'appeler `main(["ls", ...])` sans lancer de vrai processus.

**Pourquoi.** `cli.py` est la seule couche qui parle à l'utilisateur (affichage, codes de sortie). Le reste du code renvoie des données ou lève des exceptions.

**Comment le maintenir.** Pour une nouvelle sous-commande, par exemple `pull` :
1. dans `build_parser`, `subparsers.add_parser("pull", ...)` avec ses arguments ;
2. une fonction `run_pull(args) -> int` qui appelle les modules métier et gère les erreurs ;
3. une branche `if args.command == "pull"` dans `main` ;
4. des tests dans `tests/test_cli.py`.

Quand le fichier grossira, chaque commande pourra partir dans son propre module (`commands/ls.py`, etc.).

---

## Les tests : `tests/`

Lance-les avec `python -m uv run pytest`. Il y en a 92, et ils tournent en environ trois secondes, sans console.

Quelques notions pytest utiles :
- Une **fixture** est une ressource préparée automatiquement pour un test : il suffit de la nommer en paramètre. `tmp_path` (dossier temporaire neuf, fourni par pytest), `capsys` (capture de ce qui est affiché) et `monkeypatch` (remplacement temporaire d'une fonction) sont fournies par pytest ; `fake_vita` est la nôtre.
- `@pytest.mark.parametrize` lance le même test avec plusieurs jeux de données.
- `pytest.raises(Erreur, match="texte")` vérifie qu'une erreur est bien levée, avec ce texte dans le message.

### `fake_vita.py`

**Ce qu'il fait.** La classe `FakeVita` démarre un vrai serveur FTP (pyftpdlib) sur ton PC, dans un thread, sur un port libre choisi par le système (`port 0`). Son dossier racine est un dossier temporaire. `config` donne la `VitaConfig` qui permet de s'y connecter.

**Pourquoi.** Tester le client FTP de bout en bout, en vrai réseau local, sans allumer la Vita, et dans la CI.

**Limite à connaître.** Ce faux serveur ne reproduit pas tout VitaShell : il n'a pas de partitions `ux0:` (le `:` est interdit dans les noms de dossiers Windows) et accepte plusieurs clients à la fois. Les tests utilisent donc des chemins comme `/p4g_dump`. Le comportement propre à VitaShell se vérifie à la main sur la console, comme tu l'as fait avec `vitasync ls`.

### `conftest.py`

**Ce qu'il fait.** Il définit la fixture `fake_vita` : il crée le dossier, démarre le serveur, le donne au test (`yield`), puis l'arrête proprement une fois le test terminé, même en cas d'échec.

**Pourquoi.** pytest charge automatiquement `conftest.py` : tous les fichiers de test y ont accès sans import.

### `test_config.py`

Il vérifie qu'une config complète est bien lue, que le port par défaut vaut 1337, et que six fichiers invalides (TOML cassé, section absente, port hors limites, port en texte, etc.) sont rejetés. À compléter dès que `config.py` gagne un réglage.

### `test_ftp.py`

- `to_ftp_path` et `parse_list_line` sont testés seuls, sur des exemples écrits à la main.
- `list_dir`, `download_dir` et `upload_dir` sont testés contre le faux serveur, avec une fausse sauvegarde P4G (`make_save`).
- Les cas d'erreur sont testés aussi. Pour « Vita injoignable », on se connecte à un port où rien n'écoute (`free_port`). Pour « dossier introuvable », on liste un dossier inexistant. Pour le transfert interrompu, `monkeypatch` remplace `retrbinary` par une fonction qui envoie quelques octets puis simule une coupure Wi-Fi. Le test vérifie alors que l'ancien fichier est intact et qu'aucun `.part` ne traîne.

### `test_manifest.py`

Il vérifie qu'une fiche minimale est bien lue, que la fiche P4G livrée contient les bonnes valeurs, qu'un jeu inconnu donne un message utile et que cinq fiches invalides sont rejetées.

### `test_store.py`

La fixture `store` utilise `fake_clock`, une horloge qui avance d'une minute à chaque appel : les identifiants de version sont donc connus d'avance. Les tests couvrent la copie et la relecture, l'indépendance d'une version par rapport à sa source, l'ordre de l'historique, deux copies dans la même microseconde (jusqu'à `-10`), le refus de `put` en cas de conflit, les versions introuvables et une copie interrompue (`monkeypatch` simule un disque plein).

### `test_safety.py`

Il vérifie que la copie de sécurité est faite avant l'écriture, que seuls les fichiers fournis sont remplacés (le slot 2 reste intact), qu'un dossier neuf est créé sans copie, et que rien n'est envoyé à la Vita si sa copie de sécurité échoue.

### `fake_saveconv.py`

Un faux p4g-saveconv, puisque le vrai n'est pas dans le dépôt (ni donc dans la CI). `install(dossier)` y écrit deux petits scripts `convert_vita2pc.py` et `convert_pc2vita.py` qui se comportent comme l'outil : ils lisent un dossier et produisent `<dossier>_conv`, avec des `.binslot` et un `sdslot.dat` valides. Ils ne convertissent rien pour de vrai : ils préfixent le contenu par `pc:` ou `vita:`, ce qui permet aux tests de vérifier quel fichier est arrivé où. `install(..., broken=True)` donne un outil qui plante.

Le fichier fournit aussi `make_pc_save`, `make_vita_save`, `make_binslot` et `make_sdslot` pour fabriquer de fausses sauvegardes P4G.

La vraie conversion se vérifie sur tes vraies sauvegardes, comme lors du test de la phase 3.

### `test_p4g.py`

Noms de fichiers et `--slots`, `check_binslot` (fichier correct, `.bin` modifié, métadonnées abîmées, mauvais en-tête), `merge_sdslot`, les deux conversions avec le faux outil (slots filtrés, outil absent ou en panne, `.binslot` incohérent) et le contenu exact de `remotecache.vdf`.

### `test_p4g_sync.py`

`pull` contre le faux serveur, un faux dossier Steam et le faux outil : seul le slot demandé change, le dossier Steam et `remotecache.vdf` sont copiés avant, rien n'est écrit si Steam est ouvert (même s'il s'ouvre en cours de route) ou si `p4g_dump` manque. `push` : `p4g_in` est vidé des restes d'un ancien `push`, ne contient que le slot demandé et `sdslot.dat`, garde les métadonnées Vita des autres slots, et rien n'est envoyé sans copie de la Vita.

### `test_cli.py`

`--version`, l'aide, puis `ls` contre le faux serveur, avec `--host` ou avec un fichier de config, et le message d'erreur quand la config est absente. Puis `backup` (PC, Vita, dossier absent), `history` (vide, jeu inconnu) et un `restore` complet : le test vérifie que la version est écrite et que l'ancien contenu a été copié dans le stockage. Enfin `pull` et `push` de bout en bout (avec un faux Steam fermé), et un `--slots` invalide.

---

## Routine de maintenance

Avant chaque commit :

```bash
python -m uv run ruff format          # remet en forme automatiquement
python -m uv run ruff check --fix     # corrige ce qui peut l'être
python -m uv run mypy
python -m uv run pytest
```

Si les quatre passent en local, la CI passera aussi.

Quelques réflexes :
- **Lire une erreur mypy** : elle donne le fichier, la ligne et le type attendu. Corrige le type plutôt que d'ajouter `# type: ignore`.
- **Un bug trouvé** : écris d'abord un test qui le reproduit (il échoue), corrige le code, puis vérifie que le test passe. Le bug ne pourra plus revenir.
- **Petits commits** : un commit par changement cohérent, avec un message au format `type: description` (`feat`, `fix`, `docs`, `test`, `build`, `ci`, `chore`), comme dans l'historique actuel.
