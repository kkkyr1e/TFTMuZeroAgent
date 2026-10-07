# Fork notes

Fixes and options on top of upstream `main` at `a5718dd` (silverlight6/TFTMuZeroAgent).
Each bug fix is its own branch off `a5718dd` with one unit test and can go upstream as a
standalone PR. `develop` merges all of them plus `action-budget-options`. This file exists
only on `develop`.

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
| 8b | Fortune pays +3 on every win | `Simulator/game/player.py:1875-1883, 1900-1908, 1925-1928`; `Simulator/battle/origin_class_stats.py:304` | Fortune pays out on a win by rounds lost; wiki table 2.5/6/10.5/17/24/31/38/45/55/70 for 0-9 losses (wiki.leagueoflegends.com/en-us/Fortune_(Teamfight_Tactics)); V10.20 set the 0-loss value to 3, V10.21 to 2.5; 6 Fortune adds an extra orb on a win | Design approximation, not changed. Sim pays `ceil(value)` as plain gold (3 after 0 losses, which is the "+3 on every win"); the real payout is a loot orb of that value. 6 Fortune counts losses twice instead of an extra orb | none | none | n/a |
| 9 | Matchups fixed before planning | `Simulator/game/game_round.py:291-296` (`decide_player_combat` in `start_round`), `257-284` (`opponent_options`), `274-275` (`possible_opponents` reset); obs `Simulator/encoding/token/basic_observation.py:368-376`, `Simulator/encoding/vector/observation.py:289-294`; infos `Simulator/simulators/tft_simulator.py:162, 292, 347` | The real client does not show the next opponent; trackers can narrow the candidates but not pinpoint them (Upcomer, 2021) | Design choice with information exposure, not changed. The obs candidate set is the eligible seats plus the real opponent, which `game_round.py:270-273` always adds (`1 not in opponent_options` tests the keys, so it is always true); that is the tracker view. Exact leaks: when nobody is eligible the set is only the real opponent, and the ghost fight names the copied seat (`game_round.py:280-284`); on main a drawn ineligible opponent can also stand out (fixed by #4). Outside the obs: `info["player"]` is the live Player, and its `possible_opponents` is already 0 for the drawn opponent (`game_round.py:274-275`); `env.unwrapped.game_round.matchups` lists every pairing | none | none | n/a |
| B | 15 actions per turn, passes included | `Simulator/config.py:16`; `Simulator/simulators/tft_simulator.py:34, 194-195, 302-307`; obs scale `basic_observation.py:352`, `vector/observation.py:302` | n/a (env interface) | Not a bug: new options. `TFTConfig.pass_ends_turn` (default False) and `max_actions_per_round` now also scales the obs. Agents whose turn is over stay in the cycle with a pass-only mask and `info["turn_over"]`; no truncation | `action-budget-options` | `UnitTests/action_budget_test.py` (8 tests, incl. PettingZoo api_test / parallel_api_test) | No with defaults: 12-round parallel and AEC trajectories hash-identical to main. Yes when enabled |

## Unverifiable or needs checking

- 6-7 monster: which board Set 4 used at 6-7 (the sim reuses the Herald board for 6-7 and 7-7).
  Needs a Set 4 round list (patch 10.19-11.8).
- Fortune: the payout at 0 losses (wiki says 2.5, a Set 4 loot-table guide on tacter.com says
  none), whether the sim targets 11.2+ values (patch 11.2 changed the low-loss values), and
  how 6 Fortune's extra orb should be modelled.
- Matchmaking: exact Set 4 rules for 8 and 5 or fewer alive players and for ghost fights.
- PvE damage (below): Set 4 damage for losing to monsters.

## Other findings, not fixed

- PvE losses deal no HP damage: `game_round.py:304, 319` call `minion.minion_round` without
  `other_rewards`, and `minion.py:283` only applies damage when it is truthy. TFT:Monster
  wiki: "Like player combats, the Tactician will take damage if they lose the combat."
  Likely bug; fixing it changes outcomes.
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

## Tests

`python -m pytest UnitTests -q --continue-on-collection-errors -p no:randomly`, serially.
Known failures on main and on every branch: `api_compliance_test.py::test_gymnasium_item_env`,
`::test_gymnasium_single_player_env` (observations share an object between reset and step),
and a collection error in `env_stats_test.py` (`env_stats_lib` not importable).

Results (2026-10-07): main 2 failed / 49 passed / 1 error; every fix branch and
`action-budget-options` show only those same failures; `develop` (before this file):
2 failed / 111 passed / 1 error.
