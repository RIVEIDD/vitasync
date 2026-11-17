import sys
from pathlib import Path

import pytest

from vitasync import frozen


def test_commande_sous_python(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    script = tmp_path / "outil.py"
    assert frozen.python_command(script) == [sys.executable, str(script)]


def test_commande_dans_l_exe(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    script = tmp_path / "outil.py"
    assert frozen.python_command(script) == [sys.executable, frozen.RUN_SCRIPT, str(script)]


@pytest.fixture
def isole(monkeypatch: pytest.MonkeyPatch) -> None:
    """run_script modifie sys.argv et sys.path : on les restaure après le test."""
    monkeypatch.setattr(sys, "argv", list(sys.argv))
    monkeypatch.setattr(sys, "path", list(sys.path))


@pytest.mark.usefixtures("isole")
def test_run_script_importe_ses_voisins_et_lit_ses_arguments(tmp_path: Path) -> None:
    (tmp_path / "voisin.py").write_text("VALEUR = 'ok'\n", encoding="utf-8")
    sortie = tmp_path / "sortie.txt"
    script = tmp_path / "outil.py"
    script.write_text(
        "import sys\nfrom pathlib import Path\nfrom voisin import VALEUR\n"
        "if __name__ == '__main__':\n"
        "    Path(sys.argv[1]).write_text(VALEUR, encoding='utf-8')\n",
        encoding="utf-8",
    )
    assert frozen.run_script([str(script), str(sortie)]) == 0
    assert sortie.read_text(encoding="utf-8") == "ok"


@pytest.mark.usefixtures("isole")
@pytest.mark.parametrize(
    ("corps", "code"),
    [
        ("raise SystemExit(3)\n", 3),
        ("raise SystemExit('message')\n", 1),
        ("raise ValueError('boum')\n", 1),
    ],
)
def test_run_script_code_de_sortie(tmp_path: Path, corps: str, code: int) -> None:
    script = tmp_path / "outil.py"
    script.write_text(corps, encoding="utf-8")
    assert frozen.run_script([str(script)]) == code
