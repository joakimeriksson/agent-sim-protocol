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
- Exit codes from the shared table in `SPEC.md`: 0 pass, 1 assertion, 2 configuration,
  3 unsupported, 4 simulator error, 5 guest failure, 6 timeout, 7 cancelled. The current
  fail-loud cases (no criteria, no verdict, unknown medium) map to `configuration_error`.

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
`led`) and `node` on every event.

New observation types only where the stream lacks them: routing events and topology changes
(from log conventions or a Contiki-NG hook, decided per Phase 4), per-node energest counters at
intervals.

## Phase 3 — Actions

Existing: `move`, `send`, `send_all`, `remove`, `add`. Rename nothing; advertise them.

Add, as timed actions and as control-plane actions:

- `link.set_loss` / `link.set` on plugin media (today a static medium config)
- `medium.set_noise` / interference where the medium supports it
- `radio.inject` (a raw 802.15.4 frame onto the medium; the lock-step `tx` path already exists)
- `node.reset` as an explicit name for `remove` + `add` at the same time
- clock perturbation only if a platform actually supports it; otherwise leave it out of capabilities

All actions take effect at simulation time and are deterministic for a given experiment and seed.

## Phase 4 — Metrics

Radio duty cycle and energy come from energest and are well defined; ship them first with
their definition string in the result.

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

A `metric` in `expect` is evaluated at the end of the run; an unavailable metric makes the
verdict `inconclusive`, not a pass.

JS scripts remain the escape hatch and are advertised as such.

Multi-seed:

```yaml
seeds: [1, 2, 3, 4, 5]
```

The runner writes one run directory per seed plus an aggregate `result.json` that lists every
seed's verdict and never conceals a failed seed. This enables workloads such as:

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
node-scoped entries in `events.ndjson`, `result.json` and the bundle. This needs the lock-step
`done` reply to carry a `diag` list, or a side file per external node in `run_dir`.

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
5. corpus check: how many of the 93 upstream Contiki-NG tests fit `expect` and `invariants` without JS (Phase 5)
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
