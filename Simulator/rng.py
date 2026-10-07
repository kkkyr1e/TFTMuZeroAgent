"""Two-tier seeding for training runs and deterministic env playouts.

Category 1 — run seed
    Trainer / experiment level.  Derive a distinct episode seed for every
    (env_index, episode_index) pair so a research run can start from the same
    conditions.  Does not by itself guarantee bit-identical playouts across
    different parallel layouts.

Category 2 — episode seed
    Per ``env.reset(seed=...)``.  Drives an isolated :class:`EnvRNG` so the
    same seed reproduces the same game (shop rolls, combat, rewards), including
    under in-process parallel execution once combat state is env-local.
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

_MASK64 = (1 << 64) - 1
_MASK31 = (1 << 31) - 1


def _splitmix64(value: int) -> int:
    """Stable, platform-independent 64-bit mix (SplitMix64)."""
    value = (value + 0x9E3779B97F4A7C15) & _MASK64
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & _MASK64
    return value ^ (value >> 31)


def derive_episode_seed(run_seed: int, env_index: int = 0, episode_index: int = 0) -> int:
    """Derive a Category-2 episode seed from a Category-1 run seed.

    The mix is deterministic and does not touch process-global RNG state.
    """
    mixed = _splitmix64(int(run_seed) & _MASK64)
    mixed = _splitmix64(mixed ^ (_splitmix64(int(env_index) + 1)))
    mixed = _splitmix64(mixed ^ (_splitmix64(int(episode_index) + 1) << 1))
    return int(mixed & _MASK31)


class NPRandomFacade:
    """Subset of ``numpy.random`` used by the simulator, backed by a Generator."""

    def __init__(self, generator: np.random.Generator):
        self._g = generator

    def randint(self, low, high=None, size=None):
        if high is None:
            high = low
            low = 0
        result = self._g.integers(low, high, size=size)
        if size is None:
            return int(result)
        return result

    def rand(self, *size):
        if not size:
            return float(self._g.random())
        if len(size) == 1:
            return self._g.random(size[0])
        return self._g.random(size)

    def choice(self, a, size=None, replace=True, p=None):
        if size is None and p is not None:
            index = int(self._g.choice(len(a), p=p))
            return a[index]
        result = self._g.choice(a, size=size, replace=replace, p=p)
        if size is None:
            return result.item() if hasattr(result, "item") else result
        return result

    def seed(self, *_args, **_kwargs):
        return None


@dataclass
class EnvRNG:
    """Isolated Python + NumPy generators created from an episode seed."""

    py: random.Random
    np: np.random.Generator
    episode_seed: Optional[int] = None
    np_api: NPRandomFacade = field(init=False)

    def __post_init__(self):
        self.np_api = NPRandomFacade(self.np)

    def reseed(self, seed) -> None:
        """Re-seed in place, so every holder of this object sees it. An int gives the state of
        EnvRNG.from_episode_seed(seed); a numpy SeedSequence is also accepted. Replacing
        `.np` by hand would not reach `.np_api`, which the simulator's numpy draws use."""
        if isinstance(seed, np.random.SeedSequence):
            self.py = random.Random(int.from_bytes(seed.generate_state(8, dtype=np.uint32).tobytes(), "little"))
            self.np = np.random.Generator(np.random.PCG64(seed))
            self.episode_seed = None
        else:
            seed = int(seed) & _MASK31
            self.py = random.Random(seed)
            self.np = np.random.default_rng(seed)
            self.episode_seed = seed
        self.np_api = NPRandomFacade(self.np)

    @classmethod
    def from_episode_seed(cls, episode_seed: Optional[int] = None) -> "EnvRNG":
        if episode_seed is None:
            episode_seed = int.from_bytes(os.urandom(8), "little") & _MASK31
        seed = int(episode_seed) & _MASK31
        return cls(
            py=random.Random(seed),
            np=np.random.default_rng(seed),
            episode_seed=seed,
        )


def seed_info(episode_seed, run_seed) -> dict:
    return {"episode_seed": episode_seed, "run_seed": run_seed}


def expand_vector_seeds(num_envs: int, seeds=None, options=None, run_seed=None):
    """Turn a run seed into per-env episode seeds for vector wrappers."""
    if isinstance(options, dict):
        if run_seed is None:
            run_seed = options.get("run_seed")
        options = [dict(options) for _ in range(num_envs)]
    options = list(options) if options is not None else [None] * num_envs
    if len(options) < num_envs:
        options = options + [None] * (num_envs - len(options))
    if run_seed is not None and (seeds is None or all(s is None for s in seeds)):
        seeds = [derive_episode_seed(run_seed, index, 0) for index in range(num_envs)]
        options = [dict(opt or {}, run_seed=run_seed) for opt in options]
    seeds = list(seeds) if seeds is not None else [None] * num_envs
    if len(seeds) < num_envs:
        seeds = seeds + [None] * (num_envs - len(seeds))
    return seeds, options


