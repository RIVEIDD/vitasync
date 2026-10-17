from pathlib import Path

import pytest

from vitasync.config import SteamConfig
from vitasync.paths import PathError, resolve_pc_path

STEAM = SteamConfig(userdata=Path("C:/Steam/userdata/42"))


def test_dossier_steam() -> None:
    expected = Path("C:/Steam/userdata/42/1113000/remote")
    assert resolve_pc_path("{steam_userdata}/1113000/remote", STEAM) == expected
    # Ancienne écriture, sans accolades : relative au dossier Steam.
    assert resolve_pc_path("1113000/remote", STEAM) == expected


def test_documents(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    resolved = resolve_pc_path("{documents}/My Games/HotlineMiami", None)
    assert resolved == tmp_path / "Documents" / "My Games" / "HotlineMiami"


def test_appdata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert resolve_pc_path("{appdata}/Balatro", None) == tmp_path / "Balatro"


def test_erreurs() -> None:
    with pytest.raises(PathError, match="inconnu"):
        resolve_pc_path("{bureau}/jeu", STEAM)
    with pytest.raises(PathError, match=r"\[steam\]"):
        resolve_pc_path("{steam_userdata}/1", None)
