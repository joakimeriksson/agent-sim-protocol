# Roadmap — from strawman to two conforming simulators

Companion to `SPEC.md`, `COOJA_NG_AGENT_PLAN.md` and `ESP32SIM_AGENT_PLAN.md`.
This document answers two questions: where the protocol lives, and in what order the two
simulators implement it.

## 0. The goal: close the loop

The point of all of this is to close the OODA loop for agents developing firmware, network
stacks, and the simulators themselves: observe a run, orient on what the evidence means, decide
what to change, act, and run again, without a human in the cycle.

| step | what closes it | milestone |
| --- | --- | --- |
| Observe | `events.ndjson`, `result.json`, simulation time on every event | M1 |
| Orient | `capabilities.limitations`, `diagnose` with facts separated from hypotheses, metrics with definitions | M3, M4 |
| Decide | a failed `expect` returns expected, observed and artifacts; the escalation workflow is the decision tree: guest bug, stack bug, declared limitation, simulator bug | M2, M3 |
| Act | actions and scenarios on the simulated world; editing and rebuilding firmware stay outside the protocol, and the firmware hash in `result.json` ties each observation to a build | M2 |

The loop first closes at M2, when a failed run produces evidence that points at the next edit.
It is proven at M5, where a fresh agent, given only `capabilities --json`, runs the broken
firmware demo to a passing test. The second M5 demo closes the loop on the simulator itself:
failure, minimal reproducer, regression, fix, PR.

Two loop metrics are recorded at M5 and kept afterwards, so a protocol change can be judged by
whether it makes agents faster and not only compliant:

- wall time per iteration on the demo, split into build, run and agent thinking;
- iterations to a passing test, per agent model, on the demo fixtures.

The agent harness and model used for the acceptance run are pinned and named in the demo, so
the numbers are comparable across protocol changes and not across model updates.

Build is outside the protocol on purpose, but inside the demo: `idf.py build` and Contiki `make`
are part of the measured cycle, since a slow or flaky build breaks the loop more often than the
simulator does.

## 1. Where the protocol lives

### Decision: a small specification repo, downstream of the implementations

Make this directory the repo `agent-sim-protocol`. It is a specification repo, not a library:
the simulators are in C and Rust and will not share code. What they can share is schemas, test
vectors, and one client.

```text
agent-sim-protocol/
  SPEC.md                      the protocol
  AGENTS.md                    the rules below, for coding agents working on this repo
  ROADMAP.md                   this file
  schema/
    envelope.json              request/response/event envelope: id, type, t, ok, error
    capabilities.json
    result.json
    events.json                one schema per event type, shared lock-step names, node on every event
    conditions.json            the closed condition set and its evaluation windows
    scenario-common.json       the fields both scenario formats share (expect, invariants, actions[].at)
    replay.json                scenario.replay.yaml: initial config, seed, hashes, action history
  conformance/
    check.py                   validates capabilities / result.json / events.ndjson against schema/
    vectors/                   recorded sessions and results from both simulators, per spec version
  clients/python/agentsim/     spawn a simulator, hello, capabilities, run_until, read run_dir
    mcp_adapter.py             MCP server generated from a simulator's capabilities
  examples/
    esp32sim-button.yaml
    cooja-ng-rpl-chain.yaml
```

Rules that keep the spec honest:

- Nothing enters `SPEC.md` or `schema/` until it exists in at least one simulator, and nothing
  is marked stable until it exists in both. The spec records; it does not lead.
- A spec change is one PR in this repo plus a linked PR in the first simulator. The second
  simulator follows within the same milestone or the change is marked `provisional`.
- Versions are `agent-sim/0.x`. A simulator states the version it implements in `hello` and in
  `capabilities`. `conformance/check.py` pins a schema version and is run in both simulators' CI
  against their own output.
- The Python client and the MCP adapter live here because they are the payoff of having one
  protocol: one adapter for both simulators. They are consumers of the spec, never its
  definition.

### Where the two plans live

Move them to the code they describe, where implementers and coding agents will read them:

