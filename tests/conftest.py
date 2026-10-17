from collections.abc import Iterator
from pathlib import Path

import pytest
from fake_vita import FakeVita


def _serve(root: Path, app: bool) -> Iterator[FakeVita]:
    root.mkdir()
    vita = FakeVita(root, app=app)
    vita.thread.start()
    yield vita
    vita.server.close_all()
    vita.thread.join(timeout=5)


@pytest.fixture
def fake_vita(tmp_path: Path) -> Iterator[FakeVita]:
    """Faux FTP de VitaShell ou de vitacompanion (sans commandes VitaSync)."""
    yield from _serve(tmp_path / "vita", app=False)


@pytest.fixture
def fake_app(tmp_path: Path) -> Iterator[FakeVita]:
    """Faux FTP de l'appli VitaSync (avec VSVR, VSBK et VSRS)."""
    yield from _serve(tmp_path / "vita-app", app=True)
