from pathlib import Path

import pytest
from fake_vita import FakeVita

from vitasync import __version__
from vitasync.cli import main


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
