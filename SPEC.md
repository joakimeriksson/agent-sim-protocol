# Agent Simulation Protocol — Strawman v0.3

## Purpose

A small simulator-neutral protocol for coding and research agents operating executable simulation environments.

This is deliberately a strawman, not a proposed standard. Validate it first with esp32sim and Cooja-NG.

Conceptual influences:

- Gymnasium: environment, action, observation, reset, seed
- FMI: simulator lifecycle, stepping, events, co-simulation
- MCP: discoverability and typed tool interfaces

MCP should be an adapter to this protocol, not the simulator semantics themselves.

## Relationship to the existing lock-step protocol

A working NDJSON protocol already ships between the two simulators: Cooja-NG's external-node
protocol (csim `docs/design/external-nodes-plan.md` §4, esp32sim `--cooja`). It settled the
transport (NDJSON on stdin/stdout), the time unit (integer nanoseconds), the handshake (`hello`)
and the event names (`tx`, `rx`, `log`, `serial`, `radio`, `led`). This strawman does not replace
it and must not invent a parallel envelope.

Two planes, one envelope:

| plane | who talks to whom | protocol |
| --- | --- | --- |
| data plane (co-simulation) | a simulation kernel ↔ one node it steps | lock-step: `hello` / `step` / `stop` → `done` |
| control plane (this document) | an agent, CI or script ↔ one simulator session | `hello` / `capabilities` / `run_until` / `action` / … |

Both use one object per line, a `type` field naming the message, and `t` as an integer in
nanoseconds of simulation time. Observation events on the control plane reuse the lock-step
event names and fields verbatim where the concept is the same (`log`, `tx`, `rx`, `radio`).

### Nested simulators

When esp32sim runs as a Cooja-NG node its stdin and stdout are owned by csim. The agent then
talks to Cooja-NG only. Per-node facilities (esp32sim's traces, VCD, unimplemented-register
log) surface through Cooja-NG as node-scoped artifacts and diagnostics. A simulator that can be
nested advertises `nestable: true` and, when nested, refuses control-plane connections.

## Vocabulary

One name per concept, used in every document:

| word | meaning |
| --- | --- |
| `run_until` | the operation: advance until a condition holds or a timeout expires, report which |
| `expect` | a scenario file's ordered list of conditions, each a `run_until` with `assert: true` |
| `invariants` | a scenario file's run-wide conditions, checked continuously, a hit ends the run |
| `assertion_failed` | the error when an `expect` entry or a `run_until` with `assert: true` is not reached |
| `run` | the CLI verb that runs a scenario file, in both simulators |

The word "assert" appears only in `assert: true` and `assertion_failed`.

## Core concepts

The smallest useful vocabulary of operations is:

```text
hello
capabilities
describe
configure
reset
run_until
action
observe
cancel
diagnose
terminate
```

Not every simulator must implement every operation. Capability discovery is mandatory.

Deliberately absent from v0.3: `snapshot` / `restore` (neither simulator has it; Cooja-NG's `add`
is a reboot) and `step` (agents want semantic progression; the kernel-level step belongs to the
data plane).

## Transport and envelope

NDJSON over stdin/stdout or another bidirectional stream. Requests carry an `id`; responses echo
it. Asynchronous events carry no `id`. `t` is a 64-bit integer; parsers must not truncate it to a
double, although 2^53 ns is 104 days and no run reaches it.

```json
{"id":1,"type":"hello","protocol":"agent-sim/0.3"}
{"id":1,"ok":true,"protocol":"agent-sim/0.3","simulator":"esp32sim","version":"0.4.1","commit":"2873374","run_dir":"runs/2026-09-12T08-31-00"}
```

`hello` echoes the protocol version the simulator implements and returns `run_dir`: the
directory every artifact of this session is written to (below). A missing prerequisite (mask ROM
ELF, firmware path, Contiki-NG tree) is a `configuration_error` on `hello` or `configure` naming
the path that was looked for, never a later silent failure.

The same semantics are exposed as a one-shot CLI (below) for batch use; the streaming session is
for interactive debugging and is implemented second.

## Capability discovery

```json
{"id":2,"type":"capabilities"}
```

