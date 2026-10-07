"""Carousel pick choice: a per-seat picker fn(player, options) -> index.

Seats without a picker take the most expensive unit as before. A picker sees the units
still on the carousel (slot, name, cost, stars, item) when its turn comes, in carousel
order, and returns an index into that list. Pickers are set with
TFTConfig(carousel_pickers={seat: fn}) or env.unwrapped.set_carousel_picker(seat, fn) and
survive pickle.dumps(env) when the callable is picklable. TFTConfig(carousel_fixes=True)
shuffles which unit holds which item and uses the Set 4 fifth-carousel table.
"""

from __future__ import annotations

import contextlib
import io
import pickle

import numpy as np
import pytest

from Simulator import config
from Simulator.battle.combat_context import CombatContext
from Simulator.battle.item_stats import item_builds, starting_items
from Simulator.game import carousel as carousel_module
from Simulator.game.carousel import carousel, carousel_options, default_pick_index, generateHeldItems
from Simulator.game.player import Player
from Simulator.game.pool import pool
from Simulator.rng import EnvRNG
from Simulator.simulators.tft_simulator import TFTConfig, env as aec_env, parallel_env


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


# --- picklable pickers (module level) ---

def cheapest(player, options):
    return min(range(len(options)), key=lambda i: (options[i]["cost"], i))


def default_like(player, options):
    best = 0
    for i, option in enumerate(options):
        if option["cost"] > options[best]["cost"]:
            best = i
    return best


class Recorder:
    """Records what it was shown and takes the last option."""

    def __init__(self):
        self.calls = []

    def __call__(self, player, options):
        self.calls.append((player.player_num, player.round, [dict(o) for o in options]))
        return len(options) - 1


def _bench_units(player):
    return [(u.name, u.cost, tuple(u.items)) for u in player.bench if u]


# --- carousel() ---

def test_picker_chooses_and_sees_the_remaining_units():
    recorders = {f"player_{i}": Recorder() for i in range(8)}
    with _quiet(), CombatContext(rng=EnvRNG.from_episode_seed(4)).bind():
        base_pool = pool()
        players = [Player(base_pool, i) for i in range(8)]
        for player, hp in zip(players, [80, 90, 70, 60, 100, 50, 30, 95]):
            player.health = hp
        carousel(players, 6, base_pool, pickers=recorders)
    calls = sorted((c for r in recorders.values() for c in r.calls), key=lambda c: -len(c[2]))
    assert [len(c[2]) for c in calls] == [9, 8, 7, 6, 5, 4, 3, 2]
    first_options = calls[0][2]
    assert [o["slot"] for o in first_options] == list(range(9))
    assert sorted(o["cost"] for o in first_options) == [1, 2, 2, 2, 2, 3, 3, 3, 3]
    assert all(o["stars"] == 1 and o["item"] in starting_items + ["spatula"] for o in first_options)
    # Pick order is lowest HP first (pairs), and each picker took the last option shown.
    assert sorted(players[c[0]].health for c in calls[:2]) == [30, 50]
    for player_num, _, options in calls:
        taken = options[-1]
        assert _bench_units(players[player_num]) == [(taken["name"], taken["cost"], (taken["item"],))]
    # Each later list is the previous one without the unit taken.
    for (_, _, before), (_, _, after) in zip(calls, calls[1:]):
        assert after == before[:-1]


def test_seats_without_a_picker_take_the_most_expensive_unit():
    with _quiet(), CombatContext(rng=EnvRNG.from_episode_seed(4)).bind():
        base_pool = pool()
        players = [Player(base_pool, i) for i in range(8)]
        carousel(players, 12, base_pool, pickers={"player_3": cheapest})
    costs = {p.player_num: [u.cost for u in p.bench if u] for p in players}
    assert costs[3] == [1]
    assert sorted(c[0] for n, c in costs.items() if n != 3) == [2, 3, 3, 3, 4, 4, 4]


def test_default_like_picker_gives_the_same_carousel_as_no_picker():
    def run(pickers):
        with _quiet(), CombatContext(rng=EnvRNG.from_episode_seed(9)).bind() as ctx:
            base_pool = pool()
            players = [Player(base_pool, i) for i in range(8)]
            for r in (0, 6, 12, 18, 24, 30):
                carousel(players, r, base_pool, pickers=pickers)
            return [_bench_units(p) for p in players], ctx.rng.py.random()

    assert run({f"player_{i}": default_like for i in range(8)}) == run(None) == run({})


def test_default_pick_index_is_first_most_expensive():
    class Unit:
        def __init__(self, cost):
            self.cost = cost

    assert default_pick_index([Unit(c) for c in (1, 3, 2, 3)]) == 1
    assert default_pick_index([Unit(1)]) == 0


@pytest.mark.parametrize("bad", [9, -1, 1.0, "0", None, True])
def test_bad_pick_raises(bad):
    def picker(player, options):
        return bad

    with _quiet(), CombatContext(rng=EnvRNG.from_episode_seed(1)).bind():
        base_pool = pool()
        players = [Player(base_pool, 0)]
        with pytest.raises(ValueError):
            carousel(players, 0, base_pool, pickers={"player_0": picker})


