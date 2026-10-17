from pathlib import Path

import pytest
from fake_vita import FakeVita

from vitasync.ftp import TransferError, VitaFtpClient
from vitasync.safety import (
    BACKUP_PC,
    BACKUP_VITA,
    backup_pc_dir,
    write_pc_files,
    write_vita_files,
)
from vitasync.store import LocalStore


def make_slots(path: Path, **slots: bytes) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    for name, content in slots.items():
        (path / f"{name}.bin").write_bytes(content)
    return path


@pytest.fixture
def store(tmp_path: Path) -> LocalStore:
    return LocalStore(tmp_path / "store")


def test_pas_de_copie_si_le_dossier_n_existe_pas(store: LocalStore, tmp_path: Path) -> None:
    assert backup_pc_dir(store, "p4g", tmp_path / "absent") is None
    assert store.history("p4g") == []


def test_write_pc_files_sauvegarde_puis_remplace_seulement_les_slots(
    store: LocalStore, tmp_path: Path
) -> None:
    dest = make_slots(tmp_path / "remote", data0001=b"ancien 1", data0002=b"ancien 2")
    source = make_slots(tmp_path / "nouveau", data0001=b"nouveau 1")

    backup = write_pc_files(store, "p4g", source, dest)

    assert (dest / "data0001.bin").read_bytes() == b"nouveau 1"
    assert (dest / "data0002.bin").read_bytes() == b"ancien 2"
    assert sorted(p.name for p in dest.iterdir()) == ["data0001.bin", "data0002.bin"]
    assert backup is not None
    assert backup.origin == BACKUP_PC
    assert (backup.files / "data0001.bin").read_bytes() == b"ancien 1"


def test_write_pc_files_cree_le_dossier(store: LocalStore, tmp_path: Path) -> None:
    source = make_slots(tmp_path / "nouveau", data0001=b"1")

    assert write_pc_files(store, "p4g", source, tmp_path / "neuf") is None
    assert (tmp_path / "neuf" / "data0001.bin").read_bytes() == b"1"


def test_write_vita_files_sauvegarde_puis_envoie(
    store: LocalStore, fake_vita: FakeVita, tmp_path: Path
) -> None:
    make_slots(fake_vita.root / "save", data0001=b"vita 1", data0002=b"vita 2")
    source = make_slots(tmp_path / "nouveau", data0001=b"pc 1")

    with VitaFtpClient(fake_vita.config) as ftp:
        backup = write_vita_files(store, "p4g", ftp, source, "/save")

    assert (fake_vita.root / "save" / "data0001.bin").read_bytes() == b"pc 1"
    assert (fake_vita.root / "save" / "data0002.bin").read_bytes() == b"vita 2"
    assert backup is not None
    assert backup.origin == BACKUP_VITA
    assert (backup.files / "data0001.bin").read_bytes() == b"vita 1"


def test_write_vita_files_dossier_neuf(
    store: LocalStore, fake_vita: FakeVita, tmp_path: Path
) -> None:
    source = make_slots(tmp_path / "nouveau", data0001=b"pc 1")

    with VitaFtpClient(fake_vita.config) as ftp:
        assert write_vita_files(store, "p4g", ftp, source, "/p4g_in") is None

    assert (fake_vita.root / "p4g_in" / "data0001.bin").read_bytes() == b"pc 1"


def test_rien_n_est_envoye_si_la_copie_echoue(
    store: LocalStore, fake_vita: FakeVita, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_slots(fake_vita.root / "save", data0001=b"vita 1")
    source = make_slots(tmp_path / "nouveau", data0001=b"pc 1")

    def coupure(self: VitaFtpClient, remote: str, local: Path) -> list[Path]:
        raise TransferError("Wi-Fi coupé")

    monkeypatch.setattr(VitaFtpClient, "download_dir", coupure)
    with VitaFtpClient(fake_vita.config) as ftp, pytest.raises(TransferError):
        write_vita_files(store, "p4g", ftp, source, "/save")

    assert (fake_vita.root / "save" / "data0001.bin").read_bytes() == b"vita 1"
