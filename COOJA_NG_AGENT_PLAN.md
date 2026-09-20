# Cooja-NG — Agent-Native Development Plan (v0.3)

## Goal

Make Cooja-NG an agent-operable IoT/network experimentation environment where coding and research agents can create reproducible experiments, manipulate network conditions, observe system behavior, evaluate metrics, diagnose failures, and improve either the guest software or simulator when justified.

The central loop should be:

`modify → build → simulate → perturb → measure → evaluate → diagnose → repeat`

Cooja-NG complements esp32sim: esp32sim focuses on MCU/firmware execution while Cooja-NG focuses on multi-node and network/system behavior.

## Starting point (csim, 2026-09-12)

This plan is a delta. Most of what v0.1 called Phases 1, 2, 4 and 6 already exists in `csim`:

| exists | where |
| --- | --- |
| headless runner with strict YAML/JSON configs: seed, timeout, medium, mote types, nodes | `test_runner test config.yaml`, `docs/test-format.md` |
| scheduled actions: `move`, `send`, `send_all`, `remove`, `add` (reboot) | `test.actions` |
| conditions: `wait` + `node` + `count` + `timeout_ms`, validators with `min_count`, `fail_on`, `timeout_is_success`, full JS | `test.steps`, `test.validators`, `js_script_inline` |
| seeded, byte-identical runs; `--seed` overrides the file | `docs/contiki-ng-testing.md` §3 |
| effective configuration written at end of run (positions, live node list, seed, duration) | `--save-config` |
| fail-loud exit contract (no criteria, no verdict, hang = FAIL) | `docs/contiki-ng-testing.md` §5 |
| internal observer stream: log line, UART byte, packet frame, radio tx/rx start/end, interference, radio state, LED, mote added/removed, cpu state | `sim_observer_event_t`, `SIM_OBS_*` |
| pcap, timeline, energest, progress services; lossy and Gilbert-Elliott media | services and medium plugins |
| lock-step external nodes (esp32sim as a C6 mote); Renode as clock master | `docs/design/external-nodes-plan.md`, `renode-cosim-plan.md` |
| `AGENTS.md` with build and test commands | repo root |

What does not exist: a JSON result summary, an exported event stream, `capabilities`, metrics
with stated semantics, per-link and radio-injection actions, a multi-seed aggregate, an evidence
bundle, and an escalation workflow in `AGENTS.md`.

Two existing behaviors must be hardened before exposing this as an agent/CI contract:

- An unknown custom medium currently warns and falls back to the default medium. A requested
  medium, plugin, or required service must instead make configuration fail before simulation
  (`configuration_error`, exit 2); fallback is allowed only when explicitly requested in the
  experiment. This is a Phase 1 item.
- `--save-config` exports the live final setup. It is useful for continuing a session, but it is
  not a replay of a run that moved, removed, or re-added nodes. The replay artifact is
  `scenario.replay.yaml` (`SPEC.md`, "Replay"): the initial setup, the effective seed, resolved
  firmware and plugin hashes, and the ordered action history with effective simulation times.
  It is itself a valid config for `run`.

## Code audit (csim a09e798, 2026-09-18)

Checked against the code, not the docs. Every M1 and M2 item is an additive hook on a seam
that exists; three items need a small kernel or protocol change; two are in no plan before
this note.

Easy, on existing seams:

| protocol concept | seam in csim |
| --- | --- |
| capabilities | `sim_registry_t` holds boards, mote kinds, services and media as arrays with counts; enumerate them, add static action and condition lists |
| `events.ndjson` | every service gets every kernel event through `sim_service_ops_t.on_event` with `time_ns`, `mote_index`, and the Cooja node id on log lines; `pcap_service.c` and `timeline_service.c` are the template; dispatch is single-threaded and the pump pops in (time, seq) order, so `seq` is a counter in the exporter |
| `result.json`, exit codes | the runner ends in one place: `json_test_report()` returns the code, the JS verdict folds in, wall time is measured, `--save-config` writes there; firmware paths are in `sim_config` (`char firmware[256]`), hashes are a loader-time addition |
| `expect` / `invariants` | `json_test_service.c` is already the model: sequential steps, the match counter resets per step (the window starts where the previous step was reached), `fail_on` is checked first on every line, a timed-out step exits 1, validators are whole-run counts (`since: reset`) |
| medium fallback | one `fprintf` and a fall-through at the custom-medium lookup in the runner; exit 2 is a one-line change |
| replay | timed actions dispatch at one site in the outer loop; the loaded config is kept; the save-config writer reloads what it wrote |
| seeds | one seed feeds `radio_medium_set_seed` and an LCG (`x*1103515245+12345`) that draws startup delays in node order; the derivation string can be exact |
| session `run_until` | the outer loop's `clock_source->next_horizon()` hook lets an external master hand out horizons with sub-stepping at timed actions (the Renode path); a control-plane clock source that reads NDJSON is the session; `sim_runtime_request_stop()` is `cancel` |
| nested diagnostics | `ext_node.c` ignores unknown output event types on purpose, so esp32sim can emit `diag` today; forwarding it is one branch |

