from dataclasses import replace
from pathlib import Path

import pytest
from fake_vita import FakeVita

from vitasync import hotline_miami as hm
from vitasync.config import SteamConfig
from vitasync.ftp import VitaFtpClient
from vitasync.hotline_miami import SaveContainer, SaveFormatError
from vitasync.hotline_miami_sync import pull, push, status
from vitasync.manifest import GameManifest, find_game
from vitasync.store import LocalStore

VITA_HEADER = bytes.fromhex("9a975f0c0e1ee3") + bytes(45)


def save(header: bytes, progress: bytes, **extra: bytes) -> bytes:
    entries = {"saves.dat": progress + b"\n0\n", "mask.nfo": b"0", **extra}
    return hm.build(SaveContainer(header=header, entries=entries))


def pc_save(progress: bytes) -> bytes:
    return save(b"", progress, **{"volume.dat": b"46\n100"})


def vita_save(progress: bytes) -> bytes:
    return save(VITA_HEADER, progress, **{"achProgress.dat": b"11\n6"})


def test_lecture_ecriture_identiques() -> None:
    for data in (pc_save(b"1100"), vita_save(b"1000")):
        assert hm.build(hm.parse(data)) == data
        assert len(data) == hm.SAVE_SIZE
    assert hm.parse(vita_save(b"1")).header == VITA_HEADER


def test_transfer_garde_l_en_tete_et_les_fichiers_propres() -> None:
    merged = hm.parse(hm.transfer(pc_save(b"1110"), vita_save(b"1000")))

    assert merged.header == VITA_HEADER
    assert merged.entries["saves.dat"].startswith(b"1110")
    assert merged.entries["achProgress.dat"] == b"11\n6"
    assert "volume.dat" not in merged.entries


def test_progress() -> None:
    assert hm.progress(pc_save(b"11000\n10")) == 3


def test_fichier_illisible() -> None:
    with pytest.raises(SaveFormatError):
        hm.parse(bytes(hm.SAVE_SIZE))


@pytest.fixture
def game() -> GameManifest:
    manifest = find_game("hotline_miami")
    vita = replace(
        manifest.vita,
        dump="/savegames/PCSB00318/SLOT0",
        inbox="/savegames/PCSB00318/SLOT1",
    )
    return replace(manifest, vita=vita)


@pytest.fixture
def pc_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    folder = tmp_path / "home" / "Documents" / "My Games" / "HotlineMiami"
    folder.mkdir(parents=True)
    (folder / hm.SAVE_FILE).write_bytes(pc_save(b"1000"))
    return folder


def vita_dir(app: FakeVita, progress: bytes) -> Path:
    folder = app.root / "savedata" / "PCSB00318"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / hm.SAVE_FILE).write_bytes(vita_save(progress))
    return folder


def test_status(fake_app: FakeVita, pc_dir: Path, game: GameManifest) -> None:
    vita_dir(fake_app, b"1111")
    with VitaFtpClient(fake_app.config) as ftp:
        (state,) = status(ftp, None, game)
    assert (state.pc, state.vita, state.newer) == (1, 4, "vita")


def test_pull(fake_app: FakeVita, pc_dir: Path, game: GameManifest, tmp_path: Path) -> None:
    vita_dir(fake_app, b"1111")
    store = LocalStore(tmp_path / "store")

    with VitaFtpClient(fake_app.config) as ftp:
        result = pull(store, ftp, None, game, steam_running=lambda: False)

    pc = hm.parse((pc_dir / hm.SAVE_FILE).read_bytes())
    assert result.automatic
    assert pc.header == b""
    assert pc.entries["saves.dat"].startswith(b"1111")
    assert pc.entries["volume.dat"] == b"46\n100"
    assert result.backup is not None and result.backup.origin == "backup-pc"


def test_push(fake_app: FakeVita, pc_dir: Path, game: GameManifest, tmp_path: Path) -> None:
    (pc_dir / hm.SAVE_FILE).write_bytes(pc_save(b"1111"))
    folder = vita_dir(fake_app, b"1000")
    store = LocalStore(tmp_path / "store")

    with VitaFtpClient(fake_app.config) as ftp:
        result = push(store, ftp, SteamConfig(userdata=tmp_path), game)

    vita = hm.parse((folder / hm.SAVE_FILE).read_bytes())
    assert result.automatic
    assert vita.header == VITA_HEADER
    assert vita.entries["saves.dat"].startswith(b"1111")
    assert vita.entries["achProgress.dat"] == b"11\n6"
