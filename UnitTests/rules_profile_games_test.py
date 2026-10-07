"""Full games under the economy rules profiles.

1. The default profile ("set4") is bit-identical to develop at 9149656 (before profiles
   existed): seeded 12-round trajectories (parallel and AEC, random legal actions) and a full
   Default_Agent game hash to the values recorded on develop, with TFTConfig() and with
   TFTConfig(rules="set4").
2. Smoke: full Default_Agent games under rules="set18" finish, and every income payment, XP
   purchase and player combat matches the Set 18 tables (literal values below, sources in
   FORK_NOTES.md): gold, XP and the HP each player loses per round.
"""

from __future__ import annotations

import contextlib
import hashlib
import io

import numpy as np
import pytest

from Simulator import config
from Simulator.battle import champion as champion_module
from Simulator.battle.combat_context import get_ctx
from Simulator.game.game_round import Game_Round
from Simulator.game.player import Player
from Simulator.simulators.tft_simulator import TFTConfig, env as aec_env, parallel_env
from Simulator.utils import decode_action

# Recorded on develop (9149656) with the helpers below.
DEVELOP_PARALLEL_SEED3_12_ROUNDS = "e613751eb3ca10533e293dd6fb787d742573854e0256e690cb40dec6bc8b6a6c"
DEVELOP_AEC_SEED4_12_ROUNDS = "b61d853ad14af0ff4b8768764a26e260b5e00cd30aff822cee46b549299aae11"
DEVELOP_DEFAULT_AGENT_SEED5 = ("a2bbdaad224a95c6c53d88177ee73af561eb5316fca8c86c951cf85403de0720", 32, 465)

SET18_EARLY_GOLD = (2, 2, 3, 4)  # planning phases of 1-2, 1-3, 1-4, 2-1
SET18_STREAK = (0, 0, 1, 1, 1, 2, 3)  # by streak length, 6+ pays 3
SET18_XP = (2, 2, 6, 10, 20, 36, 56, 68, 68)  # level i -> i + 1
SET18_STAGE_DAMAGE = (0, 2, 6, 7, 10, 12, 17, 150)  # stages 1..8
SET18_POOL = (30, 25, 18, 10, 9)


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


def _digest(h, obj):
    if isinstance(obj, dict):
        for key in sorted(obj, key=str):
            h.update(str(key).encode())
            _digest(h, obj[key])
    elif isinstance(obj, (list, tuple)):
        h.update(b"[")
        for item in obj:
            _digest(h, item)
        h.update(b"]")
    elif isinstance(obj, np.ndarray):
        h.update(str(obj.dtype).encode() + str(obj.shape).encode())
        h.update(np.ascontiguousarray(obj).tobytes())
    else:
        h.update(repr(obj).encode())


def _player_state(player):
    if player is None:
        return None
    board = [(x, y, u.name, u.stars, tuple(u.items or ())) for x, col in enumerate(player.board)
             for y, u in enumerate(col) if u]
    bench = [(i, u.name, u.stars) for i, u in enumerate(player.bench) if u]
    return (player.gold, player.health, player.level, player.exp, player.win_streak, player.loss_streak,
            tuple(player.shop), board, bench, tuple(player.item_bench), round(float(player.reward), 6))


def _parallel_random_hash(config_kwargs, seed, rounds):
    env = parallel_env(TFTConfig(**config_kwargs))
    rng = np.random.RandomState(seed)
    h = hashlib.sha256()
    observations, _ = env.reset(seed=seed)
    _digest(h, observations)
    while env.agents and env.unwrapped.game_round.current_round < rounds:
        actions = {}
        for agent in env.agents:
            legal = np.flatnonzero(observations[agent]["action_mask"])
            actions[agent] = int(legal[rng.randint(len(legal))])
        observations, rewards, terminations, truncations, _ = env.step(actions)
        _digest(h, [actions, observations, rewards, terminations, truncations])
        states = env.unwrapped.player_manager.player_states
        _digest(h, {seat: _player_state(states.get(seat)) for seat in sorted(states)})
    env.close()
    return h.hexdigest()


