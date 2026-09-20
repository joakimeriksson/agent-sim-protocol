# M1 in Cooja-NG: what recording the vectors turned up

Recorded 2026-09-20 from Cooja-NG branch `feat/agent-m1-evidence` (`1045b07`, on main
`a7317f2`), macOS/arm64. The four run kinds of the M1 exit criterion are now recorded vectors
under `conformance/vectors/cooja-ng/`; all four pass `check.py`. Without `--run-dir` the
simulator is unchanged: its baseline check reports nine workloads byte-identical to `a7317f2`,
and `events.ndjson` is byte-identical across two runs of one seed.

Each item below is a place where the spec, the schema or the checker met the implementation.
Items 1 and 2 are changed in this branch; the rest need a decision.

## Changed here

1. **Rule D4 demanded an event for an action that never happened.** A replay action with
   `applied: false` was still pending when the run was cut short, so it has no `action` event.
   D4 now compares the applied actions with the events. Two tests cover both directions.
2. **Status table.** `capabilities`, `result.json`, `events.ndjson`, `scenario.replay.yaml`,
   `expect` and `log_contains` move to provisional for Cooja-NG.

## For a decision

3. **What `t` means on `tx`.** An emulated radio knows the frame when it ends. Cooja-NG stamps
   `tx` with the end of the frame and adds `start` (ns). Stamped with the start, the event
   lands behind events already written for that node, by up to a frame (7.6 ms), and trips E1.
   A lock-step external mote reports `tx` up front with the start as `t`. The spec should say
   which it is, or name both fields.
4. **E1 does not hold on Cooja-NG's ARM motes today.** Sky and nRF54L15 runs are in order.
   CC2538 and nRF52840 runs are not (218 regressions in a 180 s four-node chain, worst 6.8 ms):
   console lines, radio state and frames are stamped from three clocks that disagree. This is
   a Cooja-NG defect the checker found, not a reason to loosen E1; the simulator counts the
   regressions and reports them in `result.json` as `event_time_regressions` until it is fixed.
5. **`node` on a simulation-wide event.** `send_all` addresses no node, and the envelope
   requires `node` (minimum 1) on every event. Cooja-NG writes its `action` event without
   `node`, which the schema rejects. Either `node` is optional on `action`, or there is a
   reserved value for the whole simulation.
6. **P2 and a run that ends at its last `expect`.** A scheduled action later than the last
   `expect` is never applied, and the run is `completed`. P2 calls that an error. Cooja-NG
   records it honestly as `applied: false`; the corpus check should say whether any of the 93
   tests does this.
7. **A refused action.** `move` on a node id that does not exist is recorded with
   `applied: false` and no event. That overloads `applied` (pending versus refused). A third
   state, or a `reason`, would keep them apart.
8. **`error` and `message`.** `result.json.error` is the closed code; the human text ("medium:
   unknown type 'no-such-medium'") goes in `message`, which the schema allows but does not
   name.
9. **`operations` for a batch-only simulator.** Cooja-NG advertises `["capabilities"]` and
   five actions; the checker warns (W-C4) that actions need `describe`. In M1 actions come from
   the scenario file, so the warning is expected until sessions exist.
10. **State sampling.** MSP430 radio and LED state is sampled once per scheduler slice, so those
    events carry the slice time. It is declared in `capabilities.limitations.notes`; the state
    timing audit already plans the callback that removes it.
11. **Silent fallbacks are gone.** An unknown medium, plugin or built-in service is exit 2 in
    this branch. That changes behaviour for anyone who relied on the warning.
