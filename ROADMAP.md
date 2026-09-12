# Roadmap — from strawman to two conforming simulators

Companion to `AGENT_SIM_PROTOCOL.md`, `COOJA_NG_AGENT_PLAN.md` and `ESP32SIM_AGENT_PLAN.md`.
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
  SPEC.md                      the protocol (today's AGENT_SIM_PROTOCOL.md)
  ROADMAP.md                   this file
  schema/
    envelope.json              request/response/event envelope: id, type, t, ok, error
    capabilities.json
    result.json
    events.json                one schema per event type, shared lock-step names
    conditions.json            the closed condition set
    scenario-common.json       the fields both scenario formats share (expect, actions[].at)
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

Batch CLI first in both simulators, streaming session second, and only in esp32sim at first.
The batch form carries most of the agent value and is the conformance surface. Each milestone
ends with both simulators passing `conformance/check.py` on the same spec version and the
Python client running one scenario on each.

Sizes are relative: S is a day or two, M a week, L more, with a coding agent doing most of it.

### M1 — Vertical slice: every run leaves evidence (S+M)

Goal: both simulators produce `capabilities --json`, a run directory with `result.json`,
`events.ndjson` and `config.effective.yaml`, and exit codes from the shared table, for one
existing scenario each. The conformance checker and Python client exist and pass.

Spec repo (S): `schema/envelope.json`, `capabilities.json`, `result.json`, `events.json` for
`log`, `gpio`, `tx`, `rx`, `radio`, `exception`, `unimplemented_access`, `stub`; `check.py`;
the client's spawn, hello, capabilities and run-directory reading.

csim (M):
- a `json_export` service (`src/services/`, implementing `sim_service_ops_t` like
  `pcap_service.c` and `timeline_service.c`) that serializes every `SIM_OBS_*` event to
  `events.ndjson`. The kernel already delivers them; this is a formatter. The record/replay
  service from `external-nodes-plan.md` §5.3 is not built yet; when it is, it should share this
  writer.
- `--run-dir DIR` on `test_runner test`; `--save-config` output always written there as
  `config.effective.yaml`.
- `result.json` written at `SIM_OBS_SIM_STOP` by the JSON test engine (`json_test_service.c`):
  verdict, seed, version and commit, firmware hashes, simulation and wall time, per-step
  outcome, artifact paths.
- `test_runner capabilities --json` from the board registry, medium registry and plugin
  registry, plus static lists of actions, conditions and services.
- exit codes mapped in `test_runner` main.
- a CI step running `check.py` on `configs/chain-4node-sky.yaml`'s output.

esp32sim (M):
- subcommands in `cli/src/lib.rs`: `capabilities`, `run`, `test`; the existing flag-style
  invocation stays as-is.
- a `json` observer in `esp-soc/src/observers/` next to `vcd.rs` and `trace.rs`: console lines
  as `log`, GPIO edges as `gpio` (the VCD observer already sees them), exceptions, unknown
  register accesses (the `--log-periph` path) as `unimplemented_access`, stub hits as `stub`,
  script actions as they fire. Written to `events.ndjson` in `--run-dir`, never interleaved
  with the console on stdout.
- `result.json` at exit from the end-of-run figures plus chip, board, image hashes, version and
  commit, active stubs, unimplemented accesses seen, last PC and cause on a guest failure.
- `capabilities --json` from the chip and board tables plus static action, condition and
  limitation lists; must work with no ROM and no firmware.
- the missing-ROM error as `configuration_error`, exit 2, naming the path looked for.
- a golden for `esp32sim test --json` on `hello-s3`, byte-identical like the others.
- a CI step running `check.py`.

Exit criterion: `agentsim run esp32sim examples/esp32sim-button.yaml` and
`agentsim run cooja-ng examples/cooja-ng-rpl-chain.yaml` both return a validated `result.json`.

### M2 — Conditions and scenarios (M+M)

Goal: the shared closed condition set works in both, `expect` fails with expected, observed and
artifacts, and exit codes distinguish assertion, guest failure and timeout.

Spec repo (S): `schema/conditions.json`, `scenario-common.json`; `run_until` semantics written
down from what the implementations did; vectors for a failing assertion from each simulator.

csim (S to M):
- map the existing `wait` + `count`, validators and `fail_on` onto `log_contains`, `log_matches`,
  `no_event`, `event_count` in `result.json` so the report speaks the shared vocabulary. No
  change to the config format yet.
- accept the shared names as an alternative spelling in `test.expect`, alongside the existing
  `steps` and `validators`.
- `metric` conditions wait for M4.

esp32sim (M):
- a YAML scenario loader that produces the existing `Script` events plus an `expect` list; keep
  the `--script` verbs as the action names.
- a condition observer evaluating `log_contains`, `log_matches`, `gpio_level`, `time`,
  `event_count`, `no_event`, plus `probe_reached` on the `--trace-fn`/`--stub` entry mechanism
  and `memory_value` on the `--watch` mechanism.
- `expect` entries run in order as `run_until` over `Machine::run_until_cycle`; `within_ms`
  becomes the timeout.
- `deterministic: false` in `result.json` when `--net nat` or `--realtime` is active.

Exit criterion: the broken-firmware demo fixture fails with exit 1 and a `result.json` that
names the failed `expect`, on both a fresh build and in the golden suite.

### M3 — Limitations, diagnose, bundle, escalation (S+S+S)

Goal: an agent can tell a declared limitation from a bug and hand over a replayable failure.

Spec repo (S): `limitations` schema; `diagnose` facts/hypotheses schema; bundle layout.

csim (S): `limitations` per platform from a static table (unmodelled peripherals, UDGM
simplifications); `test_runner bundle <run_dir>`; the escalation section in `AGENTS.md`.

esp32sim (S): the "Not there yet" lists of `docs/esp32c3.md` and `docs/esp32c6.md` as a static
table surfaced in `capabilities.limitations`, with active stubs; `esp32sim diagnose <run_dir>`
reading `result.json` and the traces; `esp32sim bundle <run_dir>`; the escalation section in
`AGENTS.md`, which today only covers PR stacks.

### M4 — Metrics and multi-seed in Cooja-NG (M)

csim only. Energest duty cycle and energy into `result.json` with definition strings. PDR,
latency and route churn over Contiki-NG log conventions, definitions stated. `seeds: [...]`
loop in `test_runner` with one run directory per seed and an aggregate `result.json`. `metric`
conditions. The spec repo adds `schema/metrics.json` as provisional until esp32sim has any metric
at all (instruction count and simulation time qualify).

### M5 — MCP adapter and the agent demo (S+M)

Spec repo (S): `mcp_adapter.py` generates one tool per operation and one per advertised action
from `capabilities`, for either simulator, and is checked against both.

esp32sim (M): the deliberately broken ESP-IDF project under `examples/`, the acceptance run
with a fresh agent given only `capabilities --json`, and the second demo that exposes a known
emulator defect and ends in a regression plus fix. Both demos record the loop metrics from
section 0: wall time per iteration split into build, run and agent time, and iterations to a
passing test.

csim (S): a research-style demo driven by the Python client: minimum interference that breaks a
PDR requirement over five seeds.

### M6 — Streaming session and nested diagnostics (M+M)

esp32sim (M): the control-plane session on stdin/stdout: `hello`, `capabilities`, `configure`,
`reset`, `action`, `run_until`, `observe`, `terminate`. The loop shape is the `--cooja` loop
with the roles reversed: read a request, `run_until_cycle` or until a condition, reply. Refused
when `--cooja` is active.

csim (M): the same session on `test_runner`, smaller in scope since most agents will use the
batch form; and the nested-node diagnostics: an optional `diag` list in the lock-step `done`
reply so esp32sim's unimplemented accesses and stub hits reach `events.ndjson` and
`result.json` as node-scoped entries. This is a lock-step protocol change and is documented in
`external-nodes-plan.md`, not in this spec.

Spec repo (S): session semantics written from the implementation; vectors recorded from both.

## 3. Sequencing across the two repos

Work M1 in both simulators in parallel; the schemas are small enough to draft in a day and
fix as the two implementations disagree. From M2 onward, esp32sim leads on conditions and the
session, csim leads on metrics and multi-seed, and each milestone closes only when the other
simulator has caught up or the feature is marked provisional.

Keep the three determinism bars: csim's byte-identical seed runs, esp32sim's goldens, and the
lock-step `cooja-*.ndjson` tests. Every new output is a golden in esp32sim and a CI-checked
config in csim before it is called done.

## 4. Risks

- **csim scope.** The repo carries several open plans (Renode, RISC-V, Zephyr, TrustZone). The
  agent work is formatter-and-reporting work on the existing kernel, and should stay that way;
  anything that needs a kernel change goes through `refactor-plan.md` first.
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
