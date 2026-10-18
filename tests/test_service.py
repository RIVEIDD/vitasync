from dataclasses import replace
from pathlib import Path

import pytest

from vitasync import service
from vitasync.manifest import find_game
from vitasync.p4g_sync import SlotState, SyncError, plan_sync


def status(states: list[SlotState], in_levels: bool = False) -> service.GameStatus:
    game = find_game("hotline_miami" if in_levels else "p4g")
    try:
        direction, slots = plan_sync(states)
    except SyncError as exc:
        return service.GameStatus(game, states, in_levels, None, [], conflict=str(exc))
    return service.GameStatus(game, states, in_levels, direction, slots)


def test_resume_et_annonce() -> None:
    assert status([SlotState(1, 10, 10)]).summary == "Identiques"
    push = status([SlotState(7, 20, 10)])
    assert push.summary == "Plus avancé sur PC"
    assert service.describe_plan(push) == "Plus avancé sur PC : push des slots 7."
    pull = status([SlotState(1, 1, 4)], in_levels=True)
    assert service.describe_plan(pull) == "Plus avancé sur Vita : pull."
    conflict = status([SlotState(1, 20, 10), SlotState(2, 1, 5)])
    assert conflict.summary.startswith("Conflit")


def test_open_session(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text('[vita]\nhost = "192.168.1.5"\n', encoding="utf-8")

    session = service.open_session(config, port=1340, store_path=tmp_path / "store")

    assert session.vita.host == "192.168.1.5"
    assert session.vita.port == 1340
    assert session.steam is None


def test_jeu_non_pris_en_charge() -> None:
    game = replace(find_game("p4g"), adapter="inconnu")
    with pytest.raises(SyncError, match="pas encore pris en charge"):
        service.check_supported(game)
