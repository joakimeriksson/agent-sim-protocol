# Conformance vectors

One directory per vector, laid out like a run directory: `result.json`, `events.ndjson`,
`scenario.replay.yaml`, `capabilities.json`, plus `meta.json` saying where it came from.

`meta.json.source` is `hand-written` or `recorded`. A hand-written vector shows what M1 output
is intended to look like and is **not evidence** that a simulator emits it; the checker warns on
every one. The first real run of a simulator replaces its hand-written vector with a recorded
one, and from then on a disagreement is settled by changing the schema or the simulator, never
by loosening the checker.

`negative/` holds files that must fail, each with `meta.json` naming the file and the rule id it
must trip (`E1`, `R1`, …, or `S-RES` for a schema violation in result.json).
