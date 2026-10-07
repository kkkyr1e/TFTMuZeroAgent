"""TFTConfig(rng_streams="keyed"): independent random streams per seat and event.

With "shared" (default) every draw comes from one stream, so one extra draw (a seat's extra
shop refresh) reshuffles every later shop, carousel, pairing and fight of every seat. With
"keyed" shops (per seat, round and refresh index), planning actions (per seat, round and
action index), start-of-round effects, pairings and carousels (per round), fights (per round
and matchup), PvE fights, loot and Fortune orbs (per seat and round) each draw from their own
stream, and the rule bot gets a generator per seat. env.unwrapped.reseed_rng(seed) re-seeds
all streams of a (restored) env.
"""

from __future__ import annotations

import contextlib
import io
import os
import pickle
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from Simulator import config
from Simulator.battle.combat_context import CombatContext, get_ctx
from Simulator.game.player import Player
from Simulator.game.pool import pool
from Simulator.rng import EnvRNG, KeyedStreams, STREAM_SHOP
from Simulator.simulators.tft_simulator import TFTConfig, env as aec_env, parallel_env

REPO_ROOT = Path(__file__).resolve().parents[1]
PASS = [0, 0, 0]
REFRESH = [2, 0, 0]


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


def _seat_state(player):
    board = sorted((x, y, u.name, u.stars, tuple(u.items)) for x, col in enumerate(player.board)
                   for y, u in enumerate(col) if u)
    bench = [(u.name, u.stars) if u else None for u in player.bench]
    return (tuple(player.shop), player.health, player.gold, player.level, player.exp,
            tuple(player.item_bench), tuple(board), tuple(bench))


def _extra_refresh_branches(mode, seed=3, refresh_round=5, last_round=9):
    """Two games from one seed: seat 0 passes throughout, except that in the second it refreshes
    once at the start of refresh_round. The other seats take random legal actions from their own
    RandomState, so they act alike as long as their own state is alike.
    Returns, per game, [(round, step in round, {seat: state})] from refresh_round on."""
    traces = []
    for extra in (False, True):
        env = parallel_env(TFTConfig(rng_streams=mode))
        observations, _ = env.reset(seed=seed)
        rngs = {agent: np.random.RandomState(100 + i) for i, agent in enumerate(env.agents)}
        trace = []
        step_in_round, last = 0, env.unwrapped.game_round.current_round
        while env.agents and env.unwrapped.game_round.current_round < last_round:
            current = env.unwrapped.game_round.current_round
            if current != last:
                step_in_round, last = 0, current
            states = env.unwrapped.player_manager.player_states
            if current >= refresh_round:
                trace.append((current, step_in_round, {s: _seat_state(p) for s, p in states.items() if p}))
            actions = {}
            for agent in env.agents:
                if agent == "player_0":
                    first = extra and current == refresh_round and step_in_round == 0
                    actions[agent] = REFRESH if first else PASS
                else:
                    legal = np.flatnonzero(observations[agent]["action_mask"])
                    actions[agent] = int(legal[rngs[agent].randint(len(legal))])
            observations, *_ = env.step(actions)
            step_in_round += 1
        traces.append(trace)
        env.close()
    return traces


def test_keyed_extra_refresh_leaves_other_seats_unchanged():
    with _quiet():
        plain, refreshed = _extra_refresh_branches("keyed")
    assert len(plain) == len(refreshed) == 4 * 15
    differences = set()
    for (round_a, step_a, seats_a), (round_b, step_b, seats_b) in zip(plain, refreshed):
        assert (round_a, step_a) == (round_b, step_b)
        assert seats_a.keys() == seats_b.keys()
        for seat in seats_a:
            if seat != "player_0":
                # Rounds r .. r+3: every other seat's shop, board, bench, items, gold, HP identical
                assert seats_a[seat] == seats_b[seat], (round_a, step_a, seat)
        shop_a, *rest_a = seats_a["player_0"]
        shop_b, *rest_b = seats_b["player_0"]
        if round_a > 5 or step_a == 0:
            # Seat 0's own later shops are unchanged too (the refresh index restarts each round);
            # only its gold (2 less, and interest) differs.
            assert shop_a == shop_b, (round_a, step_a)
        else:
            differences.add("shop")
        if rest_a != rest_b:
            differences.add("gold")
    assert differences == {"shop", "gold"}