def _aec_random_hash(config_kwargs, seed, rounds):
    env = aec_env(TFTConfig(**config_kwargs))
    rng = np.random.RandomState(seed)
    h = hashlib.sha256()
    env.reset(seed=seed)
    for agent in env.agent_iter():
        if env.unwrapped.game_round.current_round >= rounds:
            break
        observation, reward, termination, truncation, _ = env.last()
        _digest(h, [agent, observation, reward, termination, truncation])
        if termination or truncation:
            action = None
        else:
            legal = np.flatnonzero(observation["action_mask"])
            action = int(legal[rng.randint(len(legal))])
        _digest(h, action)
        env.step(action)
    env.close()
    return h.hexdigest()


def _default_agent_game(config_kwargs, seed, on_round=None):
    """Every seat plays Default_Agent until the game ends. Returns (hash, final round index, steps, env)."""
    # Default_Agent picks its comp with the global np.random; seed it so the game is reproducible.
    saved_np_state = np.random.get_state()
    np.random.seed(seed)
    env = parallel_env(TFTConfig(**config_kwargs))
    h = hashlib.sha256()
    observations, _ = env.reset(seed=seed)
    last_round = env.unwrapped.game_round.current_round
    steps = 0
    try:
        while env.agents:
            actions = {}
            for agent in env.agents:
                player = env.unwrapped.player_manager.player_states.get(agent)
                action = [0, 0, 0]
                if player is not None:
                    mask = np.asarray(observations[agent]["action_mask"]).reshape(55, 38)
                    action_str = player.default_policy(env.unwrapped.game_round.current_round, player.shop, mask)
                    if isinstance(action_str, str) and action_str.strip():
                        action = [int(v) for v in decode_action([action_str])[0]]
                actions[agent] = action
            observations, rewards, _, _, _ = env.step(actions)
            steps += 1
            current = env.unwrapped.game_round.current_round
            if current != last_round:
                states = env.unwrapped.player_manager.player_states
                _digest(h, [current, rewards, {seat: _player_state(states.get(seat)) for seat in sorted(states)}])
                if on_round is not None:
                    on_round(env, current)
                last_round = current
    finally:
        np.random.set_state(saved_np_state)
    final_round = env.unwrapped.game_round.current_round
    env.close()
    return h.hexdigest(), final_round, steps, env


# --- 1. default rules are bit-identical to develop ---

@pytest.mark.parametrize("config_kwargs", [{}, {"rules": "set4"}], ids=["default", "set4"])
def test_set4_random_trajectories_match_develop(config_kwargs):
    with _quiet():
        assert _parallel_random_hash(config_kwargs, 3, 12) == DEVELOP_PARALLEL_SEED3_12_ROUNDS
        assert _aec_random_hash(config_kwargs, 4, 12) == DEVELOP_AEC_SEED4_12_ROUNDS


def test_default_agent_full_game_matches_develop():
    with _quiet():
        digest, final_round, steps, _ = _default_agent_game({}, 5)
    assert (digest, final_round, steps) == DEVELOP_DEFAULT_AGENT_SEED5


# --- 2. Set 18 smoke ---

def _stage(round_index):
    return 1 if round_index <= 2 else (round_index - 3) // 6 + 2


def _total_xp(level, exp):
    return sum(SET18_XP[:level - 1]) + exp


