# Fork notes

Fixes and options on top of upstream `main` at `a5718dd` (silverlight6/TFTMuZeroAgent).
Each bug fix is its own branch off `a5718dd` with one unit test and can go upstream as a
standalone PR. `develop` merges all of them plus `action-budget-options`. This file exists
only on `develop` and on the branches made from it: `rules-profile` (from `9149656`) and the
realism branches of the "Realism options" section (from `a2840a1` on), which carry it unchanged.

Round indices: idx0 = 1-1 carousel + 1-2 PvE, idx1 = 1-3, idx2 = 1-4, then six indices per
stage from idx3 = 2-1 (x-1 .. x-7, with the x-4 carousel folded into x-5). So idx8 = 2-7,
idx9 = 3-1, idx32 = 6-7, idx38 = 7-7. File:line references are to `a5718dd`.

## Candidate issues

| # | Issue | File:line (a5718dd) | Real Set 4 rule and source | Classification | Branch | Test | Changes game outcomes |
|---|---|---|---|---|---|---|---|
| 0 | Carousel gave a unit only to players with HP <= the first player's; at 1-1 only one player got a unit | `Simulator/game/carousel.py:14-21` | Everyone picks at the first carousel; later carousels release players in pairs from lowest HP (fandom wiki "Carousel (Teamfight Tactics)", linked in carousel.py:12) | Bug (fix was already on the branch, not re-researched here) | `fix-carousel-order` | `UnitTests/carousel_order_test.py` (4 tests) | Yes: every player now gets carousel units, and stage-1 PvE loot is no longer limited to one seat |
| 1 | Stage damage cutoffs one round late | `Simulator/game/game_round.py:17-24` (lookup 89-92); same table in `Simulator/battle/minion.py:262-269` and `Simulator/game/single_player_game_round.py:14-21` | Base player damage per stage 0/0/2/3/5/8/15 for stages 1-7. Patch 10.24 notes: "Base Player Damage Per Stage: 0/0/1/2/5/10/15 ⇒ 0/0/2/3/5/8/15"; no change in 10.25 or 11.1-11.8 notes (teamfighttactics.leagueoflegends.com/en-us/news/game-updates/teamfight-tactics-patch-10-24-notes/) | Bug. Tiers ended at idx 3/9/15/21/27, the first round of the next stage, so x-2 .. x-7 already used the next tier. Against the 10.24 table that is a full stage early: stage 2 dealt 2 from 2-2, stage 6 dealt 15 from 6-2 | `fix-stage-damage` | `UnitTests/stage_damage_test.py` (20 cases, 11 fail on main) | Yes: less damage per loss in stages 2-6, so HP, loss-streak length and game length change |
| 2 | 6-7 PvE round skipped | `Simulator/battle/minion.py:249` (`>= 33`); schedule `Simulator/game/game_round.py:38-83` | PvE is "first 3 fights on stage 1, and at the end of every stage afterwards" (wiki.leagueoflegends.com/en-us/TFT:Monster) | Bug. idx32 (6-7) is a minion round but fell through to "invalid round". Which monster Set 4 used at 6-7 is unverified; the fix uses the existing Herald board | `fix-pve-6-7` | `UnitTests/pve_schedule_test.py` (3 tests) | Yes, in games that reach 6-7: one more fight and loot drop |
| 3 | Round income starts late | `Simulator/game/player.py:1062-1068`; `Simulator/game/game_round.py:298-306`, `Simulator/game/single_player_game_round.py:124-133` (no income in round_1) | Passive gold "2 / 2 / 3 / 4 at the beginning of rounds 1-2 / 1-3 / 1-4 / 2-1", then 5 plus interest and streak (wiki.leagueoflegends.com/en-us/TFT:Gold); 2 XP per round (TFT:Experience) | Bug. No income at 1-2 or 1-3; table [0,2,2,3,4] paid 2/3/4 at 1-4/2-1/2-2. Now 4/7/11/17 gold at 1-3/1-4/2-1/2-2 and level 4 at 2-2 | `fix-early-income` | `UnitTests/early_income_test.py` (4 tests) | Yes: +7 gold by 2-2 and earlier levels for every player |
| 4 | Matchmaking weight bug | `Simulator/game/game_round.py:242` (`if i < 0`), `248-253` (weighted walk, `randint(0, weights)`) | Riot's matchmaker makes repeat opponents "extremely unlikely" (Dexerto on patch 9.16); with 7 alive you cannot face anyone from your last 4 rounds, with 6 the last 3 (Upcomer, 2021) | Bug. The walk could land on opponents below `MATCHMAKING_WEIGHTS`; the fallback never took the highest weight. 12000 pairings: ineligible picks with an eligible one available 1498 -> 0; repeat of last opponent 383 -> 307. The weight scheme itself is a design approximation and unchanged | `fix-matchmaking-weights` | `UnitTests/matchmaking_test.py` (3 tests; the proportionality test also passes on main) | Yes: different pairings and RNG draws |
| 5 | `shop_empty` closes the buy mask after one purchase | `Simulator/game/player.py:1053-1059` (`not all(self.shop)`); mask `Simulator/encoding/token/action.py:313-317` | Every unit left in the shop can be bought (basic game rule) | Bug. After one buy the whole buy mask was 0 until the next refresh | `fix-shop-buy-mask` | `UnitTests/shop_buy_mask_test.py` (3 tests) | Yes for any masked policy (RL agents, Default_Agent): more than one buy per shop |
| 6 | Seat order from a Python set | `Simulator/game/player_manager.py:14-16, 23-26, 159-161` | n/a (reproducibility) | Bug. Seat -> player_num and every loop that draws from the shared RNG followed set order, which depends on PYTHONHASHSEED (with 0, seat player_5 is player_num 0) | `fix-seat-order` | `UnitTests/seat_order_test.py` (2 tests, one runs resets under PYTHONHASHSEED 0/1/2) | Yes: same seed now gives one game in every process; per-seat results differ from runs made before |
| 7a | Rule bot: "katerina" | `Simulator/generators/default_agent_stats.py:54, 69, 102` | Unit is Katarina (`katarina` in the pool) | Bug | `fix-default-agent` | `UnitTests/default_agent_test.py::test_every_name_in_the_bot_tables_is_a_champion`, `::test_katarina_gets_a_board_slot` | Default_Agent baselines only |
| 7b | Rule bot: bench-to-board swap dead | `Simulator/generators/default_agent.py:317, 324` (round_3_10, also returned buy "3_" instead of move "5_"), `484` (round_11_end) | n/a (bot logic) | Bug. Champion object compared with a list of names | `fix-default-agent` | `::test_round_3_10_swaps_a_better_bench_unit_in`, `::test_round_11_end_swaps_a_comp_unit_in` | Default_Agent baselines only |
| 8a | Chosen units "1-star at base cost" | `Simulator/game/player.py:341`; `Simulator/encoding/token/action.py:317` | Chosen "are already at 2-star level, so they cost three times their normal 1-star price" (patch 10.19 notes) | Bug in price only. The audit claim is partly wrong: Chosen are 2-star, take 3 copies from the pool and fight with 2-star stats. They were charged the 2-star sell value (3/5/8/11/14) instead of 3/6/9/12/15 | `fix-chosen-price` | `UnitTests/chosen_price_test.py` (11 cases) | Yes: Chosen cost 1 more gold for 2-5 costs |
| 8b | Fortune pays +3 on every win | `Simulator/game/player.py:1875-1883, 1900-1908, 1925-1928`; `Simulator/battle/origin_class_stats.py:304` | Fortune pays out on a win by rounds lost; wiki table 2.5/6/10.5/17/24/31/38/45/55/70 for 0-9 losses (wiki.leagueoflegends.com/en-us/Fortune_(Teamfight_Tactics)); V10.20 set the 0-loss value to 3, V10.21 to 2.5; 6 Fortune adds an extra orb on a win | Design approximation; now `TFTConfig(fortune_orbs=True)`, see row 13. Sim pays `ceil(value)` as plain gold (3 after 0 losses, which is the "+3 on every win"); the real payout is a loot orb of that value. 6 Fortune counts losses twice instead of an extra orb | `realism-fortune-orbs` (row 13) | `fortune_orbs_test.py` | No with defaults |
| 9 | Matchups fixed before planning | `Simulator/game/game_round.py:291-296` (`decide_player_combat` in `start_round`), `257-284` (`opponent_options`), `274-275` (`possible_opponents` reset); obs `Simulator/encoding/token/basic_observation.py:368-376`, `Simulator/encoding/vector/observation.py:289-294`; infos `Simulator/simulators/tft_simulator.py:162, 292, 347` | The real client does not show the next opponent; trackers can narrow the candidates but not pinpoint them (Upcomer, 2021) | Design choice with information exposure; `TFTConfig(hide_next_opponent=True)` removes it, see row 14. In default mode (unchanged) the obs candidate set is the eligible seats plus the real opponent, which `game_round.py:270-273` always adds (`1 not in opponent_options` tests the keys, so it is always true); that is the tracker view. Exact leaks: when nobody is eligible the set is only the real opponent, and the ghost fight names the copied seat (`game_round.py:280-284`); on main a drawn ineligible opponent can also stand out (fixed by #4). Outside the obs: `info["player"]` is the live Player, and its `possible_opponents` is already 0 for the drawn opponent (`game_round.py:274-275`); `env.unwrapped.game_round.matchups` lists every pairing | `realism-hidden-opponent` (row 14) | `hidden_opponent_test.py` | No with defaults |
| B | 15 actions per turn, passes included | `Simulator/config.py:16`; `Simulator/simulators/tft_simulator.py:34, 194-195, 302-307`; obs scale `basic_observation.py:352`, `vector/observation.py:302` | n/a (env interface) | Not a bug: new options. `TFTConfig.pass_ends_turn` (default False) and `max_actions_per_round` now also scales the obs. Agents whose turn is over stay in the cycle with a pass-only mask and `info["turn_over"]`; no truncation | `action-budget-options` | `UnitTests/action_budget_test.py` (8 tests, incl. PettingZoo api_test / parallel_api_test) | No with defaults: 12-round parallel and AEC trajectories hash-identical to main. Yes when enabled |

## Unverifiable or needs checking

- 6-7 monster: which board Set 4 used at 6-7 (the sim reuses the Herald board for 6-7 and 7-7).
  Needs a Set 4 round list (patch 10.19-11.8).
- Fortune: the payout at 0 losses (wiki says 2.5, a Set 4 loot-table guide on tacter.com says
  none; that guide now returns 404), the orb contents (row 13 uses assumptions) and the
  10-12 loss values (separate tables since 10.23, never published). The sim targets 10.21-11.1
  (11.2, Set 4.5, lowered 0/1 losses to 2.2/5.5).
- Matchmaking: exact Set 4 rules for 8 and 5 or fewer alive players and for ghost fights.
- PvE damage (row 10): no Set 4 page gives a separate PvE formula; the player-combat formula is
  used. Whether a PvE loss breaks a win streak or counts for Fortune in Set 4 is not confirmed
  (row 10 leaves streaks alone).
- Carousel cost mix per carousel and the PvE orb tables (see the audits in "Realism options").

## Other findings, not fixed

- PvE losses deal no HP damage: moved to row 10 (`TFTConfig(pve_damage=True)`).
- A win against a ghost pays nothing: `game_round.py` `combat_phase` only handles the ghost
  fight's loss; `Player.won_ghost` (win gold, streak, Fortune) is never called. Probably a bug
  (the real game counts a ghost win as a win); fixing it changes default games.
- `composition_test.py::test_list` is flaky: it draws actions with unseeded global
  `np.random` and plays them through an unbound context with a random seed; with fixed NumPy
  seeds it failed 1-2 of 30 runs on `a2840a1` too. It failed in one of the full-suite runs
  below.
- `game_over` is `current_round > 48` (`tft_simulator.py:210`) but `game_rounds` has 44
  entries (`game_round.py:38-83`), so a game still running at idx44 would raise IndexError.
- Buy mask is all 0 when the bench is full (`action.py:313`), even when the buy would
  complete an upgrade, which the real game allows.
- Default_Agent: the checks[4] block resets `checks[3]` (`default_agent.py:378, 523, 630`),
  so the sell-for-interest check runs on every step.
- `examples/default_agent_vs_random.py:16-17` passes the flat env mask to Default_Agent,
  which indexes a 2D mask (`default_agent.py:111, 278, 348`).
- Single-player env: `reset()` does not zero `action_count`
  (`tft_single_player_simulator.py:44, 52, 159`).
- The greedy pairing order still produces about 2.6% repeat opponents after #4.

## Rules profiles (branch `rules-profile`)

`TFTConfig(rules="set4" | "set18")`, default `"set4"`. A profile
(`Simulator/game/rules.py`, `RulesProfile`) holds every economy number; champions, traits,
items, Chosen and combat stay Set 4 in both. The env passes the profile to the shared `pool`
(`pool(rules=...)`), and `Player` and both `Game_Round` classes read it from the pool, so
objects built without one (unit tests, the position/item simulators, battle generators) keep
Set 4. The single-player env honours `rules` too.

Routed through the profile: shop odds per level (`pool.sample`), Chosen cost odds per level,
copies per champion (`pool.reset`, `pool.update_pool` cap), XP table and max level, passive
XP, Buy XP gold and XP, refresh cost, passive gold, interest, streak gold, PvP win gold
(`Player`), base player damage per stage (`game_round.py`, `single_player_game_round.py`,
`minion.py`) and damage per surviving unit (`champion.unit_damage`, used by `champion.run`).
`"set4"` uses exactly the old values (the same shop and Chosen odds objects); with default
settings a seed gives the same game as `develop` at `9149656`
(`UnitTests/rules_profile_games_test.py` compares 12-round parallel and AEC random
trajectories and a full Default_Agent game with hashes recorded on `develop`).

Set 18 is "Enchanted Wilds" (patch 18.1 notes published 2026-08-25, live 2026-08-26); values
are as of patch 18.4 (notes 2026-10-06). 18.1 changed no economy numbers, 18.2 changed XP, 18.3
and 18.4 changed none (18.4 only shortened combat arrival/departure by 1 s each). Patch notes
for 17.2-17.8 have no economy changes; 17.1 changed level 7 odds. Earlier values come from the
patch that last changed them, checked against the LoL wiki and Set 18 tables on third-party
sites. Percentages are cost 1/2/3/4/5.

| Rule | Set 4 (`set4`) | Set 18 (`set18`) | Source for the Set 18 value | Confidence |
|---|---|---|---|---|
| Shop odds L1-L5 | L1-2 100; L3 75/25; L4 55/30/15; L5 45/32.5/20/2.5/0 | L1-2 100; L3 75/25; L4 55/30/15; L5 45/33/20/2/0 | wiki.leagueoflegends.com/en-us/TFT:Champion; same on seemeta.com/en/tft/set-18/odds, tftsense.gg, esportstales.com, tftflow.com, noxutft.com | wiki |
| Shop odds L6 | 25/40/30/5/0 | 30/40/25/5/0 | Patch 13.23 notes "Level 6: 25/40/30/5/0% ⇒ 30/40/25/5/0%" (teamfighttactics.leagueoflegends.com/en-us/news/game-updates/teamfight-tactics-patch-13-23-notes/); wiki agrees | official |
| Shop odds L7 | 20/30/35/14/1 | 19/30/40/10/1 | Patch 17.1 notes "Level 7: 16/30/43/10/1% ⇒ 19/30/40/10/1%" (…/teamfighttactics-patch-17-1/), undoing 16.4 "19/30/40/10/1% ⇒ 16/30/43/10/1%" (…/teamfighttactics-patch-16-4/); no later change in 17.2-18.4. Wiki, seemeta, tftsense agree. **Conflict:** esportstales, tftflow, noxutft and tft.ninja list 16/30/43/10/1, the value 17.1 reverted | official (flagged) |
| Shop odds L8 | 15/20/35/25/5 | 15/20/32/30/3 | Patch 16.1 notes "Level 8: 17/24/32/24/3% ⇒ 15/20/32/30/3%" (…/teamfighttactics-patch-16-1/); wiki and third-party agree | official |
| Shop odds L9 | 10/15/30/30/15 | 10/17/25/33/15 | Patch 16.1 notes "Level 9: 12/18/25/33/12% ⇒ 10/17/25/33/15%"; wiki and third-party agree | official |
| Shop odds L10 | row 5/10/20/40/25 present, unreachable | 5/10/20/40/25 | Patch 13.23 notes "Level 10: 5/10/20/40/25 (No change)"; no later change found; wiki TFT:Champion and all third-party tables agree | official |
| Shop odds L11 | row 1/2/12/50/35 present, unreachable | 1/2/12/50/35, stored but unreachable (max level 10) | wiki TFT:Champion ("Level 11 ... is a combination of Level Up and High End Shopping Augments") | wiki |
| Max level | 9 | 10 | wiki.leagueoflegends.com/en-us/TFT:Experience; 16.1 and 18.2 notes change "XP to 10" | official |
| XP to next level, 1→2 … 9→10 | 2/2/6/10/20/36/56/80/- (212 to level 9) | 2/2/6/10/20/36/56/68/68 (268 to level 10) | Patch 18.2 notes "Level 7 to Level 8: 60 ⇒ 56", "Level 8 to Level 9: 68 ⇒ 64", "Level 9 to Level 10: 68 ⇒ 64", and 18.2 mid-patch update (Sep 14) "XP From Level 8-9: 64 ⇒ 68", "XP From Level 9-10: 64 ⇒ 68" (teamfighttactics.leagueoflegends.com/en-sg/news/game-updates/teamfight-tactics-patch-18-2); 1→7 unchanged since 14.15 notes "2/2/6/10/20/36/…" (…/teamfighttactics-patch-14-15-notes/). tftips.app (Set 18) agrees. **Conflict:** the brief said only 9→10 was reverted; the notes revert both 8→9 and 9→10. Wiki and noxutft still show 60 for 7→8 (before 18.2) | official (flagged) |
| Passive XP | 2 per round from 1-2 | same | wiki TFT:Experience ("You gain 2 Experience for free at the end of each round") | wiki |
| Buy XP | 4 gold → 4 XP | same | wiki TFT:Experience; noxutft | wiki |
| Shop refresh | 2 gold | 2 gold | No change in any 16.x-18.x notes read; no explicit Set 18 statement found | guess (unchanged) |
| Copies per champion, cost 1-5 | 29/22/18/12/10 (the left side of 13.23's "1-cost copies: 29 ⇒ 22" etc.) | 30/25/18/10/9 | Patch 14.15 notes "1-costs: 22 ⇒ 30", "2-costs: 20 ⇒ 25", "3-costs: 17 ⇒ 18", 4-costs 10, 5-costs 9; no later change found; wiki and every Set 18 table agree | official |
| Roster | 13/13/13/11/8 champions per cost | Set 4 roster kept (Set 18 has 14/13/14/14/10), so the pool holds 390/325/234/110/72 units instead of Set 18's 420/325/252/140/90 | by design | - |
| Passive gold 1-2 / 1-3 / 1-4 / 2-1 | 2/2/3/4 | 2/2/3/4 | wiki.leagueoflegends.com/en-us/TFT:Gold; noxutft (Set 18) | wiki |
| Passive gold from 2-2 | 5 | 5 | same | wiki |
| Interest | 1 per 10 gold held before income, max 5 | same | same | wiki |
| Streak gold (length: gold) | 2-3: 1, 4: 2, 5+: 3 (V10.8) | 2-4: 1, 5: 2, 6+: 3 | Patch 14.1 notes "1g: 2 - 3 ⇒ 3 - 4", "2g: 4 ⇒ 5", "3g: 5 ⇒ 6" (…/teamfighttactics-patch-14-1-notes/) and 14.8 notes "A streak of 2 wins or losses in a row now grants 1 gold" (…/teamfighttactics-patch-14-8-notes/); tftips.app and noxutft (Set 18) agree. **Conflict:** wiki TFT:Gold still lists 3-4: 1 (it misses 14.8) | official (flagged) |
| PvP win gold | 1 | 1 | wiki TFT:Gold | wiki |
| Base player damage, stages 1..8 | 0/0/2/3/5/8/15/15 (10.24) | 0/2/6/7/10/12/17/150 | 14.8 notes "0/0/3/5/7/9/15/150 ⇒ 0/2/5/7/9/11/17/150"; 14.9 notes "0/2/5/7/9/11/17/150 ⇒ 0/2/5/8/10/12/17/150" (…/teamfighttactics-patch-14-9-notes/); 16.1 notes "Stage 3 Base Damage: 5 ⇒ 6", "Stage 4 Base Damage: 8 ⇒ 7"; tftips.app, tftflow, lolchess (Set 18) agree. **Conflict:** op.gg and tft.ninja show 0/2/5/8/10/12/17 (before 16.1); the brief's 2/5/7/10/12/17 matches no single patch | official (flagged) |
| Damage per surviving enemy unit | 0/2/4/6/8/10/11/12/... (2 each for the first 5, then 1) | 1 each | 14.8 notes "Surviving Enemies Damage: 2/2/2/1/1/etc ⇒ 1/1/1/1/1/etc" | official |
| PvE rounds | 1-2, 1-3, 1-4, x-7 every stage | same, not routed | 18.1 notes ("You still shouldn't miss loot at Stage 4-7"); stage layout on tft.ninja/guides/game-mechanics/stages | official / third-party |
| Carousel at 1-1 and x-4 | yes | same, not routed | 18.1 notes ("The Carousel has returned!") | official |
| Sell value | full cost at 1-star or 1-cost, otherwise 1 less | same, not routed | wiki TFT:Champion | wiki |
| Chosen cost odds at levels 10-11 | n/a | repeat level 9 (60% 4-cost, 40% 5-cost) | Chosen is Set 4 only, Set 4 had no level 10 | guess |

Set 4 column: the values the simulator already used. Stage damage (10.24), streak gold (V10.8)
and passive gold (wiki TFT:Gold) were checked earlier; the shop odds, XP table and pool sizes
are not re-verified here.

Data Dragon lead: Riot's developer docs (developer.riotgames.com/docs/tft) list the TFT Data
Dragon files as tft-arena, tft-augments, tft-champion, tft-item, tft-queues, tft-regalia,
tft-tactician and tft-trait; none has shop odds. The noxelisdev/TFT_DDragon mirror's `data/`
folder could not be listed from here (GitHub API access to that repo is not enabled, tree
pages are blocked by robots.txt), so no odds were taken from it. Its README labels 18.1 as
"Set 17 (Enchanted Wilds)" and gives a Set 18 date of August 12th; the patch notes say
Set 18 and August 25.

Levels 10 and 11: Set 18 reaches level 10 with XP (max_level 10, board cap 10 units). Set 18
also has five cost tiers, so the level 10 odds apply unchanged to the Set 4 roster's five
tiers. Level 11 only comes from augments, which are not modelled; its odds row is stored but
nothing reaches it. Chosen (Set 4) has no odds for level 10, so levels 10-11 reuse level 9's.
The token observation's `assert level < 10` is now `level <= player.max_level`;
`level / 10` scalars reach 1.0 at level 10.

Out of scope (Set 18 mechanics with no Set 4 content to hang them on): Wisps (every other
shop, seven categories, bought with gold, 18.2/18.3 Wisp price changes), augments (including
economy augments and level 11), Opening Encounters (Reroll Subscription etc.), artifacts and
emblems, 4-star units, unit roles and their mana rules, the Set 18 roster, traits and items,
the Set 18 carousel contents ("more champions and/or champions with higher costs"), PvE loot
overflow from 4-7, Set 18 PvE monsters and loot tables (the Set 4 loot orbs are kept), the
18.3 targeting revert and the 18.4 combat arrival/departure times, Double Up and Hyper Roll
values. PvE losses still deal no HP damage under either profile (see "Other findings").

Other findings while doing this, not changed: the carousel (`carousel.py`) and loot orbs
(`loot_orb.give_champion`) read the module-level `pool_stats.COST_*` dicts, not the live
pool, so they ignore pool depletion and the profile's copy counts; the token observation
asserts `game_round < 40`, so a game still alive at 8-2 (idx 40) would stop with an
AssertionError (not hit in the games run here; stage 8 deals 150 damage per loss under
`set18`).

Game pace with Default_Agent in all 8 seats (6 seeds per profile, 11-16; means over the
living players at the start of each stage, after income). The bot is tuned to Set 4: it buys
XP only below level 8 with 54+ gold and rolls at level 8, so it never uses levels 9-10 and
levels the same under both profiles; the differences come from streak gold, damage, pool
sizes and shop odds.

| Stage start | set4 gold / level / HP / alive | set18 gold / level / HP / alive |
|---|---|---|
| 2-1 | 7.4 / 3.00 / 100 / 8 | 7.5 / 3.00 / 100 / 8 |
| 3-1 | 47.3 / 5.00 / 86.1 / 8 | 45.8 / 5.00 / 88.1 / 8 |
| 4-1 | 68.4 / 6.77 / 60.3 / 8 | 69.5 / 6.71 / 63.5 / 8 |
| 5-1 | 70.8 / 8.00 / 39.5 / 6.3 | 69.9 / 8.00 / 41.5 / 7.0 |
| 6-1 | 66.7 / 8.00 / 31.2 / 2.8 | 51.2 / 8.00 / 26.7 / 3.5 |
| 7-1 | no game reached it | 68.0 / 8.00 / 8.5 / 2 (1 game) |

Last round played (round index): set4 30/29/27/28/27/29 (mean 28.3, about 6-2); set18
28/30/33/31/29/28 (mean 29.8, about 6-3). Set 18 moves damage from units to the stage: with
n survivors (n <= 5) a loss costs 2n in stage 2 under set4 and 2 + n under set18, and with 4
survivors both profiles charge 10 / 11 / 13 vs 14 / 16 in stages 3-6. Fewer survivors hurt
more under set18, more survivors hurt more under set4; stage 8 (150) ends a set18 game.

## Realism options (develop after `a2840a1`)

Six opt-in `TFTConfig` fields, one branch each off `develop`, merged in this order:
`fix-pve-damage`, `realism-carousel-pick` (two options), `realism-fortune-orbs`,
`realism-hidden-opponent`, `rng-keyed-streams`. Every option is off by default and
`TFTConfig()` games are identical to `a2840a1`: `UnitTests/realism_defaults_test.py` hashes two
complete seeded random-action games (seed 11 ends at round index 34, seed 12 at 32;
observations, rewards, terminations, truncations, infos with the Player reduced to its state,
and every player's state after each step) against hashes recorded on `a2840a1`, once with
`TFTConfig()` and once with every option explicitly off; `rules_profile_games_test.py` still
matches its 12-round parallel and AEC hashes and the full Default_Agent game. None of the
options is wired into the single-player env (`tft_single_player_simulator.py`). File:line
references in this section are to `develop` at `158ee62`.

| # | Change | File:line | Real rule and source | Classification | Branch | Test | Default trajectories |
|---|---|---|---|---|---|---|---|
| 10 | PvE losses cost HP: `TFTConfig(pve_damage=True)` | `Simulator/battle/minion.py:213` (`minion_round(..., pve_damage)`), `309-315` (loss path); `Simulator/game/player.py:1987` (`pve_loss`); `Simulator/game/game_round.py:375, 396`; `tft_simulator.py:56` | "Like player combats, the Tactician will take damage if they lose the combat." (wiki.leagueoflegends.com/en-us/TFT:Monster); the Sets 1-3 page says the same (leagueoflegends.fandom.com/wiki/Monster_(Teamfight_Tactics)); upstream's own `UnitTests/minion_test.py::combatTest` expects HP loss. No Set 4 page gives a separate PvE formula, so the player-combat formula is used: stage damage (10.24 table) plus damage per surviving monster (`champion.unit_damage`, 2 per unit for the first five under `set4`). A draw (time-out) costs stage damage | Bug (was "Other findings"): `game_round.py` never passed `other_rewards`, and `minion_combat` only applied damage when it was truthy. Behind an option so default games keep their hashes; recommended on. Streaks, match history and the Fortune counter are not touched by PvE results (assumption: monster rounds are streak-neutral; no Set 4 source found either way). The old `other_rewards=True` path (calls `loss_round`, so it also changes streaks) is unchanged and unused by the game | `fix-pve-damage` | `UnitTests/pve_damage_test.py` (15: fake and real fights at 1-2 .. 6-7, env stage 1 with three seeds) | No with defaults. On: two random games end at index 30 / 29 instead of 34 / 32 |
| 11 | Carousel pick choice per seat: `TFTConfig(carousel_pickers={seat: fn})`, `env.unwrapped.set_carousel_picker(seat, fn)` | `Simulator/game/carousel.py:22-68` (`carousel`, picker call), `71` (`default_pick_index`), `80` (`carousel_options`), `89` (`_checked_pick`); `Simulator/game/game_round.py` (`carousel_pickers`, passed by both carousel calls); `tft_simulator.py:60, 154` | Players pick in carousel order and choose any remaining unit with its item; a player who does not pick gets "a random remaining unit with priority for higher-tier units" (wiki.leagueoflegends.com/en-us/TFT:Carousel) | New option (the sim took the most expensive unit for everyone). Seats without a picker keep that rule with the same RNG use | `realism-carousel-pick` | `UnitTests/carousel_pick_test.py` (17, incl. pickle/branch with pickers set and "default-like picker = no picker" over 13 rounds) | No with defaults (no picker) |
| 12 | Carousel items: `TFTConfig(carousel_fixes=True)` | `carousel.py:42-45` (item shuffle), `175-226` (`generateHeldItems(..., set4_fifth_carousel)`) | Set 4 carousel item tables (patch 10.19 notes, teamfighttactics.leagueoflegends.com/en-us/news/game-updates/teamfight-tactics-patch-10-19-notes/; same table on TFT:Carousel): fifth carousel "50% unbuilt [random components], 25.4% full items, 3% each [full items built from one component], 0.6% Force of Nature" | Bug (fifth carousel: the 50% unbuilt case gave full items from one component, so 5-4 always offered full items instead of half the time) plus design approximation (item lists come in a fixed order and units in cost order, so e.g. at 2-4, in the 80% one-of-each case, the 1-cost always held B.F. Sword and the 3-costs Bow / Gloves / Tear / the duplicate); with the option the items are shuffled onto the units (assumption: pairing is random in the real game) | `realism-carousel-pick` | `carousel_pick_test.py::test_items_follow_cost_order_without_fixes_and_are_shuffled_with_fixes`, `::test_fifth_carousel_table` | No with defaults |
| 13 (was 8b) | Fortune pays loot orbs: `TFTConfig(fortune_orbs=True)` | `Simulator/game/loot_orb.py:149-320` (`FORTUNE_*`, `gen_fortune_orb`, `gen_fortune_extra_orb`, `give_fortune_orb`); `Simulator/game/player.py:1911, 1939, 1967` (switches), `1974` (`fortune_orb_payout`); `player_manager.py` (flag per player); `tft_simulator.py:69` | Set 4: "Winning combat against a player will give bonus orbs. The longer you've gone without an orb, the bigger the payout"; 3: bonus orbs, 6: "extra bonus orbs with rare loot"; average value 2.5/6/10.5/17/24/31/38/45/55/70 for 0-9 losses (wiki.leagueoflegends.com/en-us/Fortune_(Teamfight_Tactics); 10.20 notes .../teamfight-tactics-patch-10-20-notes/ raised them, 10.21 notes .../teamfight-tactics-patch-10-21-notes/ set 0/1/2 losses to 2.5/6/10.5, removed 5-costs at 4 losses, 6 Fortune orb average 10.25 -> 11.65); 10.23 added separate tables for 10-12 losses (values unpublished); hidden counter "can go up to 12", the 6 Fortune orb "does not scale with loss streaks" (leagueoflegends.fandom.com/wiki/Fortune_(Teamfight_Tactics)) | Design approximation, now behind an option (default off keeps the old payout so default games do not change). With it: one orb per win from the loss table, the counter counts each loss once (the old code counts twice with 6 Fortune) and stops at 12, 6 Fortune adds the 11.65 extra orb. Contents are assumptions, see "Fortune orb contents" below; every package has the table value in expectation | `realism-fortune-orbs` | `UnitTests/fortune_orbs_test.py` (42: per-package and per-orb means for 0-12 losses, contents rules, counter, 6 Fortune, option off = old gold payout, delivery) | No with defaults. On: 11 orbs paid in 4 Default_Agent games (seeds 5-8) |
| 14 (was 9) | Hidden next opponent: `TFTConfig(hide_next_opponent=True)` | `Simulator/game/game_round.py:319-327` (`start_round`), `331` (`has_player_combat`), `336` (`opponent_candidates`), `354` (`expose_opponent_candidates`), `408-412` (draw in `combat_round`, `last_matchups`); `tft_simulator.py:74, 301` (`info["opponent_candidates"]`) | The client does not show the next opponent; players can narrow it to the opponents not excluded by the recent-opponent rule (Upcomer, 2021; see row 9) | Information exposure, now behind an option. Pairings are drawn in `combat_round` after the last planning action. During planning `player.opponent_options` (the obs opponent slots) and `info["opponent_candidates"]` hold the candidates: alive opponents whose weight on either side is >= `MATCHMAKING_WEIGHTS` (both follow from the public matchup history), every alive opponent if that leaves none, nobody before a PvE round. The weights now advance only on player-combat rounds (default mode also draws before PvE rounds) | `realism-hidden-opponent` | `UnitTests/hidden_opponent_test.py` (9: obs/info = candidates for 22 rounds, `matchups == []` while planning, a different RNG state at the end of planning changes the pairings but not in default mode, one draw per combat round) | No with defaults |
| 15 | Independent random streams: `TFTConfig(rng_streams="keyed")`, `env.unwrapped.reseed_rng(seed)` | `Simulator/rng.py:94` (`EnvRNG.reseed`), `143-259` (stream kinds, `LazyStreamRNG`, `KeyedStreams`); `Simulator/battle/combat_context.py:40` (`streams`), `87-93` (`reset_combat` keeps it), `119` (`rng_stream`); scopes in `player.py:283` (shop), `1688` (start of round), `1977` (Fortune), `game_round.py:107, 192-195` (fights), `241` (pairings), `374, 394` (PvE), `carousel.py:22`, `minion.py:319` (loot), `tft_simulator.py:413` (actions); `default_agent.py:31` (bot generator); `tft_simulator.py:80, 198-230` (`reset`, `reseed_rng`, `_seed_bots`) | n/a (reproducibility, common random numbers for branch comparisons) | New option. "shared" (default) is the old single stream; `rng_stream` is a no-op then | `rng-keyed-streams` | `UnitTests/rng_streams_test.py` (11: extra refresh by one seat leaves every other seat identical for rounds r..r+3, shared mode diverges, PYTHONHASHSEED 0/1/2 subprocesses, reseed of restored copies in both modes, numpy reseed, bot generators, shop odds, pickle) | No with "shared" |
| 16 | Guardian Angel holders get their own `will_revive` list (a bug fix, not an option) | `Simulator/battle/items.py:45-49` (`initiate` copies the list); the shared entry is `Simulator/battle/item_stats.py:24`, the in-place write `Simulator/battle/ability.py:2854` (`zilean`) | n/a (state isolation) | Bug: every Guardian Angel holder got the item table's own list, and a Zilean orb is written into it in place. From the first fight where a Zilean put an orb on a Guardian Angel holder, every Guardian Angel holder on both teams, in that fight and in every later fight of the process (any game), had that Zilean's revive, and Zilean skipped them as targets. Games depended on what the process had played before: a long-lived worker built different states than a fresh process (found through the bank v2 rebuild check in kkkyr1e/tft) | `fix-guardian-angel-shared-state` | `UnitTests/guardian_angel_state_test.py` (3: one list per holder, the table unchanged after a Zilean fight, a later fight unchanged) | Yes, from the first fight where a Zilean orb lands on a Guardian Angel holder; none of the recorded hash-test games has one (they all still pass) |
| 17 | A mage's second cast needs a target, like the first (a bug fix, not an option) | `Simulator/battle/champion.py:389-396` (`champion.ability`); the crash site was `Simulator/battle/ability.py:1682` (`nunu`) | n/a (crash) | Bug: `champion.ability` skips the cast when no enemy can be targeted (the remaining enemies wait on a Guardian Angel or Zilean revive), but the mage trait's second cast ran without that check. When the first cast killed the target and the only enemies left were waiting on a revive, the second cast ran with `target` None and abilities that read the target crashed: `nunu` (`champion.target.health`) raised AttributeError and ended the game. Seen once in about 3,800 bank branches played on `5e2cb1c` in kkkyr1e/tft (a Mage's Cap Nunu against an Evelynn holding a Zilean orb; the branch replays to the crash on `5e2cb1c` and finishes with the fix). The fix finds a new target before the second cast (as the first cast's `default_ability_calls` would) and skips the cast when there is none | `fix-mage-second-cast-target` | `UnitTests/mage_second_cast_test.py` (3: no second cast without a target, a second cast retargets, a second cast on a surviving target) | Only where the second cast had no target: before, a game crashed (or a target-free ability cast anyway), now the cast is skipped; the recorded hash-test games all still pass |

Row 8b and row 9 of the first table are now rows 13 and 14; the PvE-damage item of "Other
findings" is row 10.

### Using the options

```python
from Simulator.simulators.tft_simulator import TFTConfig, parallel_env

def pick_cheapest(player, options):          # module level, so the env stays picklable
    return min(range(len(options)), key=lambda i: options[i]["cost"])

env = parallel_env(TFTConfig(pve_damage=True, carousel_fixes=True, fortune_orbs=True,
                             hide_next_opponent=True, rng_streams="keyed",
                             carousel_pickers={0: pick_cheapest}))
env.unwrapped.set_carousel_picker("player_3", my_picker)   # or 3; None restores the default
observations, infos = env.reset(seed=1)
infos["player_0"]["opponent_candidates"]                   # e.g. ["player_2", "player_5", "player_6"]
env.unwrapped.reseed_rng(np.random.SeedSequence(42))      # after restoring a pickled copy
```

- Carousel picker: `fn(player, options) -> int`. Called when that seat's turn comes, during
  `reset()` for 1-1 (set it before `reset`) and during the `step` that plays 2-4, 3-4, ...
  (index 6, 12, ...). `player` is the live `Player` (gold, HP, board, bench, items, `round`);
  `options` lists the units still on the carousel in carousel order, each
  `{"slot": 0-8, "name": str, "cost": int, "stars": 1, "item": str}`; return an index into
  `options` (Python or NumPy int). Anything else raises `ValueError`. Pickers live in a plain
  dict `env.unwrapped.carousel_pickers` (shared with `game_round`), are kept across `reset`, and
  are pickled with the env, so they must be module-level functions or instances of
  module-level classes (no lambdas or closures). Draw from your own RNG inside a picker, not
  from the simulator's.
- Fortune orbs: `player.fortune_orb_log` lists every payout as
  `{"round", "losses", "orbs": [[("gold", n) | ("champion", cost) | ("component",) | ("neekos_help",) | ("spatula",)], ...]}`.
- Hidden opponent: during planning the observation's opponent fields hold the candidate set:
  token obs `game_scalars[2:5]` = the first three candidate seat numbers (0 if fewer),
  `emb_scalars[4]` = bit mask over the other seven seats in seat order; vector obs
  `opponent_options[x] / 20`. `info["opponent_candidates"]` (only present with the option) is
  the sorted seat list, `[]` before a PvE round. `env.unwrapped.game_round.last_matchups` holds
  the pairings just played (both modes).
- Keyed streams and re-seeding: see "Random streams" below.

### Carousel audit (Set 4, patch 10.19 table and TFT:Carousel)

- Matches the sources: 9 units per carousel whatever the number of living players (leftovers
  stay unclaimed), 1-1 is 1-costs only, every unit holds one item, pick order (row 0), the
  first to fourth and sixth carousel item tables (65/11/11/11/1.5/0.5; 80/15/5; 50/30/15/5;
  80/15/5; half full items, half components).
- Fifth carousel (5-4, index 24): see row 12 (fixed with `carousel_fixes`).
- Item-to-unit pairing follows the list order (row 12, fixed with `carousel_fixes`).
- Not verified, unchanged: the cost mix per carousel (2-4: 1/4/4 of 1/2/3-costs; 3-4:
  1/2/3/3 up to 4-costs; 4-4 on: 1/2/2/2/2 up to 5-costs); the wiki only says 1-1 is tier 1.
  The seventh carousel (7-4) reuses the sixth's table (the sources list six). "Components" in
  the half-and-half table are drawn from `basic_items`, so they can be Spatulas. The
  "Defense components" first-carousel set is all Vest/Belt/Cloak (11.2, Set 4.5, replaced it).
  Units come from the module-level `pool_stats` counts, so a depleted champion can still appear
  (known since `rules-profile`). A unit nobody picks never returns to anyone.

### Fortune orb contents (assumptions)

Riot published only average values. The contents use the hints in the patch notes and on the
wiki: the wiki's 5-loss example (23.5 gold before 10.20) lists "23 gold", "two tier 4 units
and two items", "one item and 16 gold", "one Neeko's Help, one item and 8 gold", "two items
and 8 gold", which values a component and Neeko's Help at about 7.5 gold; the Set 4.5 drops
quoted at bunnymuffins.lol/fortune-guide-for-set-4-5/ (from a community loot table) include
"20 gold + 5 Spatulas" at 9 losses (Spatula about 10 gold) and "5 five-costs + 14 gold + 2
items" at 8 losses. In `loot_orb.py`:

- Values: component 7.5, Neeko's Help (`champion_duplicator`) 7.5, Spatula 10, champion = its
  cost. 10-12 losses keep the simulator's 90/115/145.
- An orb is one package, chosen uniformly from those allowed at that loss count: all gold
  (0-3 losses only; 10.20 removed all-gold drops "at higher levels of losses", threshold
  unknown), champions (up to 5, cost 1/2/3/3/4/4 for 0-5 losses and 5 from 6 losses; 10.21
  removed 5-costs at 4 losses), components (up to 6), a mix (about a third each of components,
  champions and gold), Neeko's Help plus a component (from 15 gold), Spatulas (from 5 losses,
  10.20; up to 5). The rest of the value is gold, paid as floor or ceil with the probability
  that makes the expected value exactly the table value.
- 6 Fortune extra orb (11.65 average): a 1% "Jackpot" of 6 components (10.20 mentions a very
  rare Jackpot of "lots of items"), otherwise one of a 5-cost, a component, Neeko's Help or a
  Spatula plus gold (no all-gold drop, 10.20), averaging 11.65 overall.
- Delivery is the PvE-loot one: champions to the bench (their cost in gold if it is full),
  components from the player's item pool (refilled if empty), items lost if the item bench is
  full.
- The counter still counts draws and only rises while Fortune is active, as before; a win
  against a ghost pays nothing (no `won_*` call happens for ghost wins, see below).
- The sim's roster is Set 4 (Jinx is Fortune), so the 10.21-11.1 values apply; 11.2 (Set 4.5)
  lowered 0/1 losses to 2.2/5.5.

### PvE loot audit (not changed)

Sources: TFT:Monster ("At least one loot orb is guaranteed by winning a PvE round", "The
first 3 PvE rounds always drop at least 1 orb"); 10.19 notes ("Adjusted the types of orbs and
their contents across all stages of the game", "Completed items can no longer drop from
orbs", "Spatula items can now drop from end game PVE rounds, but only if you have at least
one of that trait on the board"). No Set 4 orb table or per-round orb count was found.

- Stage 1 (`minion.py` FirstMinion/SecondMinion/ThirdMinion): the code's comment says 18 gold
  of orbs (3 blue, or 2 blue and 2 gray). Enumerating the code: 18 gold 83.8%, 21 gold 7.5%,
  15 gold 8.75% (gray 3, blue 6). Unverified either way.
- Krugs 3 draws, Wolves and Raptors 5 draws, each orb or nothing (5% / 10% / 10% nothing), so
  a win can drop nothing (0.0125% / 0.001% / 0.001%), against the "at least one orb" rule.
  Minor, not changed (changes default games).
- Orbs hold components only (the 10.19 rule holds); Nexus (5-7) and Herald (6-7, 7-7) add a
  full item outside the orbs, drawn from `thieves_gloves_items`, so emblems ("Spatula items")
  never drop although 10.19 says they can at end-game PvE.
- Orb tables (gray: 3 gold / 3-cost / 2-cost + 1 / three 1-costs / duplicator + 1; blue: 6 gold
  / two 3-costs / three 2-costs / component 60% / duplicator + 2-cost + 1; gold: 10 gold /
  duplicator + 5 / Spatula 75%) and the 5-7 / 6-7 / 7-7 monsters: no Set 4 source found.

### Hidden opponent: what is reachable while planning (option on)

- Observation: only the candidate set (above). `info`: `opponent_candidates` and
  `info["player"]`, the live `Player`: `opponent_options` (= candidates), `possible_opponents`
  (the weights; past pairings only, no draw has happened), `opponent` (the previous
  round's opponent as a live `Player`, i.e. that seat's full private state, in both modes),
  `pool_obj` (the shared pool). Nothing there depends on the coming draw.
- `env.unwrapped` (internal): `game_round.matchups` is `[]` until `combat_round` draws;
  `game_round.last_matchups` is the previous round; `env.unwrapped.rng` / `combat_ctx` hold the
  RNG state, so a harness that copies the env and plays the round out can learn the pairing.
  With `rng_streams="keyed"` the pairing comes from the round's matchmaking stream, so it does
  not depend on the planning actions at all.
- Measured: in 8 random games the drawn opponent was outside the exposed candidate set in 122
  of 1266 pairings (9.6%), all from the greedy matchmaker falling back to an excluded opponent
  when a player's candidates were already paired (rows 4 and 9). With an odd number alive one
  player fights a ghost copy of any living player, which the candidate set does not list.

### Random streams

With `rng_streams="keyed"` (`Simulator/rng.py`), each event draws from a stream derived from
the episode seed: root `SeedSequence(episode_seed, spawn_key=(1,))`, child key
`(round index, kind, ids..., use index)` with kinds shop (seat; the use index is the refresh
index in the round, 0 = the round's free shop), action (seat; action index), start of round
(seat), matchmaking, carousel, combat (blue seat, red seat), ghost (seat, ghost seat), PvE
fight (seat), loot (seat), Fortune (seat); the rule bot gets one generator per seat
(`player.default_agent.rng`) instead of global `np.random`. Anything else would draw from a
"misc" stream; two full random games with every option on drew nothing from it. Keys are ints,
so PYTHONHASHSEED does not matter. Only small use counters (pruned to the last two rounds) are
stored; generators are built lazily, so the env pickles as before. The draw code is unchanged,
so the shop odds and every other marginal distribution are too, and shops stay coupled
through the shared pool (a purchase changes later shops; shop rolls do not take units out of
the pool, so a refresh alone does not).

Re-seeding a restored env: call `env.unwrapped.reseed_rng(seed)` with an int or a
`np.random.SeedSequence`. Under "keyed" it replaces the root of every stream (counters such as
refresh and action indices are kept, so two copies of one state re-seeded with the same seed
draw identical numbers for identical events: common random numbers) and re-derives the
per-seat bot generators; it does not touch `env.rng`, which "keyed" does not use. Under
"shared" it re-seeds `env.rng` in place (`EnvRNG.reseed`; an int gives the state a fresh
`reset(seed=int)` starts from). A harness that assigns `env.rng.np = ...` by hand leaves
`env.rng.np_api` (which the simulator's NumPy draws use: loot orb choice, the auto-battler
check) on the old generator; `EnvRNG.reseed` replaces both. Under "shared" the rule bot still
uses global `np.random`, which the harness seeds itself.

Test of the isolation (`rng_streams_test.py`): from one seed, seat 0 passes and refreshes once
more at round 5 in one branch; the other seats take random legal actions from their own
generators. Under "keyed" every other seat's shop, board, bench, items, gold and HP are
identical at every step of rounds 5-8, and seat 0's own shops from round 6 on too (only its
gold differs). Under "shared" all seven other seats diverge.

## Tests

`python -m pytest UnitTests -q --continue-on-collection-errors -p no:randomly`, serially.
Known failures on main and on every branch: `api_compliance_test.py::test_gymnasium_item_env`,
`::test_gymnasium_single_player_env` (observations share an object between reset and step),
and a collection error in `env_stats_test.py` (`env_stats_lib` not importable).

Results (2026-10-07): main 2 failed / 49 passed / 1 error; every fix branch and
`action-budget-options` show only those same failures; `develop` (before this file):
2 failed / 111 passed / 1 error; `rules-profile`: 2 failed / 156 passed / 1 error (the same
known failures; 45 new tests in `rules_profile_test.py` and `rules_profile_games_test.py`, the
latter about 5 minutes because it plays three full games).

Realism branches (2026-10-07, `PYTHONHASHSEED=0`, same command): `develop` at `a2840a1`
2 failed / 156 passed / 1 error; `fix-pve-damage` and `realism-carousel-pick` (which
contains it) 2 failed / 192 passed / 1 error; `realism-fortune-orbs` 2 failed / 234 passed /
1 error; `develop` after the hidden-opponent merge 3 failed / 242 passed / 1 error (the third
is the flaky `composition_test.py::test_list`, see "Other findings"; it passes on rerun);
`rng-keyed-streams` 2 failed / 254 passed / 1 error. Only the known failures otherwise.
`realism_defaults_test.py` checks that a fixed-seed default game (all new options off) has
the same trajectory hash as `a2840a1`, so default trajectories are unchanged on every branch.
