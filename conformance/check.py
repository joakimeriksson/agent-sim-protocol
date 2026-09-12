#!/usr/bin/env python3
"""Conformance checker for the Agent Simulation Protocol (agent-sim/0.3, provisional).

    check.py capabilities FILE        validate a capabilities reply
    check.py result FILE              validate a result.json
    check.py events FILE              validate an events.ndjson
    check.py replay FILE              validate a scenario.replay.yaml
    check.py run-dir DIR              all of the above for one run directory, plus the cross-file rules
    check.py vectors [ROOT]           every recorded vector under conformance/vectors must pass,
                                      every negative vector must fail with the rule it names

Exit code 0 when everything passes, 1 on any violation, 2 on usage or unreadable input.
Rules that a schema cannot express are numbered (E1, R1, ...) so a negative vector can name
the one it expects to trip.  Warnings (W*) do not fail a check.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

HERE = Path(__file__).resolve().parent
SCHEMA_DIR = HERE.parent / "schema"
SCHEMAS = ["envelope", "capabilities", "conditions", "result", "events", "replay"]

# exit code expected for each termination_reason; None means "depends on the verdict"
EXIT_FOR_REASON = {
    "completed": None,
    "assertion_failed": 1,
    "timeout_wall": 6,
    "cancelled": 7,
    "guest_failure": 5,
    "peer_disconnect": 4,
    "simulator_error": 4,
}


@dataclass
class Report:
    name: str
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def error(self, rule: str, msg: str) -> None:
        self.errors.append((rule, msg))

    def warn(self, rule: str, msg: str) -> None:
        self.warnings.append((rule, msg))

    @property
    def ok(self) -> bool:
        return not self.errors

    def rules(self) -> set:
        return {r for r, _ in self.errors}

    def print(self, out=sys.stdout) -> None:
        status = "ok" if self.ok else "FAIL"
        print(f"{status:4} {self.name}", file=out)
        for rule, msg in self.errors:
            print(f"     {rule}: {msg}", file=out)
        for rule, msg in self.warnings:
            print(f"     {rule} (warning): {msg}", file=out)


# ---------------------------------------------------------------- schemas

def _load_schemas() -> dict:
    schemas = {}
    for name in SCHEMAS:
        with open(SCHEMA_DIR / f"{name}.json", encoding="utf-8") as f:
            schemas[name] = json.load(f)
    return schemas


_SCHEMAS = _load_schemas()
_REGISTRY = Registry().with_resources(
    (s["$id"], Resource.from_contents(s)) for s in _SCHEMAS.values()
)
_VALIDATORS = {name: Draft202012Validator(s, registry=_REGISTRY) for name, s in _SCHEMAS.items()}
KNOWN_EVENT_TYPES = set(_SCHEMAS["events"]["$defs"]["known_types"]["enum"])
KNOWN_CONDITIONS = set(_SCHEMAS["conditions"]["properties"].keys())


def _schema_errors(name: str, instance: Any, rep: Report, rule: str, where: str = "") -> bool:
    ok = True
    for err in sorted(_VALIDATORS[name].iter_errors(instance), key=lambda e: list(e.path)):
        path = "/".join(str(p) for p in err.absolute_path) or "."
        rep.error(rule, f"{where}{path}: {err.message}")
        ok = False
    return ok


def _read(path: Path, rep: Report) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        rep.error("IO", f"{path}: {e}")
        return None
    try:
        if path.suffix in (".yaml", ".yml"):
            return yaml.safe_load(text)
        return json.loads(text)
    except (ValueError, yaml.YAMLError) as e:
        rep.error("IO", f"{path}: not valid {'YAML' if path.suffix in ('.yaml', '.yml') else 'JSON'}: {e}")
        return None


# ---------------------------------------------------------------- single files

def check_capabilities(doc: Any, rep: Report) -> None:
    if not _schema_errors("capabilities", doc, rep, "S-CAP"):
        return
    # C2: every action schema must itself be a valid JSON Schema
    for name, a in doc.get("actions", {}).items():
        try:
            Draft202012Validator.check_schema(a["schema"])
        except Exception as e:  # jsonschema.SchemaError
            rep.error("C2", f"actions.{name}.schema is not a valid JSON Schema: {getattr(e, 'message', e)}")
    # C3: advertised conditions outside the closed set are simulator-specific; note them
    extra = set(doc.get("conditions", [])) - KNOWN_CONDITIONS
    if extra:
        rep.warn("W-C3", f"simulator-specific conditions advertised: {sorted(extra)}")
    # C4: describe is needed for any advertised action to be self-describing
    if doc.get("actions") and "describe" not in doc.get("operations", []):
        rep.warn("W-C4", "actions advertised but describe is not an operation")


def check_result(doc: Any, rep: Report) -> None:
    if not _schema_errors("result", doc, rep, "S-RES"):
        return
    verdict, reason, code = doc["verdict"], doc["termination_reason"], doc["exit_code"]
    # R1: exit code follows termination_reason and verdict
    expected = EXIT_FOR_REASON[reason]
    if expected is None:
        expected = 0 if verdict == "pass" else 1
    if code != expected:
        rep.error("R1", f"exit_code {code} but termination_reason={reason}, verdict={verdict} requires {expected}")
    if reason == "completed" and verdict == "fail" and not any(
        not c["ok"] for c in doc.get("conditions", [])
    ):
        rep.error("R1", "verdict fail on a completed run with no failed condition and no error")
    if reason != "completed" and verdict == "pass":
        rep.error("R1", f"verdict pass with termination_reason={reason}")
    # R2: a failed condition is never a pass; a pass has no failed condition
    failed = [c for c in doc.get("conditions", []) if not c["ok"]]
    if failed and verdict == "pass":
        rep.error("R2", f"{len(failed)} condition(s) not ok but verdict is pass")
    # R6: an unavailable metric is inconclusive, not a pass
    if verdict == "pass" and any(m.get("value") is None for m in doc.get("metrics", {}).values()):
        rep.error("R6", "a metric has value null but verdict is pass (must be inconclusive)")
    # R7: conditions used must be in the closed set or warned as simulator-specific
    for i, c in enumerate(doc.get("conditions", [])):
        (name,) = c["condition"].keys()
        if name not in KNOWN_CONDITIONS:
            rep.warn("W-R7", f"conditions[{i}] uses simulator-specific condition {name!r}")
        if c["kind"] == "expect" and name == "no_event":
            rep.error("R8", f"conditions[{i}]: no_event in expect; it belongs in invariants")


def check_events(lines: Iterable[str], rep: Report) -> list:
    events = []
    last_t: dict = {}
    last_seq = -1
    for n, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except ValueError as e:
            rep.error("IO", f"line {n}: not JSON: {e}")
            continue
        if not _schema_errors("events", ev, rep, "S-EVT", where=f"line {n} "):
            continue
        events.append(ev)
        # E1: t non-decreasing per node
        node = ev["node"]
        if node in last_t and ev["t"] < last_t[node]:
            rep.error("E1", f"line {n}: t={ev['t']} goes backwards for node {node} (previous {last_t[node]})")
        last_t[node] = ev["t"]
        # E2: seq strictly increasing across the whole stream
        if ev["seq"] <= last_seq:
            rep.error("E2", f"line {n}: seq={ev['seq']} not greater than previous {last_seq}")
        last_seq = ev["seq"]
        # E3: unknown event type is allowed but noted
        if ev["type"] not in KNOWN_EVENT_TYPES:
            rep.warn("W-E3", f"line {n}: simulator-specific event type {ev['type']!r}")
    # E4: action_seq strictly increasing
    seqs = [ev["action_seq"] for ev in events if ev.get("type") == "action"]
    if any(b <= a for a, b in zip(seqs, seqs[1:])):
        rep.error("E4", f"action_seq not strictly increasing: {seqs}")
    return events


def check_replay(doc: Any, rep: Report) -> None:
    if not _schema_errors("replay", doc, rep, "S-RPL"):
        return
    acts = doc["actions"]
    # P1: action_seq strictly increasing, t non-decreasing
    seqs = [a["action_seq"] for a in acts]
    if any(b <= a for a, b in zip(seqs, seqs[1:])):
        rep.error("P1", f"actions.action_seq not strictly increasing: {seqs}")
    ts = [a["t"] for a in acts]
    if any(b < a for a, b in zip(ts, ts[1:])):
        rep.error("P1", f"actions.t goes backwards: {ts}")


# ---------------------------------------------------------------- run directory

def check_run_dir(run_dir: Path, rep: Report) -> None:
    result_path = run_dir / "result.json"
    if not result_path.exists():
        rep.error("D1", "result.json missing")
        return
    result = _read(result_path, rep)
    if result is None:
        return
    check_result(result, rep)
    if not rep.ok and any(r.startswith("S-") for r in rep.rules()):
        return

    # D2: every artifact path exists and stays inside run_dir
    for name, rel in result["artifacts"].items():
        p = (run_dir / rel)
        try:
            p.resolve().relative_to(run_dir.resolve())
        except ValueError:
            rep.error("D2", f"artifacts.{name} = {rel!r} escapes run_dir")
            continue
        if not p.exists():
            rep.error("D2", f"artifacts.{name} = {rel!r} does not exist")

    events_rel = result["artifacts"]["events"]
    replay_rel = result["artifacts"]["replay"]
    events = []
    if (run_dir / events_rel).exists():
        with open(run_dir / events_rel, encoding="utf-8") as f:
            events = check_events(f, rep)
    replay = _read(run_dir / replay_rel, rep) if (run_dir / replay_rel).exists() else None
    if replay is not None:
        check_replay(replay, rep)

    caps = None
    caps_path = run_dir / "capabilities.json"
    if caps_path.exists():
        caps = _read(caps_path, rep)
        if caps is not None:
            check_capabilities(caps, rep)

    # R5: one protocol version across the files of a run
    versions = {("result", result.get("protocol"))}
    if replay is not None:
        versions.add(("replay", replay.get("protocol")))
    if caps is not None:
        versions.add(("capabilities", caps.get("protocol")))
    if len({v for _, v in versions}) > 1:
        rep.error("R5", f"protocol versions differ across files: {sorted(versions)}")

    # D3: simulation_time_ns is not before the last event
    if events:
        last = max(ev["t"] for ev in events)
        if result["simulation_time_ns"] < last:
            rep.error("D3", f"simulation_time_ns={result['simulation_time_ns']} but an event is stamped {last}")

    # R9: a satisfied/hit condition points at an event that exists
    if events:
        seqs = {ev["seq"] for ev in events}
        for i, c in enumerate(result.get("conditions", [])):
            if c.get("seq") is not None and c["seq"] not in seqs:
                rep.error("R9", f"conditions[{i}].seq={c['seq']} is not an event in events.ndjson")

    # D4: every action in the replay appears as an action event, and vice versa
    if replay is not None:
        ev_seqs = sorted(ev["action_seq"] for ev in events if ev.get("type") == "action")
        rp_seqs = sorted(a["action_seq"] for a in replay["actions"])
        if ev_seqs != rp_seqs:
            rep.error("D4", f"action_seq differ: events {ev_seqs} vs replay {rp_seqs}")

    if caps is not None:
        det = caps["determinism"]
        # R4: seed is null exactly when the simulator is not seedable
        if not det["seedable"] and result["seed"] is not None:
            rep.error("R4", f"seed={result['seed']} but capabilities say seedable=false")
        if det["seedable"] and result["seed"] is None and result["deterministic"]:
            rep.error("R4", "seed null on a seedable, deterministic run")
        # C1: conditions and event types used must be advertised
        for i, c in enumerate(result.get("conditions", [])):
            (name,) = c["condition"].keys()
            if name not in caps["conditions"]:
                rep.error("C1", f"conditions[{i}] uses {name!r}, not in capabilities.conditions")
        used = {ev["type"] for ev in events}
        unadvertised = used - set(caps["observations"])
        if unadvertised:
            rep.error("C1", f"event types not in capabilities.observations: {sorted(unadvertised)}")
        if result["simulator"] != caps["simulator"]:
            rep.error("R5", f"simulator differs: result {result['simulator']!r}, capabilities {caps['simulator']!r}")


# ---------------------------------------------------------------- vectors

def check_vectors(root: Path) -> list:
    reports = []
    for sim_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for vec in sorted(p for p in sim_dir.iterdir() if p.is_dir()):
            meta = _read(vec / "meta.json", Report("meta")) if (vec / "meta.json").exists() else {}
            rep = Report(f"{sim_dir.name}/{vec.name}")
            if sim_dir.name == "negative":
                expect = (meta or {}).get("expect")
                target = (meta or {}).get("file")
                if not expect or not target:
                    rep.error("META", "negative vector needs meta.json with 'file' and 'expect'")
                else:
                    inner = Report(target)
                    _dispatch(vec / target, inner)
                    if expect not in inner.rules():
                        rep.error("NEG", f"expected rule {expect} to fail, got {sorted(inner.rules()) or 'nothing'}")
            else:
                if not meta or "source" not in meta:
                    rep.error("META", "vector needs meta.json with 'source' (hand-written | recorded)")
                check_run_dir(vec, rep)
                if meta and meta.get("source") == "hand-written":
                    rep.warn("W-META", "hand-written vector: not evidence that a simulator emits this")
            reports.append(rep)
    return reports


def _dispatch(path: Path, rep: Report) -> None:
    kind = path.name
    if kind == "capabilities.json":
        doc = _read(path, rep)
        if doc is not None:
            check_capabilities(doc, rep)
    elif kind == "result.json":
        doc = _read(path, rep)
        if doc is not None:
            check_result(doc, rep)
    elif kind.endswith(".ndjson"):
        with open(path, encoding="utf-8") as f:
            check_events(f, rep)
    elif kind.startswith("scenario.replay"):
        doc = _read(path, rep)
        if doc is not None:
            check_replay(doc, rep)
    else:
        rep.error("IO", f"do not know how to check {path.name}")


# ---------------------------------------------------------------- main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("capabilities", "result", "events", "replay"):
        sub.add_parser(c).add_argument("file", type=Path)
    sub.add_parser("run-dir").add_argument("dir", type=Path)
    sub.add_parser("vectors").add_argument("root", type=Path, nargs="?", default=HERE / "vectors")
    args = ap.parse_args(argv)

    if args.cmd == "vectors":
        if not args.root.is_dir():
            print(f"no such directory: {args.root}", file=sys.stderr)
            return 2
        reports = check_vectors(args.root)
        for r in reports:
            r.print()
        failed = [r for r in reports if not r.ok]
        print(f"{len(reports) - len(failed)}/{len(reports)} vectors ok")
        return 1 if failed else 0

    rep = Report(str(args.dir if args.cmd == "run-dir" else args.file))
    if args.cmd == "run-dir":
        if not args.dir.is_dir():
            print(f"no such directory: {args.dir}", file=sys.stderr)
            return 2
        check_run_dir(args.dir, rep)
    else:
        if not args.file.is_file():
            print(f"no such file: {args.file}", file=sys.stderr)
            return 2
        if args.cmd == "capabilities":
            doc = _read(args.file, rep)
            if doc is not None:
                check_capabilities(doc, rep)
        elif args.cmd == "result":
            doc = _read(args.file, rep)
            if doc is not None:
                check_result(doc, rep)
        elif args.cmd == "events":
            with open(args.file, encoding="utf-8") as f:
                check_events(f, rep)
        elif args.cmd == "replay":
            doc = _read(args.file, rep)
            if doc is not None:
                check_replay(doc, rep)
    rep.print()
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
