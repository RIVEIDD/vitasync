from pathlib import Path

import pytest

from vitasync.config import (
    DEFAULT_PORT,
    ConfigError,
    SteamConfig,
    VitaConfig,
    load_config,
    load_steam_config,
)


def write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(content, encoding="utf-8")
    return path


def test_charge_une_config_complete(tmp_path: Path) -> None:
    path = write(tmp_path, '[vita]\nhost = "192.168.1.42"\nport = 2121\ntimeout = 5\n')

    assert load_config(path) == VitaConfig(host="192.168.1.42", port=2121, timeout=5.0)


def test_port_par_defaut_de_vitashell(tmp_path: Path) -> None:
    path = write(tmp_path, '[vita]\nhost = "vita.local"\n')

    assert load_config(path).port == DEFAULT_PORT == 1337


def test_fichier_absent(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="introuvable"):
        load_config(tmp_path / "absent.toml")


@pytest.mark.parametrize(
    "content",
    [
        "pas du toml = = =",
        "[autre]\nhost = 'x'\n",
        "[vita]\nport = 1337\n",
        "[vita]\nhost = 'x'\nport = 70000\n",
        "[vita]\nhost = 'x'\nport = '1337'\n",
        "[vita]\nhost = 'x'\ntimeout = 0\n",
    ],
)
def test_config_invalide(tmp_path: Path, content: str) -> None:
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, content))


def test_charge_la_section_steam(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "[steam]\nuserdata = 'C:/Steam/userdata/125320760'\np4g_saveconv = 'outils/p4g-saveconv'\n",
    )

    assert load_steam_config(path) == SteamConfig(
        userdata=Path("C:/Steam/userdata/125320760"),
        p4g_saveconv=Path("outils/p4g-saveconv"),
    )


def test_steam_sans_saveconv(tmp_path: Path) -> None:
    path = write(tmp_path, "[steam]\nuserdata = 'C:/Steam/userdata/1'\n")

    assert load_steam_config(path).p4g_saveconv is None


@pytest.mark.parametrize(
    "content",
    [
        "[vita]\nhost = 'x'\n",
        "[steam]\nuserdata = ''\n",
        "[steam]\nuserdata = 'x'\np4g_saveconv = 3\n",
    ],
)
def test_section_steam_invalide(tmp_path: Path, content: str) -> None:
    with pytest.raises(ConfigError):
        load_steam_config(write(tmp_path, content))


def test_accepte_un_fichier_avec_bom(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[vita]\nhost = "192.168.1.5"\n', encoding="utf-8-sig")

    assert load_config(path).host == "192.168.1.5"
