import pytest

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