Needs a small change:

1. **`rx` has no sender.** The observer's radio event carries data, length, channel and RSSI,
   not the transmitter. Add a field to the observer event (kernel change, through
   `refactor-plan.md`) rather than inferring it in the exporter. Phase 2.
2. **Metrics have no data path.** `energest_engine_report()` prints strings at teardown; add a
   numeric accessor for `result.json`. PDR and latency over log lines are a new service. Phase 4.
3. **Multi-seed.** The runner is one 3200-line main with a restart label for reboots; loop seeds
   by spawning the runner per seed, as `run-cooja-tests.sh` already does, and aggregate in
   `cooja-ng run`. Phase 5.
4. **No wall-clock bound exists.** The outer loop already reads the wall clock for reporting; a
   check there is `--wall-timeout`. Phase 1.
5. **No config passthrough for nested nodes.** `ext_node_start()` sends id, position, seed and
   frame size in `hello`; it does not send `args`, although `external-nodes-plan.md` §4 lists it
   and esp32sim parses `hello.args`. Add a per-node `args` object to the config and pass it
   untouched; the node's own simulator validates it against its `scenario_schema`. Phase 10.

Risk is scope, not feasibility: the runner already hosts the UI, the serial bridge, Renode and
TUN in one file. M1 and M2 are additive hooks there. The session mode is another mode in that
file, so the refactor plan's runner extraction should land before it.

## Design principles

- Preserve Cooja as a useful simulator for humans and CI.
- Make headless deterministic operation first-class.
- Treat experiments as machine-readable artifacts.
- Separate actions, observations, metrics, and assertions.
- Make randomness explicit through seeds.
- Emit structured evidence for failed experiments.
- Keep the core protocol independent of MCP/LLM vendors.
- Allow agents to identify simulator/model defects without silently adapting application code around them.
- Reuse the existing config schema, observer stream and services. Add exporters and a summary, not a second engine.

## Phase 1 — Structured results on the existing runner

Delta, not a new runner:

- `cooja-ng run experiment.yaml --run-dir DIR` as a thin alias of `test_runner test`, keeping
  every existing flag; `--wall-timeout S` added.
- A run directory per run (`run_dir`) holding `result.json`, `events.ndjson`,
  `scenario.replay.yaml`, `config.effective.yaml` (today's `--save-config` output, always
  written), the existing `COOJA.testlog`, and pcap when enabled. Artifact paths are relative to
  the run directory.
- `result.json`: `verdict` and `termination_reason`, effective seed, Cooja-NG version and
  commit, firmware paths and hashes, simulation time, wall time, per-condition outcome, metrics,
  artifact paths.
- `--wall-timeout S`: a check in the outer loop against `get_time_ms()`; expiry is `timeout`
  (6), `termination_reason: timeout_wall`. Nothing bounds wall time today.
- A run directory holding a `result.json` is refused without `--overwrite`; `result.json` is
  written last. A configuration error (unknown medium, missing firmware) still writes a
  `result.json` with `termination_reason: configuration_error` and no events when a run
  directory was given.
- Exit codes from the shared table in `SPEC.md`: 0 pass, 1 assertion, 2 configuration,
  3 unsupported, 4 simulator error, 5 guest halted, 6 wall-clock timeout, 7 cancelled. The
  current fail-loud cases (no criteria, no verdict, unknown medium) map to
  `configuration_error`; `timeout_ms` expiring with a step pending is `assertion_failed`, with
  `timeout_is_success` or nothing pending it is `completed`; `testFailed()` is
  `guest_failure`.

