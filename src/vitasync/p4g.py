"""Format des sauvegardes de Persona 4 Golden et conversion PC <-> Vita.

La conversion des ``.bin`` est déléguée à l'outil externe p4g-saveconv
(https://github.com/zarroboogs/p4g-saveconv), appelé tel quel. Ce module
choisit les slots, vérifie les empreintes MD5 et régénère ``remotecache.vdf``,
d'après le format documenté dans le README de cet outil.
"""

import hashlib
import math
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from pathlib import Path

SYSTEM_SLOT = 0
"""Numéro du slot ``system.bin`` (données communes à toutes les parties)."""

MAX_SLOT = 16
SDSLOT = Path("sce_sys") / "sdslot.dat"
SDSLOT_ACTIVE_OFFSET = 0x200
SDSLOT_ENTRY_OFFSET = 0x400
SDSLOT_ENTRY_SIZE = 0x400
BINSLOT_MAGIC = b"SAVE0001"
BINSLOT_SALT = b"P4GOLDEN"
STEAM_APPID = "1113000"


class ConversionError(Exception):
    """La conversion ou la vérification d'une sauvegarde P4G a échoué."""


def bin_name(slot: int) -> str:
    """Renvoie le nom du fichier ``.bin`` d'un slot.

    Args:
        slot: 0 pour ``system.bin``, 1 à 16 pour ``data0001.bin`` à ``data0016.bin``.

    Returns:
        Le nom du fichier.
    """
    return "system.bin" if slot == SYSTEM_SLOT else f"data{slot:04d}.bin"


def parse_slots(text: str) -> list[int]:
    """Analyse l'option ``--slots``.

    Args:
        text: ``all``, ou une liste séparée par des virgules de numéros
            (1 à 16) et de ``system``, par exemple ``7`` ou ``1,7,system``.

    Returns:
        Les numéros de slot, triés et sans doublon (0 pour ``system``).

    Raises:
        ValueError: Si un élément est invalide.
    """
    if text.strip() == "all":
        return list(range(SYSTEM_SLOT, MAX_SLOT + 1))
    slots: set[int] = set()
    for part in text.split(","):
        item = part.strip()
        if item == "system":
            slots.add(SYSTEM_SLOT)
        elif item.isdigit() and 1 <= int(item) <= MAX_SLOT:
            slots.add(int(item))
        else:
            raise ValueError(f"slot invalide : « {item} » (1 à {MAX_SLOT}, system ou all)")
    return sorted(slots)


def check_binslot(bin_path: Path, binslot_path: Path) -> None:
    """Vérifie qu'un ``.binslot`` PC est cohérent avec son ``.bin``.

    Structure d'un ``.binslot`` : ``SAVE0001``, puis le MD5 des octets 0x28 à
    la fin suivis de ``P4GOLDEN``, puis le MD5 du ``.bin``, puis les métadonnées.

    Args:
        bin_path: Fichier ``.bin``.
        binslot_path: Fichier ``.binslot`` correspondant.

    Raises:
        ConversionError: Si le fichier est absent ou si une empreinte est fausse.
    """
    if not binslot_path.is_file():
        raise ConversionError(f"{binslot_path.name} manquant")
    data = binslot_path.read_bytes()
    if data[:8] != BINSLOT_MAGIC:
        raise ConversionError(f"{binslot_path.name} : en-tête invalide")
    if data[8:0x18] != hashlib.md5(data[0x28:] + BINSLOT_SALT).digest():
        raise ConversionError(f"{binslot_path.name} : empreinte des métadonnées fausse")
    if data[0x18:0x28] != hashlib.md5(bin_path.read_bytes()).digest():
        raise ConversionError(f"{binslot_path.name} : ne correspond pas à {bin_path.name}")


