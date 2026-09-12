# Agent Simulation Protocol

> **Strawman, v0.2.** This protocol will change without notice. Do not implement it outside the
> two reference simulators yet. Nothing here is stable until it exists in both
> [esp32sim](https://github.com/joakimeriksson/esp32sim) and
> [Cooja-NG](https://github.com/joakimeriksson/cooja-ng).

A small simulator-neutral protocol for coding and research agents operating executable
simulation environments: capability discovery, actions, observations, `run_until`, evidence and
diagnostics, over NDJSON and a batch CLI.

| document | what |
| --- | --- |
| [AGENT_SIM_PROTOCOL.md](AGENT_SIM_PROTOCOL.md) | the protocol |
| [ROADMAP.md](ROADMAP.md) | the goal, where the spec lives, and the six milestones to two conforming simulators |
| [ESP32SIM_AGENT_PLAN.md](ESP32SIM_AGENT_PLAN.md) | esp32sim plan, as a delta against the emulator (to move to `esp32sim/docs/agent-plan.md`) |
| [COOJA_NG_AGENT_PLAN.md](COOJA_NG_AGENT_PLAN.md) | Cooja-NG plan, as a delta against csim (to move to `csim/docs/design/agent-plan.md`) |

The spec records what the implementations do; it does not lead them.
