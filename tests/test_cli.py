from pathlib import Path

import pytest
from fake_vita import FakeVita

from vitasync import __version__
from vitasync.cli import main
from vitasync.store import LocalStore


def test_version_affiche_la_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])

    assert exc_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"vitasync {__version__}"


def test_sans_argument_affiche_l_aide(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "usage: vitasync" in capsys.readouterr().out


def test_ls_affiche_le_dossier(fake_vita: FakeVita, capsys: pytest.CaptureFixture[str]) -> None:
    (fake_vita.root / "p4g_dump" / "sce_sys").mkdir(parents=True)
    (fake_vita.root / "p4g_dump" / "system.bin").write_bytes(b"system")

    code = main(["ls", "/p4g_dump", "--host", "127.0.0.1", "--port", str(fake_vita.port)])

    assert code == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines == [f"{'<dir>':>12}  sce_sys/", f"{6:>12}  system.bin"]


def test_ls_lit_le_fichier_de_config(
    fake_vita: FakeVita, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (fake_vita.root / "data").mkdir()
    config = tmp_path / "config.toml"
    config.write_text(f'[vita]\nhost = "127.0.0.1"\nport = {fake_vita.port}\n', encoding="utf-8")

    assert main(["ls", "/", "--config", str(config)]) == 0
    assert "data/" in capsys.readouterr().out


def test_ls_sans_config(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["ls", "ux0:data", "--config", str(tmp_path / "absent.toml")]) == 1
    assert "introuvable" in capsys.readouterr().err


def test_history_vide(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["history", "p4g", "--store", str(tmp_path)]) == 0
    assert "Aucune version enregistrée pour Persona 4 Golden" in capsys.readouterr().out


def test_history_jeu_inconnu(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["history", "zelda", "--store", str(tmp_path)]) == 1
    assert "Jeu inconnu" in capsys.readouterr().err


def test_history_puis_restore(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store = LocalStore(tmp_path / "store")
    saved = tmp_path / "sauvegarde"
    saved.mkdir()
    (saved / "data0001.bin").write_bytes(b"version enregistree")
    version = store.snapshot("p4g", saved, origin="pc")
    dest = tmp_path / "remote"
    dest.mkdir()
    (dest / "data0001.bin").write_bytes(b"version actuelle")

    assert main(["history", "p4g", "--store", str(store.root)]) == 0
    out = capsys.readouterr().out
    assert out.startswith(version.id) and out.rstrip().endswith("pc")

    args = ["restore", "p4g", version.id, "--to", str(dest), "--store", str(store.root)]
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "Copie de sécurité" in out and f"Version {version.id} restaurée" in out
    assert (dest / "data0001.bin").read_bytes() == b"version enregistree"
    backup = store.get("p4g")
    assert backup.origin == "backup-pc"
    assert (backup.files / "data0001.bin").read_bytes() == b"version actuelle"


def test_restore_version_introuvable(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    args = ["restore", "p4g", "1999", "--to", str(tmp_path / "d"), "--store", str(tmp_path)]
    assert main(args) == 1
    assert "Aucune version" in capsys.readouterr().err


def test_backup_pc(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    remote = tmp_path / "remote"
    remote.mkdir()
    (remote / "data0001.bin").write_bytes(b"slot 1")
    store = tmp_path / "store"

    assert main(["backup", "p4g", "--pc", str(remote), "--store", str(store)]) == 0
    assert "(1 fichiers)" in capsys.readouterr().out
    version = LocalStore(store).get("p4g")
    assert version.origin == "pc"
    assert (version.files / "data0001.bin").read_bytes() == b"slot 1"


def test_backup_vita(
    fake_vita: FakeVita, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (fake_vita.root / "p4g_dump" / "sce_sys").mkdir(parents=True)
    (fake_vita.root / "p4g_dump" / "sce_sys" / "sdslot.dat").write_bytes(b"slots")
    store = tmp_path / "store"
    args = ["backup", "p4g", "--vita", "/p4g_dump", "--store", str(store)]

    assert main([*args, "--host", "127.0.0.1", "--port", str(fake_vita.port)]) == 0
    version = LocalStore(store).get("p4g")
    assert version.origin == "vita"
    assert (version.files / "sce_sys" / "sdslot.dat").read_bytes() == b"slots"


def test_backup_dossier_absent(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    args = ["backup", "p4g", "--pc", str(tmp_path / "absent"), "--store", str(tmp_path)]
    assert main(args) == 1
    assert "introuvable" in capsys.readouterr().err