```json
{
  "id":2,
  "ok":true,
  "protocol":"agent-sim/0.3",
  "targets":["esp32s3","esp32c3","esp32c6"],
  "operations":["describe","configure","reset","run_until","action","observe","cancel","diagnose"],
  "actions":{
    "gpio.set":{
      "schema":{"type":"object","required":["pin","value"],
                "properties":{"pin":{"type":"integer","minimum":0,"maximum":48},
                              "value":{"type":"integer","enum":[0,1]}}}
    }
  },
  "observations":["log","gpio","exception","unimplemented_access","stub"],
  "observables":["node.state","gpio","memory"],
  "conditions":["log_contains","log_matches","gpio_level","time","event_count","no_event","probe_reached","memory_value"],
  "metrics":{},
  "scenario_schema":"schema/scenario.esp32sim.json",
  "determinism":{"deterministic":true,"seedable":false,"breaks_with":["--net nat","--realtime"]},
  "nestable":true,
  "limitations":{"stubs":["bb_init=0"],"unmodelled":["watchdogs","ble","wifi6"],"notes":["run_until on the S3 schedules both cores through the block path; the cycle-exact path is single-core"]}
}
```

Schemas are JSON Schema from day one. They are what generates MCP tools and what lets an agent
call the simulator without prompt stuffing. `scenario_schema` is the schema (inline or a path
under the install) of the scenario file `run` accepts, so an agent that has only this reply can
author one. `describe <name>` returns the schema and documentation of one action, condition,
observable or metric.

`limitations` is mandatory. Active stubs and known unmodelled blocks are declared here so an
agent never reads a stubbed function or an unimplemented register as a firmware bug.

## Lifecycle

```text
hello
→ capabilities / describe
→ configure
→ reset(seed)
→ action / run_until / observe   (repeat)
→ diagnose / artifacts if needed
→ reset or terminate
```

## Time

Simulation time is explicit, distinct from wall clock, and an integer `t` in nanoseconds on
every event and every result. This is the lock-step unit; csim is ns-precise and esp32sim's bus
cycle is 6.25 ns, so microseconds would lose information the radio timing depends on. Requests
may use convenience units (`simulation_ms`) but results never do.

Every event carries `node`, also in a standalone single-device simulator (`node: 1`), so a
consumer never branches on whether the run was nested.

```json
{"type":"log","t":124100000,"node":1,"line":"ready"}
```

## Actions

Actions manipulate the simulated world. Names are simulator-defined namespaces advertised
through capabilities, with schemas.

```json
{"id":20,"type":"action","name":"gpio.set","args":{"pin":4,"value":1}}
{"id":21,"type":"action","name":"link.set_loss","args":{"src":1,"dst":2,"loss":0.3}}
```

An action is applied at the current simulation time unless it carries `at` (ns). Scheduled
actions in a scenario file are the same objects with `at` set. An `at` in the past is
`invalid_request`. Simultaneous actions apply in request order. A rejected action (capability or
state validation) is reported and not recorded in the replay.

Every accepted action is recorded with its effective `t` and a monotonic sequence number in
`scenario.replay.yaml` (below).

## Observations

Observations describe simulator state or events without implying pass/fail. Streaming events
reuse the lock-step names. `observe` is the explicit query for state that has no event; the
queryable names are the `observables` list in capabilities.

```json
{"type":"gpio","t":123400000,"node":1,"pin":4,"value":1}
{"type":"tx","t":125000000,"node":3,"ch":26,"len":84}
{"id":25,"type":"observe","what":"node.state","args":{"node":3}}
```

## run_until

`run_until` advances simulation time until a condition holds or a timeout expires, and reports
which:

```json
{"id":10,"type":"run_until","condition":{"log_contains":{"node":1,"text":"connected"}},"timeout":{"simulation_ms":5000,"wall_ms":60000}}
{"id":10,"ok":true,"reached":true,"t":2310400000}
```

With `"assert": true`, `reached: false` is instead an `assertion_failed` error carrying expected,
observed and artifacts. There is no separate assertion operation.

`timeout.simulation_ms` bounds simulation time; `timeout.wall_ms` bounds host time, for a guest
that spins or a host that is slow. Either expiring is `timeout`, and the result says which.
`cancel` with the `id` of a running `run_until` stops it at the next scheduling point with
`termination_reason: cancelled`.

### Conditions

The condition language is the hard part. v0.3 fixes a small closed set; a simulator advertises
which it supports:

