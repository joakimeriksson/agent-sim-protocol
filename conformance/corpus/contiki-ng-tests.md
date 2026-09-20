# Corpus check: the upstream Contiki-NG Cooja tests against the closed condition set

93 simulation tests, 42 distinct scripts (Contiki-NG `55e7ef6c8`).
Each script was read and classified by hand; `classification.json` holds the verdict and the
reason per script, `extract.py` and `report.py` regenerate this file.

| category | tests | share of in-simulator tests | meaning |
| --- | --- | --- | --- |
| A | 36 | 42% | fits expect / invariants / actions with the closed condition set as written |
| B1 | 17 | 20% | fits with a log-filtered invariant: no_event on log lines with text / regex / not_text (csim's fail_on) |
| B2 | 12 | 14% | fits with `then` actions on an expect entry: stimulus sent when an expectation is reached, not at a fixed time |
| B3 | 10 | 12% | fits with a log-derived sequence metric over the app's 'Data received' lines: received, lost, max_seq, last_gap_seq |
| B4 | 4 | 5% | fits with all_of: several conditions satisfied in any order within one window |
| B5 | 1 | 1% | needs a comparison between captured fields of one line (regex backreference or capture compare) |
| C | 5 | 6% | needs the JS escape hatch |
| D | 8 |  | not an in-simulator assertion: real-time run whose verdict comes from an external driver process |

Of the 85 tests whose verdict is decided inside the simulator, **36 (42%) fit the
closed set as written** and **79 (93%) fit with four additions** (B1–B4). 6 need the JS escape hatch.
8 tests are real-time runs judged by an external driver and are outside `expect` altogether.

## Per test

| test | script | category | how it maps |
| --- | --- | --- | --- |
| `07-simulation-base/01-hello-world-sky.csc` | `9fd59e5b` | A | expect log_matches '^Hello, world$' |
| `07-simulation-base/02-ringbufindex.csc` | `8e7ef5a9` | B1 | expect '=check-me= DONE'; invariant on '=check-me= .*FAILED' (deferred in JS, fail-fast here) |
| `07-simulation-base/03-nullnet-broadcast.csc` | `10cd7c6a` | A | three sequential expects, one per node: exactly the sequential window rule |
| `07-simulation-base/04-nullnet-broadcast-tsch.csc` | `10cd7c6a` | A | three sequential expects, one per node: exactly the sequential window rule |
| `07-simulation-base/05-nullnet-unicast.csc` | `360fba77` | A | one expect with node |
| `07-simulation-base/06-nullnet-unicast-tsch.csc` | `360fba77` | A | one expect with node |
| `07-simulation-base/07-hello-world-z1.csc` | `9fd59e5b` | A | expect log_matches '^Hello, world$' |
| `07-simulation-base/08-ipv6-unicast.csc` | `a1a953ca` | B1 | expect '^Data 60 received length 100$'; invariant regex 'parent switch:.*-> \(NULL IP addr\)' |
| `07-simulation-base/09-ipv6-broadcast.csc` | `a1a953ca` | B1 | expect '^Data 60 received length 100$'; invariant regex 'parent switch:.*-> \(NULL IP addr\)' |
| `07-simulation-base/14-cooja-multicast-11-hops-mpl.csc` | `6144eb74` | A | expect log_matches '^In: ' |
| `07-simulation-base/15-cooja-multicast-11-hops-rollt-tm.csc` | `6144eb74` | A | expect log_matches '^In: ' |
| `07-simulation-base/16-cooja-multicast-11-hops-smrf.csc` | `6144eb74` | A | expect log_matches '^In: ' |
| `07-simulation-base/17-cooja-multicast-11-hops-esmrf.csc` | `6144eb74` | A | expect log_matches '^In: ' |
| `07-simulation-base/18-cooja-multicast-31-hops.csc` | `6144eb74` | A | expect log_matches '^In: ' |
| `07-simulation-base/19-cooja-rpl-tsch.csc` | `d4d2ebb3` | A | expect node 1 text 'Routing links: 9' |
| `07-simulation-base/20-cooja-rpl-tsch-orchestra.csc` | `d4d2ebb3` | A | expect node 1 text 'Routing links: 9' |
| `07-simulation-base/21-cooja-rpl-tsch-security.csc` | `5453a2cc` | A | expect node 1 text 'Routing links: 9' |
| `07-simulation-base/22-stack-guard-sky.csc` | `c90f9b79` | B4 | a stack-usage line below 900 and one at or above 1000, in any order: all_of of two log_matches with numeric-range regexes |
| `07-simulation-base/23-rpl-tsch-z1.csc` | `dd674407` | A | expect node 1 text 'Routing links: 6' |
| `07-simulation-base/24-cooja-rpl-tsch-orchestra-storing.csc` | `8c13e87f` | A | expect node 1 text 'Routing entries: 8' |
| `07-simulation-base/25-cooja-rpl-tsch-orchestra-link-based.csc` | `8c13e87f` | A | expect node 1 text 'Routing entries: 8' |
| `07-simulation-base/26-cooja-rpl-tsch-orchestra-perfect-link.csc` | `e06e412b` | B5 | pass when tx > 0 and tx == ack on one 'Link Stats' line: equality between two captured fields |
| `07-simulation-base/26-tsch-drift-z1.csc` | `411edf52` | A | expect text 'drift 2 ppm' count 5 |
| `07-simulation-base/27-cooja-rpl-tsch-orchestra-root-rule-storing.csc` | `d5c9059f` | A | two sequential expects: 'use the root rule', then 'Routing entries: 8' |
| `07-simulation-base/28-cooja-rpl-tsch-orchestra-root-rule-ns.csc` | `fe016785` | A | two sequential expects: 'use the root rule', then 'Routing links: 9' |
| `07-simulation-base/28-ipv6-tcp-sockets.csc` | `f744ddab` | A | expect text 'Test OK' |
| `07-simulation-base/31-data-structures-sky.csc` | `8e7ef5a9` | B1 | expect '=check-me= DONE'; invariant on '=check-me= .*FAILED' (deferred in JS, fail-fast here) |
| `09-ipv6/01-ping-lla-csma-w-rpl.csc` | `c6ba68e6` | B2 | on 'Node ID:' from node 1 send 'rpl-set-root 1'; after 20 s send ping; on reply send 'ip-nbr'; expect the neighbour line with the address, MAC and 'Reachable' |
| `09-ipv6/02-ping-ula-csma-w-rpl.csc` | `4b643ffb` | B2 | as above with a regex alternation for the two acceptable addresses |
| `09-ipv6/03-ping-lla-tsch-w-rpl.csc` | `c6ba68e6` | B2 | on 'Node ID:' from node 1 send 'rpl-set-root 1'; after 20 s send ping; on reply send 'ip-nbr'; expect the neighbour line with the address, MAC and 'Reachable' |
| `09-ipv6/04-ping-ula-tsch-w-rpl.csc` | `4b643ffb` | B2 | as above with a regex alternation for the two acceptable addresses |
| `09-ipv6/05-ping-lla-csma-wo-rpl.csc` | `c6ba68e6` | B2 | on 'Node ID:' from node 1 send 'rpl-set-root 1'; after 20 s send ping; on reply send 'ip-nbr'; expect the neighbour line with the address, MAC and 'Reachable' |
| `09-ipv6/06-ping-ula-csma-wo-rpl.csc` | `4b643ffb` | B2 | as above with a regex alternation for the two acceptable addresses |
| `09-ipv6/07-ping-lla-tsch-wo-rpl.csc` | `c6ba68e6` | B2 | on 'Node ID:' from node 1 send 'rpl-set-root 1'; after 20 s send ping; on reply send 'ip-nbr'; expect the neighbour line with the address, MAC and 'Reachable' |
| `09-ipv6/08-ping-ula-tsch-wo-rpl.csc` | `4b643ffb` | B2 | as above with a regex alternation for the two acceptable addresses |
| `09-ipv6/09-ping-lla-ula-csma-w-rpl.csc` | `f254098f` | B2 | as above, two pings; the with-RPL / without-RPL branch is static per test file, so the converter picks one expect list |
| `09-ipv6/10-ping-lla-ula-tsch-w-rpl.csc` | `f254098f` | B2 | as above, two pings; the with-RPL / without-RPL branch is static per test file, so the converter picks one expect list |
| `09-ipv6/11-ping-lla-ula-csma-wo-rpl.csc` | `f254098f` | B2 | as above, two pings; the with-RPL / without-RPL branch is static per test file, so the converter picks one expect list |
| `09-ipv6/12-ping-lla-ula-tsch-wo-rpl.csc` | `f254098f` | B2 | as above, two pings; the with-RPL / without-RPL branch is static per test file, so the converter picks one expect list |
| `13-ieee802154/01-panid-handling.csc` | `ae3a87eb` | B1 | expect '=check-me= DONE'; invariant on FAILED (immediate in JS too) |
| `13-ieee802154/02-tsch-flush-nbr-queue.csc` | `0a779011` | B1 | expect text '=check-me= DONE' count = number of nodes; invariant on '=check-me= .*FAILED'. JS defers the failure to the end, the invariant fails fast: same verdict |
| `13-ieee802154/03-cooja-test-sixtop.csc` | `0a779011` | B1 | expect text '=check-me= DONE' count = number of nodes; invariant on '=check-me= .*FAILED'. JS defers the failure to the end, the invariant fails fast: same verdict |
| `13-ieee802154/04-cooja-test-sixp-pkt.csc` | `0a779011` | B1 | expect text '=check-me= DONE' count = number of nodes; invariant on '=check-me= .*FAILED'. JS defers the failure to the end, the invariant fails fast: same verdict |
| `13-ieee802154/05-cooja-test-sixp-trans.csc` | `0a779011` | B1 | expect text '=check-me= DONE' count = number of nodes; invariant on '=check-me= .*FAILED'. JS defers the failure to the end, the invariant fails fast: same verdict |
| `13-ieee802154/06-cooja-test-sixp-nbr.csc` | `0a779011` | B1 | expect text '=check-me= DONE' count = number of nodes; invariant on '=check-me= .*FAILED'. JS defers the failure to the end, the invariant fails fast: same verdict |
| `13-ieee802154/07-cooja-test-sixp.csc` | `0a779011` | B1 | expect text '=check-me= DONE' count = number of nodes; invariant on '=check-me= .*FAILED'. JS defers the failure to the end, the invariant fails fast: same verdict |
| `13-ieee802154/08-cooja-test-sixtop-sf-error-handler.csc` | `0a779011` | B1 | expect text '=check-me= DONE' count = number of nodes; invariant on '=check-me= .*FAILED'. JS defers the failure to the end, the invariant fails fast: same verdict |
| `13-ieee802154/09-cooja-test-csma-security.csc` | `6823ffcd` | B1 | expect '=check-me= DONE' count = nodes; invariant on FAILED |
| `13-ieee802154/10-framer-negative.csc` | `ae3a87eb` | B1 | expect '=check-me= DONE'; invariant on FAILED (immediate in JS too) |
| `14-rpl-lite/01-rpl-up-route.csc` | `8c2db223` | B3 | pass at the timeout if received >= 1 and lost == 0 |
| `14-rpl-lite/02-rpl-root-reboot-2.csc` | `5bd4bd19` | B4 | send / send_all / remove / add at fixed times; after each 'ip-addr' broadcast, every node's address line must appear within 1 s in any order: all_of over one window, gated by `time` entries |
| `14-rpl-lite/03-rpl-28-hours.csc` | `672af665` | B3 | 28-hour run; received >= 1 and lost == 0 |
| `14-rpl-lite/05-rpl-up-and-down-routes.csc` | `0d55089d` | B3 | pass at the timeout if lost == 0 |
| `14-rpl-lite/06-rpl-temporary-root-loss.csc` | `be28930d` | B3 | remove / add the sink; pass if max_seq >= 62 and last_gap_seq <= 45 |
| `14-rpl-lite/07-rpl-random-rearrangement.csc` | `acc1e336` | C | node positions drawn in the script from java.util.Random(sim.getRandomSeed()) at four times; the verdict (count of Data > 50) would fit, the seeded random actions do not |
| `14-rpl-lite/08-rpl-dao-route-loss-0.csc` | `e38aa9bf` | A | 4 move actions (2 at t=0, 2 at 600 s); expect log_matches ^Data count 16. JS decides at the timeout, expect passes at the 16th line: same verdict, run ends earlier |
| `14-rpl-lite/08-rpl-dao-route-loss-1.csc` | `e38aa9bf` | A | 4 move actions (2 at t=0, 2 at 600 s); expect log_matches ^Data count 16. JS decides at the timeout, expect passes at the 16th line: same verdict, run ends earlier |
| `14-rpl-lite/08-rpl-dao-route-loss-2.csc` | `e38aa9bf` | A | 4 move actions (2 at t=0, 2 at 600 s); expect log_matches ^Data count 16. JS decides at the timeout, expect passes at the 16th line: same verdict, run ends earlier |
| `14-rpl-lite/08-rpl-dao-route-loss-3.csc` | `e38aa9bf` | A | 4 move actions (2 at t=0, 2 at 600 s); expect log_matches ^Data count 16. JS decides at the timeout, expect passes at the 16th line: same verdict, run ends earlier |
| `14-rpl-lite/08-rpl-dao-route-loss-4.csc` | `e38aa9bf` | A | 4 move actions (2 at t=0, 2 at 600 s); expect log_matches ^Data count 16. JS decides at the timeout, expect passes at the 16th line: same verdict, run ends earlier |
| `14-rpl-lite/08-rpl-dao-route-loss-5.csc` | `e38aa9bf` | A | 4 move actions (2 at t=0, 2 at 600 s); expect log_matches ^Data count 16. JS decides at the timeout, expect passes at the 16th line: same verdict, run ends earlier |
| `14-rpl-lite/09-rpl-probing.csc` | `d209dd16` | C | needs the hop count of the last delivered message, reconstructed from Cooja visualizer '#L' lines between 'Sending' and 'Data'; plus lost <= 2 and seq > 20 |
| `14-rpl-lite/10-rpl-resetting-dio-timer-by-dis.csc` | `b2725273` | A | expect node 1 text 'sending a multicast-DIO' count 10 within 60 s |
| `15-rpl-classic/01-rpl-up-route.csc` | `8c2db223` | B3 | pass at the timeout if received >= 1 and lost == 0 |
| `15-rpl-classic/02-rpl-root-reboot-2.csc` | `5bd4bd19` | B4 | send / send_all / remove / add at fixed times; after each 'ip-addr' broadcast, every node's address line must appear within 1 s in any order: all_of over one window, gated by `time` entries |
| `15-rpl-classic/02-rpl-root-reboot.csc` | `58800fb1` | B3 | remove and add the sink at the same time; received >= 1 and lost == 0 |
| `15-rpl-classic/03-rpl-28-hours.csc` | `672af665` | B3 | 28-hour run; received >= 1 and lost == 0 |
| `15-rpl-classic/05-rpl-up-and-down-routes-non-storing.csc` | `0d55089d` | B3 | pass at the timeout if lost == 0 |
| `15-rpl-classic/05-rpl-up-and-down-routes.csc` | `0d55089d` | B3 | pass at the timeout if lost == 0 |
| `15-rpl-classic/06-rpl-temporary-root-loss.csc` | `51a5cd64` | B3 | as 14-rpl-lite/06 with last_gap_seq <= 55 |
| `15-rpl-classic/07-rpl-random-rearrangement.csc` | `acc1e336` | C | node positions drawn in the script from java.util.Random(sim.getRandomSeed()) at four times; the verdict (count of Data > 50) would fit, the seeded random actions do not |
| `15-rpl-classic/08-rpl-dao-route-loss-0.csc` | `e38aa9bf` | A | 4 move actions (2 at t=0, 2 at 600 s); expect log_matches ^Data count 16. JS decides at the timeout, expect passes at the 16th line: same verdict, run ends earlier |
| `15-rpl-classic/08-rpl-dao-route-loss-1.csc` | `e38aa9bf` | A | 4 move actions (2 at t=0, 2 at 600 s); expect log_matches ^Data count 16. JS decides at the timeout, expect passes at the 16th line: same verdict, run ends earlier |
| `15-rpl-classic/08-rpl-dao-route-loss-2.csc` | `e38aa9bf` | A | 4 move actions (2 at t=0, 2 at 600 s); expect log_matches ^Data count 16. JS decides at the timeout, expect passes at the 16th line: same verdict, run ends earlier |
| `15-rpl-classic/08-rpl-dao-route-loss-3.csc` | `e38aa9bf` | A | 4 move actions (2 at t=0, 2 at 600 s); expect log_matches ^Data count 16. JS decides at the timeout, expect passes at the 16th line: same verdict, run ends earlier |
| `15-rpl-classic/08-rpl-dao-route-loss-4.csc` | `e38aa9bf` | A | 4 move actions (2 at t=0, 2 at 600 s); expect log_matches ^Data count 16. JS decides at the timeout, expect passes at the 16th line: same verdict, run ends earlier |
| `15-rpl-classic/08-rpl-dao-route-loss-5.csc` | `e38aa9bf` | A | 4 move actions (2 at t=0, 2 at 600 s); expect log_matches ^Data count 16. JS decides at the timeout, expect passes at the 16th line: same verdict, run ends earlier |
| `15-rpl-classic/09-rpl-probing.csc` | `d209dd16` | C | needs the hop count of the last delivered message, reconstructed from Cooja visualizer '#L' lines between 'Sending' and 'Data'; plus lost <= 2 and seq > 20 |
| `15-rpl-classic/10-rpl-multi-dodag.csc` | `7cba0eb8` | A | remove / add actions; expect ^Data, then a `time` gate at 12000 s, then ^Data again: the time condition sequences the second window |
| `15-rpl-classic/11-rpl-resetting-dio-timer-by-dis.csc` | `bcff125c` | A | expect node 1 text 'Sending a multicast-DIO' count 10 within 60 s |
| `15-rpl-classic/12-rpl-rank-error.csc` | `6be204a7` | B1 | expect 'Received all packets'; invariant on 'RPL Option Error: Dropping Packet' |
| `15-rpl-classic/13-rpl-rank-dao-garbled.csc` | `f65f8c09` | B4 | node 2 'RPL forwarding error' and node 1 no-path DAO in any order, then 'No more routes'; invariant on 'icmpv6 bad checksum' (also B1) |
| `17-tun-rpl-br/01-border-router-cooja.csc` | `697c6b01` | D | sim.setSpeedLimit(1.0), no verdict in the script; a bash driver pings through the TUN border router |
| `17-tun-rpl-br/02-border-router-cooja-tsch.csc` | `697c6b01` | D | sim.setSpeedLimit(1.0), no verdict in the script; a bash driver pings through the TUN border router |
| `17-tun-rpl-br/03-border-router-sky.csc` | `697c6b01` | D | sim.setSpeedLimit(1.0), no verdict in the script; a bash driver pings through the TUN border router |
| `17-tun-rpl-br/04-border-router-traceroute.csc` | `697c6b01` | D | sim.setSpeedLimit(1.0), no verdict in the script; a bash driver pings through the TUN border router |
| `17-tun-rpl-br/07-native-border-router-cooja.csc` | `697c6b01` | D | sim.setSpeedLimit(1.0), no verdict in the script; a bash driver pings through the TUN border router |
| `17-tun-rpl-br/08-border-router-cooja-frag.csc` | `697c6b01` | D | sim.setSpeedLimit(1.0), no verdict in the script; a bash driver pings through the TUN border router |
| `17-tun-rpl-br/09-native-border-router-cooja-frag.csc` | `697c6b01` | D | sim.setSpeedLimit(1.0), no verdict in the script; a bash driver pings through the TUN border router |
| `17-tun-rpl-br/10-native-nat64-cooja.csc` | `31844564` | D | real-time run; a bash driver greps the test log for echo markers |
| `21-security-protocols/01-edhoc-tests-cooja-method0.csc` | `0449d242` | C | compares the content of two different lines for equality (client and server master secret) and counts error lines with an exclusion |
| `21-security-protocols/02-edhoc-tests-cooja-method3.csc` | `e9f805fd` | B1 | known-answer checks: a line containing a key must also contain the expected bytes: invariant with text + not_text; ends on 'Client finished'; the production-mode branch is static per build |
| `21-security-protocols/03-edhoc-tests-cooja-method3-rfc9529-eph-keys.csc` | `b9983199` | B1 | as above with RFC 9529 ephemeral keys |
