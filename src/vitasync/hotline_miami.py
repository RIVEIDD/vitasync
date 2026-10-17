"""Format des sauvegardes de Hotline Miami et conversion PC <-> Vita.

Des deux côtés, ``SaveData.sav`` (256 Kio) est un conteneur de petits
fichiers texte :

    [en-tête] 0x01 { u32 longueur du nom, nom, u32 longueur, contenu }... EF BE AD DE, zéros

L'en-tête est vide sur PC et fait 52 octets sur Vita ; le jeu Vita ne le
vérifie pas (testé). Les fichiers communs (progression, succès,
statistiques) passent d'un côté à l'autre ; chaque côté garde les siens
(trophées sur Vita, réglages sur PC).
"""

import struct
from dataclasses import dataclass

SAVE_FILE = "SaveData.sav"
SAVE_SIZE = 0x40000
END_MARK = b"\xef\xbe\xad\xde"
START_MARK = 0x01
PROGRESS_ENTRY = "saves.dat"


class SaveFormatError(Exception):
    """Fichier SaveData.sav illisible."""


@dataclass(frozen=True)
class SaveContainer:
    """Contenu décodé d'un ``SaveData.sav``.

    Attributes:
        header: Octets avant le contenu (vide sur PC, 52 octets sur Vita).
        entries: Fichiers internes, par nom.
    """

    header: bytes
    entries: dict[str, bytes]


def _is_start(data: bytes, offset: int) -> bool:
    if data[offset] != START_MARK or offset + 5 > len(data):
        return False
    (length,) = struct.unpack_from("<I", data, offset + 1)
    name = data[offset + 5 : offset + 5 + length]
    return 0 < length < 64 and name.replace(b".", b"").replace(b"_", b"").isalnum()


def parse(data: bytes) -> SaveContainer:
    """Décode un ``SaveData.sav``.

    Args:
        data: Contenu du fichier.

    Returns:
        L'en-tête et les fichiers internes.

    Raises:
        SaveFormatError: Si le fichier ne suit pas le format attendu.
    """
    start = next((i for i in range(min(len(data), 0x100)) if _is_start(data, i)), None)
    if start is None:
        raise SaveFormatError("début du contenu introuvable")
    entries: dict[str, bytes] = {}
    pos = start + 1
    try:
        while data[pos : pos + 4] != END_MARK:
            (name_len,) = struct.unpack_from("<I", data, pos)
            name = data[pos + 4 : pos + 4 + name_len].decode("ascii")
            pos += 4 + name_len
            (size,) = struct.unpack_from("<I", data, pos)
            if pos + 4 + size > len(data):
                raise SaveFormatError(f"{name} dépasse la fin du fichier")
            entries[name] = data[pos + 4 : pos + 4 + size]
            pos += 4 + size
    except (struct.error, UnicodeDecodeError) as exc:
        raise SaveFormatError(f"contenu illisible ({exc})") from exc
    return SaveContainer(header=data[:start], entries=entries)


def build(container: SaveContainer) -> bytes:
    """Encode un ``SaveData.sav`` (fichiers triés par nom, comme le jeu).

    Args:
        container: En-tête et fichiers internes.

    Returns:
        Le contenu du fichier, complété par des zéros jusqu'à 256 Kio.

    Raises:
        SaveFormatError: Si le contenu dépasse 256 Kio.
    """
    out = bytearray(container.header)
    out.append(START_MARK)
    for name in sorted(container.entries):
        raw_name = name.encode("ascii")
        content = container.entries[name]
        out += struct.pack("<I", len(raw_name)) + raw_name
        out += struct.pack("<I", len(content)) + content
    out += END_MARK
    if len(out) > SAVE_SIZE:
        raise SaveFormatError("sauvegarde trop grande")
    return bytes(out.ljust(SAVE_SIZE, b"\0"))


def transfer(source: bytes, target: bytes) -> bytes:
    """Copie la progression de ``source`` dans la sauvegarde ``target``.

    Les fichiers présents des deux côtés viennent de ``source`` ; l'en-tête
    et les fichiers propres à ``target`` sont conservés.

    Args:
        source: ``SaveData.sav`` d'où vient la progression.
        target: ``SaveData.sav`` à mettre à jour (son en-tête est gardé).

    Returns:
        Le nouveau contenu de ``target``.

    Raises:
        SaveFormatError: Si l'un des fichiers est illisible.
    """
    src, dst = parse(source), parse(target)
    entries = dict(dst.entries)
    for name in src.entries.keys() & dst.entries.keys():
        entries[name] = src.entries[name]
    return build(SaveContainer(header=dst.header, entries=entries))


def progress(data: bytes) -> int:
    """Mesure l'avancement : nombre de niveaux débloqués.

    C'est le nombre de ``1`` dans les deux premières lignes de ``saves.dat``.

    Args:
        data: Contenu d'un ``SaveData.sav``.

    Returns:
        Le nombre de niveaux débloqués.

    Raises:
        SaveFormatError: Si le fichier est illisible ou sans ``saves.dat``.
    """
    entries = parse(data).entries
    if PROGRESS_ENTRY not in entries:
        raise SaveFormatError(f"{PROGRESS_ENTRY} absent")
    lines = entries[PROGRESS_ENTRY].split(b"\n")[:2]
    return sum(line.count(b"1") for line in lines)
