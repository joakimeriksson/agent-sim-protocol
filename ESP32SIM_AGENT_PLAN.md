# esp32sim — Agent-Native Development Plan (v0.3)

## Goal

Turn esp32sim from a high-fidelity ESP32 emulator into an execution and testing environment that coding agents, CI systems, and humans can operate reliably.

The central loop should be:

`build → run → stimulate → observe → assert → diagnose → edit → repeat`

The emulator remains useful independently of AI. Agent support should primarily expose existing emulator capabilities through stable, deterministic, machine-readable interfaces.

## Starting point (esp32sim, 2026-09-12)

This plan is a delta. Most of what v0.1 called Phases 1, 2 and 4 exists as CLI flags:

| exists | where |
| --- | --- |
| scheduled host actions at emulated times: `press`, `release`, `gpio`, `knob`, `serial`, `uart0`, `touch`, `stop` | `--script F` (`docs/cli.md`, "Action scripts") |
| run bounds | `--max-seconds`, `--max-insns`, `--break`, `--watch`, `--stop-after-exceptions` |
| evidence as files: VCD, per-instruction trace, function-call trace, coverage, block profile, IRQ latency, register access stats, unknown-register log, register trace for `hw/compare.py` | `--vcd`, `--trace`, `--trace-fn`, `--coverage`, `--profile-blocks`, `--irq-latency`, `--regstat`, `--log-periph`, `--regtrace` |
| declared workarounds | `--stub SYMBOL[=value]` (e.g. `bb_init=0` on the C6) |
| determinism | no host clock or randomness; goldens require byte-identical console, audio hash and instruction count |
| differential evidence against silicon | JTAG lock-step, console diffs, `hw/` |
| lock-step node mode for Cooja-NG: NDJSON `hello`/`step`/`stop` → `done`, ns times, `tx`/`rx`/`log`/`serial`/`radio`/`led` | `--cooja` (`docs/esp32c6.md`) |
| `AGENTS.md` | GitHub PR-stack guidance only |

What does not exist: a JSON event stream, an expect/assert block, a scenario file, exit codes
by class, a run directory, `capabilities`, a seed (the emulator is unseedable), packaging that
finds the mask ROM for a fresh agent, and an escalation workflow in `AGENTS.md`.

