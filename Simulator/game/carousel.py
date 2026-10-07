import numbers

from Simulator.battle.item_stats import item_builds as item_builds, basic_items, starting_items, offensive_items, defensive_items
from Simulator.battle.champion import champion
from Simulator.battle.combat_context import RandomProxy, rng_stream
from Simulator.game.pool_stats import COST_1, COST_2, COST_3, COST_4, COST_5
from Simulator.rng import STREAM_CAROUSEL

random = RandomProxy()

# A carousel picker is a callable fn(player, options) -> index. `options` is the list of
# units still on the carousel when that player's turn comes, each a dict
#   {"slot": position 0-8 on this carousel, "name": str, "cost": int, "stars": int,
#    "item": str or None}
# and the return value is an index into that list. Seats without a picker take the most
# expensive unit (the first one in carousel order among equal costs), as before.
# TFT_Simulator stores pickers per seat ("player_0" ...): TFTConfig.carousel_pickers or
# env.unwrapped.set_carousel_picker(seat, fn). A picker must be picklable (a module-level
# function or an instance of a module-level class) if the env is pickled.


def carousel(players, r, pool_obj, pickers=None, shuffle_items=False):
    """Run the carousel at round index r.

    pickers: optional {"player_<n>": fn(player, options) -> index}; see the note above.
    shuffle_items (TFTConfig.carousel_fixes): hand the items to the units in random order and
    use the Set 4 fifth-carousel table (see generateHeldItems).
    """
    # Keyed RNG streams: the round's carousel stream; no-op otherwise.
    with rng_stream(STREAM_CAROUSEL):
        _carousel(players, r, pool_obj, pickers, shuffle_items)


def _carousel(players, r, pool_obj, pickers, shuffle_items):
    # probability of certain arrangements during certain carousels
    # https://leagueoflegends.fandom.com/wiki/Carousel_(Teamfight_Tactics)
    alive = carousel_order(players, r)

    champions = generateChampions(r, pool_obj)
    items = generateHeldItems(r, set4_fifth_carousel=shuffle_items)
    if shuffle_items:
        # The item lists come in a fixed order (e.g. one of each component in item order) and
        # the units in cost order, so without a shuffle the same cost tier always holds the
        # same items.
        random.shuffle(items)

    # give all champions on the carousel an item
    for i, champ in enumerate(champions):
        champ.add_item(items[i])
    slots = list(range(len(champions)))

    # alive is in pick order
    for player in alive:
        if not champions:
            break
        picker = pickers.get("player_" + str(player.player_num)) if pickers else None
        if picker is None:
            # No picker: the highest cost available regardless of item
            index = default_pick_index(champions)
        else:
            index = _checked_pick(picker(player, carousel_options(champions, slots)), len(champions))
        current = champions[index]
        player.add_to_bench(current, from_carousel=True)
        champions.remove(current)
        slots.pop(index)
        # pool updating should be handled upon a player choosing a champion
        # much easier this way
        pool_obj.update_pool(current, -1)


def default_pick_index(champions):
    """Index of the most expensive unit; the first one in carousel order among equal costs."""
    best = 0
    for i, champ in enumerate(champions):
        if champ.cost > champions[best].cost:
            best = i
    return best


def carousel_options(champions, slots=None):
    """What a picker sees: one dict per unit still on the carousel, in carousel order."""
    if slots is None:
        slots = range(len(champions))
    return [{"slot": slot, "name": champ.name, "cost": champ.cost, "stars": champ.stars,
             "item": champ.items[0] if champ.items else None}
            for slot, champ in zip(slots, champions)]


def _checked_pick(index, count):
    if isinstance(index, bool) or not isinstance(index, numbers.Integral) or not 0 <= index < count:
        raise ValueError(f"carousel picker returned {index!r}; expected an int in [0, {count})")
    return int(index)


def carousel_order(players, r):
    """Pick order for the carousel at round index r: every living player, first pick first.

    The first carousel releases everyone at once (random order). Later carousels release
    players two at a time from lowest HP up; ties and the order inside a pair are random.
    Built from a list rather than by comparing players, because Player.__eq__ compares
    boards and benches, so identical players (e.g. everyone at the first carousel) compare equal.
    """
    alive = [player for player in players if player and player.health > 0]
    random.shuffle(alive)
    if r == 0:
        return alive
    alive.sort(key=lambda player: player.health)  # stable, so ties keep the shuffled order
    order = []
    for i in range(0, len(alive), 2):
        pair = alive[i:i + 2]
        random.shuffle(pair)
        order.extend(pair)
    return order


