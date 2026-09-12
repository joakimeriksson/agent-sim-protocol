# Agent Simulation Protocol

> **Strawman, v0.3.** This protocol will change without notice. Do not implement it outside the
> two reference simulators yet. Nothing here is stable until it exists in both
> [esp32sim](https://github.com/joakimeriksson/esp32sim) and
> [Cooja-NG](https://github.com/joakimeriksson/cooja-ng).

A small simulator-neutral protocol for coding and research agents operating executable
simulation environments: capability discovery, actions, observations, `run_until`, evidence and
diagnostics, over NDJSON and a batch CLI.

| document | what |
| --- | --- |
| [SPEC.md](SPEC.md) | the protocol |
| [AGENTS.md](AGENTS.md) | rules for coding agents working on this repo |
| [ROADMAP.md](ROADMAP.md) | the goal, where the spec lives, and the six milestones to two conforming simulators |
| [ESP32SIM_AGENT_PLAN.md](ESP32SIM_AGENT_PLAN.md) | esp32sim plan, as a delta against the emulator (to move to `esp32sim/docs/agent-plan.md`) |
| [COOJA_NG_AGENT_PLAN.md](COOJA_NG_AGENT_PLAN.md) | Cooja-NG plan, as a delta against csim (to move to `csim/docs/design/agent-plan.md`) |

| [schema/](schema/) | JSON Schemas for the envelope, capabilities, conditions, result.json, events.ndjson and scenario.replay.yaml (provisional) |
| [conformance/check.py](conformance/check.py) | the checker a simulator's CI runs on its own output; `conformance/vectors/` holds the vectors |
| [clients/python/agentsim](clients/python/agentsim/__init__.py) | minimal batch client: `capabilities`, `run`, read a run directory |
| [examples/](examples/) | one scenario per simulator in the shared spelling |

```sh
uv sync --group dev
uv run python conformance/check.py vectors          # every vector passes, every negative trips its rule
uv run python conformance/check.py run-dir out/x    # a simulator's run directory
uv run pytest -q
```

The spec records what the implementations do; it does not lead them. Every vector today is
hand-written and says so in its `meta.json`; the first recorded Cooja-NG run replaces its vector.
