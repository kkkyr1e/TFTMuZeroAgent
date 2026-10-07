"""Economy rules profiles: TFTConfig(rules="set4" | "set18").

Every table is checked under both profiles against literal values (the Set 18 values and
their sources are listed in FORK_NOTES.md, "Rules profiles"). Champions, traits, items and
combat are Set 4 in both profiles; only the economy differs.

Round indices: idx0 = 1-1 carousel + 1-2 PvE, idx1 = 1-3, idx2 = 1-4, then six indices
per stage from idx3 = 2-1.
"""

from __future__ import annotations

import numpy as np
import pytest

from Simulator.battle import champion as champion_module
from Simulator.battle import minion
from Simulator.battle.combat_context import CombatContext
from Simulator.battle.stats import COST
from Simulator.encoding.token.action import ActionToken
from Simulator.encoding.token.basic_observation import ObservationToken
from Simulator.game import pool_stats
from Simulator.game.game_round import Game_Round
from Simulator.game.player import Player
from Simulator.game.pool import pool
from Simulator.game.rules import SET4, SET18, get_rules
from Simulator.rng import EnvRNG
from Simulator.simulators.tft_simulator import TFTConfig, parallel_env
from Simulator.simulators.tft_single_player_simulator import TFT_Single_Player_Simulator

PROFILES = ("set4", "set18")

# Shop odds in percent by level, cost 1..5.
SHOP = {
    "set4": {
        1: (100, 0, 0, 0, 0), 2: (100, 0, 0, 0, 0), 3: (75, 25, 0, 0, 0), 4: (55, 30, 15, 0, 0),
        5: (45, 32.5, 20, 2.5, 0), 6: (25, 40, 30, 5, 0), 7: (20, 30, 35, 14, 1),
        8: (15, 20, 35, 25, 5), 9: (10, 15, 30, 30, 15),
    },
    "set18": {
        1: (100, 0, 0, 0, 0), 2: (100, 0, 0, 0, 0), 3: (75, 25, 0, 0, 0), 4: (55, 30, 15, 0, 0),
        5: (45, 33, 20, 2, 0), 6: (30, 40, 25, 5, 0), 7: (19, 30, 40, 10, 1),
        8: (15, 20, 32, 30, 3), 9: (10, 17, 25, 33, 15), 10: (5, 10, 20, 40, 25),
    },
}
POOL_COPIES = {"set4": (29, 22, 18, 12, 10), "set18": (30, 25, 18, 10, 9)}
# XP to go from level i to i + 1, for i = 1 .. max_level - 1
XP = {"set4": (2, 2, 6, 10, 20, 36, 56, 80), "set18": (2, 2, 6, 10, 20, 36, 56, 68, 68)}
MAX_LEVEL = {"set4": 9, "set18": 10}
# Gold by streak length 0..9 (win or loss)
STREAK = {"set4": (0, 0, 1, 1, 2, 3, 3, 3, 3, 3), "set18": (0, 0, 1, 1, 1, 2, 3, 3, 3, 3)}
# Base player damage for stages 1..8
STAGE_DAMAGE = {"set4": (0, 0, 2, 3, 5, 8, 15, 15), "set18": (0, 2, 6, 7, 10, 12, 17, 150)}
# Extra damage for 1..10 surviving enemy units
UNIT_DAMAGE = {"set4": (2, 4, 6, 8, 10, 11, 12, 13, 14, 15), "set18": (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)}
PVE_ROUNDS = (0, 1, 2, 8, 14, 20, 26, 32, 38)


def _stage(round_index):
    return 1 if round_index <= 2 else (round_index - 3) // 6 + 2


def _bound(seed=1):
    return CombatContext(rng=EnvRNG.from_episode_seed(seed)).bind()


# --- profile selection ---

def test_default_profile_is_set4():
    assert TFTConfig().rules == "set4"
    assert get_rules(None) is SET4 and get_rules("set4") is SET4 and get_rules("SET18") is SET18
    with _bound():
        base_pool = pool()
        player = Player(base_pool, 0)
        assert base_pool.rules is SET4 and player.rules is SET4
        assert Game_Round({"player_0": player}, base_pool, None).rules is SET4


def test_unknown_profile_is_rejected():
    with pytest.raises(ValueError):
        get_rules("set99")
    with pytest.raises(ValueError):
        parallel_env(TFTConfig(rules="set99"))


@pytest.mark.parametrize("rules", PROFILES)
def test_env_passes_the_profile_to_pool_players_and_rounds(rules):
    env = parallel_env(TFTConfig(rules=rules))
    env.reset(seed=1)
    unwrapped = env.unwrapped
    profile = get_rules(rules)
    assert unwrapped.pool_obj.rules is profile
    assert unwrapped.game_round.rules is profile
    for player in unwrapped.player_manager.player_states.values():
        assert player.rules is profile and player.max_level == MAX_LEVEL[rules]
    env.close()

    single = TFT_Single_Player_Simulator(TFTConfig(num_players=1, rules=rules))
    single.reset(seed=1)
    assert single.PLAYER.rules is profile
    assert single.game_round.rules is profile