# this will handle champion generation based on the current round
def generateChampions(r, pool_obj):
    oneCosts = list(COST_1.items())
    twoCosts = list(COST_2.items())
    threeCosts = list(COST_3.items())
    fourCosts = list(COST_4.items())
    fiveCosts = list(COST_5.items())
    # remove champions from the list that have been exhausted from the pool (checking COST_1, COST_2, etc)
    for champ, count in oneCosts:
        if count <= 0:
            oneCosts.pop(champ)
    for champ, count in twoCosts:
        if count <= 0:
            twoCosts.pop(champ)
    for champ, count in threeCosts:
        if count <= 0:
            threeCosts.pop(champ)
    for champ, count in fourCosts:
        if count <= 0:
            fourCosts.pop(champ)
    for champ, count in fiveCosts:
        if count <= 0:
            fiveCosts.pop(champ)
    carouselChamps = []
    # first carousel - all 1 costs
    if r == 0:
        for _ in range(9):
            carouselChamps.append(champion(oneCosts.pop(random.randint(0, len(oneCosts) - 1))[0]))
    # second carousel - 1 one cost, 4 two costs, 4 three costs
    elif r == 6:
        carouselChamps.append(champion(oneCosts.pop(random.randint(0, len(oneCosts) - 1))[0]))
        for _ in range(4):
            carouselChamps.append(champion(twoCosts.pop(random.randint(0, len(twoCosts) - 1))[0]))
        for _ in range(4):
            carouselChamps.append(champion(threeCosts.pop(random.randint(0, len(threeCosts) - 1))[0]))
    # third carousel - 1 one cost, 2 two costs, 3 three costs, 3 four costs
    elif r == 12:
        carouselChamps.append(champion(oneCosts.pop(random.randint(0, len(oneCosts) - 1))[0]))
        for _ in range(2):
            carouselChamps.append(champion(twoCosts.pop(random.randint(0, len(twoCosts) - 1))[0]))
        for _ in range(3):
            carouselChamps.append(champion(threeCosts.pop(random.randint(0, len(threeCosts) - 1))[0]))
        for _ in range(3):
            carouselChamps.append(champion(fourCosts.pop(random.randint(0, len(fourCosts) - 1))[0]))
    # fourth carousel and beyond - 1 one cost, 2 two costs, 2 three costs, 2 four costs, 2 five costs
    elif r >= 18:
        carouselChamps.append(champion(oneCosts.pop(random.randint(0, len(oneCosts) - 1))[0]))
        for _ in range(2):
            carouselChamps.append(champion(twoCosts.pop(random.randint(0, len(twoCosts) - 1))[0]))
        for _ in range(2):
            carouselChamps.append(champion(threeCosts.pop(random.randint(0, len(threeCosts) - 1))[0]))
        for _ in range(2):
            carouselChamps.append(champion(fourCosts.pop(random.randint(0, len(fourCosts) - 1))[0]))
        for _ in range(2):
            carouselChamps.append(champion(fiveCosts.pop(random.randint(0, len(fiveCosts) - 1))[0]))
    return carouselChamps

