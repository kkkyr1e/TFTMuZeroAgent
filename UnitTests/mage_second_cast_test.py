"""A mage's second cast needs a target, like the first one (champion.ability).

The first cast is skipped when no enemy can be targeted (the remaining enemies wait on a Guardian
Angel or Zilean revive), but the mage trait's second cast ran without that check: when the first
cast killed the target and the only enemies left were waiting on a revive, the second cast ran with
target None, and abilities that read the target crashed (ability.nunu: `champion.target.health`;
seen in a full game with a Mage's Cap Nunu against an Evelynn holding a Zilean orb). The last test is
a real fight that raised that AttributeError before the fix.
"""

from Simulator.battle import ability, field, origin_class
from Simulator.battle import champion as champion_module
from Simulator.battle.combat_context import CombatContext
from Simulator.game.player import Player
from Simulator.game.pool import pool
from Simulator.rng import EnvRNG


def _cast(monkeypatch, kills_target, retarget=None):
    """Run champion.ability for a Mage's Cap Nunu (a mage team) whose cast is a stub; returns the
    targets each cast saw."""
    seen = []

    def cast(ch):
        seen.append(ch.target)
        if kills_target:
            ch.target = None

    monkeypatch.setattr(ability, "nunu", cast)
    monkeypatch.setattr(origin_class, "get_origin_class_tier", lambda team, trait: 1 if trait == "mage" else 0)
    with CombatContext(rng=EnvRNG.from_episode_seed(1)).bind():
        nunu = champion_module.champion("nunu", team="red", stars=3, itemlist=["mages_cap"])
        enemy = champion_module.champion("evelynn", team="blue")
        other = champion_module.champion("vayne", team="blue")
        nunu.target = enemy
        monkeypatch.setattr(nunu, "enemy_team", lambda: [enemy])
        monkeypatch.setattr(field, "find_target", lambda c: setattr(c, "target", retarget and other) if retarget else None)
        nunu.ability()
    return [t and t.name for t in seen]


def test_no_second_cast_without_a_target(monkeypatch):
    assert _cast(monkeypatch, kills_target=True) == ["evelynn"]


def test_second_cast_retargets_when_another_enemy_is_there(monkeypatch):
    assert _cast(monkeypatch, kills_target=True, retarget=True) == ["evelynn", "vayne"]


def test_second_cast_on_the_same_target_when_it_survives(monkeypatch):
    assert _cast(monkeypatch, kills_target=False) == ["evelynn", "evelynn"]


def test_fight_where_the_first_cast_kills_a_lone_guardian_angel_holder():
    """Three mages (a Mage's Cap Nunu, Ahri, Annie) against a lone Guardian Angel Garen: Nunu's first
    cast kills Garen, who then waits on the revive and cannot be targeted, so the second cast has no
    target. The fight now runs to the end (red wins with all three units)."""
    base = pool()
    blue, red = Player(base, 0), Player(base, 1)
    blue.board[3][0] = champion_module.champion("garen", itemlist=["guardian_angel"])
    blue.num_units_in_play = 1
    for x, name, stars, items in [(3, "nunu", 2, ["mages_cap", "blue_buff"]), (0, "ahri", 1, []), (6, "annie", 1, [])]:
        red.board[x][0] = champion_module.champion(name, stars=stars, itemlist=items)
    red.num_units_in_play = 3
    with CombatContext(rng=EnvRNG.from_episode_seed(1)).bind():
        assert champion_module.run(champion_module.champion, blue, red, 0) == (2, 6)