# --- shop odds ---

def _percent_row(thresholds):
    capped = [min(t, 1.0) for t in thresholds]
    row, previous = [], 0.0
    for value in capped:
        row.append(round((value - previous) * 1000) / 10)
        previous = value
    return tuple(row)


@pytest.mark.parametrize("rules", PROFILES)
def test_shop_odds_table(rules):
    profile = get_rules(rules)
    for level in range(1, MAX_LEVEL[rules] + 1):
        assert _percent_row(profile.shop_odds[level]) == SHOP[rules][level], level
        assert len(profile.chosen_odds[level]) == 5, level  # Chosen odds exist up to max level


def test_set18_level_11_row_is_kept_for_effects_that_raise_max_level():
    assert _percent_row(SET18.shop_odds[11]) == (1, 2, 12, 50, 35)


@pytest.mark.parametrize("rules,level", [("set4", 7), ("set18", 7), ("set18", 8), ("set18", 10)])
def test_shop_samples_follow_the_odds(rules, level):
    shops = 3000
    counts = np.zeros(5)
    with _bound(3):
        base_pool = pool(rules)
        player = Player(base_pool, 0)
        player.level = level
        for _ in range(shops):
            for name in base_pool.sample(player, 5, allow_chosen=False):
                counts[COST[name] - 1] += 1
    observed = 100 * counts / counts.sum()
    expected = np.array(SHOP[rules][level], dtype=float)
    assert np.all(np.abs(observed - expected) < 1.5), (observed, expected)
    assert np.all(counts[expected == 0] == 0)


# --- pool ---

@pytest.mark.parametrize("rules", PROFILES)
def test_pool_copies_per_champion_by_cost(rules):
    with _bound():
        base_pool = pool(rules)
    rosters = (pool_stats.COST_1, pool_stats.COST_2, pool_stats.COST_3, pool_stats.COST_4, pool_stats.COST_5)
    live = (base_pool.COST_1, base_pool.COST_2, base_pool.COST_3, base_pool.COST_4, base_pool.COST_5)
    totals = (base_pool.num_cost_1, base_pool.num_cost_2, base_pool.num_cost_3, base_pool.num_cost_4,
              base_pool.num_cost_5)
    for cost, (roster, counts, total) in enumerate(zip(rosters, live, totals)):
        assert list(counts) == list(roster)  # the Set 4 roster is kept
        assert set(counts.values()) == {POOL_COPIES[rules][cost]}
        assert total == POOL_COPIES[rules][cost] * len(roster)


@pytest.mark.parametrize("rules", PROFILES)
def test_pool_never_holds_more_than_the_profile_copies(rules):
    with _bound():
        base_pool = pool(rules)
        unit = champion_module.champion("ahri")  # 4-cost
        base_pool.update_pool(unit, -1)
        assert base_pool.COST_4["ahri"] == POOL_COPIES[rules][3] - 1
        base_pool.update_pool(unit, 1)
        base_pool.update_pool(unit, 1)
        assert base_pool.COST_4["ahri"] == POOL_COPIES[rules][3]


# --- XP ---

@pytest.mark.parametrize("rules", PROFILES)
def test_xp_table_and_max_level(rules):
    with _bound():
        player = Player(pool(rules), 0)
    assert player.max_level == MAX_LEVEL[rules]
    assert tuple(player.level_costs[1:player.max_level]) == XP[rules]
    assert (player.refresh_cost, player.exp_cost) == (2, 4)


@pytest.mark.parametrize("rules", PROFILES)
def test_buying_xp_reaches_max_level_and_stops(rules):
    with _bound():
        player = Player(pool(rules), 0)
        player.gold = 1000
        purchases = 0
        while player.buy_exp_action():
            purchases += 1
    # 4 gold buys 4 XP and leftover XP carries over, so it takes total XP / 4 purchases.
    assert purchases == sum(XP[rules]) // 4
    assert (player.level, player.exp, player.gold) == (MAX_LEVEL[rules], 0, 1000 - 4 * purchases)
    assert player.max_units == MAX_LEVEL[rules]


@pytest.mark.parametrize("rules", PROFILES)
def test_passive_xp_is_two_per_round(rules):
    with _bound():
        player = Player(pool(rules), 0)
        levels = []
        for round_index in range(12):
            player.gold_income(round_index)
            levels.append((player.level, player.exp))
    # Same schedule in both profiles: level 2 at 1-2, 3 at 1-3, 4 at 2-2, 5 at 3-1 without buying XP.
    assert levels[:5] == [(2, 0), (3, 0), (3, 2), (3, 4), (4, 0)]
    assert levels[9] == (5, 0)


