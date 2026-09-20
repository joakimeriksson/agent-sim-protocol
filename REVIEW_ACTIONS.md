# Implementation review and action list

This review records the planning decisions that should guide the next implementation work. It is
deliberately separate from `SPEC.md`: these are recommendations and tooling findings, not protocol
claims. A recommendation moves into the spec only after a reference simulator emits it and a
recorded vector exists, as required by `AGENTS.md`.

## Recommended order

### 1. Record a real vertical slice first

The positive vectors are still hand-written. The next milestone should produce a recorded
Cooja-NG batch run, then an equivalent esp32sim run, including:

- a successful assertion run;
- an assertion failure with useful evidence;
- invalid configuration or unsupported operation;
- cancellation or wall-time termination with partial artifacts.

Replace the corresponding hand-written vectors and update the status table only from these runs.
This will settle the output shape more reliably than adding more provisional operations.

### 2. Move reliability prerequisites earlier than M7

The following are prerequisites for trustworthy CI and agent results and should be part of M1--M6:

- fresh run-directory identity and protection against stale `result.json` files;
- resource limits for wall time, event count, output bytes and simulator work, while retaining
  partial evidence;
- explicit handling of cancellation, disconnect and malformed session messages;
- artifact containment and integrity checks before any referenced file is opened;
- metric validity, unit and scope, including the difference between unavailable data and a zero;
- stable node and radio identities for remove/re-add and nested simulations.

The remaining M7 items (differential comparison, advanced subscriptions, and full human control
transfer) can stay later, but their acceptance cases should be written now.

### 3. Close the result and condition contracts before M2

The result schema has termination reasons for execution failures but no explicit result shape for
startup/configuration failures. Decide whether every failed invocation produces a result bundle and
make the exit code, verdict and termination reason a total, consistent mapping.

The condition rules also need executable examples for: the first event window, equal-time events,
deadline ties, cancellation with pending actions, and what happens after the final `expect`. The
current rule that metrics in an `expect` are evaluated at the end of the run, regardless of their
position, makes a metric followed by another expectation ambiguous. Restrict or define that case
before implementing M2.

Replay should distinguish an accepted action from an action that was actually applied. A scheduled
action that remains pending when a run is cancelled must be represented unambiguously, and actions
present in initial configuration must not be replayed twice.

### 4. Design human, CI and agent use around one action path

Add three acceptance workflows to the simulator plans:

1. a human configures and manipulates a run, then exports a reproducible scenario;
2. CI runs that scenario with bounded resources and archives evidence on failure;
3. an agent reads the same evidence and changes the scenario through the same validated action
   interface.

Human control can remain batch-first. The important requirement now is that GUI mutations use the
same validation and recording path as agent actions, so a human-produced run is reproducible.

### 5. Strengthen evaluation quality

Keep per-seed results and definitions for every metric. Treat five seeds as a smoke test, not as a
general research conclusion; use held-out seeds for experiments where an agent optimizes a
scenario. Measure both iterations-to-pass and correctness against protected acceptance tests, so
weakening an assertion cannot look like progress.

## Tooling findings to fix

The current test suite passes (`28 passed`), but two gaps are not covered:

- the checker accepts `agent-sim/0.999` even though the repository describes a pinned v0.3 schema;
- the Python batch client permits reuse of a run directory, so a failed invocation can return a
  nonzero process code alongside an old successful verdict.

Add negative vectors and client tests for both cases. Also make the checker stop shape-dependent
cross-file checks after a malformed result, replay or artifact path; validation should report the
input error rather than crash or read an escaped/symlinked file.

## Definition of done for the next review

The next review should be able to point to recorded vectors from both simulators, a fresh-run
policy, explicit startup and cancellation outcomes, replay equivalence tests, and one human-to-CI
exported scenario. Until then, the affected concepts should remain provisional.
