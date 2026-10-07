"""TFTConfig(hide_next_opponent=True): pairings are drawn at combat time.

By default Game_Round.start_round draws the pairings before planning, and the observation's
opponent slots, info["player"].possible_opponents / opponent_options and
env.unwrapped.game_round.matchups give the opponent away. With hide_next_opponent the draw
happens in combat_round, after every planning action, and during planning each player sees
only the candidates (alive, not excluded by the recent-opponent rule) in the observation and
in info["opponent_candidates"].
"""

from __future__ import annotations

import contextlib
import io
import pickle

import numpy as np
import pytest

from Simulator import config
from Simulator.game.game_round import Game_Round
from Simulator.simulators.tft_simulator import TFTConfig, env as aec_env, parallel_env

T = config.MATCHMAKING_WEIGHTS


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


def _random_actions(env, observations, rng):
    actions = {}
    for agent in env.agents:
        legal = np.flatnonzero(observations[agent]["action_mask"])
        actions[agent] = int(legal[rng.randint(len(legal))])
    return actions


def _expected_candidates(states, seat):
    alive = [s for s, p in states.items() if p and s != seat]
    eligible = [s for s in alive if states[seat].possible_opponents[s] >= T or states[s].possible_opponents[seat] >= T]
    return sorted(eligible or alive)


def _next_fight_scalar(candidates, own):
    value = 0
    for x in range(8):
        if x != own:
            value = value * 2 + (f"player_{x}" in candidates)
    return value


def _play_until_round(env, observations, rng, target):
    infos = {}
    while env.agents and env.unwrapped.game_round.current_round < target:
        observations, _, _, _, infos = env.step(_random_actions(env, observations, rng))
    return observations, infos


def test_planning_sees_only_candidates():
    with _quiet():
        env = parallel_env(TFTConfig(hide_next_opponent=True))
        observations, _ = env.reset(seed=4)
        rng = np.random.RandomState(4)
        checked = 0
        for target in range(3, 25):
            observations, infos = _play_until_round(env, observations, rng, target)
            unwrapped = env.unwrapped
            game_round = unwrapped.game_round
            assert game_round.matchups == []
            states = unwrapped.player_manager.player_states
            has_combat = game_round.has_player_combat()
            for seat in env.agents:
                player = states[seat]
                expected = _expected_candidates(states, seat) if has_combat else []
                assert infos[seat]["opponent_candidates"] == expected
                assert sorted(s for s, v in player.opponent_options.items() if v == 1) == expected
                obs_state = unwrapped.player_manager.observation_states[seat]
                assert obs_state.embedding_scalars[4] == _next_fight_scalar(expected, player.player_num)
                assert list(obs_state.game_scalars[2:2 + min(3, len(expected))]) == \
                    [int(s[-1]) for s in expected[:3]]
                checked += 1
        assert checked > 100
        env.close()


def test_candidates_before_a_pve_round_are_empty():
    with _quiet():
        env = parallel_env(TFTConfig(hide_next_opponent=True))
        observations, _ = env.reset(seed=2)
        observations, infos = _play_until_round(env, observations, np.random.RandomState(2), 8)  # 2-7 krugs
        assert not env.unwrapped.game_round.has_player_combat()
        assert all(info["opponent_candidates"] == [] for info in infos.values())
        env.close()


def _branch_pairings(hide, seed, perturb):
    """Play to a combat round, then finish its planning in two copies whose RNG state differs."""
    env = parallel_env(TFTConfig(hide_next_opponent=hide))
    observations, _ = env.reset(seed=seed)
    rng = np.random.RandomState(seed)
    observations, _ = _play_until_round(env, observations, rng, 4)
    for _ in range(14):  # every action of round 4's planning but the last
        observations, *_ = env.step(_random_actions(env, observations, rng))
    last_actions = _random_actions(env, observations, rng)
    branches = []
    for extra_draws in (0, perturb):
        copy = pickle.loads(pickle.dumps(env))
        for _ in range(extra_draws):
            copy.unwrapped.rng.py.random()
        planning_view = (copy.unwrapped.game_round.matchups,
                         {s: dict(p.opponent_options) for s, p in copy.unwrapped.player_manager.player_states.items() if p})
        copy.step(last_actions)
        played = copy.unwrapped.game_round.last_matchups
        branches.append((planning_view, played, copy))
    return branches


