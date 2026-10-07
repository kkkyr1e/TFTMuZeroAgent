"""Economy rules profiles.

A RulesProfile holds every economy number the simulator uses: shop odds, pool copies, the XP
table, income, interest, streak gold and player damage. Champions, traits, items, Chosen and
combat always stay Set 4; only the numbers below change between profiles.

Select a profile with ``TFTConfig(rules="set4" | "set18")``. The env hands it to the shared
``pool`` object, and every Player and Game_Round reads it from there, so objects built without
a profile (unit tests, generators) keep the Set 4 rules.

"set4" reproduces the values that were hard coded before profiles existed (same objects for
the shop and Chosen odds, so a seed gives the same game). "set18" follows the live Set 18
(Enchanted Wilds) economy as of patch 18.4. Sources and confidence for each value are in
FORK_NOTES.md ("Rules profiles").

Round indices: idx0 = 1-1 carousel + 1-2 PvE, idx1 = 1-3, idx2 = 1-4, then six indices per
stage from idx3 = 2-1, so stage s >= 2 covers idx 6s-9 .. 6s-4 (idx8 = 2-7, idx38 = 7-7).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, Union

from Simulator.battle.stats import DAMAGE_PER_UNIT
from Simulator.game.pool_stats import base_pool_values, chosen_stats, level_percentage


def cumulative_odds(percent_rows):
    """Turn per-level shop odds in whole percent into the cumulative thresholds pool.sample uses.

    Integer sums divided by 100 keep the last threshold at exactly 1.0, so random.random()
    (which is < 1) always lands on a tier.
    """
    rows = []
    for row in percent_rows:
        if sum(row) != 100:
            raise ValueError(f"shop odds must add up to 100: {row}")
        total = 0
        thresholds = []
        for percent in row:
            total += percent
            thresholds.append(total / 100)
        rows.append(tuple(thresholds))
    return tuple(rows)


@dataclass(frozen=True)
class RulesProfile:
    name: str
    # Cumulative shop odds per player level (index = level; index 0 is unused), five cost tiers.
    shop_odds: tuple
    # Cumulative odds of the cost of a Chosen unit per player level (Set 4 mechanic).
    chosen_odds: tuple
    # Copies of each champion in the shared pool, by cost 1..5.
    pool_copies: Tuple[int, int, int, int, int]
    # XP needed to go from level i to level i + 1 (index = current level). The entry at
    # max_level is a placeholder that is never used for leveling.
    level_costs: Tuple[int, ...]
    max_level: int
    xp_per_round: int
    xp_purchase_cost: int  # gold per Buy XP
    xp_per_purchase: int  # XP per Buy XP
    refresh_cost: int
    # Passive gold at the planning phases of 1-2, 1-3, 1-4 and 2-1 (round indices 0-3).
    early_round_gold: Tuple[int, ...]
    # Passive gold per round from 2-2 on.
    base_income: int
    interest_step: int  # 1 gold per this much gold held
    interest_cap: int
    # Gold by win or loss streak length (index = streak); the last entry also covers longer streaks.
    streak_gold: Tuple[int, ...]
    pvp_win_gold: int
    # Base player damage: (last round index of the tier, damage), in round order.
    round_damage: Tuple[Tuple[int, int], ...]
    # Extra damage by number of surviving enemy units (index = units).
    unit_damage_table: Tuple[int, ...]

    def __deepcopy__(self, memo):
        # Profiles are shared constants; deep copies of players (battle sims) keep the same object.
        return self

    def stage_damage(self, round_index):
        """Base player damage for a fight at this round index."""
        tier = 0
        while round_index > self.round_damage[tier][0]:
            tier += 1
        return self.round_damage[tier][1]

    def unit_damage(self, survivors):
        """Damage from surviving enemy units. Past the end of the table the last step repeats."""
        table = self.unit_damage_table
        if survivors < len(table):
            return table[survivors]
        return table[-1] + (survivors - len(table) + 1) * (table[-1] - table[-2])

    def streak_bonus(self, streak):
        return self.streak_gold[min(streak, len(self.streak_gold) - 1)]

    def interest(self, gold):
        return min(gold // self.interest_step, self.interest_cap)

    def round_damage_table(self):
        """The base damage table in the [[last round index, damage], ...] form Game_Round uses."""
        return [[last, damage] for last, damage in self.round_damage]


SET4 = RulesProfile(
    name="set4",
    shop_odds=level_percentage,
    chosen_odds=chosen_stats,
    pool_copies=tuple(base_pool_values),
    level_costs=(0, 2, 2, 6, 10, 20, 36, 56, 80, 100),
    max_level=9,
    xp_per_round=2,
    xp_purchase_cost=4,
    xp_per_purchase=4,
    refresh_cost=2,
    early_round_gold=(2, 2, 3, 4),
    base_income=5,
    interest_step=10,
    interest_cap=5,
    # 2-3: 1, 4: 2, 5+: 3 (patch 10.8)
    streak_gold=(0, 0, 1, 1, 2, 3),
    pvp_win_gold=1,
    # 0/0/2/3/5/8/15 for stages 1-7 (patch 10.24); stage 8 keeps 15
    round_damage=((8, 0), (14, 2), (20, 3), (26, 5), (32, 8), (10000, 15)),
    unit_damage_table=tuple(DAMAGE_PER_UNIT),
)

# Shop odds in percent for levels 1..11 (Set 18, patch 18.4). Level 11 is only reachable with
# effects the simulator does not model (max_level is 10); the row is kept so a profile that
# raises max_level has odds to use.
SET18_SHOP_PERCENT = (
    (100, 0, 0, 0, 0),   # 1
    (100, 0, 0, 0, 0),   # 2
    (75, 25, 0, 0, 0),   # 3
    (55, 30, 15, 0, 0),  # 4
    (45, 33, 20, 2, 0),  # 5
    (30, 40, 25, 5, 0),  # 6
    (19, 30, 40, 10, 1),  # 7
    (15, 20, 32, 30, 3),  # 8
    (10, 17, 25, 33, 15),  # 9
    (5, 10, 20, 40, 25),  # 10
    (1, 2, 12, 50, 35),  # 11
)

SET18 = RulesProfile(
    name="set18",
    # index 0 is never used (levels start at 1); it repeats level 1 like the Set 4 table
    shop_odds=cumulative_odds((SET18_SHOP_PERCENT[0],) + SET18_SHOP_PERCENT),
    # Chosen is Set 4 content. Set 4 has no level 10/11, so those rows repeat level 9 (a guess).
    chosen_odds=tuple(chosen_stats) + (chosen_stats[9], chosen_stats[9]),
    pool_copies=(30, 25, 18, 10, 9),
    level_costs=(0, 2, 2, 6, 10, 20, 36, 56, 68, 68, 100),
    max_level=10,
    xp_per_round=2,
    xp_purchase_cost=4,
    xp_per_purchase=4,
    refresh_cost=2,
    early_round_gold=(2, 2, 3, 4),
    base_income=5,
    interest_step=10,
    interest_cap=5,
    # 2-4: 1, 5: 2, 6+: 3 (patch 14.1 moved the tiers up one, 14.8 gave 2-streaks 1 gold back)
    streak_gold=(0, 0, 1, 1, 1, 2, 3),
    pvp_win_gold=1,
    # 0/2/6/7/10/12/17 for stages 1-7, 150 from stage 8
    round_damage=((2, 0), (8, 2), (14, 6), (20, 7), (26, 10), (32, 12), (38, 17), (10000, 150)),
    # 1 damage per surviving enemy unit (patch 14.8)
    unit_damage_table=tuple(range(29)),
)

PROFILES = {SET4.name: SET4, SET18.name: SET18}
DEFAULT_RULES = SET4


def get_rules(rules: Union[str, RulesProfile, None] = None) -> RulesProfile:
    """Resolve a profile name (or a profile, or None for the Set 4 default)."""
    if rules is None:
        return DEFAULT_RULES
    if isinstance(rules, RulesProfile):
        return rules
    try:
        return PROFILES[str(rules).lower()]
    except KeyError:
        raise ValueError(f"unknown rules profile {rules!r}; expected one of {sorted(PROFILES)}") from None
