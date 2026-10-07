"""TFTConfig(pve_damage=True): losing a PvE round costs HP like a player combat.

Game_Round called minion.minion_round without other_rewards, and minion_combat only applied
damage when other_rewards was truthy, so a lost monster round cost nothing. With
pve_damage the loser takes the fight's damage: stage damage plus damage per surviving
monster (champion.unit_damage, Set 4: 2 per unit for the first five). Streaks, match
history and the Fortune counter are left alone (monster rounds are streak-neutral).
The default (pve_damage=False) keeps the old behaviour.
"""

from __future__ import annotations

import contextlib
import io

import numpy as np
import pytest

from Simulator import config
from Simulator.battle import champion as champion_module
from Simulator.battle import minion
from Simulator.battle.combat_context import CombatContext
from Simulator.game.game_round import Game_Round
from Simulator.game.player import Player
from Simulator.game.pool import pool
from Simulator.rng import EnvRNG
from Simulator.simulators.tft_simulator import TFTConfig, parallel_env


@contextlib.contextmanager
def _quiet():
    import Simulator.game.player as player_module
    saved = (config.DEBUG, config.PRINTMESSAGES, config.LOGMESSAGES, player_module.DEBUG)
    config.DEBUG = config.PRINTMESSAGES = config.LOGMESSAGES = False
    player_module.DEBUG = False
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            yield
    finally:
        config.DEBUG, config.PRINTMESSAGES, config.LOGMESSAGES, player_module.DEBUG = saved


def _fixed_result(monkeypatch, index_won, damage):
    seen = []

    def fake_run(champion_q, player_1, player_2, round_damage=0):
        seen.append(round_damage)
        return index_won, damage

    monkeypatch.setattr(champion_module, "run", fake_run)
    return seen


@pytest.mark.parametrize("index_won,damage", [(2, 9), (0, 3)], ids=["loss", "draw"])
def test_pve_loss_costs_the_fight_damage(monkeypatch, index_won, damage):
    _fixed_result(monkeypatch, index_won, damage)
    with _quiet(), CombatContext(rng=EnvRNG.from_episode_seed(1)).bind():
        player = Player(pool(), 0)
        player.win_streak, player.loss_streak, player.fortune_loss_streak = 3, 0, 2
        history = list(player.match_history)
        assert minion.minion_round(player, 14, [player], pve_damage=True) is False
    assert player.health == 100 - damage
    assert player.reward == -damage
    # Streak-neutral
    assert (player.win_streak, player.loss_streak, player.fortune_loss_streak) == (3, 0, 2)
    assert player.match_history == history


def test_default_pve_loss_costs_nothing(monkeypatch):
    _fixed_result(monkeypatch, 2, 9)
    with _quiet(), CombatContext(rng=EnvRNG.from_episode_seed(1)).bind():
        player = Player(pool(), 0)
        assert minion.minion_round(player, 14, [player]) is False
    assert player.health == 100 and player.reward == 0


def test_pve_win_costs_nothing(monkeypatch):
    _fixed_result(monkeypatch, 1, 9)
    with _quiet(), CombatContext(rng=EnvRNG.from_episode_seed(1)).bind():
        player = Player(pool(), 0)
        assert minion.minion_round(player, 14, [player], pve_damage=True) is True
    assert player.health == 100


# (round index, monsters on the board, Set 4 stage damage)
EMPTY_BOARD_LOSSES = [(0, 2, 0), (8, 3, 0), (14, 5, 2), (20, 5, 3), (26, 1, 5), (32, 1, 8)]


@pytest.mark.parametrize("round_index,monsters,stage_damage", EMPTY_BOARD_LOSSES,
                         ids=[str(r[0]) for r in EMPTY_BOARD_LOSSES])
def test_empty_board_loses_stage_plus_unit_damage(round_index, monsters, stage_damage):
    """A real fight (no fake run): an empty board loses to every surviving monster."""
    with _quiet(), CombatContext(rng=EnvRNG.from_episode_seed(1)).bind():
        base_pool = pool()
        player = Player(base_pool, 0)
        game_round = Game_Round({"player_0": player}, base_pool, None, pve_damage=True)
        game_round.current_round = round_index
        if round_index == 0:
            minion.minion_round(player, 0, [player], pve_damage=True)
        else:
            game_round.minion_round()
    assert player.health == 100 - (stage_damage + 2 * monsters)


def _play_stage_one(pve_damage, seed):
    """Pass through 1-2, 1-3 and 1-4 and record each player's PvE results."""
    results = []
    original_run = champion_module.run

    def run(champion_q, player_1, player_2, round_damage=0):
        outcome = original_run(champion_q, player_1, player_2, round_damage)
        results.append((player_1.player_num, outcome))
        return outcome

    champion_module.run = run
    try:
        with _quiet():
            env = parallel_env(TFTConfig(pve_damage=pve_damage))
            env.reset(seed=seed)
            while env.unwrapped.game_round.current_round < 3:
                env.step({agent: [0, 0, 0] for agent in env.agents})
            health = {seat: p.health for seat, p in env.unwrapped.player_manager.player_states.items()}
            env.close()
    finally:
        champion_module.run = original_run
    return results, health


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_env_stage_one_health_follows_the_pve_results(seed):
    results, health = _play_stage_one(True, seed)
    assert len(results) == 3 * 8
    lost = {f"player_{i}": 0 for i in range(8)}
    for player_num, (index_won, damage) in results:
        if index_won != 1:
            lost[f"player_{player_num}"] += damage
    assert health == {seat: 100 - lost[seat] for seat in lost}


def test_env_default_stage_one_keeps_full_health():
    results, health = _play_stage_one(False, 1)
    assert len(results) == 3 * 8
    assert set(health.values()) == {100}


def test_some_stage_one_fight_is_lost():
    """Guard for the env test above: passing players do lose some stage-1 fights."""
    lost = 0
    for seed in (1, 2, 3):
        results, _ = _play_stage_one(True, seed)
        lost += sum(1 for _, (index_won, damage) in results if index_won != 1 and damage > 0)
    assert lost > 0