def test_shared_extra_refresh_reshuffles_other_seats():
    with _quiet():
        plain, refreshed = _extra_refresh_branches("shared")
    changed = {seat for (_, _, a), (_, _, b) in zip(plain, refreshed) for seat in a if a[seat] != b.get(seat)}
    assert len(changed - {"player_0"}) >= 5


_SCRIPT = r"""
import contextlib, hashlib, io, sys
import numpy as np
from Simulator.simulators.tft_simulator import TFTConfig, parallel_env
h = hashlib.sha256()
with contextlib.redirect_stdout(io.StringIO()):
    env = parallel_env(TFTConfig(rng_streams="keyed"))
    observations, _ = env.reset(seed=21)
    rng = np.random.RandomState(21)
    while env.agents and env.unwrapped.game_round.current_round < 10:
        actions = {a: int(np.flatnonzero(observations[a]["action_mask"])[
            rng.randint(len(np.flatnonzero(observations[a]["action_mask"])))]) for a in env.agents}
        observations, rewards, _, _, _ = env.step(actions)
        for seat, p in sorted(env.unwrapped.player_manager.player_states.items()):
            if p:
                h.update(repr((seat, p.shop, p.gold, p.health, [u.name for u in p.bench if u],
                               p.item_bench, sorted(rewards.items()))).encode())
print(h.hexdigest())
"""


def _keyed_hash_in_fresh_process(hash_seed, workdir):
    env = dict(os.environ, PYTHONHASHSEED=str(hash_seed), PYTHONPATH=str(REPO_ROOT))
    result = subprocess.run([sys.executable, "-c", _SCRIPT], cwd=workdir, env=env,
                            capture_output=True, text=True, timeout=900, check=True)
    return result.stdout.strip().splitlines()[-1]


def test_keyed_is_reproducible_under_any_hash_seed(tmp_path):
    hashes = [_keyed_hash_in_fresh_process(hash_seed, tmp_path) for hash_seed in (0, 1, 2)]
    assert hashes[0] == hashes[1] == hashes[2]


def test_keyed_seed_changes_the_game_and_reset_reproduces_it():
    def shops(seed):
        env = aec_env(TFTConfig(rng_streams="keyed"))
        env.reset(seed=seed)
        return {s: tuple(p.shop) for s, p in env.unwrapped.player_manager.player_states.items()}

    with _quiet():
        assert shops(4) == shops(4)
        assert shops(4) != shops(5)


def _play(env, observations, rounds, seed):
    rng = np.random.RandomState(seed)
    trace = []
    while env.agents and env.unwrapped.game_round.current_round < rounds:
        actions = {}
        for agent in env.agents:
            legal = np.flatnonzero(observations[agent]["action_mask"])
            actions[agent] = int(legal[rng.randint(len(legal))])
        observations, rewards, _, _, _ = env.step(actions)
        trace.append((rewards, {s: _seat_state(p) for s, p in env.unwrapped.player_manager.player_states.items() if p}))
    return trace