- `ESP32SIM_AGENT_PLAN.md` → `esp32sim/docs/agent-plan.md` (the repo keeps plans under `docs/*-plan.md`)
- `COOJA_NG_AGENT_PLAN.md` → `csim/docs/design/agent-plan.md` (the repo keeps plans under `docs/design/*-plan.md`)

Leave one-line pointers here. The spec repo then holds only the protocol, the schemas, the
conformance checker, the client and this roadmap.

### What not to do

- No shared C or Rust library. Two languages, two build systems, and the surface is JSON.
- No spec-first design rounds. Every open question in `SPEC.md` is answered by implementing it.
- No MCP before `capabilities` exists in both simulators. The adapter is generated, not written.

## 2. Implementation order

Cooja-NG leads. It is the research and test bench for Contiki-NG, it is where metrics and
multi-seed evaluation live, and its M1 is the smaller one: configs, seeds, actions, sequential
steps, `fail_on` and the exit contract already exist, so M1 is a formatter on the observer
stream, a `result.json` writer and capabilities from registries that exist. esp32sim follows
once Cooja-NG's real output has settled the schemas, so it implements against recorded vectors
rather than hand-written ones.

Batch CLI first, streaming session last. The batch form carries most of the agent value and is
the conformance surface. Each milestone ends with both simulators passing `conformance/check.py`
on the same spec version and the Python client running one scenario on each.

Order of work: M0 corpus check (now, no implementation needed) → M1 (Cooja-NG, then esp32sim)
→ M4 metrics and multi-seed (Cooja-NG only) → M2 conditions (Cooja-NG, then esp32sim) → M3 →
M5 → M6. The milestone numbers are kept as names; the sequence is what changed.

### M0 — Corpus check (S, spec repo, now)

The cheapest validation of the hardest part of the spec, and it needs no implementation:
convert the 93 upstream Contiki-NG Cooja tests with csim's `tools/csc2json.py`, classify each
test's script, and count how many express fully in `expect` and `invariants` with the closed
condition set and the `seq`-based windows, how many need one addition to the set, and how many
need the JS escape hatch. The result is a table in `conformance/corpus/contiki-ng-tests.md`
naming each test and its category. If the fully-expressible share is poor, the condition set
changes before either simulator implements it.

Sizes are relative: S is a day or two, M a week, L more, with a coding agent doing most of it.

### M1 — Vertical slice: every run leaves evidence (S+M)

Goal: both simulators produce `capabilities --json`, a run directory with `result.json`,
`events.ndjson`, `scenario.replay.yaml` and `config.effective.yaml`, and exit codes from the
shared table, for one existing scenario each. The conformance checker and Python client exist
and pass.

Spec repo (S), built first and marked provisional (done 2026-09-12, commit below; all vectors
hand-written until Cooja-NG produces output): `schema/envelope.json`,
`capabilities.json` (real JSON Schema for action arguments, `observables`, `scenario_schema`,
`limitations`), `result.json` (`verdict`, `termination_reason`), `events.json` for `log`,
`gpio`, `tx`, `rx`, `radio`, `exception`, `unimplemented_access`, `stub`, all with `node`;
`replay.json`; `check.py`; one hand-written vector per simulator showing the intended M1 output
and a few negative vectors that must fail; the client's spawn, hello, capabilities and
run-directory reading; `AGENTS.md`. The first real Cooja-NG output replaces its hand-written
vector, and every disagreement is settled by changing the schema or the simulator, never by
loosening the checker.

csim (M), first:
- a `json_export` service (`src/services/`, implementing `sim_service_ops_t` like
  `pcap_service.c` and `timeline_service.c`) that serializes every `SIM_OBS_*` event to
  `events.ndjson`. The kernel already delivers them; this is a formatter. The record/replay
  service from `external-nodes-plan.md` §5.3 is not built yet; when it is, it should share this
  writer.
- `--run-dir DIR` on `test_runner test`; `--save-config` output always written there as
  `config.effective.yaml`; `scenario.replay.yaml` written from the initial config plus the
  actions that fired.
- `result.json` written at `SIM_OBS_SIM_STOP` by the JSON test engine (`json_test_service.c`):
  `verdict`, `termination_reason`, seed, version and commit, firmware hashes, simulation and
  wall time, per-step outcome, artifact paths relative to the run directory.