# --- Keyed streams (TFTConfig.rng_streams = "keyed") ---
#
# With "shared" (the default) every draw in an episode comes from one EnvRNG, so one extra
# draw anywhere (a seat's extra shop refresh) shifts every later draw of every seat. With
# "keyed" each kind of event draws from its own stream, derived from the episode seed and a key
# of plain ints: (round index, stream kind, ids..., use index). The use index counts how often
# that key was used in the round (the refresh index for shops, the action index for actions),
# so a key never replays numbers and an extra refresh by one seat changes only that seat's
# later shops of the same round. Streams are created lazily and nothing but small counters is
# stored, so the env stays small and picklable.

KEYED_ROOT_TAG = 1  # spawn_key of the root SeedSequence derived from an episode seed

# Stream kinds (ints so keys do not depend on PYTHONHASHSEED)
STREAM_SHOP = 1         # (seat): a seat's shop rolls; use index = refresh index in the round
STREAM_ACTION = 2       # (seat): anything random inside one planning action of a seat
STREAM_START = 3        # (seat): start-of-round effects of a seat (Thief's Gloves, ...)
STREAM_MATCHMAKING = 4  # (): the round's pairings
STREAM_CAROUSEL = 5     # (): the round's carousel units, items and pick order
STREAM_COMBAT = 6       # (blue seat, red seat): one player combat
STREAM_GHOST = 7        # (seat, ghost seat): a fight against a ghost
STREAM_PVE = 8          # (seat): a seat's monster fight
STREAM_LOOT = 9         # (seat): a seat's PvE loot
STREAM_FORTUNE = 10     # (seat): a seat's Fortune orbs
STREAM_BOT = 11         # (seat): the rule bot's (Default_Agent) own generator, whole episode
STREAM_MISC = 12        # (): anything not routed elsewhere, whole episode


def _python_random(seed_sequence: np.random.SeedSequence) -> random.Random:
    words = seed_sequence.generate_state(8, dtype=np.uint32)
    return random.Random(int.from_bytes(words.tobytes(), "little"))


def _child(root: np.random.SeedSequence, key) -> np.random.SeedSequence:
    return np.random.SeedSequence(root.entropy, spawn_key=tuple(root.spawn_key) + tuple(int(k) for k in key))


class LazyStreamRNG:
    """EnvRNG look-alike for one keyed stream; the generators are built on first use."""

    episode_seed = None

    def __init__(self, root: np.random.SeedSequence, key):
        self._root = root
        self._key = tuple(key)
        self._py = None
        self._np = None
        self._np_api = None

    @property
    def key(self):
        return self._key

    @property
    def py(self) -> random.Random:
        if self._py is None:
            self._py = _python_random(_child(self._root, self._key + (0,)))
        return self._py

    @property
    def np(self) -> np.random.Generator:
        if self._np is None:
            self._np = np.random.Generator(np.random.PCG64(_child(self._root, self._key + (1,))))
        return self._np

    @property
    def np_api(self) -> NPRandomFacade:
        if self._np_api is None:
            self._np_api = NPRandomFacade(self.np)
        return self._np_api


class KeyedStreams:
    """Named child streams of one episode (see the note above)."""

    def __init__(self, root: np.random.SeedSequence):
        self.root = root
        # Set by the env to its Game_Round, so keys carry the current round index.
        self.game_round = None
        self._uses = {}
        self.misc = LazyStreamRNG(root, (STREAM_MISC,))

    @staticmethod
    def root_from_seed(seed) -> np.random.SeedSequence:
        """An int seed (e.g. the episode seed) or a SeedSequence used as is."""
        if isinstance(seed, np.random.SeedSequence):
            return seed
        return np.random.SeedSequence(int(seed) & _MASK64, spawn_key=(KEYED_ROOT_TAG,))

    @classmethod
    def from_seed(cls, seed) -> "KeyedStreams":
        return cls(cls.root_from_seed(seed))

    @property
    def round(self) -> int:
        return getattr(self.game_round, "current_round", 0) if self.game_round is not None else 0

    def stream(self, key) -> LazyStreamRNG:
        """A fresh stream for (current round,) + key + (use index,)."""
        round_index = self.round
        full_key = (round_index,) + tuple(int(k) for k in key)
        uses = self._uses.setdefault(round_index, {})
        count = uses.get(full_key, 0)
        uses[full_key] = count + 1
        if len(self._uses) > 2:
            for old in [r for r in self._uses if r < round_index - 1]:
                del self._uses[old]
        return LazyStreamRNG(self.root, full_key + (count,))

    def bot_generator(self, seat: int) -> np.random.Generator:
        """The rule bot's generator for a seat (one per episode)."""
        return np.random.Generator(np.random.PCG64(_child(self.root, (STREAM_BOT, seat))))

    def reseed(self, seed) -> None:
        """New root (int or SeedSequence); every later stream changes, use counters are kept."""
        self.root = self.root_from_seed(seed)
        self.misc = LazyStreamRNG(self.root, (STREAM_MISC,))