```json
{
  "verdict":"pass",
  "termination_reason":"completed",
  "seed":42,
  "deterministic":true,
  "version":"0.1.1+a09e798",
  "simulation_time_ns":600000000000,
  "nodes":50,
  "conditions":[{"log_contains":{"node":1,"text":"Data received from","count":3},"reached":true,"t":412300000000}],
  "metrics":{"radio_duty_cycle":{"value":0.021,"definition":"energest tx+rx+listen over sim time, all nodes"}},
  "artifacts":{"events":"events.ndjson","replay":"scenario.replay.yaml","pcap":"radio.pcap"}
}
```

## Phase 2 — Event export and observations

`events.ndjson` is the observer stream serialized, one object per line, `t` in ns, event names
shared with the lock-step protocol where the concept is the same (`log`, `tx`, `rx`, `radio`,
`led`) and `node` on every event. `node` is the Cooja node id, which the observer already
carries on log lines and which survives `remove` and `add`; it is never the mote slot index,
which the runner reuses.

New observation types only where the stream lacks them: routing events and topology changes
(from log conventions or a Contiki-NG hook, decided per Phase 4), per-node energest counters at
intervals. One observer change: the radio `rx` event gains the sender's mote index, so `rx`
lines carry `from`; today the observer has data, length, channel and RSSI only.

## Phase 3 — Actions

Existing: `move`, `send`, `send_all`, `remove`, `add`. Rename nothing; advertise them.

Add, as timed actions and as control-plane actions:

- `link.set_loss` / `link.set` on plugin media (today a static medium config)
- `medium.set_noise` / interference where the medium supports it
- `radio.inject` (a raw 802.15.4 frame onto the medium; the lock-step `tx` path already exists)
- `node.reset` as an explicit name for `remove` + `add` at the same time
- clock perturbation only if a platform actually supports it; otherwise leave it out of capabilities

All actions take effect at simulation time and are deterministic for a given experiment and seed.

One action path. A node dragged in the web UI is a `move` action: it goes through the same
validation as a scenario or session action and lands in `scenario.replay.yaml` with its
effective `t` and `applied: true`. Today the UI drag reaches the medium directly; route it
through the action dispatch site in the runner so a human-driven run is reproducible. The same
holds for any future UI mutation (remove, add, serial input).

## Phase 4 — State timing and metrics

### State timing (first)

The research primitive is not energy, it is the state timeline: every radio and CPU state
transition with an exact timestamp, and time in each state per node. Energy conversion is a
script over that data and leaves the simulator. Two requirements: the transitions are
timestamped accurately, and they can be collected.

Timing accuracy today, per platform (csim a09e798, 2026-09-20, from the code):

