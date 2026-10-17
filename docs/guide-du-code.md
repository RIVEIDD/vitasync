# Guide du code VitaSync

Ce guide passe en revue chaque fichier écrit pendant les phases 1 et 2 : ce qu'il fait, pourquoi il existe et comment le faire évoluer. Il reflète l'état du dépôt au commit `6de2c51`.

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
│   └── ftp.py            dialogue FTP avec VitaShell
└── tests/                les tests automatiques (pytest)
    ├── conftest.py       « fixtures » partagées entre tests
    ├── fake_vita.py      faux serveur FTP qui imite la Vita
    ├── test_cli.py       tests de la commande
    ├── test_config.py    tests de la configuration
    └── test_ftp.py       tests du client FTP
```

Le chemin d'une commande, de haut en bas : `vitasync ls ux0:data` → `cli.py` lit les arguments → `config.py` fournit l'IP et le port → `ftp.py` se connecte à la Vita et liste le dossier → `cli.py` affiche le résultat.

Chaque module a une seule responsabilité. `ftp.py` ne sait rien de la ligne de commande et `cli.py` ne sait rien du protocole FTP. C'est ce qui permettra, plus tard, de réutiliser le client FTP dans `vitasync sync` sans rien réécrire.

Ordre de lecture conseillé : `config.py`, puis `ftp.py`, puis `cli.py`, puis les tests.

---

## Fichiers de configuration du projet

### `pyproject.toml`

**Ce qu'il fait.** C'est la carte d'identité du projet, au format standard Python. Il contient :

- `[project]` : nom, version (`0.1.0`), version minimale de Python (3.12) et dépendances d'exécution. Il n'y en a aucune pour l'instant : tout le code utilise la bibliothèque standard (`ftplib`, `tomllib`, `argparse`).
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

**Pourquoi.** Valider tôt, avec un message clair, plutôt que d'obtenir plus tard une erreur réseau incompréhensible. Le plan prévoit des fiches par jeu en phase 3 : elles vivront dans un module à part, pas ici.

**Comment le maintenir.** Pour un nouveau réglage, par exemple un dossier Steam :
1. ajoute un attribut à `VitaConfig` (ou crée une nouvelle dataclass pour une nouvelle section) ;
2. lis-le et valide-le dans `load_config` ;
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
- `make_dir(remote)` teste si le dossier existe (`CWD`) et ne le crée (`MKD`) que si besoin. On peut donc renvoyer deux fois le même dossier.

**Pourquoi.** Toute la complexité réseau reste dans ce fichier. Les phases suivantes appelleront `download_dir` et `upload_dir` sans se soucier du FTP.

**Comment le maintenir.**
- Une nouvelle opération (supprimer un fichier, par exemple) devient une nouvelle méthode sur le même modèle : convertir le chemin avec `to_ftp_path`, appeler `self._conn.<commande>` dans un `try`, et traduire `ftplib.all_errors` en `TransferError`.
- Ajoute toujours un test dans `tests/test_ftp.py`, contre le faux serveur.
- Retiens que VitaShell ne sert qu'un client à la fois : ne jamais ouvrir deux `VitaFtpClient` en même temps.

### `cli.py`

**Ce qu'il fait.** C'est la ligne de commande, construite avec `argparse` (standard).

- `build_parser()` déclare l'option `--version` et la sous-commande `ls` avec ses options `path`, `--host`, `--port` et `--config`. C'est aussi ce qui produit l'aide de `vitasync -h` et `vitasync ls -h`.
- `resolve_config(args)` choisit la configuration : si `--host` est donné, le fichier est ignoré ; sinon le fichier est lu. `--port` remplace le port dans les deux cas.
- `run_ls(args)` se connecte, liste, puis affiche une ligne par entrée (taille alignée à droite, ou `<dir>`). Une `ConfigError` ou une `FtpError` est affichée sur la sortie d'erreur avec le code 1, sans trace Python effrayante.
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

Lance-les avec `python -m uv run pytest`. Il y en a 26, et ils tournent en environ une seconde, sans console.

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

### `test_cli.py`

`--version`, l'aide, puis `ls` contre le faux serveur, avec `--host` ou avec un fichier de config, et le message d'erreur quand la config est absente.

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
