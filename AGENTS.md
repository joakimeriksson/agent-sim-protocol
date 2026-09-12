# AGENTS.md — agent-sim-protocol

This is a specification repo. Read `ROADMAP.md` §1 before changing anything.

- **The spec follows the implementations.** Nothing enters `SPEC.md` or `schema/` until it exists
  in esp32sim or Cooja-NG (csim). Nothing is marked stable until it exists in both; until then it
  is `provisional`.
- **A spec change is two PRs:** one here, one linked PR in the first simulator.
- **Versioning:** `agent-sim/0.x` in `SPEC.md`, echoed by `hello` and `capabilities`.
  `conformance/check.py` pins a schema version. Bump the minor version when a schema changes
  shape; do not edit a released schema in place.
- **One name per concept:** see the Vocabulary section of `SPEC.md`. `run_until`, `expect`,
  `invariants`, `assertion_failed`, `run`. Do not introduce synonyms.
- **The Python client and MCP adapter are consumers of the spec,** never its definition. When
  they disagree with `SPEC.md`, the client is wrong or the spec needs a recorded vector.
- **Vectors** under `conformance/vectors/` are recorded from real simulator runs. A hand-written
  vector is allowed only as the intended shape before a simulator emits it, must say
  `"source": "hand-written"` in its `meta.json`, is never evidence for the Status table in
  `SPEC.md`, and is replaced by the first recorded run. Negative vectors are hand-written by
  nature.
- **Status table.** A concept in `SPEC.md` moves from none to provisional when a recorded vector
  from one simulator shows it, and to stable when both do. Update the table in the same PR as
  the vector.