- an unknown medium, plugin or required service is `configuration_error` before the run, not a
  warning and a fallback (one `fprintf` in the runner today).
- `--wall-timeout` in the outer loop; nothing bounds wall time today.
- see the code audit in `COOJA_NG_AGENT_PLAN.md` for the seams each of these lands on.
- `test_runner capabilities --json` from the board registry, medium registry and plugin
  registry, plus static lists of actions, conditions and services.
- exit codes mapped in `test_runner` main.
- a CI step running `check.py` on `configs/chain-4node-sky.yaml`'s output.

esp32sim (M), after Cooja-NG's vector is recorded:
- subcommands in `cli/src/lib.rs`: `capabilities`, `describe`, `run`; the existing flag-style
  invocation stays as-is for bare firmware runs.
- a `json` observer in `esp-soc/src/observers/` next to `vcd.rs` and `trace.rs`: console lines
  as `log`, GPIO edges as `gpio` (the VCD observer already sees them), exceptions, unknown
  register accesses (the `--log-periph` path) as `unimplemented_access`, stub hits as `stub`,
  script actions as they fire, `node: 1` on each. Written to `events.ndjson` in `--run-dir`,
  never interleaved with the console on stdout.
- `result.json` at exit from the end-of-run figures plus chip, board, image hashes, version and
  commit, active stubs, unimplemented accesses seen, last PC and cause on a guest failure;
  `scenario.replay.yaml` from the invocation plus the script events that fired.
- `capabilities --json` from the chip and board tables plus static action, condition and
  limitation lists; must work with no ROM and no firmware.
- the missing-ROM error as `configuration_error`, exit 2, naming the path looked for.
- a golden for `esp32sim run` on `hello-s3` with a fixed `--run-dir`: `events.ndjson` byte for
  byte, `result.json` with wall time, commit and run directory stripped.
- a CI step running `check.py`.

Exit criterion: `agentsim run cooja-ng examples/cooja-ng-rpl-chain.yaml` returns a validated
`result.json` and its output is the recorded vector; then the same for
`agentsim run esp32sim examples/esp32sim-button.yaml`.

### M2 — Conditions and scenarios (M+M)

Comes after M4 in the sequence, with M0's corpus table as its input.

Goal: the shared closed condition set works in both with the `seq`-based evaluation windows in
`SPEC.md`, `expect` is sequential and `invariants` are run-wide, an expired `expect` window and
an invariant hit are both `assertion_failed` (1), a halted guest is `guest_failure` (5), the
wall-clock bound is `timeout` (6), `metric` conditions in `expect` are evaluated at the end of
the run, and `scenario.replay.yaml` runs back through `run`.

Spec repo (S): `schema/conditions.json` with the window rules, `scenario-common.json` with
`expect` and `invariants`; `run_until` and `wall_ms` semantics written down from what the
implementations did; vectors for a failing `expect` and a hit invariant from each simulator.

csim (S to M), first:
- map the existing `wait` + `count` steps onto `expect` and `fail_on` onto `invariants` in
  `result.json`, so the report speaks the shared vocabulary. The steps are already sequential
  with the right windows. No change to the config format yet.
- accept the shared names as an alternative spelling in `test.expect` and `test.invariants`,
  alongside the existing `steps`, `validators` and `fail_on`.
- `--wall-timeout`; its expiry is the only `timeout` (6).
- `metric` conditions in `expect`, evaluated at the end of the run over the M4 metrics.

esp32sim (M), after the corpus check has settled the set:
- a YAML scenario loader that produces the existing `Script` events plus `expect` and
  `invariants`; keep the `--script` verbs as the action names.
- a condition observer in the scheduled run loop, next to where script events already stop the
  run at their times, so both S3 cores run (`run_until_cycle` is single-core and stays the
  lock-step path): `log_contains`, `log_matches`, `gpio_level`, `time`, `event_count`,
  `no_event`, plus `probe_reached` on the `--trace-fn`/`--stub` entry mechanism and
  `memory_value` on the `--watch` mechanism.
