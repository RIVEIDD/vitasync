from collections.abc import Iterator
from pathlib import Path

import pytest
from fake_vita import FakeVita


@pytest.fixture
def fake_vita(tmp_path: Path) -> Iterator[FakeVita]:
    root = tmp_path / "vita"
    root.mkdir()
    vita = FakeVita(root)
    vita.thread.start()
    yield vita
    vita.server.close_all()
    vita.thread.join(timeout=5)
