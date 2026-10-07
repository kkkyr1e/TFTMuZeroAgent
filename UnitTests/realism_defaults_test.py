"""With every realism option off, games are identical to develop at a2840a1.

The options (TFTConfig fields, all off by default) are listed in OPTIONS_OFF. Two seeded
random-action games are played to the end (seed 11 ends at round index 34, seed 12 at 32)
and hashed: observations, rewards, terminations, truncations, infos (the Player object in
info["player"] reduced to its state) and every player's state after each step. The hashes
were recorded on develop at a2840a1, before any of the options existed.
rules_profile_games_test.py also checks 12-round trajectories and a full Default_Agent game
for TFTConfig().
"""

from __future__ import annotations

import contextlib
import hashlib
import io

import numpy as np
import pytest

from Simulator import config
from Simulator.simulators.tft_simulator import TFTConfig, parallel_env

# (hash, last round index) recorded on develop a2840a1
A2840A1_RANDOM_GAMES = {
    11: ("67ee21deaa336c8c172ba8078937f72daa09812baa819b34365d426edf016721", 34),
    12: ("cb5eea15e6ffa988c33775d7f5b7b894152a87e5284b2e78aef00f76f7c4e9ee", 32),
}

# Every realism option, explicitly off.
OPTIONS_OFF = {"pve_damage": False, "carousel_pickers": None, "carousel_fixes": False, "fortune_orbs": False,
               "hide_next_opponent": False, "rng_streams": "shared"}


@contextlib.contextmanager
def quiet():
    import Simulator.game.player as player_module
    saved = (config.DEBUG, config.PRINTMESSAGES, config.LOGMESSAGES, player_module.DEBUG)
    config.DEBUG = config.PRINTMESSAGES = config.LOGMESSAGES = False
    player_module.DEBUG = False
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            yield
    finally:
        config.DEBUG, config.PRINTMESSAGES, config.LOGMESSAGES, player_module.DEBUG = saved


def digest(h, obj):
    if isinstance(obj, dict):
        for key in sorted(obj, key=str):
            h.update(str(key).encode())
            digest(h, obj[key])
    elif isinstance(obj, (list, tuple)):
        h.update(b"[")
        for item in obj:
            digest(h, item)
        h.update(b"]")
    elif isinstance(obj, np.ndarray):
        h.update(str(obj.dtype).encode() + str(obj.shape).encode())
        h.update(np.ascontiguousarray(obj).tobytes())
    else:
        h.update(repr(obj).encode())


def player_state(player):
    if player is None:
        return None
    board = [(x, y, u.name, u.stars, tuple(u.items or ())) for x, col in enumerate(player.board)
             for y, u in enumerate(col) if u]
    bench = [(i, u.name, u.stars) for i, u in enumerate(player.bench) if u]
    return (player.gold, player.health, player.level, player.exp, player.win_streak, player.loss_streak,
            tuple(player.shop), board, bench, tuple(player.item_bench), round(float(player.reward), 6))


def info_view(info):
    return {key: player_state(value) if key == "player" else value for key, value in info.items()}


def random_game_hash(config_kwargs, seed, rounds=40):
    """Seeded random legal actions in the parallel env until the game ends or `rounds`."""
    env = parallel_env(TFTConfig(**config_kwargs))
    rng = np.random.RandomState(seed)
    h = hashlib.sha256()
    observations, infos = env.reset(seed=seed)
    digest(h, observations)
    digest(h, {agent: info_view(info) for agent, info in infos.items()})
    while env.agents and env.unwrapped.game_round.current_round < rounds:
        actions = {}
        for agent in env.agents:
            legal = np.flatnonzero(observations[agent]["action_mask"])
            actions[agent] = int(legal[rng.randint(len(legal))])
        observations, rewards, terminations, truncations, infos = env.step(actions)
        digest(h, [actions, observations, rewards, terminations, truncations])
        digest(h, {agent: info_view(info) for agent, info in infos.items()})
        states = env.unwrapped.player_manager.player_states
        digest(h, {seat: player_state(states.get(seat)) for seat in sorted(states)})
    final_round = env.unwrapped.game_round.current_round
    env.close()
    return h.hexdigest(), final_round


@pytest.mark.parametrize("seed", sorted(A2840A1_RANDOM_GAMES))
def test_default_config_matches_a2840a1(seed):
    with quiet():
        assert random_game_hash({}, seed) == A2840A1_RANDOM_GAMES[seed]


def test_options_explicitly_off_match_a2840a1():
    with quiet():
        assert random_game_hash(dict(OPTIONS_OFF), 11) == A2840A1_RANDOM_GAMES[11]


def test_every_option_is_a_tftconfig_field_and_off_by_default():
    defaults = TFTConfig()
    for name, off in OPTIONS_OFF.items():
        assert getattr(defaults, name) == off