| condition | kind | meaning |
| --- | --- | --- |
| `log_contains` / `log_matches` | event | a console line (per node or any) contains text / matches a regex, optional `count` |
| `event_count` | event | N events of a type have been seen (`tx`, `rx`, `exception`, …) |
| `no_event` | event | no event of a type occurs; only meaningful in `invariants` (below) |
| `gpio_level` | state | a pin holds a value |
| `time` | state | simulation time has reached `t` |
| `metric` | state | a named metric compares against a threshold |

Simulator-specific conditions are advertised alongside (esp32sim: `probe_reached`,
`memory_value`).

### Evaluation windows

| rule | |
| --- | --- |
| window start | a `run_until` counts events with `t` at or after the request was issued; an `expect` entry's window starts when the previous entry was reached, or at reset for the first |
| state conditions | `gpio_level`, `time`, `metric` are satisfied immediately, at the current `t`, if already true |
| `event_count` | takes `since: previous \| reset`, default `previous` |
| `count` on log conditions | counts within the window |
| timeout | measured from the window start |

### expect and invariants

A scenario file has two lists. `expect` is sequential: each entry is a `run_until` with
`assert: true`, and its window begins where the previous one ended. `invariants` is run-wide:
each is checked continuously from reset to the end of the run, and a hit ends the run
immediately with that invariant's verdict, before any pending `expect` is evaluated.

```yaml
expect:
  - log_contains: { text: "button pressed" }
  - gpio_level:   { pin: 5, value: 1, within_ms: 200 }
invariants:
  - no_event: { type: exception }               # a hit is guest_failure
  - no_event: { type: unimplemented_access }     # a hit is assertion_failed, with the limitation named
```

`invariants` maps onto Cooja-NG's existing `fail_on`. Cooja-NG's JS scripts stay as an explicit,
simulator-specific escape hatch. A general predicate language is not standardized in this
version.

## Seeds and determinism

A simulator reports `deterministic` and `seedable` separately. esp32sim is deterministic but
unseedable (a fixed xorshift, no host clock or randomness) and loses determinism with `--net nat`
or `--realtime`. Cooja-NG is seedable and byte-identical per seed.

Every result carries `seed` (or `null`) and `deterministic: true|false` for the configuration
actually run. A replay with the same configuration, version and seed is expected to be
byte-identical when `deterministic` is true.

A seedable simulator reports the experiment seed and documents how per-component randomness
(medium, startup delay, per node) is derived from it. Where a simulator actually keeps separate
per-component seeds it reports them; a simulator with one seeded stream does not invent them.

A nested simulator receives the experiment seed explicitly through the lock-step `hello` and
uses it; a node id may enter a documented derivation but must not silently replace the seed.
(esp32sim currently parses that seed and ignores it; until it honours it, it reports
`seed: null`.)

## Replay

Every run, batch or session, writes `scenario.replay.yaml` into `run_dir`: the initial
configuration, the effective seed, the resolved firmware and plugin hashes, and every accepted
action with its effective `t` and sequence number. It is a valid scenario file for `run`, so the
batch CLI is the replay tool and a session that an agent or human drove interactively replays
without them. Final positions or a final live setup alone are not a replay of a run that moved,
removed or re-added nodes.

## Evidence and artifacts

Artifacts are files in `run_dir`, on both transports, and paths are relative to `run_dir`. The
protocol returns paths; an agent can `cat` them, a CI job can archive the directory, and no
fetch operation is needed.

```json
{
  "id":30,
  "ok":false,
  "error":"assertion_failed",
  "expected":{"gpio_level":{"pin":5,"value":1}},
  "observed":{"pin":5,"value":0,"t":1200000000},
  "artifacts":[
    {"type":"uart_log","path":"uart0.log"},
    {"type":"events","path":"events.ndjson"},
    {"type":"vcd","path":"gpio.vcd"}
  ]
}
```

Every run writes at least `events.ndjson`, `scenario.replay.yaml`, `config.effective.yaml`
(what actually ran, with the effective seed and version) and `result.json`. Traces, VCD, pcap,
coverage, register accesses and metric inputs are added on request or on failure.

`result.json` carries fields that vary between identical runs (wall time, commit, the run
directory). A golden test compares `events.ndjson` byte for byte and `result.json` with those
fields stripped; `--run-dir` fixes the directory so tests never see a timestamp.

## Diagnostics