@pytest.mark.parametrize("mode", ["shared", "keyed"])
def test_reseed_restored_copies(mode):
    with _quiet():
        env = parallel_env(TFTConfig(rng_streams=mode))
        observations, _ = env.reset(seed=6)
        _play(env, observations, 4, seed=1)
        observations = {a: env.unwrapped.observe(a) for a in env.agents}
        saved = pickle.dumps((env, observations))

        def branch(new_seed):
            copy, copy_observations = pickle.loads(saved)
            if new_seed is not None:
                copy.unwrapped.reseed_rng(new_seed)
            return _play(copy, copy_observations, 9, seed=2)

        same = branch(None)
        assert branch(None) == same  # a restored copy continues the same game
        with_seed = branch(np.random.SeedSequence(77))
        assert branch(np.random.SeedSequence(77)) == with_seed  # common random numbers
        assert branch(77) == branch(77)
        assert with_seed != same and branch(78) != branch(77)


def test_shared_reseed_reaches_numpy_draws():
    env = aec_env(TFTConfig())
    env.reset(seed=1)
    unwrapped = env.unwrapped
    unwrapped.reseed_rng(5)
    fresh = EnvRNG.from_episode_seed(5)
    with unwrapped.combat_ctx.bind():
        assert get_ctx().rng is unwrapped.rng
        assert get_ctx().rng.np_api.rand() == fresh.np_api.rand()
        assert get_ctx().rng.py.random() == fresh.py.random()


def test_keyed_bots_have_their_own_generators():
    with _quiet():
        env = parallel_env(TFTConfig(rng_streams="keyed"))
        env.reset(seed=2)
        bots = [p.default_agent for p in env.unwrapped.player_manager.player_states.values()]
        assert all(isinstance(b.rng, np.random.Generator) for b in bots)
        draws = [b._rand() for b in bots]
        assert len(set(draws)) == 8
        state = np.random.get_state()
        bots[0]._rand()
        assert np.random.get_state()[1].tolist() == state[1].tolist()  # global numpy untouched
        shared = parallel_env(TFTConfig())
        shared.reset(seed=2)
        assert all(p.default_agent.rng is None for p in shared.unwrapped.player_manager.player_states.values())


def test_shop_stream_keys_and_marginals():
    """Shop rolls go through the seat's stream; the draw code (and so the odds) is unchanged."""
    from Simulator.battle.stats import COST

    def level_4_player():
        player = Player(pool(), 3)
        player.level = 4
        player.chosen = True  # no Chosen slot, so every slot follows the level odds
        return player

    streams = KeyedStreams.from_seed(9)
    counts = np.zeros(5)
    with _quiet(), CombatContext(rng=streams.misc, streams=streams).bind():
        player = level_4_player()
        player.refresh_shop()
        first = tuple(player.shop)
        for _ in range(1999):
            player.refresh_shop()
            for name in player.shop:
                counts[COST[name] - 1] += 1
    # One stream per refresh: the refresh index of seat 3 in round 0 reached 2000.
    assert streams._uses[0][(0, STREAM_SHOP, 3)] == 2000
    # The same seed gives the same first shop.
    again = KeyedStreams.from_seed(9)
    with _quiet(), CombatContext(rng=again.misc, streams=again).bind():
        other = level_4_player()
        other.refresh_shop()
    assert tuple(other.shop) == first
    shares = counts / counts.sum()
    # Set 4 level 4 odds: 55 / 30 / 15 / 0 / 0
    assert abs(shares[0] - 0.55) < 0.02 and abs(shares[1] - 0.30) < 0.02 and abs(shares[2] - 0.15) < 0.02
    assert shares[3] == shares[4] == 0


def test_keyed_env_pickles_and_streams_survive():
    with _quiet():
        env = parallel_env(TFTConfig(rng_streams="keyed"))
        observations, _ = env.reset(seed=12)
        _play(env, observations, 3, seed=1)
        observations = {a: env.unwrapped.observe(a) for a in env.agents}
        clone, clone_observations = pickle.loads(pickle.dumps((env, observations)))
        assert clone.unwrapped.combat_ctx.streams.game_round is clone.unwrapped.game_round
        assert _play(env, observations, 8, seed=3) == _play(clone, clone_observations, 8, seed=3)


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        aec_env(TFTConfig(rng_streams="per-seat")).unwrapped
