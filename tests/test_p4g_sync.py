from dataclasses import replace
from pathlib import Path

import pytest
from fake_saveconv import install, make_pc_save, make_vita_save
from fake_vita import FakeVita

from vitasync import p4g
from vitasync.config import SteamConfig
from vitasync.ftp import VitaFtpClient
from vitasync.manifest import GameManifest, find_game
from vitasync.p4g_sync import SyncError, pull, push
from vitasync.store import LocalStore


@pytest.fixture
def game() -> GameManifest:
    p4g_game = find_game("p4g")
    # Le faux serveur ne connaît pas les partitions « ux0: ».
    return replace(p4g_game, vita=replace(p4g_game.vita, dump="/p4g_dump", inbox="/p4g_in"))


@pytest.fixture
def steam(tmp_path: Path) -> SteamConfig:
    userdata = tmp_path / "userdata"
    make_pc_save(userdata / "1113000" / "remote", {0: b"sys pc", 1: b"un pc", 7: b"sept pc"})
    (userdata / "1113000" / "remotecache.vdf").write_text("ancien", encoding="utf-8")
    return SteamConfig(userdata=userdata, p4g_saveconv=install(tmp_path / "tool"))


@pytest.fixture
def store(tmp_path: Path) -> LocalStore:
    return LocalStore(tmp_path / "store")


def remote(steam: SteamConfig) -> Path:
    return steam.userdata / "1113000" / "remote"


def test_pull_ne_remplace_que_les_slots_demandes(
    fake_vita: FakeVita, steam: SteamConfig, game: GameManifest, store: LocalStore
) -> None:
    make_vita_save(fake_vita.root / "p4g_dump", {0: b"sys vita", 1: b"un vita", 7: b"sept vita"})

    with VitaFtpClient(fake_vita.config) as ftp:
        result = pull(store, ftp, steam, game, [7], steam_running=lambda: False)

    assert result.files == ["data0007.bin"]
    assert (remote(steam) / "data0007.bin").read_bytes() == b"pc:sept vita"
    p4g.check_binslot(remote(steam) / "data0007.bin", remote(steam) / "data0007.binslot")
    assert (remote(steam) / "data0001.bin").read_bytes() == b"un pc"
    assert '"data0007.binslot"' in (remote(steam).parent / "remotecache.vdf").read_text()

    assert result.source.origin == "vita"
    assert (result.source.files / "data0007.bin").read_bytes() == b"sept vita"
    assert result.backup is not None
    assert result.backup.origin == "backup-pc"
    assert (result.backup.files / "remote" / "data0007.bin").read_bytes() == b"sept pc"
    assert (result.backup.files / "remotecache.vdf").read_text() == "ancien"


def test_pull_refuse_si_steam_est_ouvert(
    fake_vita: FakeVita, steam: SteamConfig, game: GameManifest, store: LocalStore
) -> None:
    make_vita_save(fake_vita.root / "p4g_dump", {7: b"sept vita"})

    with VitaFtpClient(fake_vita.config) as ftp, pytest.raises(SyncError, match="Steam est ouvert"):
        pull(store, ftp, steam, game, [7], steam_running=lambda: True)

    assert (remote(steam) / "data0007.bin").read_bytes() == b"sept pc"
    assert store.history("p4g") == []


def test_pull_refuse_si_steam_s_ouvre_pendant_le_transfert(
    fake_vita: FakeVita, steam: SteamConfig, game: GameManifest, store: LocalStore
) -> None:
    make_vita_save(fake_vita.root / "p4g_dump", {7: b"sept vita"})
    answers = iter([False, True])

    with VitaFtpClient(fake_vita.config) as ftp, pytest.raises(SyncError, match="pendant"):
        pull(store, ftp, steam, game, [7], steam_running=lambda: next(answers))

    assert (remote(steam) / "data0007.bin").read_bytes() == b"sept pc"


def test_pull_sans_copie_decryptee(
    fake_vita: FakeVita, steam: SteamConfig, game: GameManifest, store: LocalStore
) -> None:
    with VitaFtpClient(fake_vita.config) as ftp, pytest.raises(SyncError, match="Save Manager"):
        pull(store, ftp, steam, game, [7], steam_running=lambda: False)


def test_pull_sans_saveconv(
    fake_vita: FakeVita, steam: SteamConfig, game: GameManifest, store: LocalStore
) -> None:
    with VitaFtpClient(fake_vita.config) as ftp, pytest.raises(SyncError, match="p4g_saveconv"):
        pull(store, ftp, replace(steam, p4g_saveconv=None), game, [7], steam_running=lambda: False)


def test_push_prepare_une_sauvegarde_complete(
    fake_vita: FakeVita, steam: SteamConfig, game: GameManifest, store: LocalStore
) -> None:
    make_vita_save(fake_vita.root / "p4g_dump", {1: b"un vita", 7: b"sept vita"})
    (fake_vita.root / "p4g_dump" / "sce_sys" / "param.sfo").write_bytes(b"sfo")
    (fake_vita.root / "p4g_in").mkdir()
    (fake_vita.root / "p4g_in" / "data0003.bin").write_bytes(b"reste d'un ancien push")

    with VitaFtpClient(fake_vita.config) as ftp:
        result = push(store, ftp, steam, game, [7])

    inbox = fake_vita.root / "p4g_in"
    # Toute la sauvegarde Vita, sans les restes d'un ancien push, avec le slot 7 remplacé.
    assert sorted(p.relative_to(inbox).as_posix() for p in inbox.rglob("*") if p.is_file()) == [
        "data0001.bin",
        "data0007.bin",
        "sce_sys/param.sfo",
        "sce_sys/sdslot.dat",
    ]
    assert (inbox / "data0001.bin").read_bytes() == b"un vita"
    assert (inbox / "sce_sys" / "param.sfo").read_bytes() == b"sfo"
    assert (inbox / "data0007.bin").read_bytes() == b"vita:sept pc"
    sdslot = (inbox / "sce_sys" / "sdslot.dat").read_bytes()
    # Le slot 1 garde ses métadonnées Vita, le slot 7 prend celles du PC.
    assert sdslot[0x400 + 1 * 0x400 : 0x400 + 1 * 0x400 + 4] == b"vita"
    assert sdslot[0x400 + 7 * 0x400 : 0x400 + 7 * 0x400 + 2] == b"pc"

    assert result.source.origin == "pc"
    assert result.backup is not None
    assert result.backup.origin == "backup-vita"
    assert (result.backup.files / "data0007.bin").read_bytes() == b"sept vita"
    origins = [v.origin for v in store.history("p4g")]
    assert origins == ["pc", "backup-vita", "backup-vita"]


def test_push_refuse_sans_copie_de_la_vita(
    fake_vita: FakeVita, steam: SteamConfig, game: GameManifest, store: LocalStore
) -> None:
    with VitaFtpClient(fake_vita.config) as ftp, pytest.raises(SyncError, match="Save Manager"):
        push(store, ftp, steam, game, [7])

    assert not (fake_vita.root / "p4g_in").exists()