The existing `--cooja` mode is a data-plane lock-step peer, not the agent control plane. Its
handshake currently accepts a seed for the session while the modeled RNG starts from a fixed
default. Until seed injection is implemented, report `seed: null` and document the fixed RNG
behavior; do not imply that the Cooja seed controls ESP32 randomness. `run_until_cycle` is
documented as single-core only (the S3's second core is not scheduled there), so conditions and
the session must hook into the normal scheduled run loop, which runs both cores and already
stops at script-event times; the cycle-exact path is for the lock-step peer. Capabilities state
this under `limitations.notes`.

## Design principles

- Keep the emulator core independent of any particular AI framework.
- CLI and structured output are first-class; MCP is an adapter, not the core protocol.
- Prefer deterministic simulated time and reproducible runs.
- Make capabilities discoverable rather than requiring large prompts.
- Treat evidence and diagnostics as first-class outputs.
- Never encourage guest-firmware workarounds for behavior that contradicts real ESP32 hardware.
- Preserve and expand differential verification against real silicon.
- Reuse `--script`, the observers and the existing output flags. Add a scenario wrapper, a JSON exporter and a result, not a second machine.

## Phase 0 — Onboarding for a fresh agent

A fresh agent hits the mask ROM dependency before anything else. This is a prerequisite, not
priority 5:

- `esp32sim` reports a missing ROM as `configuration_error` (exit 2) with the path it looked
  for and the `ESP32SIM_ROM_DIR` hint, on the first command, never mid-run.
- An install path that works without ESP-IDF present: `cargo install` plus a documented
  `esp32sim fetch-rom` (the ELFs come from espressif/esp-rom-elfs, as CI already fetches them).
- `esp32sim capabilities --json` must succeed with no firmware and no ROM.

## Phase 1 — Structured output on the existing CLI

- `--run-dir DIR`: a run directory holding `events.ndjson`, `result.json`,
  `scenario.replay.yaml`, `console.log` and whichever of VCD, trace, coverage, regstat were
  requested. Events are never interleaved with the console on stdout; stdout stays the console.
- `events.ndjson`: console lines, GPIO edges, exceptions, unimplemented register accesses, stub
  hits, script actions and the end-of-run figures, `t` in ns (the bus cycle counter, as
  `--cooja` already stamps), `node: 1` on every event. Event names shared with the lock-step
  protocol (`log`, `serial`, `radio`, `led`) plus `gpio`, `exception`, `unimplemented_access`,
  `stub`.
- `result.json` with `termination_reason` and `verdict`; artifact paths relative to the run
  directory. Wall time, commit and run directory are the fields a golden strips.
- Exit codes from the shared table in `SPEC.md`: 0 pass, 1 assertion, 2 configuration,
  3 unsupported, 4 simulator error, 5 guest failure, 6 timeout, 7 cancelled.
- `--wall-timeout S` next to `--max-seconds`.

In `--cooja` mode stdin and stdout belong to csim; the control plane is refused there and
diagnostics go to the run directory or through the lock-step reply (Cooja-NG plan, Phase 10).

## Phase 2 — Scenario file, expect and invariants

A YAML scenario wraps what the command line and `--script` already express and adds `expect`
(sequential) and `invariants` (run-wide). The action lines keep their existing names; the file is
converted to the same `Script` events.

```yaml
chip: esp32s3
board: atech14
firmware: build/app.bin          # or bootloader/ptable/app, or flash-image
elf: build/app.elf
max_seconds: 5

actions:
  - { at_ms: 1000, gpio: { pin: 4, value: 0 } }
  - { at_ms: 1500, press: { button: btn1, ms: 150 } }

expect:
  - log_contains: { text: "button pressed" }
  - gpio_level:   { pin: 5, value: 1, within_ms: 200 }
invariants:
  - no_event: { type: exception }
  - no_event: { type: unimplemented_access }
```

Conditions are the shared closed set with the evaluation windows in `SPEC.md`: each `expect`
entry's window starts where the previous one was reached; `invariants` run from reset and a hit
ends the run at once. Add `probe_reached` (function entry, via the `--trace-fn` / `--stub`
mechanism) and `memory_value` (the `--watch` mechanism) as esp32sim-specific conditions.

The condition observer lives in the scheduled run loop, next to where script events already
stop the run at their times, so both S3 cores run. A failed `expect` is `assertion_failed` with
expected, observed and the artifact paths. Every run also writes `scenario.replay.yaml`, which
`run` accepts back.

There is no `seed` field. esp32sim is deterministic and unseedable; the result reports
`seed: null`, `deterministic: true`, and `deterministic: false` when `--net nat` or `--realtime`
is in effect.

```text
esp32sim run scenario.yaml --run-dir out/
```

## Phase 3 — Capability discovery

```text
esp32sim capabilities --json
esp32sim describe gpio.set --json
```

Report, with JSON Schemas: chips and boards, actions (the `--script` verbs plus `flash-at`,
`stub`), observation types, `observables` for `observe`, conditions, the scenario schema, output
artifacts, `determinism` (`deterministic: true, seedable: false, breaks_with: [--net nat,
--realtime]`), `nestable: true`, and `limitations` per chip: the "Not there yet" lists from
`docs/esp32c3.md` and `docs/esp32c6.md` made machine-readable, the single-core note on the
cycle-exact path, plus the stubs the current invocation has active. `describe <name>` returns
one entry.

Honour the seed csim sends in the lock-step `hello` for the model's xorshift (today it is
parsed and logged only), so a nested run reports the experiment seed instead of `seed: null`.
The `cooja-*.ndjson` goldens are updated with it.

Limitations are what keep an agent from filing a firmware bug against a watchdog that never
fires or a baseband calibration that is stubbed.

## Phase 4 — Diagnostics and evidence

The artifacts exist as flags. The delta is bundling and structure:

- `result.json` on every run: verdict, chip, board, firmware and ELF hashes, esp32sim version
  and commit, instruction count, simulation time, active stubs, unimplemented accesses seen,
  last PC and exception cause on a guest failure, artifact paths.
