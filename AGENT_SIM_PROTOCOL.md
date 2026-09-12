# Agent Simulation Protocol — Strawman v0.2

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

## Core concepts

The smallest useful vocabulary is:

```text
hello
capabilities
configure
reset
run_until        (assert is run_until with a verdict)
action
observe
artifact
diagnose
terminate
```

Not every simulator must implement every operation. Capability discovery is mandatory.

Deliberately absent from v0.2: `snapshot` / `restore` (neither simulator has it; Cooja-NG's `add`
is a reboot) and `step` (agents want semantic progression; the kernel-level step belongs to the
data plane).

## Transport and envelope

NDJSON over stdin/stdout or another bidirectional stream. Requests carry an `id`; responses echo
it. Asynchronous events carry no `id`.

```json
{"id":1,"type":"hello","protocol":"agent-sim/0.2"}
{"id":1,"ok":true,"simulator":"esp32sim","version":"0.4.1","commit":"2873374","run_dir":"runs/2026-09-12T08-31-00"}
```

`hello` returns `run_dir`: the directory every artifact of this session is written to (below).
A missing prerequisite (mask ROM ELF, firmware path, Contiki-NG tree) is a `configuration_error`
on `hello` or `configure` naming the path that was looked for, never a later silent failure.

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
  "targets":["esp32s3","esp32c3","esp32c6"],
  "operations":["reset","run_until","action","observe","diagnose"],
  "actions":{"gpio.set":{"schema":{"pin":"integer","value":"integer"}}},
  "observations":["log","gpio","exception","unimplemented_access"],
  "conditions":["log_contains","gpio_level","time","event_count"],
  "metrics":{},
  "determinism":{"deterministic":true,"seedable":false,"breaks_with":["--net nat","--realtime"]},
  "nestable":true,
  "limitations":{"stubs":["bb_init=0"],"unmodelled":["watchdogs","ble","wifi6"]}
}
```

Argument and result schemas are part of the response from day one (JSON Schema, however
minimal). They are what generates MCP tools and what lets an agent call the simulator without
prompt stuffing. "Eventually" means the MCP adapter gets hand-written and drifts.

`limitations` is mandatory. Active stubs and known unmodelled blocks are declared here so an
agent never reads a stubbed function or an unimplemented register as a firmware bug.

## Lifecycle

```text
hello
→ capabilities
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
actions in a scenario file are the same objects with `at` set.

## Observations

Observations describe simulator state or events without implying pass/fail. Streaming events
reuse the lock-step names. `observe` is the explicit query for state that has no event.

```json
{"type":"gpio","t":123400000,"pin":4,"value":1}
{"type":"tx","t":125000000,"node":3,"ch":26,"len":84}
{"id":25,"type":"observe","what":"node.state","args":{"node":3}}
```

## run_until and assert

`run_until` advances simulation time until a condition holds or a timeout expires, and reports
which:

```json
{"id":10,"type":"run_until","condition":{"log_contains":{"node":1,"text":"connected"}},"timeout":{"simulation_ms":5000}}
{"id":10,"ok":true,"reached":true,"t":2310400000}
```

`assert` is `run_until` where `reached:false` is an `assertion_failed` error carrying expected,
observed and artifacts. There is no separate assertion model.

The condition language is the hard part. v0.2 fixes a small closed set; a simulator advertises
which it supports:

| condition | meaning |
| --- | --- |
| `log_contains` / `log_matches` | a console line (per node or any) contains text / matches a regex, optional `count` |
| `gpio_level` | a pin holds a value |
| `time` | simulation time reaches `t` |
| `event_count` | N events of a type have been seen (`tx`, `rx`, `exception`, …) |
| `metric` | a named metric compares against a threshold |
| `no_event` | no event of a type occurs before the timeout (e.g. `exception`) |

Cooja-NG's JS scripts stay as an explicit, simulator-specific escape hatch. A general predicate
language is not standardized in this version.

## Seeds and determinism

A simulator reports `deterministic` and `seedable` separately. esp32sim is deterministic but
unseedable (a fixed xorshift, no host clock or randomness) and loses determinism with `--net nat`
or `--realtime`. Cooja-NG is seedable and byte-identical per seed.

Every result carries `seed` (or `null`) and `deterministic: true|false` for the configuration
actually run. A replay with the same configuration, version and seed is expected to be
byte-identical when `deterministic` is true.

Seed handling is part of the contract, not merely a top-level field. A seedable simulator must
report the derived seeds used by each stochastic component (for example, medium, startup delay,
and node), define reset behavior, and include them in the replay manifest. A nested simulator
must receive the experiment seed explicitly; the node ID may be part of a documented derivation,
but must not silently replace the experiment seed.

Interactive runs record every accepted action with its effective simulation timestamp and a
monotonic sequence number. Replay consumes that action history without requiring the original
agent or human to make the same decisions again. Actions scheduled in the past, simultaneous
actions, and actions rejected by capability or state validation have defined outcomes.

