from enum import Enum
from Simulator.battle import champion
from Simulator.battle.combat_context import NPRandomProxy, RandomProxy
from Simulator.game import pool_stats
from Simulator.battle.item_stats import thieves_gloves_items

random = RandomProxy()
_np_random = NPRandomProxy()

# Theives gloves items includes all full items except emblems
item_list = thieves_gloves_items

# Loot Orbs
# There are 3 types of orbs:
# Common (Gray): 3 gold worth of champions, gold, or champion duplicator
# Uncommon (Blue): 6 gold worth of champions, gold, or items
# Rare (Gold): 10 gold worth of champions, gold, or spatula
# TODO add reforgers, magnetic removers, emblem tomes, and item choosers

class LootOrb(Enum):
    COMMON = {
        'three_gold': .2,
        'three_cost': .25,
        'two_cost_one_gold': .25,
        'three_one_costs': .25,
        'champion_duplicator_one_gold': .05
    }
    UNCOMMON = {
        'six_gold': .05,
        'two_three_costs': .15,
        'three_two_costs': .15,
        'one_item': .6,
        'champion_duplicator_one_gold_two_cost': .05
    }
    RARE = {
        'ten_gold': .15,
        # 'two_five_costs': .1,
        'champion_duplicator_five_gold': .1,
        'spatula': .75,
    }

# Implementation of the loot that can be given to the player
# The rewards are pretty self explanatory;
# 'three_one_costs' gives three random one cost champions, 'one_item' gives one random item, etc.
def give_loot(player, reward):
    # I would use a match here but we're on python 3.8
    if reward == 'three_gold':
        player.gold += 3
    if reward == 'six_gold':
        player.gold += 6
    if reward == 'ten_gold':
        player.gold += 10
    if reward == 'three_one_costs':
        give_champions(player, pool_stats.COST_1, count=3)
    if reward == 'two_cost_one_gold':
        give_champions(player, pool_stats.COST_2)
        player.gold += 1
    if reward == 'three_cost':
        give_champions(player, pool_stats.COST_3)
    if reward == 'three_two_costs':
        give_champions(player, pool_stats.COST_2, count=3)
    if reward == 'two_three_costs':
        give_champions(player, pool_stats.COST_3, count=2)
    if reward == 'two_five_costs':
        give_champions(player, pool_stats.COST_5, count=2)
    if reward == 'one_item':
        give_random_item(player)
    if reward == 'full_item':
        give_random_full_item(player)
    if reward == 'champion_duplicator_one_gold':
        player.gold += 1
        player.add_to_item_bench('champion_duplicator')
    if reward == 'champion_duplicator_one_gold_two_cost':
        player.gold += 1
        give_champions(player, pool_stats.COST_2)
        player.add_to_item_bench('champion_duplicator')
    if reward == 'champion_duplicator_five_gold':
        player.gold += 5
        player.add_to_item_bench('champion_duplicator')
    if reward == 'spatula':
        player.add_to_item_bench('spatula')


# Utility Functions

## Random Chapmions
def give_champions(player, cost, count=1):
    for _ in range(count):
        give_champion(player, cost)

def give_champion(player, cost):
    # Get random champion of cost
    name = list(cost.items())[random.randint(0, len(cost) - 1)][0]
    random_champion = champion.champion(name)

    # Give gold if bench is full or there are no more of this unit available
    if player.bench_full() or cost[name] == 0:
        player.gold += random_champion.cost
    else:
        player.add_to_bench(random_champion)
        player.pool_obj.update_pool(random_champion, -1)

## Random Items
def give_random_item(player):
    item = player.random_item_from_pool()
    player.add_to_item_bench(item)

def give_random_full_item(player):
    player.add_to_item_bench(item_list[random.randint(0, len(item_list) - 1)])

# Helper functions for getting orbs after minion rounds
def gen_orbs(choices, p, count):
    orbs = []

    for _ in range(count):
        orb = _np_random.choice(choices, p=p)
        if type(orb) is tuple:
            orbs.extend(orb)
        else:
            orbs.append(orb)
            
    return orbs

# Gets a random reward based on the loot table (dictionary) defined in the LootOrb enum
def gen_orb_reward(loot_orb: LootOrb):
    choices = list(loot_orb.value.keys())
    probabilities = list(loot_orb.value.values())

    reward = _np_random.choice(choices, p=probabilities)

    return reward

# Combines `gen_orbs` and `gen_orb_reward` to directly give you the rewards from loot orbs
# e.g after raptors you might get ['one_item', 'one_item', 'one_item', 'three_gold', 'two_three_costs']
def gen_loot(choices, p, count, history):
    loot = []

    orbs = gen_orbs(choices, p, count)

    for orb in orbs:
        if orb is None:
            continue

        history.append(orb)
        loot.append(gen_orb_reward(orb))

    return loot