- On failure, the run directory also gets the last N console lines, the unimplemented-access
  list with PCs and symbols, and the register state of each core.
- `esp32sim diagnose <run_dir>`: facts (from `result.json` and the traces) and labelled
  hypotheses, never a heuristic presented as a verdict.
- `esp32sim bundle <run_dir>`: a tar with a replay command line, for an issue or a PR.

## Phase 5 — Simulator-bug escalation workflow

Extend `AGENTS.md` (today only PR stacks) with what an agent does when firmware appears correct
but simulation differs from expected hardware semantics:

1. Check `capabilities.limitations` and the active stubs first. A stub or an unmodelled block is
   a declared limitation, not a bug in either the firmware or the emulator.
2. Do not modify guest firmware merely to work around suspected emulator behavior.
3. Minimize the reproducer.
4. Record chip, board, firmware and toolchain version, esp32sim commit, the scenario, expected
   and observed behavior (`result.json` and `bundle` carry all of it).
5. Prefer evidence from real hardware, reference traces, the specification, `--no-jit` as the
   JIT oracle, or the existing differential tests.
6. Add a regression that fails before the fix: a golden, a semantics case, or a device test,
   following `tests/README.md`.
7. Fix the emulator only when evidence supports the diagnosis.
8. Run `cargo test --release --workspace -- --include-ignored --skip external_`.
9. Open a focused PR with the regression, fix, evidence and root cause, subject to the host's
   permission policy.
10. Resume the original firmware task after validating the fix.

## Phase 6 — Agent demonstration

A small deliberately broken ESP-IDF project under `examples/` demonstrating autonomous repair:

```text
agent receives broken firmware
→ builds it
→ esp32sim run fails (exit 1, result.json, events.ndjson)
→ agent reads the evidence
→ agent edits firmware
→ rebuilds
→ tests pass
```

A second demo exposes a known emulator defect and shows:

```text
failure → limitations checked → minimal repro → regression → esp32sim fix → PR-ready change → original task resumes
```

Acceptance test for the whole plan: a fresh agent, given only `capabilities --json` and the
broken project, completes the first demo with no simulator-specific prompt. The agent harness
and model are pinned and named in the demo's README so the loop metrics are comparable across
protocol changes.

## Phase 7 — Protocol adapters

Once `test` and `--json` are stable:

- the streaming session of the Agent Simulation Protocol (`hello`, `run_until`, `action`,
  `observe`, `cancel`) on stdin/stdout, driving the scheduled run loop (both cores), with the
  `--cooja` loop as the shape of the request/reply cycle
- the per-action MCP tools generated from `capabilities` (the batch-shaped adapter needs no
  session and comes earlier)
- a small Python client
- shell and CI usage stay fully supported without MCP

## Priorities

esp32sim follows Cooja-NG on the shared protocol work (`ROADMAP.md` §2) and implements against
recorded Cooja-NG vectors. Phase 0 and the demo are esp32sim-only and run whenever there is
capacity.

1. ROM discovery and error, install path (Phase 0)
2. run directory, `events.ndjson`, `result.json`, exit codes (Phase 1)
3. scenario file with `expect` and `invariants`, replay file (Phase 2)
4. `result.json` with stubs and unimplemented accesses; `capabilities` with limitations (Phases 3, 4)
5. `AGENTS.md` escalation workflow (Phase 5)
6. broken-firmware demo and acceptance test (Phase 6)
7. `diagnose`, `bundle`
8. protocol session, MCP, Python (Phase 7)
9. new peripherals and boards driven by concrete workloads
10. performance driven by measured bottlenecks

## Success criteria

esp32sim is agent-ready when a fresh coding agent, given only `capabilities --json`, can:

- install it and find the ROM,
- run unmodified ESP32 firmware,
- stimulate the virtual hardware from a scenario file,
- assert observable behavior,
- diagnose failures from `result.json` and `events.ndjson`,
- distinguish declared limitations from likely bugs,
- produce a minimal simulator regression when appropriate,
- and complete a firmware repair loop without physical hardware.
