import ftplib
import socket
from pathlib import Path
from typing import Any

import pytest
from fake_vita import FakeVita

from vitasync.config import VitaConfig
from vitasync.ftp import (
    RemoteEntry,
    TransferError,
    VitaFtpClient,
    VitaUnreachableError,
    parse_list_line,
    to_ftp_path,
)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("ux0:data/p4g_dump", "/ux0:/data/p4g_dump"),
        ("ux0:/data", "/ux0:/data"),
        ("ux0:", "/ux0:/"),
        ("/ux0:/data", "/ux0:/data"),
        ("data", "/data"),
    ],
)
def test_to_ftp_path(path: str, expected: str) -> None:
    assert to_ftp_path(path) == expected


def test_parse_list_line_vitashell() -> None:
    line = "-rw-rw-rw- 1 vita vita 216381 Oct 17 12:00 data0007.bin"
    assert parse_list_line(line) == RemoteEntry("data0007.bin", is_dir=False, size=216381)
    assert parse_list_line("drwxrwxrwx 1 vita vita 0 Oct 17 12:00 sce_sys") == RemoteEntry(
        "sce_sys", is_dir=True, size=0
    )
    assert parse_list_line("drwxrwxrwx 1 vita vita 0 Oct 17 12:00 ..") is None
    assert parse_list_line("") is None


def make_save(root: Path) -> None:
    (root / "p4g_dump" / "sce_sys").mkdir(parents=True)
    (root / "p4g_dump" / "data0001.bin").write_bytes(b"slot 1")
    (root / "p4g_dump" / "system.bin").write_bytes(b"system")
    (root / "p4g_dump" / "sce_sys" / "sdslot.dat").write_bytes(b"slots")


def test_list_dir(fake_vita: FakeVita) -> None:
    make_save(fake_vita.root)

    with VitaFtpClient(fake_vita.config) as ftp:
        entries = ftp.list_dir("/p4g_dump")

    assert entries == [
        RemoteEntry("data0001.bin", is_dir=False, size=6),
        RemoteEntry("sce_sys", is_dir=True, size=0),
        RemoteEntry("system.bin", is_dir=False, size=6),
    ]


def test_download_dir(fake_vita: FakeVita, tmp_path: Path) -> None:
    make_save(fake_vita.root)
    local = tmp_path / "pc"

    with VitaFtpClient(fake_vita.config) as ftp:
        written = ftp.download_dir("/p4g_dump", local)

    assert sorted(p.relative_to(local).as_posix() for p in written) == [
        "data0001.bin",
        "sce_sys/sdslot.dat",
        "system.bin",
    ]
    assert (local / "sce_sys" / "sdslot.dat").read_bytes() == b"slots"


def test_upload_dir(fake_vita: FakeVita, tmp_path: Path) -> None:
    local = tmp_path / "pc"
    make_save(local)

    with VitaFtpClient(fake_vita.config) as ftp:
        sent = ftp.upload_dir(local / "p4g_dump", "/p4g_in")
        ftp.upload_dir(local / "p4g_dump", "/p4g_in")  # dossier déjà présent

    assert len(sent) == 3
    assert (fake_vita.root / "p4g_in" / "sce_sys" / "sdslot.dat").read_bytes() == b"slots"
    assert (fake_vita.root / "p4g_in" / "data0001.bin").read_bytes() == b"slot 1"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
    return port


def test_vita_injoignable() -> None:
    config = VitaConfig(host="127.0.0.1", port=free_port(), timeout=1.0)

    with pytest.raises(VitaUnreachableError, match="injoignable"), VitaFtpClient(config):
        pass


def test_dossier_introuvable(fake_vita: FakeVita) -> None:
    with VitaFtpClient(fake_vita.config) as ftp, pytest.raises(TransferError, match="lister"):
        ftp.list_dir("/absent")


def test_transfert_interrompu_ne_laisse_pas_de_fichier(
    fake_vita: FakeVita, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_save(fake_vita.root)
    local = tmp_path / "pc" / "data0001.bin"
    local.parent.mkdir()
    local.write_bytes(b"ancienne version")

    def coupe(self: ftplib.FTP, cmd: str, callback: Any, *args: Any, **kwargs: Any) -> str:
        callback(b"debut")
        raise ConnectionResetError("Wi-Fi coupé")

    with VitaFtpClient(fake_vita.config) as ftp:
        monkeypatch.setattr(ftplib.FTP, "retrbinary", coupe)
        with pytest.raises(TransferError, match="téléchargement"):
            ftp.download_file("/p4g_dump/data0001.bin", local)

    assert local.read_bytes() == b"ancienne version"
    assert list(local.parent.iterdir()) == [local]
