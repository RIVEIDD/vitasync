"""Faux p4g-saveconv : imite les sorties de l'outil, sans vraie conversion."""

import hashlib
import textwrap
from pathlib import Path

from vitasync import p4g

SDSLOT_SIZE = p4g.SDSLOT_ENTRY_OFFSET + (p4g.MAX_SLOT + 1) * p4g.SDSLOT_ENTRY_SIZE


ENGLISH_METADATA = b"Play Time:1\nLANG1\nTimes Cleared:0\n"


def make_binslot(bin_content: bytes, metadata: bytes = ENGLISH_METADATA) -> bytes:
    """Construit un .binslot valide pour le contenu d'un .bin."""
    body = metadata.ljust(0x34C, b"\0")
    slot_md5 = hashlib.md5(body + p4g.BINSLOT_SALT).digest()
    return p4g.BINSLOT_MAGIC + slot_md5 + hashlib.md5(bin_content).digest() + body


def make_sdslot(entries: dict[int, bytes]) -> bytes:
    """Construit un sdslot.dat avec une entrée par slot actif."""
    data = bytearray(SDSLOT_SIZE)
    for slot, entry in entries.items():
        data[p4g.SDSLOT_ACTIVE_OFFSET + slot] = 1
        start = p4g.SDSLOT_ENTRY_OFFSET + slot * p4g.SDSLOT_ENTRY_SIZE
        data[start : start + len(entry)] = entry
    return bytes(data)


def make_pc_save(path: Path, slots: dict[int, bytes]) -> Path:
    """Écrit des .bin et .binslot PC valides."""
    path.mkdir(parents=True, exist_ok=True)
    for slot, content in slots.items():
        name = p4g.bin_name(slot)
        (path / name).write_bytes(content)
        (path / f"{name}slot").write_bytes(make_binslot(content))
    return path


def make_vita_save(path: Path, slots: dict[int, bytes]) -> Path:
    """Écrit des .bin Vita et un sdslot.dat."""
    path.mkdir(parents=True, exist_ok=True)
    for slot, content in slots.items():
        (path / p4g.bin_name(slot)).write_bytes(content)
    (path / "sce_sys").mkdir()
    (path / p4g.SDSLOT).write_bytes(make_sdslot({s: b"vita" for s in slots}))
    return path


# Les faux scripts préfixent le contenu des .bin par « pc: » ou « vita: »,
# et produisent des .binslot et un sdslot.dat valides.
COMMON = textwrap.dedent(
    """
    import hashlib, sys
    from pathlib import Path

    src = Path(sys.argv[1])
    out = src.with_name(src.name + "_conv")
    out.mkdir(exist_ok=True)

    def binslot(content):
        body = b"Play Time:1\\nLANG1\\nTimes Cleared:0\\n".ljust(0x34C, b"\\0")
        return (b"SAVE0001" + hashlib.md5(body + b"P4GOLDEN").digest()
                + hashlib.md5(content).digest() + body)
    """
)

VITA2PC = COMMON + textwrap.dedent(
    """
    for f in src.glob("*.bin"):
        content = b"pc:" + f.read_bytes()
        (out / f.name).write_bytes(content)
        (out / (f.name + "slot")).write_bytes(binslot(content))
    """
)

PC2VITA = COMMON + textwrap.dedent(
    """
    sdslot = bytearray(0x400 + 17 * 0x400)
    for f in src.glob("*.bin"):
        (out / f.name).write_bytes(b"vita:" + f.read_bytes())
        slot = 0 if f.name == "system.bin" else int(f.name[4:8])
        sdslot[0x200 + slot] = 1
        sdslot[0x400 + slot * 0x400 : 0x400 + slot * 0x400 + 2] = b"pc"
    (out / "sce_sys").mkdir(exist_ok=True)
    (out / "sce_sys" / "sdslot.dat").write_bytes(bytes(sdslot))
    """
)


def install(path: Path, broken: bool = False) -> Path:
    """Installe les faux scripts dans ``path``."""
    path.mkdir(parents=True, exist_ok=True)
    fail = "raise SystemExit('outil en panne')\n" if broken else ""
    (path / "convert_vita2pc.py").write_text(fail + VITA2PC, encoding="utf-8")
    (path / "convert_pc2vita.py").write_text(fail + PC2VITA, encoding="utf-8")
    return path