def merge_sdslot(base: bytes, new: bytes, slots: Iterable[int]) -> bytes:
    """Remplace les entrées de quelques slots dans un ``sdslot.dat`` Vita.

    Les autres slots gardent les métadonnées de ``base``, pour que la Vita
    continue d'afficher correctement les parties qui ne sont pas remplacées.

    Args:
        base: ``sdslot.dat`` actuellement sur la Vita.
        new: ``sdslot.dat`` produit par la conversion depuis le PC.
        slots: Numéros des slots à prendre dans ``new``.

    Returns:
        Le contenu fusionné.

    Raises:
        ConversionError: Si l'un des fichiers est trop court.
    """
    size = SDSLOT_ENTRY_OFFSET + (MAX_SLOT + 1) * SDSLOT_ENTRY_SIZE
    if len(base) < size or len(new) < size:
        raise ConversionError("sdslot.dat trop court")
    merged = bytearray(base)
    for slot in slots:
        active = SDSLOT_ACTIVE_OFFSET + slot
        merged[active] = new[active]
        start = SDSLOT_ENTRY_OFFSET + slot * SDSLOT_ENTRY_SIZE
        merged[start : start + SDSLOT_ENTRY_SIZE] = new[start : start + SDSLOT_ENTRY_SIZE]
    return bytes(merged)