## Evidence and artifacts

Artifacts are files in `run_dir`, on both transports. The protocol returns paths; an agent can
`cat` them, a CI job can archive the directory, and no fetch operation is needed.

```json
{
  "id":30,
  "ok":false,
  "error":"assertion_failed",
  "expected":{"gpio_level":{"pin":5,"value":1}},
  "observed":{"pin":5,"value":0,"t":1200000000},
  "artifacts":[
    {"type":"uart_log","path":"runs/.../uart0.log"},
    {"type":"events","path":"runs/.../events.ndjson"},
    {"type":"vcd","path":"runs/.../gpio.vcd"}
  ]
}
```

Every run writes at least `events.ndjson`, `config.effective.yaml` (what actually ran, with the
effective seed and version) and `result.json`. Traces, VCD, pcap, coverage, register accesses and
metric inputs are added on request or on failure.

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

One table, used by both simulators, on both transports:

| error | exit code | meaning |
| --- | --- | --- |
| (none) | 0 | run completed, every assertion held |
| `assertion_failed` | 1 | the guest ran; an expectation did not hold |
| `guest_failure` | 1 | panic, exception, or the guest's own FAIL line |
| `timeout` | 1 | the condition was not reached in simulation time |
| `configuration_error` | 2 | bad scenario, missing firmware/ROM/Contiki tree, unknown key |
| `invalid_request` | 2 | malformed protocol message |
| `unsupported_operation` / `unsupported_capability` | 3 | the simulator declares it cannot do this |
| `simulation_error` / `internal_error` | 4 | the simulator itself failed |

Exit code 3 exists so agents do not treat unsupported simulator behavior as a firmware defect.
Cooja-NG's existing fail-loud contract (no criteria, script without verdict) maps to
`configuration_error`.

Results also carry independent `termination_reason` and `verdict` fields. Normal completion,
assertion failure, simulation timeout, cancellation, guest failure, nested-peer disconnect, and
simulator failure must not be collapsed into one pass/fail message. A completed run with an
inconclusive or unavailable metric is not a passing assertion.

## Simulator bug workflow

The protocol does not automate PR creation. It makes evidence collection and reproduction easy
enough for an agent to follow repository contribution policy.

```text
suspected simulator discrepancy
→ check capabilities.limitations first (stubs, unmodelled blocks)
→ minimize reproducer
→ pin seed/configuration/version (config.effective.yaml)
→ collect evidence/reference behavior (real hardware, spec, differential tests)
→ add failing regression
→ fix simulator if justified
→ run tests
→ prepare/open PR subject to user permission
→ resume original task
```

## Mapping to MCP

Generated from `capabilities`, not hand-written: one tool per operation, one per advertised
action, argument schemas copied through. Simulator implementations do not depend on MCP.

## Mapping to CLI

```text
esp32sim test scenario.yaml --json     # exit code from the table, result.json in run_dir
cooja-ng run experiment.yaml --json
```

CI, humans, scripts and agents share one code path. The CLI is the batch form of the session:
`configure` + scheduled actions + assertions + `terminate`.

## What exists today (2026-09-12)

| concept | Cooja-NG (csim) | esp32sim |
| --- | --- | --- |
| scenario file | strict YAML/JSON: seed, timeout, medium, nodes, actions, validators, `fail_on`, JS | line-based `--script` actions only |
| scheduled actions | move, send, send_all, remove, add | press, release, gpio, knob, serial, uart0, touch, stop |
| conditions | `wait` + count + timeout, validators, `fail_on`, JS | none |
| event stream | internal observer (log, uart, frames, radio tx/rx/state, interference, led, add/remove) — no export | console text; VCD, traces, coverage as files |
| determinism | seeded, byte-identical | unseeded, byte-identical (goldens), lost with NAT/realtime |
| effective config | `--save-config` | none |
| exit codes | fail-loud contract | none |
| capabilities | none | none |
| limitations | none | `--stub`, `--log-periph` exist; not reported |
| nested | kernel side of lock-step | node side of lock-step (`--cooja`) |

## v0.2 validation questions

Decided in this revision: artifacts are files in a run directory (was Q4); snapshots are out
(was Q5); assert folds into run_until; time is ns.

Still open. Implement in both simulators and answer:

1. Is the closed condition set sufficient for the demos, or does esp32sim also need a scripted escape hatch?
2. Which operations need a persistent session, versus the batch CLI? (Guess: only interactive debugging.)
3. Which metric concepts belong in the protocol versus simulator-specific namespaces?
4. Do generated MCP tools from capability schemas work without manual editing?
5. Acceptance test: can a fresh agent, given only the `capabilities` output and the broken-firmware demo, complete the repair loop with no simulator-specific prompt?

Only standardize concepts that survive both implementations.
