import shutil
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from vitasync.store import (
    LocalStore,
    SaveStore,
    StoreError,
    VersionConflictError,
    VersionNotFoundError,
)

START = datetime(2026, 10, 17, 14, 0, 0, tzinfo=UTC)


def fake_clock(step: timedelta = timedelta(minutes=1)) -> Callable[[], datetime]:
    """Horloge qui avance d'un pas à chaque appel."""
    ticks: Iterator[int] = iter(range(10_000))
    return lambda: START + step * next(ticks)


def make_dir(path: Path, content: bytes) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "data0001.bin").write_bytes(content)
    return path


@pytest.fixture
def store(tmp_path: Path) -> LocalStore:
    return LocalStore(tmp_path / "store", clock=fake_clock())


def test_local_store_respecte_l_interface(store: LocalStore) -> None:
    as_protocol: SaveStore = store
    assert as_protocol.history("p4g") == []


def test_snapshot_puis_get(store: LocalStore, tmp_path: Path) -> None:
    version = store.snapshot("p4g", make_dir(tmp_path / "src", b"v1"), origin="pc")

    assert version.id == "20261017-140000-000000"
    assert version.created_at == START
    assert version.origin == "pc"
    assert (version.files / "data0001.bin").read_bytes() == b"v1"
    assert store.get("p4g") == version
    assert store.get("p4g", version.id) == version


def test_la_version_ne_bouge_plus_si_la_source_change(store: LocalStore, tmp_path: Path) -> None:
    source = make_dir(tmp_path / "src", b"v1")
    version = store.snapshot("p4g", source, origin="pc")
    (source / "data0001.bin").write_bytes(b"v2")

    assert (version.files / "data0001.bin").read_bytes() == b"v1"


def test_history_dans_l_ordre(store: LocalStore, tmp_path: Path) -> None:
    for content in (b"v1", b"v2", b"v3"):
        store.snapshot("p4g", make_dir(tmp_path / content.decode(), content), origin="pc")

    history = store.history("p4g")

    assert [(v.files / "data0001.bin").read_bytes() for v in history] == [b"v1", b"v2", b"v3"]
    assert store.get("p4g") == history[-1]


def test_meme_microseconde(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store", clock=lambda: START)
    first = store.snapshot("p4g", make_dir(tmp_path / "a", b"a"), origin="pc")
    second = store.snapshot("p4g", make_dir(tmp_path / "b", b"b"), origin="pc")

    assert second.id == first.id + "-2"
    for i in range(3, 11):
        store.snapshot("p4g", make_dir(tmp_path / str(i), b"x"), origin="pc")
    assert store.get("p4g").id == first.id + "-10"


def test_put_avec_version_attendue(store: LocalStore, tmp_path: Path) -> None:
    first = store.put("p4g", make_dir(tmp_path / "a", b"a"), origin="pc", expected=None)
    second = store.put("p4g", make_dir(tmp_path / "b", b"b"), origin="vita", expected=first.id)

    assert store.get("p4g") == second


def test_put_refuse_si_quelqu_un_a_ecrit_entre_temps(store: LocalStore, tmp_path: Path) -> None:
    first = store.put("p4g", make_dir(tmp_path / "a", b"a"), origin="pc", expected=None)
    store.snapshot("p4g", make_dir(tmp_path / "b", b"b"), origin="vita")

    with pytest.raises(VersionConflictError):
        store.put("p4g", make_dir(tmp_path / "c", b"c"), origin="pc", expected=first.id)
    assert len(store.history("p4g")) == 2


def test_versions_introuvables(store: LocalStore, tmp_path: Path) -> None:
    with pytest.raises(VersionNotFoundError, match="Aucune version"):
        store.get("p4g")
    store.snapshot("p4g", make_dir(tmp_path / "a", b"a"), origin="pc")
    with pytest.raises(VersionNotFoundError, match="introuvable"):
        store.get("p4g", "19990101-000000-000000")


def test_source_absente(store: LocalStore, tmp_path: Path) -> None:
    with pytest.raises(StoreError, match="introuvable"):
        store.snapshot("p4g", tmp_path / "absent", origin="pc")


def test_copie_interrompue_n_apparait_pas(
    store: LocalStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def disque_plein(*args: Any, **kwargs: Any) -> None:
        raise OSError("disque plein")

    monkeypatch.setattr(shutil, "copytree", disque_plein)

    with pytest.raises(OSError, match="disque plein"):
        store.snapshot("p4g", make_dir(tmp_path / "a", b"a"), origin="pc")
    assert store.history("p4g") == []
    assert list((store.root / "p4g").iterdir()) == []
