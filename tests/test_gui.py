from pathlib import Path

import pytest

# Certaines installations de Python (images Docker de la CI) n'ont pas Tkinter.
tk = pytest.importorskip("tkinter")

from vitasync import gui, service  # noqa: E402
from vitasync.config import VitaConfig  # noqa: E402
from vitasync.manifest import find_game  # noqa: E402
from vitasync.p4g_sync import SlotState  # noqa: E402
from vitasync.store import LocalStore  # noqa: E402


def test_format_progress() -> None:
    assert gui.format_progress(47 * 3600 + 40 * 60 + 34, in_levels=False) == "47:40:34"
    assert gui.format_progress(4, in_levels=True) == "4 niveaux"
    assert gui.format_progress(None, in_levels=False) == "-"


def test_slot_rows() -> None:
    status = service.GameStatus(
        find_game("p4g"), [SlotState(7, 20, 10)], in_levels=False, direction="push", slots=[7]
    )
    assert gui.slot_rows(status) == [("Slot 7", "0:00:20", "0:00:10", "PC")]
    hm = service.GameStatus(
        find_game("hotline_miami"), [SlotState(1, 2, 2)], True, direction=None, slots=[]
    )
    assert gui.slot_rows(hm) == [("Sauvegarde", "2 niveaux", "2 niveaux", "identiques")]


def test_la_fenetre_s_ouvre(tmp_path: Path) -> None:
    session = service.Session(
        vita=VitaConfig(host="127.0.0.1", port=1), steam=None, store=LocalStore(tmp_path)
    )
    try:
        window = gui.VitaSyncWindow(session)
    except tk.TclError:
        pytest.skip("pas d'écran disponible")
    try:
        assert set(window.games) == {"p4g", "hotline_miami"}
        assert window.game_list.item("p4g", "values") == ("?",)
        window.sync_selected()  # aucun jeu choisi : simple message dans le journal
        assert "Choisis un jeu" in window.log.get("1.0", "end")
    finally:
        window.destroy()