# --- Fortune orbs (TFTConfig.fortune_orbs) ---
# Set 4 Fortune: "Winning combat against a player will give bonus orbs. The longer you've gone
# without an orb, the bigger the payout." (3) Bonus orbs, (6) extra bonus orbs with rare loot.
# Riot published only the average value of the orb by losses since the last payout
# (FORTUNE_ORB_VALUES, patch 10.21) and of the 6 Fortune extra orb (11.65 gold, 10.21), plus
# hints about the contents: gold, champions, items, Neeko's Help, Spatulas from 5+ losses, no
# all-gold drops at high losses (10.20), no 5-cost at 4 losses (10.21), a rare "Jackpot" of
# many items in the 6 Fortune orb (10.20). The packages below are an assumption built from
# those hints; each package has the table value in expectation (gold remainders are paid as
# floor or ceil with the right probability), so the orb's expected gold value equals the table.
# Sources and assumptions: FORK_NOTES.md.

# Losses 0..12 -> average orb value (gold). 0-9 from patch 10.21; 10-12 (separate tables since
# 10.23, values not published) keep the simulator's old numbers.
FORTUNE_ORB_VALUES = (2.5, 6, 10.5, 17, 24, 31, 38, 45, 55, 70, 90, 115, 145)
FORTUNE_MAX_LOSSES = len(FORTUNE_ORB_VALUES) - 1  # the hidden counter stops at 12
FORTUNE_EXTRA_ORB_VALUE = 11.65  # 6 Fortune extra orb, does not scale with losses

# Gold value of one non-gold reward, from the 5-loss example on the wiki (23.5 gold before
# 10.20: "two tier 4 units and two items", "one item and 16 gold", "two items and 8 gold",
# "one Neeko's Help, one item and 8 gold") and the Set 4.5 9-loss drop "20 gold + 5 Spatulas".
FORTUNE_COMPONENT_VALUE = 7.5
FORTUNE_NEEKO_VALUE = 7.5
FORTUNE_SPATULA_VALUE = 10
# Cost of the champions in a Fortune orb, by losses 0..12 (assumption; 4-costs at 5 losses in
# the wiki example, 5-costs only from 5 losses after 10.21).
FORTUNE_UNIT_COST = (1, 2, 3, 3, 4, 4, 5, 5, 5, 5, 5, 5, 5)
# Most of one kind in a package; the rest of the value is gold (assumption; the largest drops
# quoted for Set 4.5 are 5 five-costs at 8 losses and 5 Spatulas at 9 losses).
FORTUNE_MAX_UNITS = 5
FORTUNE_MAX_COMPONENTS = 6
FORTUNE_MAX_SPATULAS = 5
# 6 Fortune extra orb: a rare Jackpot of components (assumed 1%, 6 components).
FORTUNE_JACKPOT_CHANCE = 0.01
FORTUNE_JACKPOT_COMPONENTS = 6

_COST_TABLES = {1: pool_stats.COST_1, 2: pool_stats.COST_2, 3: pool_stats.COST_3,
                4: pool_stats.COST_4, 5: pool_stats.COST_5}


