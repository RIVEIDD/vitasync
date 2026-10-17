import hashlib
from pathlib import Path

import pytest
from fake_saveconv import (
    install,
    make_binslot,
    make_pc_save,
    make_sdslot,
    make_vita_save,
)

from vitasync import p4g
from vitasync.p4g import ConversionError


def test_bin_name() -> None:
    assert p4g.bin_name(0) == "system.bin"
    assert p4g.bin_name(7) == "data0007.bin"
    assert p4g.bin_name(16) == "data0016.bin"


@pytest.mark.parametrize(
    ("text", "slots"),
    [("7", [7]), ("7,1,7", [1, 7]), ("system, 2", [0, 2]), ("all", list(range(17)))],
)
def test_parse_slots(text: str, slots: list[int]) -> None:
    assert p4g.parse_slots(text) == slots


@pytest.mark.parametrize("text", ["0", "17", "sept", "", "1,,2"])
def test_parse_slots_invalide(text: str) -> None:
    with pytest.raises(ValueError, match="slot invalide"):
        p4g.parse_slots(text)


def test_check_binslot(tmp_path: Path) -> None:
    make_pc_save(tmp_path, {7: b"partie"})
    bin_path, binslot = tmp_path / "data0007.bin", tmp_path / "data0007.binslot"

    p4g.check_binslot(bin_path, binslot)

    bin_path.write_bytes(b"modifiee")
    with pytest.raises(ConversionError, match="ne correspond pas"):
        p4g.check_binslot(bin_path, binslot)

    damaged = bytearray(make_binslot(b"modifiee"))
    damaged[-1] ^= 0xFF
    binslot.write_bytes(bytes(damaged))
    with pytest.raises(ConversionError, match="métadonnées"):
        p4g.check_binslot(bin_path, binslot)

    binslot.write_bytes(b"XXXX0001" + bytes(100))
    with pytest.raises(ConversionError, match="en-tête"):
        p4g.check_binslot(bin_path, binslot)


def test_merge_sdslot_ne_touche_que_les_slots_demandes() -> None:
    base = make_sdslot({1: b"vita 1", 7: b"vita 7"})
    new = make_sdslot({1: b"pc 1", 7: b"pc 7", 8: b"pc 8"})

    merged = p4g.merge_sdslot(base, new, [7, 8])

    def entry(data: bytes, slot: int) -> bytes:
        start = p4g.SDSLOT_ENTRY_OFFSET + slot * p4g.SDSLOT_ENTRY_SIZE
        return data[start : start + 4]

    assert entry(merged, 1) == b"vita"
    assert entry(merged, 7) == b"pc 7"
    assert merged[p4g.SDSLOT_ACTIVE_OFFSET + 8] == 1
    with pytest.raises(ConversionError):
        p4g.merge_sdslot(b"court", new, [7])


def test_vita_to_pc(tmp_path: Path) -> None:
    tool = install(tmp_path / "tool")
    vita = make_vita_save(tmp_path / "dump", {0: b"sys", 1: b"un", 7: b"sept"})

    written = p4g.vita_to_pc(tool, vita, tmp_path / "out", [7, 9])

    assert written == ["data0007.bin"]
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == [
        "data0007.bin",
        "data0007.binslot",
    ]
    assert (tmp_path / "out" / "data0007.bin").read_bytes() == b"pc:sept"
    assert not (tmp_path / "dump_conv").exists()


def test_vita_to_pc_sans_sdslot(tmp_path: Path) -> None:
    (tmp_path / "dump").mkdir()
    with pytest.raises(ConversionError, match="sdslot"):
        p4g.vita_to_pc(install(tmp_path / "tool"), tmp_path / "dump", tmp_path / "out", [7])


def test_vita_to_pc_slot_absent(tmp_path: Path) -> None:
    vita = make_vita_save(tmp_path / "dump", {1: b"un"})
    with pytest.raises(ConversionError, match="Aucun des slots"):
        p4g.vita_to_pc(install(tmp_path / "tool"), vita, tmp_path / "out", [7])


def test_outil_absent_ou_en_panne(tmp_path: Path) -> None:
    vita = make_vita_save(tmp_path / "dump", {7: b"sept"})
    with pytest.raises(ConversionError, match="introuvable"):
        p4g.vita_to_pc(tmp_path / "absent", vita, tmp_path / "out", [7])
    with pytest.raises(ConversionError, match="outil en panne"):
        p4g.vita_to_pc(install(tmp_path / "tool", broken=True), vita, tmp_path / "out", [7])


def test_pc_to_vita_fusionne_sdslot(tmp_path: Path) -> None:
    tool = install(tmp_path / "tool")
    pc = make_pc_save(tmp_path / "remote", {1: b"un", 7: b"sept"})
    vita_sdslot = make_sdslot({1: b"vita 1", 7: b"vita 7"})

    written = p4g.pc_to_vita(tool, pc, tmp_path / "out", [7], vita_sdslot)

    assert written == ["data0007.bin"]
    assert (tmp_path / "out" / "data0007.bin").read_bytes() == b"vita:sept"
    assert not (tmp_path / "out" / "data0001.bin").exists()
    sdslot = (tmp_path / "out" / p4g.SDSLOT).read_bytes()
    assert sdslot[0x400 + 1 * 0x400 : 0x400 + 1 * 0x400 + 4] == b"vita"
    assert sdslot[0x400 + 7 * 0x400 : 0x400 + 7 * 0x400 + 2] == b"pc"


def test_pc_to_vita_refuse_un_binslot_incoherent(tmp_path: Path) -> None:
    pc = make_pc_save(tmp_path / "remote", {7: b"sept"})
    (pc / "data0007.bin").write_bytes(b"modifiee")
    with pytest.raises(ConversionError, match="ne correspond pas"):
        p4g.pc_to_vita(install(tmp_path / "tool"), pc, tmp_path / "out", [7], None)


def test_write_remotecache(tmp_path: Path) -> None:
    remote = make_pc_save(tmp_path / "remote", {0: b"sys", 7: b"sept"})
    vdf = tmp_path / "remotecache.vdf"

    p4g.write_remotecache(remote, vdf)

    text = vdf.read_text(encoding="utf-8")
    assert text.startswith('"1113000"\n{\n\t"system.bin"\n\t{\n\t\t"root"\t\t"0"\n')
    assert text.endswith("\t}\n}\n")
    assert [line.strip() for line in text.splitlines() if line.startswith('\t"')] == [
        '"system.bin"',
        '"system.binslot"',
        '"data0007.bin"',
        '"data0007.binslot"',
    ]
    assert f'"sha"\t\t"{hashlib.sha1(b"sept").hexdigest()}"' in text
    assert "\r" not in vdf.read_bytes().decode()
