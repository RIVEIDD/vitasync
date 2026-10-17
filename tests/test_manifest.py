import pytest

from vitasync.manifest import ManifestError, builtin_manifests, find_game, parse_manifest

VALID = """
id: demo
name: Jeu de démo
adapter: passthrough
pc:
  path: Saves/Demo
vita:
  title_id: PCSB00000
  path: ux0:data/demo
"""


def test_parse_manifest_sans_steam() -> None:
    manifest = parse_manifest(VALID)

    assert manifest.id == "demo"
    assert manifest.pc.path == "Saves/Demo"
    assert manifest.pc.steam_appid is None
    assert manifest.vita.path == "ux0:data/demo"


def test_fiche_p4g_livree() -> None:
    p4g = find_game("p4g")

    assert p4g.name == "Persona 4 Golden"
    assert p4g.pc.steam_appid == 1113000
    assert p4g.vita.title_id == "PCSB00245"
    assert "p4g" in builtin_manifests()


def test_jeu_inconnu() -> None:
    with pytest.raises(ManifestError, match="Jeu inconnu : zelda.*p4g"):
        find_game("zelda")


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("id: [", "YAML invalide"),
        ("- une liste", "dictionnaire"),
        (VALID.replace("name: Jeu de démo\n", ""), "name"),
        (VALID.replace("vita:", "autre:"), "vita"),
        (
            VALID.replace("  path: Saves/Demo\n", "  path: Saves/Demo\n  steam_appid: abc\n"),
            "entier",
        ),
    ],
)
def test_fiche_invalide(text: str, message: str) -> None:
    with pytest.raises(ManifestError, match=message):
        parse_manifest(text)