```json
{"id":40,"type":"diagnose","scope":"last_failure"}
{
  "id":40,
  "ok":true,
  "facts":["unimplemented register access at 0x600A0040 from 0x4200_1234 (bb_init)","stub active: bb_init=0"],
  "hypotheses":[{"kind":"possible_simulator_limitation","confidence":"medium"}]
}
```

Facts are things the simulator observed. Hypotheses are heuristics and are labelled as such. The
protocol never presents a heuristic bug classification as established truth.

## Error taxonomy and exit codes

One table, used by both simulators, on both transports. Nonzero is a failure for CI; the value
tells an agent in a shell loop the class without opening `result.json`:

| error | exit code | meaning |
| --- | --- | --- |
| (none) | 0 | run completed, every `expect` reached, no invariant hit |
| `assertion_failed` | 1 | the guest ran; an `expect` or an `invariant` did not hold |
| `configuration_error` | 2 | bad scenario, missing firmware/ROM/Contiki tree, unknown key, unknown medium or plugin |
| `invalid_request` | 2 | malformed protocol message, `at` in the past |
| `unsupported_operation` / `unsupported_capability` | 3 | the simulator declares it cannot do this |
| `simulation_error` / `internal_error` | 4 | the simulator itself failed, including a nested peer that vanished |
| `guest_failure` | 5 | panic, exception, or the guest's own FAIL line |
| `timeout` | 6 | the condition was not reached in simulation or wall time |
| `cancelled` | 7 | stopped by `cancel` or a signal |

Exit code 3 exists so agents do not treat unsupported simulator behavior as a firmware defect.
Cooja-NG's existing fail-loud contract (no criteria, script without verdict, unknown medium)
maps to `configuration_error`.

Results carry independent `termination_reason` (completed, assertion_failed, timeout_simulation,
timeout_wall, cancelled, guest_failure, peer_disconnect, simulator_error) and `verdict` (pass,
fail, inconclusive) fields. A completed run with an inconclusive or unavailable metric is
`inconclusive`, not a pass.

## Simulator bug workflow

The protocol does not automate PR creation. It makes evidence collection and reproduction easy
enough for an agent to follow repository contribution policy.

```text
suspected simulator discrepancy
→ check capabilities.limitations first (stubs, unmodelled blocks)
→ minimize reproducer
→ pin seed/configuration/version (scenario.replay.yaml, config.effective.yaml)
→ collect evidence/reference behavior (real hardware, spec, differential tests)
→ add failing regression
→ fix simulator if justified
→ run tests
→ prepare/open PR subject to user permission
→ resume original task
```

## Mapping to MCP

Generated from `capabilities`, not hand-written. The batch-shaped adapter exposes
`capabilities`, `describe`, `run` (a scenario file), `read_result` and `diagnose`; it needs no
session. Per-action and `run_until` tools are added once the session exists, with argument
schemas copied through. Simulator implementations do not depend on MCP.

## Mapping to CLI

```text
esp32sim run scenario.yaml --run-dir DIR --wall-timeout 120
cooja-ng run experiment.yaml --run-dir DIR --wall-timeout 600
```

One verb, `run`, in both. Exit code from the table, `result.json` and the other artifacts in the
run directory. CI, humans, scripts and agents share one code path. The CLI is the batch form of
the session: `configure` + scheduled actions + `expect` + `invariants` + `terminate`.

What each simulator has today is inventoried in the two plans (`ESP32SIM_AGENT_PLAN.md`,
`COOJA_NG_AGENT_PLAN.md`), not here.

## v0.3 validation questions

Decided so far: artifacts are files in a run directory; snapshots are out; assert is a flag on
`run_until`; time is ns; `expect` is sequential and `invariants` are run-wide, with the windows
above; replay is a scenario file; exit codes distinguish assertion, guest failure and timeout.

Still open. Implement in both simulators and answer:

1. Is the closed condition set sufficient? Measured on the 93 upstream Contiki-NG Cooja tests: how many express fully in `expect` and `invariants`, how many need JS. Does esp32sim also need a scripted escape hatch?
2. Which operations need a persistent session, versus the batch CLI? (Guess: only interactive debugging.)
3. Which metric concepts belong in the protocol versus simulator-specific namespaces?
4. Do generated MCP tools from capability schemas work without manual editing?
5. Acceptance test: can a fresh agent, given only the `capabilities` output and the broken-firmware demo, complete the repair loop with no simulator-specific prompt?

Only standardize concepts that survive both implementations.