# handles the item generation based on the current round
# also chooses what kind of item set to generate (e.g. offensive components only, defensive, utility, etc.)
def generateHeldItems(r, set4_fifth_carousel=False):
    """Item set for the carousel at round index r (Set 4 table, patch 10.19 notes).

    set4_fifth_carousel: draw the fifth carousel's 50% "all random unbuilt components" case as
    random components. Without it that case gives the full items built from one component,
    as the 3%-each cases do (kept as the default so default games do not change).
    """
    roll = random.random()
    if r == 0:
        if roll < 0.65:
            return generateAllComponents()
        elif roll < 0.76:
            return generateOffenseComponents()
        elif roll < 0.87:
            return generateDefenseComponents()
        elif roll < 0.98:
            return generateUtilComponents()
        elif roll < 0.995:
            return generateAllSpats()
        else:
            return generateFONs()
    elif r == 6:
        if roll < 0.80:
            return generateAllComponents()
        elif roll < 0.95:
            return generateAllComponentsSpat()
        else:
            return generateThreeSpatsRandComponents()
    elif r == 12:
        if roll < 0.50:
            return generateAllRandomComponents()
        elif roll < 0.80:
            return generateAllComponents()
        elif roll < 0.95:
            return generateAllComponentsSpat()
        else:
            return generateThreeSpatsRandComponents()
    elif r == 18:
        if roll < 0.80:
            return generateAllComponents()
        elif roll < 0.95:
            return generateAllComponentsSpat()
        else:
            return generateThreeSpatsRandComponents()
    elif r == 24:
        if roll < 0.50:
            if set4_fifth_carousel:
                return generateAllRandomComponents()
            return generateComponentItems(starting_items[random.randint(0, len(starting_items) - 1)])
        elif roll < 0.754:
            return generateFullItems()
        # 3% chance for a full set of items made with each component = 24% chance for all components
        elif roll < 0.994:
            # since they are equally weighted, can just do a random selection of non-spat components
            return generateComponentItems(starting_items[random.randint(0, len(starting_items) - 1)])
        else:
            return generateFONs()
    elif r >= 30:
        return generateHalfItems()

# random helper methods for generation of item sets for carousel below

def generateAllComponents():
    # generate a list of 1 of every component + 1 random duplicate component
    items = []
    for i in range(8):
        items.append(starting_items[i])
    # only 8 components but 9 champs on the carousel, so choose a random component
    items.append(starting_items[random.randint(0, len(starting_items) - 1)])
    return items

def generateOffenseComponents():
    # generate an item list of only offense components (BF, Rod, Bow)
    items = []
    for i in range(9):
        items.append(offensive_items[i % len(offensive_items)])
    return items

def generateDefenseComponents():
    # generate an item list of only defense components (Chain Vest, Belt, Cloak)
    items = []
    for i in range(9):
        items.append(defensive_items[i % len(offensive_items)])
    return items

def generateUtilComponents():
    # generate an item list of utility components and random components (sparring glove, tear, 7 random components)
    # NEED TO DOUBLE CHECK IF THIS IS ACTUALLY HOW UTILITY CAROUSEL IS GENERATED
    items = ['sparring_gloves', 'tear_of_the_goddess']
    for _ in range(7):
        items.append(starting_items[random.randint(0, len(starting_items) - 1)])
    return items

def generateAllSpats():
    # generate an item list of spatulas
    return ['spatula' for _ in range(9)]

def generateFONs():
    # generate an item list of FoN items
    return ['force_of_nature' for _ in range(9)]

def generateAllComponentsSpat():
    # generate an item list of all components, including a spatula
    items = []
    for i in range(9):
        items.append(basic_items[i])
    return items

def generateThreeSpatsRandComponents():
    # generate an item list of 3 spatulas and 6 random components
    items = ['spatula', 'spatula', 'spatula']
    for _ in range(6):
        items.append(starting_items[random.randint(0, len(starting_items) - 1)])
    return items

def generateAllRandomComponents():
    # generate an item list of completely random components
    items = []
    for _ in range(9):
        items.append(starting_items[random.randint(0, len(starting_items) - 1)])
    return items

def generateFullItems():
    # generate an item list of completely random items
    items = []
    # list of all possible completed items
    fullitems = list(item_builds.keys())
    for _ in range(9):
        # randomly choose an item from the full items list and simultaneously remove it (prevents duplicates)
        items.append(fullitems.pop(random.randint(0, len(fullitems) - 1)))
    return items

def generateComponentItems(component):
    # generate an item list of only items with the specified component
    # Since only 9 unique components, there should be exactly as many unique items as champions
    items = []
    for item in item_builds:
        if component in item_builds[item]:
            items.append(item)
    return items

def generateHalfItems():
    # generate an item list of half full items, half random components
    items = []
    fullitems = list(item_builds.keys())
    for _ in range(5):
        items.append(fullitems.pop(random.randint(0, len(fullitems) - 1)))
    
    for _ in range(4):
        items.append(basic_items[random.randint(0, len(basic_items) - 1)])
        
    return items