def _gold(value):
    """Pay a fractional gold value as floor or ceil so the expected payout is exactly `value`."""
    whole = int(value // 1)
    fraction = value - whole
    if fraction > 1e-9 and random.random() < fraction:
        whole += 1
    return whole


def _package(kind, value, unit_cost):
    """Contents of one package worth `value` on average: a list of reward atoms.

    Atoms: ("gold", n), ("champion", cost), ("component",), ("neekos_help",), ("spatula",).
    """
    contents = []
    rest = value
    if kind == "units":
        count = min(FORTUNE_MAX_UNITS, max(1, int(value // unit_cost)))
        contents += [("champion", unit_cost)] * count
        rest -= count * unit_cost
    elif kind == "components":
        count = min(FORTUNE_MAX_COMPONENTS, max(1, int(value // FORTUNE_COMPONENT_VALUE)))
        contents += [("component",)] * count
        rest -= count * FORTUNE_COMPONENT_VALUE
    elif kind == "mixed":
        components = min(FORTUNE_MAX_COMPONENTS // 2, max(1, int(value / 3 // FORTUNE_COMPONENT_VALUE)))
        units = min(FORTUNE_MAX_UNITS, max(1, int(value / 3 // unit_cost)))
        contents += [("component",)] * components + [("champion", unit_cost)] * units
        rest -= components * FORTUNE_COMPONENT_VALUE + units * unit_cost
    elif kind == "neekos_help":
        contents += [("neekos_help",), ("component",)]
        rest -= FORTUNE_NEEKO_VALUE + FORTUNE_COMPONENT_VALUE
    elif kind == "spatulas":
        count = min(FORTUNE_MAX_SPATULAS, max(1, int(value // 14)))
        contents += [("spatula",)] * count
        rest -= count * FORTUNE_SPATULA_VALUE
    elif kind != "gold":
        raise ValueError(kind)
    if rest < -1e-9:
        raise ValueError(f"{kind} package over value {value}")
    gold = _gold(max(rest, 0.0))
    if gold:
        contents.append(("gold", gold))
    return contents


def fortune_package_kinds(losses):
    """Packages a 3 Fortune orb can hold after `losses` losses (all equally likely)."""
    value = FORTUNE_ORB_VALUES[losses]
    unit_cost = FORTUNE_UNIT_COST[losses]
    kinds = []
    if losses <= 3:
        kinds.append("gold")  # 10.20 removed the all-gold drops at higher losses
    kinds.append("units")
    if value >= FORTUNE_COMPONENT_VALUE:
        kinds.append("components")
    if value >= 3 * max(FORTUNE_COMPONENT_VALUE, unit_cost):
        kinds.append("mixed")
    if value >= FORTUNE_NEEKO_VALUE + FORTUNE_COMPONENT_VALUE:
        kinds.append("neekos_help")
    if losses >= 5:
        kinds.append("spatulas")  # 10.20: Spatulas can drop from 5+ losses
    return kinds


def gen_fortune_orb(losses):
    """Contents of the 3 Fortune orb paid on a win after `losses` losses (capped at 12)."""
    losses = max(0, min(int(losses), FORTUNE_MAX_LOSSES))
    kinds = fortune_package_kinds(losses)
    kind = kinds[random.randint(0, len(kinds) - 1)]
    return _package(kind, FORTUNE_ORB_VALUES[losses], FORTUNE_UNIT_COST[losses])


FORTUNE_EXTRA_KINDS = ("units", "components", "neekos_help", "spatulas")


def gen_fortune_extra_orb():
    """Contents of the 6 Fortune extra orb (11.65 gold on average, no all-gold drop)."""
    jackpot_value = FORTUNE_JACKPOT_COMPONENTS * FORTUNE_COMPONENT_VALUE
    if random.random() < FORTUNE_JACKPOT_CHANCE:
        return [("component",)] * FORTUNE_JACKPOT_COMPONENTS
    # The other packages make up the rest of the 11.65 average.
    value = (FORTUNE_EXTRA_ORB_VALUE - FORTUNE_JACKPOT_CHANCE * jackpot_value) / (1 - FORTUNE_JACKPOT_CHANCE)
    kind = FORTUNE_EXTRA_KINDS[random.randint(0, len(FORTUNE_EXTRA_KINDS) - 1)]
    if kind == "neekos_help":
        contents = [("neekos_help",)]
        gold = _gold(value - FORTUNE_NEEKO_VALUE)
    elif kind == "spatulas":
        contents = [("spatula",)]
        gold = _gold(value - FORTUNE_SPATULA_VALUE)
    elif kind == "components":
        contents = [("component",)]
        gold = _gold(value - FORTUNE_COMPONENT_VALUE)
    else:
        contents = [("champion", 5)]
        gold = _gold(value - 5)
    if gold:
        contents.append(("gold", gold))
    return contents


def fortune_orb_value(contents):
    """Gold value of orb contents with the FORTUNE_* values (champions at their cost)."""
    values = {"component": FORTUNE_COMPONENT_VALUE, "neekos_help": FORTUNE_NEEKO_VALUE,
              "spatula": FORTUNE_SPATULA_VALUE}
    total = 0
    for atom in contents:
        if atom[0] in ("gold", "champion"):
            total += atom[1]
        else:
            total += values[atom[0]]
    return total


def give_fortune_orb(player, contents):
    """Hand orb contents to the player like PvE loot: champions go to the bench (their cost in
    gold if the bench is full), items to the item bench (lost if it is full, as with PvE loot),
    Neeko's Help is the champion_duplicator item."""
    for atom in contents:
        kind = atom[0]
        if kind == "gold":
            player.gold += atom[1]
        elif kind == "champion":
            give_champion(player, _COST_TABLES[atom[1]])
        elif kind == "component":
            if not player.item_pool:
                player.refill_item_pool()
            give_random_item(player)
        elif kind == "neekos_help":
            player.add_to_item_bench('champion_duplicator')
        elif kind == "spatula":
            player.add_to_item_bench('spatula')
        else:
            raise ValueError(atom)