# --- gold ---

@pytest.mark.parametrize("rules", PROFILES)
def test_passive_gold_by_round(rules):
    with _bound():
        paid = []
        for round_index in range(6):
            player = Player(pool(rules), 0)
            player.gold_income(round_index)
            paid.append(player.gold)
    assert paid == [2, 2, 3, 4, 5, 5]


@pytest.mark.parametrize("rules", PROFILES)
def test_interest_is_one_per_ten_gold_up_to_five(rules):
    with _bound():
        for gold in (0, 9, 10, 19, 25, 49, 50, 59, 99, 150):
            player = Player(pool(rules), 0)
            player.gold = gold
            player.gold_income(10)
            assert player.gold == gold + min(gold // 10, 5) + 5, gold


@pytest.mark.parametrize("rules", PROFILES)
@pytest.mark.parametrize("side", ("win_streak", "loss_streak"))
def test_streak_gold(rules, side):
    with _bound():
        for streak, bonus in enumerate(STREAK[rules]):
            player = Player(pool(rules), 0)
            setattr(player, side, streak)
            player.gold_income(10)
            assert player.gold == 5 + bonus, (side, streak)


@pytest.mark.parametrize("rules", PROFILES)
def test_pvp_win_pays_one_gold(rules):
    with _bound():
        base_pool = pool(rules)
        player, other = Player(base_pool, 0), Player(base_pool, 1)
        player.opponent = other
        player.won_round(0)
        assert player.gold == 1
        player.combat = False
        player.won_ghost()
        assert player.gold == 2


# --- player damage ---

def _record_base_damage(monkeypatch):
    seen = []

    def fake_run(champion_q, player_1, player_2, round_damage=0):
        seen.append(round_damage)
        return 1, round_damage

    monkeypatch.setattr(champion_module, "run", fake_run)
    return seen


@pytest.mark.parametrize("rules", PROFILES)
def test_base_damage_by_stage_in_player_combat(monkeypatch, rules):
    seen = _record_base_damage(monkeypatch)
    with _bound():
        base_pool = pool(rules)
        players = {"player_0": Player(base_pool, 0), "player_1": Player(base_pool, 1)}
        game_round = Game_Round(players, base_pool, None)
        game_round.matchups = [["player_0", "player_1"]]
        for round_index in range(44):
            game_round.combat_phase(players, round_index)
    assert seen == [STAGE_DAMAGE[rules][_stage(r) - 1] for r in range(44)]
    assert [get_rules(rules).stage_damage(r) for r in range(44)] == seen


@pytest.mark.parametrize("rules", PROFILES)
def test_base_damage_by_stage_in_pve(monkeypatch, rules):
    seen = _record_base_damage(monkeypatch)
    with _bound():
        for round_index in PVE_ROUNDS:
            minion.minion_round(Player(pool(rules), 0), round_index)
    assert seen == [STAGE_DAMAGE[rules][_stage(r) - 1] for r in PVE_ROUNDS]


def _board_with(player, units):
    for i in range(units):
        player.board[i % 7][i // 7] = champion_module.champion("garen")
    player.num_units_in_play = units


@pytest.mark.parametrize("rules", PROFILES)
def test_damage_per_surviving_unit(rules):
    with _bound():
        base_pool = pool(rules)
        for units in range(1, 11):
            winner, loser = Player(base_pool, 0), Player(base_pool, 1)
            _board_with(winner, units)
            assert champion_module.run(champion_module.champion, winner, loser, 0) == (1, UNIT_DAMAGE[rules][units - 1])
            assert champion_module.run(champion_module.champion, loser, winner, 0) == (2, UNIT_DAMAGE[rules][units - 1])


@pytest.mark.parametrize("rules,expected", [("set4", 2 + 6), ("set18", 6 + 3)])
def test_damage_taken_per_loss(rules, expected):
    """3 surviving enemy units at 3-1 (idx 9): stage damage plus unit damage comes off the loser's HP."""
    with _bound():
        base_pool = pool(rules)
        players = {"player_0": Player(base_pool, 0), "player_1": Player(base_pool, 1)}
        _board_with(players["player_0"], 3)
        game_round = Game_Round(players, base_pool, None)
        game_round.matchups = [["player_0", "player_1"]]
        game_round.combat_phase(players, 9)
    assert players["player_1"].health == 100 - expected
    assert players["player_0"].health == 100
    assert players["player_0"].gold == 1  # PvP win gold


# --- observations at the Set 18 max level ---

def test_set18_level_10_is_observable_and_masks_buy_xp():
    with _bound():
        player = Player(pool("set18"), 0)
        player.gold = 1000
        while player.buy_exp_action():
            pass
        assert player.level == 10
        observation = ObservationToken(player)
        assert observation.create_embedding_scalars(player)[-1] == 10
        assert not ActionToken(player).create_exp_action_mask(player)