- `expect` entries run in order; `within_ms` becomes the simulation timeout; `--wall-timeout`.
- `deterministic: false` in `result.json` when `--net nat` or `--realtime` is active.

Exit criterion: the broken-firmware demo fixture fails with exit 1 and a `result.json` that
names the failed `expect` with the `seq` of its window's last event, on both a fresh build and
in the golden suite; a fixture that panics exits 5; a fixture that recovers from an exception
passes unless an invariant says otherwise; `esp32sim run out/scenario.replay.yaml` reproduces
a run byte for byte.

### M3 — Limitations, diagnose, bundle, escalation (S+S+S)

Goal: an agent can tell a declared limitation from a bug and hand over a replayable failure.

Spec repo (S): `limitations` schema; `diagnose` facts/hypotheses schema; bundle layout.

csim (S): `limitations` per platform from a static table (unmodelled peripherals, UDGM
simplifications); `test_runner bundle <run_dir>`; the escalation section in `AGENTS.md`.

esp32sim (S): the "Not there yet" lists of `docs/esp32c3.md` and `docs/esp32c6.md` as a static
table surfaced in `capabilities.limitations`, with active stubs and the single-core note;
`esp32sim diagnose <run_dir>` reading `result.json` and the traces; `esp32sim bundle <run_dir>`;
the escalation section in `AGENTS.md`, which today only covers PR stacks; the lock-step `hello`
seed honoured by the model's xorshift, with the `cooja-*.ndjson` goldens updated, so a nested
run reports the experiment seed.

### M4 — Metrics and multi-seed in Cooja-NG (M)

Directly after Cooja-NG's M1, before M2: this is the research payoff and the part a coding agent
cannot approximate with grep. csim only. Energest duty cycle and energy into `result.json` with
definition strings. PDR, latency and route churn over Contiki-NG log conventions, definitions
stated. `seeds: [...]` loop in `test_runner` with one run directory per seed and an aggregate
`result.json` that never conceals a failed seed. Metrics land in `result.json` only; `metric`
as a condition arrives with M2, which introduces the `expect` spelling. The spec repo adds
`schema/metrics.json` as provisional until esp32sim has any metric at all (instruction count
and simulation time qualify).

Exit criterion: one config, five seeds, an aggregate `result.json` with PDR, p95 latency and
duty cycle per seed and overall, each metric carrying its definition.

### M5 — MCP adapter and the demos (S+M+M)

Spec repo (S): `mcp_adapter.py`, batch-shaped: `capabilities`, `describe`, `run` (a scenario
file), `read_result` and `diagnose`, generated from `capabilities` for either simulator and
checked against both. It needs no session. Per-action and `run_until` tools arrive with M6.

csim (M), the headline demo: a research agent driven by the Python client finds the minimum
interference (Gilbert-Elliott medium parameters) that breaks a PDR requirement over five seeds,
and reports the experiment definition, the per-seed results and the evidence bundle, not only
the number. A second Cooja-NG demo bisects a Contiki-NG regression between two commits with the
same scenario. Both record the loop metrics from section 0.

esp32sim (M), the loop-closure proof: the deliberately broken ESP-IDF project under
`examples/`, the acceptance run with a fresh agent given only `capabilities --json`, and the
second demo that exposes a known emulator defect and ends in a regression plus fix. Both record
the loop metrics.

### M6 — Streaming session and nested diagnostics (M+M)

esp32sim (M): the control-plane session on stdin/stdout: `hello`, `capabilities`, `describe`,
`configure` (which installs the invariants), `reset`, `action`, `run_until`, `observe`,
`cancel`, `terminate`. The request/reply shape is the `--cooja` loop with the roles reversed,
but it drives the scheduled run loop (both cores), not `run_until_cycle`. An invariant hit ends
the current `run_until` with `assertion_failed` and leaves the session open. Every accepted
action goes into `scenario.replay.yaml`. Refused when `--cooja` is active.