def run_saveconv(saveconv: Path, script: str, save_dir: Path) -> Path:
    """Lance un script de p4g-saveconv sur un dossier.

    Args:
        saveconv: Dossier de l'outil p4g-saveconv.
        script: ``convert_vita2pc.py`` ou ``convert_pc2vita.py``.
        save_dir: Dossier à convertir.

    Returns:
        Le dossier produit par l'outil (``<save_dir>_conv``).

    Raises:
        ConversionError: Si l'outil est introuvable ou échoue.
    """
    script_path = saveconv / script
    if not script_path.is_file():
        raise ConversionError(f"p4g-saveconv introuvable : {script_path}")
    result = subprocess.run(
        [sys.executable, str(script_path), str(save_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ConversionError(f"{script} a échoué :\n{result.stderr.strip()}")
    return save_dir.with_name(save_dir.name + "_conv")


def vita_to_pc(saveconv: Path, vita_dir: Path, out_dir: Path, slots: Iterable[int]) -> list[str]:
    """Convertit une sauvegarde Vita décryptée au format PC.

    Args:
        saveconv: Dossier de l'outil p4g-saveconv.
        vita_dir: Copie de ``Open decrypted`` (``data*.bin``, ``system.bin``,
            ``sce_sys/sdslot.dat``).
        out_dir: Dossier qui reçoit les ``.bin`` et ``.binslot`` des slots demandés.
        slots: Numéros des slots à garder.

    Returns:
        Les noms des ``.bin`` écrits dans ``out_dir``.

    Raises:
        ConversionError: Si la conversion échoue, si une empreinte est fausse
            ou si aucun des slots demandés n'existe.
    """
    if not (vita_dir / SDSLOT).is_file():
        raise ConversionError(f"{SDSLOT.as_posix()} manquant dans {vita_dir}")
    with tempfile.TemporaryDirectory(prefix="vitasync-p4g-") as tmp:
        work = Path(tmp) / "vita"
        work.mkdir()
        for file in vita_dir.glob("*.bin"):
            shutil.copy2(file, work / file.name)
        (work / SDSLOT).parent.mkdir()
        shutil.copy2(vita_dir / SDSLOT, work / SDSLOT)

        converted = run_saveconv(saveconv, "convert_vita2pc.py", work)
        out_dir.mkdir(parents=True, exist_ok=True)
        written: list[str] = []
        for slot in slots:
            name = bin_name(slot)
            if not (converted / name).is_file():
                continue
            check_binslot(converted / name, converted / f"{name}slot")
            shutil.copy2(converted / name, out_dir / name)
            shutil.copy2(converted / f"{name}slot", out_dir / f"{name}slot")
            written.append(name)
    if not written:
        raise ConversionError("Aucun des slots demandés n'existe dans la sauvegarde Vita")
    return written


def pc_to_vita(
    saveconv: Path,
    pc_dir: Path,
    out_dir: Path,
    slots: Iterable[int],
    vita_sdslot: bytes | None,
) -> list[str]:
    """Convertit une sauvegarde Steam au format Vita.

    Tous les slots sont convertis (l'outil a besoin de tous les ``.binslot``
    pour construire ``sdslot.dat``), mais seuls les slots demandés sont
    copiés dans ``out_dir``.

    Args:
        saveconv: Dossier de l'outil p4g-saveconv.
        pc_dir: Dossier Steam ``remote`` (``.bin`` et ``.binslot``).
        out_dir: Dossier qui reçoit les ``.bin`` demandés et ``sce_sys/sdslot.dat``.
        slots: Numéros des slots à envoyer.
        vita_sdslot: ``sdslot.dat`` actuel de la Vita, pour ne remplacer que les
            entrées des slots demandés ; ``None`` pour prendre celui du PC en entier.

    Returns:
        Les noms des ``.bin`` écrits dans ``out_dir``.

    Raises:
        ConversionError: Si la conversion échoue, si un ``.binslot`` PC est
            incohérent ou si aucun des slots demandés n'existe.
    """
    slots = list(slots)
    with tempfile.TemporaryDirectory(prefix="vitasync-p4g-") as tmp:
        work = Path(tmp) / "pc"
        work.mkdir()
        for file in pc_dir.iterdir():
            if file.suffix in (".bin", ".binslot"):
                shutil.copy2(file, work / file.name)
        for slot in slots:
            name = bin_name(slot)
            if (work / name).is_file():
                check_binslot(work / name, work / f"{name}slot")

        converted = run_saveconv(saveconv, "convert_pc2vita.py", work)
        out_dir.mkdir(parents=True, exist_ok=True)
        written: list[str] = []
        for slot in slots:
            name = bin_name(slot)
            if (converted / name).is_file():
                shutil.copy2(converted / name, out_dir / name)
                written.append(name)
        if not written:
            raise ConversionError("Aucun des slots demandés n'existe dans la sauvegarde Steam")

        sdslot = (converted / SDSLOT).read_bytes()
        if vita_sdslot is not None:
            sdslot = merge_sdslot(vita_sdslot, sdslot, slots)
        (out_dir / SDSLOT).parent.mkdir(parents=True, exist_ok=True)
        (out_dir / SDSLOT).write_bytes(sdslot)
    return written


def write_remotecache(remote_dir: Path, vdf_path: Path) -> None:
    """Régénère ``remotecache.vdf`` pour tous les fichiers de ``remote``.

    Le jeu ne voit que les sauvegardes listées dans ce fichier. Chaque entrée
    donne la taille, la date et le SHA-1 du fichier.

    Args:
        remote_dir: Dossier Steam ``remote``.
        vdf_path: Fichier ``remotecache.vdf`` à écrire.
    """
    names = [bin_name(SYSTEM_SLOT)] + [bin_name(i) for i in range(1, MAX_SLOT + 1)]
    lines = [f'"{STEAM_APPID}"', "{"]
    for name in names:
        for file in (remote_dir / name, remote_dir / f"{name}slot"):
            if not file.is_file():
                continue
            stat = file.stat()
            mtime = math.floor(stat.st_mtime)
            sha = hashlib.sha1(file.read_bytes()).hexdigest()
            lines += [f'\t"{file.name}"', "\t{"]
            for key, value in (
                ("root", 0),
                ("size", stat.st_size),
                ("localtime", mtime),
                ("time", mtime),
                ("remotetime", mtime),
                ("sha", sha),
                ("syncstate", 4),
                ("persiststate", 0),
                ("platformstosync2", -1),
            ):
                lines.append(f'\t\t"{key}"\t\t"{value}"')
            lines.append("\t}")
    lines.append("}")
    partial = vdf_path.with_name(vdf_path.name + ".part")
    partial.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    partial.replace(vdf_path)
