"""Per-round action budget: TFTConfig.max_actions_per_round and TFTConfig.pass_ends_turn.

Defaults (15 actions, passes count, no early end) must behave as before. With
pass_ends_turn a pass ends that agent's planning phase; the agent stays in the agent
cycle (so the AEC order and the parallel wrapper are unchanged), its later actions are
ignored, its mask only allows pass, and the round is played once every agent is done.
"""

from __future__ import annotations

import numpy as np
from pettingzoo.test import api_test, parallel_api_test

from Simulator.battle.combat_context import CombatContext
from Simulator.encoding.token.action import ActionToken
from Simulator.encoding.token.action_multi import ActionMultiDiscrete
from Simulator.encoding.token.action_vector import ActionVector
from Simulator.game.player import Player
from Simulator.game.pool import pool
from Simulator.rng import EnvRNG
from Simulator.simulators.tft_simulator import TFTConfig, env as aec_env, parallel_env
from Simulator.simulators.tft_single_player_simulator import TFT_Single_Player_Simulator

PASS = [0, 0, 0]
LEVEL = [1, 0, 0]
TOKEN_PASS_INDEX = 52 * 38


def _round(env):
    return env.unwrapped.game_round.current_round


def _step_all(env, action_for):
    return env.step({agent: action_for(agent) for agent in env.agents})


def test_default_round_is_fifteen_actions():
    env = parallel_env(TFTConfig())
    env.reset(seed=1)
    for step in range(1, 15):
        _, _, _, truncations, infos = _step_all(env, lambda agent: PASS)
        assert _round(env) == 1
        assert not any(truncations.values())
        assert all(info["actions_taken"] == step and not info["turn_over"] for info in infos.values())
    _step_all(env, lambda agent: PASS)
    assert _round(env) == 2
    env.close()


def test_cap_can_be_raised():
    env = parallel_env(TFTConfig(max_actions_per_round=30))
    env.reset(seed=1)
    player = env.unwrapped.player_manager.player_states["player_0"]
    observation = env.unwrapped.player_manager.observation_states["player_0"]
    assert player.actions_remaining == 30
    assert observation.create_private_scalars(player)[3] == 1.0  # actions_remaining / budget
    for _ in range(29):
        _step_all(env, lambda agent: PASS)
    assert _round(env) == 1
    _step_all(env, lambda agent: PASS)
    assert _round(env) == 2
    env.close()


def test_pass_ends_only_that_agents_turn():
    env = parallel_env(TFTConfig(pass_ends_turn=True, max_actions_per_round=30))
    env.reset(seed=1)
    observations, _, _, _, infos = _step_all(env, lambda agent: PASS if agent == "player_0" else LEVEL)
    assert infos["player_0"]["turn_over"]
    assert not any(infos[agent]["turn_over"] for agent in env.agents if agent != "player_0")
    assert np.flatnonzero(observations["player_0"]["action_mask"]).tolist() == [TOKEN_PASS_INDEX]
    assert _round(env) == 1

    # A waiting agent's actions are ignored until the round is played.
    player_0 = env.unwrapped.player_manager.player_states["player_0"]
    player_0.gold = 50
    for step in range(2, 30):
        _, _, terminations, truncations, infos = _step_all(env, lambda agent: LEVEL)
        assert _round(env) == 1, step
        assert infos["player_0"]["actions_taken"] == 1
        assert not any(terminations.values()) and not any(truncations.values())
    assert player_0.gold == 50

    # The others reach the 30-action cap on this step, so the round is played.
    _, _, _, _, infos = _step_all(env, lambda agent: LEVEL)
    assert _round(env) == 2
    assert not any(info["turn_over"] for info in infos.values())
    observations = {agent: env.unwrapped.observe(agent) for agent in env.agents}
    assert np.count_nonzero(observations["player_0"]["action_mask"]) > 1
    env.close()


def test_round_ends_as_soon_as_everyone_passed():
    env = parallel_env(TFTConfig(pass_ends_turn=True, max_actions_per_round=30))
    env.reset(seed=1)
    for expected_round in (2, 3, 4):
        _step_all(env, lambda agent: PASS)
        assert _round(env) == expected_round
    env.close()


def test_aec_cycle_keeps_waiting_agents():
    env = aec_env(TFTConfig(pass_ends_turn=True, max_actions_per_round=5))
    env.reset(seed=1)
    steps_per_round = {}
    for agent in env.agent_iter():
        current = _round(env)
        if current >= 3:
            break
        observation, _, termination, truncation, info = env.last()
        assert not termination and not truncation
        if info.get("turn_over"):
            assert np.flatnonzero(observation["action_mask"]).tolist() == [TOKEN_PASS_INDEX]
        steps_per_round[current] = steps_per_round.get(current, 0) + 1
        env.step(LEVEL if agent == "player_3" else PASS)
    # player_3 uses its 5 actions; the other 7 pass at once and are stepped (ignored) each cycle.
    assert steps_per_round == {1: 5 * 8, 2: 5 * 8}
    env.close()


def test_pettingzoo_api_with_pass_ends_turn():
    parallel = parallel_env(TFTConfig(pass_ends_turn=True, max_actions_per_round=30))
    parallel_api_test(parallel, num_cycles=50)
    parallel.close()
    aec = aec_env(TFTConfig(pass_ends_turn=True, max_actions_per_round=30))
    api_test(aec, num_cycles=50)
    aec.close()


def test_pass_only_masks_decode_to_pass():
    with CombatContext(rng=EnvRNG.from_episode_seed(1)).bind():
        player = Player(pool(), 0)
        for action_class in (ActionToken, ActionVector):
            mask = np.asarray(action_class.pass_only_mask()).reshape(-1)
            assert mask.shape == np.asarray(action_class(player).fetch_action_mask()).reshape(-1).shape
            assert [action_class.action_space_to_action(i) for i in np.flatnonzero(mask)] == [PASS]
        mask = ActionMultiDiscrete.pass_only_mask()
        space = ActionMultiDiscrete.action_space()
        space.seed(0)
        for _ in range(20):
            sample = space.sample(mask=ActionMultiDiscrete.mask_to_sample_mask(mask))
            assert ActionMultiDiscrete.action_space_to_action(sample) == PASS


def test_single_player_pass_ends_turn():
    env = TFT_Single_Player_Simulator(TFTConfig(num_players=1, pass_ends_turn=True, max_actions_per_round=30))
    env.reset(seed=1)
    assert env.PLAYER.actions_remaining == 30
    env.step(np.asarray(PASS))
    assert env.game_round.current_round == 2

    env = TFT_Single_Player_Simulator(TFTConfig(num_players=1))
    env.reset(seed=1)
    env.step(np.asarray(PASS))
    assert env.game_round.current_round == 1
