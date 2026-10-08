"""A Zilean orb on a Guardian Angel holder must not leak into the item table.

items.initiate gave every Guardian Angel holder the `will_revive` list of the module-level item
table (item_stats.items["guardian_angel"]["will_revive"]) itself, and ability.zilean writes its orb
into that list in place. After the first fight in a process where a Zilean put an orb on a GA
holder, every later GA holder of every later fight in that process (any game) started with that
Zilean's orb: an extra revive, and Zilean skipping it as a target. A game's result then depended
on what the process had played before (long-lived workers vs. a fresh process).
"""

import pytest

from Simulator.battle import champion as champion_module
from Simulator.battle import item_stats
from Simulator.battle.combat_context import CombatContext, get_ctx
from Simulator.game.player import Player
from Simulator.game.pool import pool
from Simulator.rng import EnvRNG

GA = item_stats.items["guardian_angel"]


@pytest.fixture(autouse=True)
def restore_ga_table():
    """Start clean, and do not leave a polluted table (on the unfixed code) to the other tests."""
    GA["will_revive"] = [[None], ["guardian_angel"]]
    yield
    GA["will_revive"] = [[None], ["guardian_angel"]]


def _fight(blue_units, red_units, seed=1):
    """One combat between two fresh players; (result, end time, health of the survivors)."""
    base = pool("set4")
    players = Player(base, 0), Player(base, 1)
    for player, units in zip(players, (blue_units, red_units)):
        for x, y, name, stars, items in units:
            player.board[x][y] = champion_module.champion(name, stars=stars, itemlist=list(items))
        player.num_units_in_play = len(units)
    with CombatContext(rng=EnvRNG.from_episode_seed(seed)).bind():
        result = champion_module.run(champion_module.champion, *players, 0)
        ctx = get_ctx()
        survivors = sorted(round(u.health, 1) for u in list(ctx.blue) + list(ctx.red) if u.health > 0)
        return result, ctx.milliseconds, survivors


ZILEAN_AND_GA = [(0, 3, "zilean", 1, []), (3, 0, "garen", 1, ["guardian_angel"]), (2, 0, "nidalee", 1, [])]
WEAK_ENEMY = [(3, 0, "vayne", 1, []), (2, 0, "ashe", 1, [])]
LONE_GA = [(3, 0, "garen", 1, ["guardian_angel"])]
STRONG_ENEMY = [(3, 0, "vayne", 2, []), (2, 0, "ashe", 2, []), (4, 0, "warwick", 2, [])]


def test_each_holder_gets_its_own_will_revive():
    with CombatContext(rng=EnvRNG.from_episode_seed(1)).bind():
        a = champion_module.champion("garen", team="blue", itemlist=["guardian_angel"])
        b = champion_module.champion("garen", team="red", itemlist=["guardian_angel"])
        zilean = champion_module.champion("zilean", team="blue")
    assert a.will_revive == [[None], ["guardian_angel"]]
    assert a.will_revive is not GA["will_revive"] and a.will_revive[0] is not GA["will_revive"][0]
    a.will_revive[0][0] = zilean  # what ability.zilean does
    assert b.will_revive == [[None], ["guardian_angel"]]
    assert GA["will_revive"] == [[None], ["guardian_angel"]]


def test_zilean_orb_on_ga_holder_leaves_the_table_alone():
    _fight(ZILEAN_AND_GA, WEAK_ENEMY)
    assert GA["will_revive"] == [[None], ["guardian_angel"]]


def test_fight_does_not_depend_on_earlier_fights_in_the_process():
    clean = _fight(LONE_GA, STRONG_ENEMY)
    _fight(ZILEAN_AND_GA, WEAK_ENEMY)  # the Zilean orb lands on the Guardian Angel holder
    assert _fight(LONE_GA, STRONG_ENEMY) == clean