def test_numpy_integer_pick_is_accepted():
    def picker(player, options):
        return np.int64(0)

    with _quiet(), CombatContext(rng=EnvRNG.from_episode_seed(1)).bind():
        base_pool = pool()
        player = Player(base_pool, 0)
        carousel([player], 0, base_pool, pickers={"player_0": picker})
    assert len(_bench_units(player)) == 1


# --- env ---

def test_env_config_and_setter_reach_the_first_carousel():
    recorder = Recorder()
    with _quiet():
        env = parallel_env(TFTConfig(carousel_pickers={2: recorder}))
        env.reset(seed=3)
        assert len(recorder.calls) == 1 and recorder.calls[0][0] == 2 and recorder.calls[0][1] == 0
        player = env.unwrapped.player_manager.player_states["player_2"]
        taken = recorder.calls[0][2][-1]
        units = [u for u in player.bench if u] + [u for col in player.board for u in col if u]
        assert any(u.name == taken["name"] and u.items[:1] == [taken["item"]] for u in units)

        other = Recorder()
        env.unwrapped.set_carousel_picker("player_5", other)
        env.unwrapped.set_carousel_picker(2, None)
        while env.unwrapped.game_round.current_round < 7:  # the 2-4 carousel is played at index 6
            env.step({agent: [0, 0, 0] for agent in env.agents})
        assert len(recorder.calls) == 1
        assert len(other.calls) == 1 and other.calls[0][1] == 6
        env.close()


def test_setter_validates():
    env = aec_env(TFTConfig())
    with pytest.raises(ValueError):
        env.unwrapped.set_carousel_picker("player_9", cheapest)
    with pytest.raises(TypeError):
        env.unwrapped.set_carousel_picker("player_1", "cheapest")


def _play(env, observations, rounds, seed):
    rng = np.random.RandomState(seed)
    trace = []
    while env.agents and env.unwrapped.game_round.current_round < rounds:
        actions = {}
        for agent in env.agents:
            legal = np.flatnonzero(observations[agent]["action_mask"])
            actions[agent] = int(legal[rng.randint(len(legal))])
        observations, rewards, _, _, _ = env.step(actions)
        states = env.unwrapped.player_manager.player_states
        trace.append((env.unwrapped.game_round.current_round, rewards,
                      {s: (p.gold, p.health, _bench_units(p)) for s, p in states.items() if p}))
    return trace, observations


def test_env_with_pickers_pickles_and_branches_identically():
    with _quiet():
        env = parallel_env(TFTConfig(carousel_pickers={0: cheapest}))
        observations, _ = env.reset(seed=8)
        env.unwrapped.set_carousel_picker("player_1", Recorder())
        _, observations = _play(env, observations, 4, seed=1)
        clone, clone_observations = pickle.loads(pickle.dumps((env, observations)))
        assert clone.unwrapped.carousel_pickers["player_0"] is cheapest
        assert clone.unwrapped.game_round.carousel_pickers is clone.unwrapped.carousel_pickers
        original_trace, _ = _play(env, observations, 13, seed=2)
        clone_trace, _ = _play(clone, clone_observations, 13, seed=2)
        assert original_trace == clone_trace
        # Both carousels after the branch point (indices 6 and 12) went through the picker copies.
        assert [c[1] for c in env.unwrapped.carousel_pickers["player_1"].calls] == [6, 12]
        assert [c[1] for c in clone.unwrapped.carousel_pickers["player_1"].calls] == [6, 12]
        env.close()
        clone.close()


def test_env_default_like_pickers_match_no_pickers():
    with _quiet():
        plain = parallel_env(TFTConfig())
        plain_observations, _ = plain.reset(seed=5)
        picked = parallel_env(TFTConfig(carousel_pickers={i: default_like for i in range(8)}))
        picked_observations, _ = picked.reset(seed=5)
        assert _play(plain, plain_observations, 13, seed=3)[0] == _play(picked, picked_observations, 13, seed=3)[0]


# --- carousel_fixes ---

def _held_items(seed, r, fixes):
    with CombatContext(rng=EnvRNG.from_episode_seed(seed)).bind():
        base_pool = pool()
        players = [Player(base_pool, i) for i in range(8)]
        seen = []

        def look(player, options):
            if not seen:
                seen.extend(options)
            return 0

        carousel(players, r, base_pool, pickers={f"player_{i}": look for i in range(8)}, shuffle_items=fixes)
        return seen


def test_items_follow_cost_order_without_fixes_and_are_shuffled_with_fixes():
    one_cost_items = {False: set(), True: set()}
    for fixes in (False, True):
        for seed in range(40):
            options = _held_items(seed, 6, fixes)
            one_cost = [o for o in options if o["cost"] == 1]
            one_cost_items[fixes].add(one_cost[0]["item"])
    # Without the shuffle the 1-cost at 2-4 holds the first item of the list (B.F. Sword in the
    # 80% "one of each" case, 95% with the spatula variant); with it, many different items.
    assert one_cost_items[False] <= {"bf_sword", "spatula"}
    assert len(one_cost_items[True]) >= 6


def test_fifth_carousel_table():
    full_items = set(item_builds)

    def share_all_components(fixes):
        hits = 0
        for seed in range(400):
            with CombatContext(rng=EnvRNG.from_episode_seed(seed)).bind():
                items = generateHeldItems(24, set4_fifth_carousel=fixes)
            hits += all(item not in full_items for item in items)
        return hits / 400

    assert share_all_components(False) == 0
    assert 0.43 < share_all_components(True) < 0.57