| platform | how radio state reaches the observer | accuracy |
| --- | --- | --- |
| CC2538 | `cc2538_rfcore.c` has one `set_state` funnel with `state_callback`; the runner (`mixed_rf_state_handler`) stamps it from the CPU cycle counter (`arm_elf_mote_now_ns`) | exact |
| MSP430 + CC2420 (Sky, Z1) | polled: `update_radio_state()` once per outer-loop iteration reads `cc2420.state` through the `ui_radio_state` op and stamps it with `sim_runtime_now_ns` | quantised to the loop cadence (the mote's next timer event, milliseconds); a state shorter than one iteration is never seen |
| nRF52840, nRF54L15 | `nrf_radio_common.c` has no state callback and the ARM mote's `ui_radio_state` op is NULL | not tracked at all |
| CPU (all) | `lpm_ns` accrues cycle-exactly at each LPM fast-forward (`msp430_cpu.c`), active = elapsed − lpm; read once through `cpu_power_ns` at the end of the run (`emit_cpu_state_obs`) | totals exact; no transitions, LPM0–4 lumped, nothing mid-run |
| gating | `sim_runtime_radio_state_tracking` is on only when the energest plugin or the UI is attached | otherwise no transitions are emitted |

Work, in order:

1. **State callback in the CC2420 and Nordic models.** `cc2420.c` has a single `set_state`
   funnel like the CC2538's; add the same callback there and in `nrf_radio_common.c`, stamped
   with the mote's cycle clock, and retire the polled path for radio state. This makes Sky and
   Z1 exact and gives the Nordic boards data at all.
2. **CPU transitions as events.** Emit a `cpu` event on each active/LPM transition with the LPM
   level, stamped from the cycle clock; keep the end-of-run totals as a cross-check.
3. **Time in state per node in `result.json`**, in nanoseconds per radio state (off, on, tx,
   rx, interfered) and per CPU state, computed from the transition stream, with the definition
   string saying exactly that. The transitions in `events.ndjson` are the time series; nothing
   is sampled.
4. **Tracking always on when a run directory is requested.** The gate stays for plain runs so
   existing output is byte-identical.
5. **Agreement test against the firmware's own energest.** Contiki-NG's energest counts rtimer
   ticks per state from inside the emulated mote. On the same run, the simulator's dwell times
   and the firmware's tick counts must agree within one rtimer tick (Sky: 1/32768 s ≈ 30.5 µs).
   Pin it as a regression. Where silicon traces exist, the same comparison against hardware is
   the second bar. This is the fidelity claim.

The CC2420 and MSP430 current tables in `energest_engine.c` leave the simulator and become a
script in the spec repo (`tools/energy.py`, time-in-state × a per-board current table the user
supplies). The engine's 64-mote cap goes with it.

### Metrics (second)

Radio duty cycle follows directly from time in state and is well defined; ship it first with
its definition string.

Packet delivery ratio, latency and retransmissions need packet identity, which the radio
observer does not carry. Decide one of:

1. define them over Contiki-NG's application log conventions (what the upstream tests do), or
2. track 802.15.4 sequence numbers and addresses on the medium.

Option 1 is cheap and matches the test suite; option 2 is protocol-agnostic but counts MAC
frames, not application packets. Pick 1 for v0.2, name it in the metric definition, and keep 2
as a future medium service.

Route churn and convergence time are log-derived (RPL parent switches, DAG join) and belong to
option 1 as well.

Every metric in a result states its calculation semantics and inputs. Nothing is hidden.

## Phase 5 — Conditions and multi-seed evaluation

Existing conditions map onto the shared closed set and its two lists: `test.steps` (`wait` +
`count`) is `expect` with `log_contains`, sequential, each window starting where the previous
step was reached, which is what the steps already do; `fail_on` is `invariants` with `no_event`
on a log pattern; validators are `expect` entries with `count`. The shared names are accepted as
an alternative spelling next to the existing keys; nothing is renamed. Add `metric` thresholds:

```yaml
expect:
  - metric: { name: pdr, op: ">=", value: 0.99 }
  - metric: { name: latency_p95_ms, op: "<", value: 200 }
  - metric: { name: radio_duty_cycle, op: "<", value: 0.03 }
```

A `metric` in `expect` is evaluated at the end of the run (the spec's window rule: a metric is
evaluated when its window closes); an unavailable metric makes the verdict `inconclusive`, not
a pass, exit 1.

JS scripts remain the escape hatch and are advertised as such.

Multi-seed:

```yaml
seeds: [1, 2, 3, 4, 5]
```

`cooja-ng run` spawns the runner once per seed (the runner is one long main; the upstream test
wrapper already loops seeds this way), writes one run directory per seed, and an aggregate
`result.json` that lists every seed's verdict and never conceals a failed seed. This enables workloads such as:

> Improve RPL behavior while maintaining PDR >= 99%, p95 latency < 200 ms, and radio duty cycle < 3% over all specified seeds.

## Phase 6 — Capability discovery

```text
cooja-ng capabilities --json
cooja-ng describe radio.inject --json
```

Report, with JSON Schemas: platforms (from the board registry), media and medium plugins,
actions, observation types, `observables`, conditions, the scenario schema (the existing
`docs/test-format.md` schema, machine-readable), metrics with definitions, services,
`determinism` (`seedable: true`, with the documented derivation of startup delay and medium
randomness from the one seed), `nestable` (kernel side), and `limitations` (per-platform
unmodelled peripherals, known model simplifications such as UDGM). `describe <name>` returns
one entry.

## Phase 7 — Evidence bundle

Every failed run can produce a directory that another human or agent replays exactly:

- `config.effective.yaml` (exists) and the exact seed
- Cooja-NG version and commit
- firmware paths and hashes; the Contiki-NG commit when the tree is present
- node logs, `events.ndjson`, pcap
- metric inputs and definitions
- simulator warnings and errors

`cooja-ng bundle <run_dir>` is a tar of the run directory plus a `README` describing how to
replay. `scenario.replay.yaml` inside it is the replay: initial configuration, resolved
firmware and plugin hashes, the experiment seed and its documented derivation, and the ordered
action history. Final positions alone are insufficient to reproduce a dynamic topology run.

## Phase 8 — Simulator/model bug escalation

Document in `AGENTS.md` (today only build and test) the distinction between:

1. guest/application bug,
2. Contiki-NG/network-stack bug,
3. expected model limitation (declared in capabilities),
4. Cooja-NG implementation bug.

Agent workflow for a suspected Cooja-NG bug:

1. Check `capabilities.limitations` first.
2. Minimize node count, topology, runtime, and firmware needed to reproduce.
3. Pin the seed; keep `scenario.replay.yaml` and `config.effective.yaml`.
4. Compare against specifications, other models, Java Cooja, traces, or physical experiments where feasible.
5. Add a minimal regression config under `configs/` or `test/`.
6. Fix Cooja-NG only when evidence supports the diagnosis.
7. Run the unit suites and the upstream Contiki-NG Cooja suite.
8. Prepare/open a focused PR according to host permissions.
9. Resume the original networking task.

Do not allow an agent to "optimize" application/network code around a simulator defect without explicitly identifying the discrepancy.

## Phase 9 — Research-agent workflows

Demonstrations beyond pass/fail. These are agent orchestration on top of the runner, not
simulator features, and live outside the simulator repo. The first two are the M5 headline
demos in `ROADMAP.md`:

- optimize RPL parameters over multiple topologies/seeds;
- find the minimum interference that causes a reliability requirement to fail;
- reproduce and minimize a network partition;
- compare two MAC/routing implementations under identical conditions;
- bisect a regression between two Contiki-NG commits.

Agents report the experiment definition and evidence, not only conclusions.

## Phase 10 — Integration with esp32sim

The lock-step protocol already makes esp32sim a Cooja-NG node. The control-plane rule from the
protocol document applies: when esp32sim is nested, the agent talks to Cooja-NG only, and
esp32sim's per-node diagnostics (unimplemented accesses, stubs, traces, VCD) surface as
node-scoped entries in `events.ndjson`, `result.json` and the bundle. The lock-step parser
already ignores unknown output event types, so a `diag` event from the node breaks nothing
today; csim forwards it as an observer event.

Config passthrough: a node of an external type carries an opaque `args` object in the config,
`ext_node_start()` puts it in `hello.args` untouched, and the node's simulator validates it
against its own `scenario_schema`. This is how the same board configuration runs standalone
and as a node. `external-nodes-plan.md` §4 lists `args`; the implementation does not send it.

```text
             Coding / research agent
                       |
              Agent Simulation Protocol (control plane)
                 /             \
            esp32sim          Cooja-NG ── lock-step (data plane) ── esp32sim as a node
           MCU behavior     network behavior
                 \             /
                  real devices
```

## Priorities

Cooja-NG leads the protocol work (`ROADMAP.md` §2): it is the research and test bench for
Contiki-NG, and metrics are the payoff.

1. `result.json`, run directory, replay file, exit-code table, no silent medium fallback (Phase 1)
2. `events.ndjson` export (Phase 2)
3. energest metrics with definitions; PDR, latency and route churn over log conventions (Phase 4)
4. `metric` conditions and multi-seed aggregate (Phase 5)
5. corpus check: how many of the 93 upstream Contiki-NG tests fit `expect` and `invariants` without JS (Phase 5; runs now, before Phase 1, as `ROADMAP.md` M0)
6. capabilities with limitations (Phase 6)
7. new actions: link loss, injection, node reset (Phase 3)
8. bundle and `AGENTS.md` escalation workflow (Phases 7, 8)
9. research demos: minimum interference over seeds, regression bisect (Phase 9)
10. nested-node diagnostics through lock-step (Phase 10)
11. protocol session mode, per-action MCP tools

## Success criteria

Cooja-NG is agent-ready when a fresh agent, given only `capabilities --json`, can:

- construct and run a deterministic multi-node experiment,
- perturb network/environment conditions,
- consume `events.ndjson` and `result.json`,
- evaluate explicit engineering constraints over several seeds,
- replay and minimize a failure from its bundle,
- distinguish guest bugs from declared model limitations and from simulator problems,
- and produce a regression-tested simulator fix when justified.