csim (M): the same session on `test_runner`, smaller in scope since most agents will use the
batch form; and the nested-node diagnostics: an optional `diag` list in the lock-step `done`
reply so esp32sim's unimplemented accesses and stub hits reach `events.ndjson` and
`result.json` as node-scoped entries (csim's parser ignores unknown event types, so this is
additive); and the `args` passthrough in the lock-step `hello`, listed in
`external-nodes-plan.md` §4 but not sent today, so a nested node gets the same configuration
it would standalone. Both are lock-step protocol changes documented there, not in this spec.

Spec repo (S): session and `cancel` semantics written from the implementation; the per-action
and `run_until` MCP tools added to the adapter; vectors recorded from both.

### M7 — Operational hardening candidates (after M6)

This is a backlog, not part of agent-sim/0.3. Each item enters `SPEC.md` and `schema/` only
after one reference simulator implements it and supplies a recorded vector:

- session identity, request ancestry, and a single-writer control lease so a GUI, agent and CI
  observer cannot race simulation-changing commands;
- declared resource budgets for nodes, events, instructions, output bytes and wall time, with
  partial evidence retained when a limit or cancellation stops a run;
- selection-sensitive capabilities: an action says which target, radio model and execution
  mode support it, plus protocol-version negotiation rather than one assumed version;
- event subscriptions, filters, bounded buffering and an explicit overflow event. A consumer
  must be able to tell that its observation or metric input is incomplete;
- capability declarations for host effects: network access, filesystem access, subprocesses,
  dynamic libraries and external devices, so CI can reject an experiment before running it;
- explicit attach, detach, pause, resume and control-transfer behavior for human/agent handoff;
- stable node, mote-slot and radio identities across remove/re-add and nested simulators;
- versioned metric definitions with unit, scope, sample count and validity
  (`valid`, `unavailable`, `inconclusive`);
- a differential comparison tool that runs two builds/configurations with one replay and reports
  the first divergent event, outcome or metric;
- conformance cases for malformed sessions, command races, cancellation, resource limits,
  stream overflow, replay equivalence, artifact integrity and nested-peer failure.

The spec-repo checker may add auxiliary tooling before these become protocol fields. In v0.3,
`check.py manifest` hashes the files referenced by a run directory for CI archiving, while the
manifest itself remains outside the protocol schema.

## 3. Sequencing across the two repos

Cooja-NG leads every milestone that has a Cooja-NG part; esp32sim follows once the schemas have
been settled by real Cooja-NG output. The exceptions are esp32sim-only items (ROM onboarding,
the firmware repair demo, the session in M6), which run whenever esp32sim has capacity. Each
milestone closes only when the other simulator has caught up or the feature is marked
provisional.

Keep the three determinism bars: csim's byte-identical seed runs, esp32sim's goldens, and the
lock-step `cooja-*.ndjson` tests. Every new output is a golden in esp32sim and a CI-checked
config in csim before it is called done.

## 4. Risks

- **csim scope.** The repo carries several open plans (Renode, RISC-V, Zephyr, TrustZone) and
  is the research bench this tooling is meant to serve. The agent work is formatter-and-
  reporting work on the existing kernel, and must stay that way; anything that needs a kernel
  change goes through `refactor-plan.md` first, so the tooling never destabilises the bench.
- **Output interleaving in esp32sim.** Console text and JSON on one stdout will break goldens
  and agents alike. Events go to the run directory; stdout stays the console unless `--json`
  replaces it entirely.
- **The client becoming the spec.** Agents will read the Python client, not `SPEC.md`. The
  conformance vectors are what prevents the client from drifting into the definition.
- **PDR semantics.** Log-convention metrics are only as good as the firmware's log lines. State
  the convention in the metric definition and keep sequence-number tracking as the later,
  protocol-agnostic option.
- **Nested diagnostics** touch the lock-step protocol, which has its own tests in both repos
  and a byte-identical bar. Version it (`proto: 2`) rather than extending `proto: 1` silently.
- **Single-core cycle path in esp32sim.** `run_until_cycle` does not schedule the S3's second
  core. Conditions and the session must live in the scheduled run loop; if that loop cannot
  stop precisely enough at a condition, M2's esp32sim estimate grows, and the S3 demo is the
  one that would notice.