class Set18EconomyCheck:
    """Wraps income, Buy XP and combat to compare every payment and every loss with the tables."""

    def __init__(self, monkeypatch):
        self.errors = []
        self.incomes = 0
        self.xp_buys = 0
        self.losses = 0
        self.fights = []
        self.max_level_seen = 1

        original_income = Player.gold_income
        original_buy_xp = Player.buy_exp_action
        original_run = champion_module.run
        original_combat_round = Game_Round.combat_round

        def gold_income(player, t_round):
            gold, level, exp = player.gold, player.level, player.exp
            streak = max(player.win_streak, player.loss_streak)
            original_income(player, t_round)
            interest = min(gold // 10, 5)
            if t_round < len(SET18_EARLY_GOLD):
                expected = gold + interest + SET18_EARLY_GOLD[t_round]
            else:
                expected = gold + interest + 5 + SET18_STREAK[min(streak, len(SET18_STREAK) - 1)]
            if player.gold != expected:
                self.errors.append(("income", t_round, gold, streak, player.gold, expected))
            self._check_xp("passive xp", (level, exp), player, 2)
            self.incomes += 1

        def buy_exp_action(player):
            gold, level, exp = player.gold, player.level, player.exp
            bought = original_buy_xp(player)
            if bought:
                if player.gold != gold - 4:
                    self.errors.append(("buy xp gold", gold, player.gold))
                self._check_xp("buy xp", (level, exp), player, 4)
                self.xp_buys += 1
            elif player.gold != gold or (gold >= 4 and level < 10):
                self.errors.append(("buy xp refused", gold, level))
            return bought

        def run(champion_q, player_1, player_2, round_damage=0):
            result = original_run(champion_q, player_1, player_2, round_damage)
            ctx = get_ctx()
            survivors = {1: len(ctx.blue), 2: len(ctx.red)}.get(result[0], 0)
            self.fights.append((round_damage, result, survivors))
            return result

        def combat_round(game_round):
            players = {seat: p for seat, p in game_round.PLAYERS.items() if p}
            health = {seat: p.health for seat, p in players.items()}
            first = len(self.fights)
            outcome = original_combat_round(game_round)
            self._check_round(game_round, players, health, self.fights[first:])
            return outcome

        monkeypatch.setattr(Player, "gold_income", gold_income)
        monkeypatch.setattr(Player, "buy_exp_action", buy_exp_action)
        monkeypatch.setattr(champion_module, "run", run)
        monkeypatch.setattr(Game_Round, "combat_round", combat_round)

    def _check_xp(self, label, before, player, gained):
        level, exp = before
        self.max_level_seen = max(self.max_level_seen, player.level)
        if player.level > 10:
            self.errors.append((label, "level above 10", player.level))
        elif player.level == 10 and level < 10:
            # Reaching max level drops the leftover XP.
            if _total_xp(level, exp) + gained < _total_xp(10, 0) or player.exp != 0:
                self.errors.append((label, before, player.level, player.exp))
        elif level < 10 and _total_xp(player.level, player.exp) != _total_xp(level, exp) + gained:
            self.errors.append((label, before, player.level, player.exp))

    def _check_round(self, game_round, players, health, fights):
        round_index = game_round.current_round
        stage_damage = SET18_STAGE_DAMAGE[min(_stage(round_index), 8) - 1]
        if len(fights) != len(game_round.matchups):
            self.errors.append(("fights", round_index, len(fights), len(game_round.matchups)))
            return
        lost = {seat: 0 for seat in players}
        for match, (base, (won, damage), survivors) in zip(game_round.matchups, fights):
            if base != stage_damage:
                self.errors.append(("stage damage", round_index, base, stage_damage))
            expected = base + survivors if won in (1, 2) else base
            if damage != expected:
                self.errors.append(("unit damage", round_index, won, damage, survivors))
            if match[1] == "ghost":
                losers = [match[0]] if won in (0, 2) else []
            else:
                losers = {0: [match[0], match[1]], 1: [match[1]], 2: [match[0]]}[won]
            for seat in losers:
                lost[seat] += damage
                self.losses += 1
        for seat, player in players.items():
            if health[seat] - player.health != lost[seat]:
                self.errors.append(("hp", round_index, seat, health[seat], player.health, lost[seat]))


@pytest.mark.parametrize("seed", [21, 22])
def test_set18_default_agent_games_follow_the_tables(monkeypatch, seed):
    check = Set18EconomyCheck(monkeypatch)
    pool_errors = []

    def on_round(env, current):
        game_pool = env.unwrapped.pool_obj
        tiers = (game_pool.COST_1, game_pool.COST_2, game_pool.COST_3, game_pool.COST_4, game_pool.COST_5)
        for cost, counts in enumerate(tiers):
            if not all(0 <= n <= SET18_POOL[cost] for n in counts.values()):
                pool_errors.append((current, cost + 1))

    with _quiet():
        _, final_round, steps, env = _default_agent_game({"rules": "set18"}, seed, on_round)

    unwrapped = env.unwrapped
    assert unwrapped.game_over() and unwrapped.num_alive <= 1
    assert all(unwrapped.terminations.values())
    assert final_round < len(unwrapped.game_round.game_rounds)
    assert check.errors == []
    assert pool_errors == []
    # The checks actually ran: every living player gets income each round, and fights were lost.
    assert check.incomes >= 8 * final_round // 2
    assert check.losses > final_round
