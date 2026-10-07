"""TFTConfig(fortune_orbs=True): Fortune pays loot orbs instead of plain gold.

Set 4 Fortune pays an orb on a win against a player, worth on average the loss table
(2.5/6/10.5/17/24/31/38/45/55/70 gold after 0-9 losses, patch 10.21; the simulator's
90/115/145 for 10-12). The hidden loss counter counts each loss once and stops at 12;
6 Fortune adds an extra orb worth 11.65 gold on average. The contents are packages of
gold, champions, components, Neeko's Help (champion_duplicator) and Spatulas whose expected
gold value equals the table. Off (default) keeps the old ceil(table) gold payout.
"""

from __future__ import annotations

import contextlib
import io
import math

import pytest

from Simulator import config
from Simulator.battle.combat_context import CombatContext
from Simulator.battle.item_stats import starting_items
from Simulator.battle.origin_class_stats import fortune_returns
from Simulator.game import loot_orb
from Simulator.game.player import Player
from Simulator.game.pool import pool
from Simulator.rng import EnvRNG
from Simulator.simulators.tft_simulator import TFTConfig, parallel_env

TABLE_10_21 = (2.5, 6, 10.5, 17, 24, 31, 38, 45, 55, 70)


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


def test_table_matches_patch_10_21():
    assert loot_orb.FORTUNE_ORB_VALUES[:10] == TABLE_10_21
    assert loot_orb.FORTUNE_MAX_LOSSES == 12
    assert loot_orb.FORTUNE_EXTRA_ORB_VALUE == 11.65


@pytest.mark.parametrize("losses", range(13))
def test_every_package_is_worth_the_table_on_average(losses):
    value = loot_orb.FORTUNE_ORB_VALUES[losses]
    with CombatContext(rng=EnvRNG.from_episode_seed(losses)).bind():
        for kind in loot_orb.fortune_package_kinds(losses):
            draws = [loot_orb.fortune_orb_value(loot_orb._package(kind, value, loot_orb.FORTUNE_UNIT_COST[losses]))
                     for _ in range(3000)]
            # Only the gold remainder is random (floor or ceil), so every draw is within 1 gold
            # of the table value and the mean is the table value.
            assert all(abs(d - value) < 1 for d in draws), kind
            assert abs(sum(draws) / len(draws) - value) < 0.04, kind


@pytest.mark.parametrize("losses", range(13))
def test_orb_mean_and_contents(losses):
    value = loot_orb.FORTUNE_ORB_VALUES[losses]
    with CombatContext(rng=EnvRNG.from_episode_seed(100 + losses)).bind():
        orbs = [loot_orb.gen_fortune_orb(losses) for _ in range(3000)]
    assert abs(sum(map(loot_orb.fortune_orb_value, orbs)) / len(orbs) - value) < 0.04
    kinds = {atom[0] for orb in orbs for atom in orb}
    all_gold = sum(1 for orb in orbs if all(atom[0] == "gold" for atom in orb))
    if losses >= 4:
        assert all_gold == 0  # 10.20: no all-gold drops at higher losses
    else:
        assert all_gold > 0
    assert ("spatula" in kinds) == (losses >= 5)
    costs = {atom[1] for orb in orbs for atom in orb if atom[0] == "champion"}
    assert costs == {loot_orb.FORTUNE_UNIT_COST[losses]}
    if losses <= 4:
        assert 5 not in costs  # 10.21: no 5-cost at 4 losses
    assert max(sum(1 for atom in orb if atom[0] == "champion") for orb in orbs) <= loot_orb.FORTUNE_MAX_UNITS


def test_counter_is_capped_for_the_orb_lookup():
    with CombatContext(rng=EnvRNG.from_episode_seed(1)).bind():
        assert loot_orb.fortune_orb_value(loot_orb.gen_fortune_orb(40)) >= 145 - 1


def test_extra_orb_mean_and_contents():
    with CombatContext(rng=EnvRNG.from_episode_seed(7)).bind():
        orbs = [loot_orb.gen_fortune_extra_orb() for _ in range(40000)]
    assert abs(sum(map(loot_orb.fortune_orb_value, orbs)) / len(orbs) - 11.65) < 0.1
    assert not any(all(atom[0] == "gold" for atom in orb) for orb in orbs)  # 10.20: no all-gold drop
    jackpots = sum(1 for orb in orbs if orb == [("component",)] * loot_orb.FORTUNE_JACKPOT_COMPONENTS)
    assert 0.005 < jackpots / len(orbs) < 0.015
    assert any(("spatula",) in orb for orb in orbs) and any(("champion", 5) in orb for orb in orbs)