def test_pairings_are_drawn_after_planning():
    changed = 0
    with _quiet():
        for seed in range(6):
            (view_a, played_a, env_a), (view_b, played_b, env_b) = _branch_pairings(True, seed, perturb=3)
            assert view_a == view_b  # same planning view
            assert view_a[0] == []
            changed += played_a != played_b
    # A different RNG state at the end of planning gives different pairings, so they were not
    # fixed during planning.
    assert changed >= 3


def test_default_draws_pairings_before_planning():
    with _quiet():
        env = parallel_env(TFTConfig())
        observations, _ = env.reset(seed=1)
        observations, _ = _play_until_round(env, observations, np.random.RandomState(1), 4)
        matchups = env.unwrapped.game_round.matchups
        assert len(matchups) == 4
        for pair in matchups:
            # Each player's opponent slots contain its drawn opponent.
            states = env.unwrapped.player_manager.player_states
            assert states[pair[0]].opponent_options.get(pair[1]) == 1
        env.close()


def test_one_draw_per_player_combat_round(monkeypatch):
    calls = []
    original = Game_Round.decide_player_combat

    def decide(self):
        calls.append(self.current_round)
        original(self)

    monkeypatch.setattr(Game_Round, "decide_player_combat", decide)
    with _quiet():
        env = parallel_env(TFTConfig(hide_next_opponent=True))
        observations, _ = env.reset(seed=3)
        _play_until_round(env, observations, np.random.RandomState(3), 16)
        env.close()
    assert calls == [3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 15]


def test_drawn_opponent_is_usually_a_candidate(monkeypatch):
    """The greedy matchmaker sometimes falls back to an excluded opponent when a player's
    candidates are already paired; FORK_NOTES gives the measured rate (about 10%)."""
    seen = []
    original = Game_Round.decide_player_combat

    def decide(self):
        candidates = {s: {k for k, v in p.opponent_options.items() if v == 1} for s, p in self.PLAYERS.items() if p}
        original(self)
        for match in self.matchups:
            if match[1] != "ghost":
                seen.append(match[1] in candidates[match[0]])
                seen.append(match[0] in candidates[match[1]])

    monkeypatch.setattr(Game_Round, "decide_player_combat", decide)
    with _quiet():
        for seed in (1, 2):
            env = parallel_env(TFTConfig(hide_next_opponent=True))
            observations, _ = env.reset(seed=seed)
            _play_until_round(env, observations, np.random.RandomState(seed), 40)
            env.close()
    assert len(seen) > 200
    assert sum(seen) / len(seen) > 0.8


def test_aec_infos_carry_candidates():
    with _quiet():
        env = aec_env(TFTConfig(hide_next_opponent=True))
        env.reset(seed=5)
        rng = np.random.RandomState(5)
        for agent in env.agent_iter():
            if env.unwrapped.game_round.current_round >= 5:
                break
            observation, _, termination, truncation, info = env.last()
            assert "opponent_candidates" in info
            if env.unwrapped.game_round.current_round >= 3:
                assert info["opponent_candidates"] == \
                    _expected_candidates(env.unwrapped.player_manager.player_states, agent)
            legal = np.flatnonzero(observation["action_mask"])
            env.step(None if termination or truncation else int(legal[rng.randint(len(legal))]))
        env.close()


def test_default_infos_have_no_candidates_key():
    with _quiet():
        env = parallel_env(TFTConfig())
        _, infos = env.reset(seed=1)
        assert all("opponent_candidates" not in info for info in infos.values())
        env.close()


def test_default_pairings_are_fixed_before_planning_ends():
    with _quiet():
        for seed in range(3):
            (_, played_a, _), (_, played_b, _) = _branch_pairings(False, seed, perturb=3)
            assert played_a == played_b and len(played_a) == 4