# --- Player ---

def _fortune_player(fortune_orbs, tier=1):
    base_pool = pool()
    player = Player(base_pool, 0)
    player.opponent = Player(base_pool, 1)
    player.fortune_orbs = fortune_orbs
    player.team_tiers['fortune'] = tier
    return player


def _lose(player, times):
    for _ in range(times):
        player.loss_round(5)


def test_orbs_paid_on_a_win_after_losses():
    with _quiet(), CombatContext(rng=EnvRNG.from_episode_seed(3)).bind():
        player = _fortune_player(True)
        _lose(player, 5)
        assert player.fortune_loss_streak == 5
        gold_before = player.gold
        player.won_round(5)
    assert player.fortune_loss_streak == 0
    (payout,) = player.fortune_orb_log
    assert payout["losses"] == 5 and len(payout["orbs"]) == 1
    orb = payout["orbs"][0]
    gold_in_orb = sum(atom[1] for atom in orb if atom[0] == "gold")
    units = [u for u in player.bench if u]
    items = [i for i in player.item_bench if i]
    assert player.gold == gold_before + 1 + gold_in_orb  # 1 = PvP win gold
    assert len(units) == sum(1 for atom in orb if atom[0] == "champion")
    assert len(items) == sum(1 for atom in orb if atom[0] in ("component", "neekos_help", "spatula"))


def test_six_fortune_counts_each_loss_once_and_adds_an_extra_orb():
    with _quiet(), CombatContext(rng=EnvRNG.from_episode_seed(4)).bind():
        player = _fortune_player(True, tier=2)
        _lose(player, 3)
        assert player.fortune_loss_streak == 3
        player.won_round(5)
    assert len(player.fortune_orb_log[0]["orbs"]) == 2


def test_counter_stops_at_twelve():
    with _quiet(), CombatContext(rng=EnvRNG.from_episode_seed(5)).bind():
        player = _fortune_player(True)
        _lose(player, 20)
    assert player.fortune_loss_streak == 12


@pytest.mark.parametrize("losses", [0, 1, 4, 9, 12, 14])
def test_option_off_keeps_the_gold_payout(losses):
    with _quiet(), CombatContext(rng=EnvRNG.from_episode_seed(6)).bind():
        player = _fortune_player(False)
        _lose(player, losses)
        player.won_round(5)
    if losses >= len(fortune_returns):
        expected = math.ceil(fortune_returns[-1] + 15 * (losses - len(fortune_returns)))
    else:
        expected = math.ceil(fortune_returns[losses])
    assert player.gold == 1 + expected
    assert player.fortune_orb_log == [] and player.fortune_loss_streak == 0


def test_option_off_six_fortune_still_counts_double():
    with _quiet(), CombatContext(rng=EnvRNG.from_episode_seed(6)).bind():
        player = _fortune_player(False, tier=2)
        _lose(player, 3)
    assert player.fortune_loss_streak == 6


def test_no_fortune_no_orb():
    with _quiet(), CombatContext(rng=EnvRNG.from_episode_seed(6)).bind():
        player = _fortune_player(True, tier=0)
        _lose(player, 3)
        player.won_round(5)
    assert player.fortune_orb_log == [] and player.gold == 1


def test_give_fortune_orb_delivery():
    with _quiet(), CombatContext(rng=EnvRNG.from_episode_seed(8)).bind():
        player = _fortune_player(True)
        player.item_pool = []  # an empty item pool is refilled, not an error
        loot_orb.give_fortune_orb(player, [("champion", 5), ("component",), ("neekos_help",), ("spatula",),
                                           ("gold", 4)])
        assert player.gold == 4
        assert [u.cost for u in player.bench if u] == [5]
        items = [i for i in player.item_bench if i]
        assert items[1:] == ["champion_duplicator", "spatula"] and items[0] in starting_items
        # A full bench turns champions into their cost in gold.
        player.bench = [object()] * 9
        loot_orb.give_fortune_orb(player, [("champion", 3)])
        assert player.gold == 7


def test_env_passes_the_option_to_every_player():
    with _quiet():
        for flag in (False, True):
            env = parallel_env(TFTConfig(fortune_orbs=flag))
            env.reset(seed=1)
            assert {p.fortune_orbs for p in env.unwrapped.player_manager.player_states.values()} == {flag}
            env.close()
