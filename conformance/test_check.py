"""The checker against its own vectors: every recorded or hand-written vector passes,
every negative vector trips exactly the rule it names."""
from pathlib import Path
import json
import shutil

import pytest
import yaml

import check

VECTORS = Path(__file__).parent / "vectors"
POSITIVE = sorted(p for d in VECTORS.iterdir() if d.is_dir() and d.name != "negative" for p in d.iterdir() if p.is_dir())
NEGATIVE = sorted(p for p in (VECTORS / "negative").iterdir() if p.is_dir())


@pytest.mark.parametrize("vec", POSITIVE, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_positive_vector_passes(vec):
    rep = check.Report(vec.name)
    check.check_run_dir(vec, rep)
    assert rep.ok, rep.errors


@pytest.mark.parametrize("vec", NEGATIVE, ids=lambda p: p.name)
def test_negative_vector_trips_named_rule(vec):
    meta = check._read(vec / "meta.json", check.Report("meta"))
    rep = check.Report(meta["file"])
    check._dispatch(vec / meta["file"], rep)
    assert meta["expect"] in rep.rules(), (meta["expect"], rep.errors)


def test_vectors_command_passes():
    reports = check.check_vectors(VECTORS)
    assert reports, "no vectors found"
    assert all(r.ok for r in reports), [(r.name, r.errors) for r in reports if not r.ok]


def test_schemas_are_valid_json_schema():
    from jsonschema import Draft202012Validator
    for name, schema in check._SCHEMAS.items():
        Draft202012Validator.check_schema(schema)


def test_run_dir_replay_identity_must_match_result(tmp_path):
    source = VECTORS / "cooja-ng" / "m1-chain-4node-sky"
    run_dir = tmp_path / "run"
    shutil.copytree(source, run_dir)
    replay_path = run_dir / "scenario.replay.yaml"
    replay = check._read(replay_path, check.Report("read"))
    replay["seed"] += 1
    replay_path.write_text(yaml.safe_dump(replay, sort_keys=False), encoding="utf-8")
    rep = check.Report("run")
    check.check_run_dir(run_dir, rep)
    assert "D5" in rep.rules()


def test_run_dir_action_event_must_match_replay(tmp_path):
    source = VECTORS / "cooja-ng" / "m1-chain-4node-sky"
    run_dir = tmp_path / "run"
    shutil.copytree(source, run_dir)

    replay_path = run_dir / "scenario.replay.yaml"
    replay = check._read(replay_path, check.Report("read"))
    replay["actions"].append({"action_seq": 0, "t": 180_000_000_000, "name": "move", "node": 1,
                              "args": {"x": 1.0, "y": 0.0}})
    replay_path.write_text(yaml.safe_dump(replay, sort_keys=False), encoding="utf-8")

    events_path = run_dir / "events.ndjson"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    events.append({"type": "action", "t": 180_000_000_000, "node": 1,
                   "seq": events[-1]["seq"] + 1, "action_seq": 0, "name": "move",
                   "args": {"x": 2.0, "y": 0.0}})
    events_path.write_text("".join(json.dumps(event, separators=(",", ":")) + "\n" for event in events),
                           encoding="utf-8")

    rep = check.Report("run")
    check.check_run_dir(run_dir, rep)
    assert "D4" in rep.rules()


def test_artifact_manifest_is_deterministic_and_hashed():
    run_dir = VECTORS / "esp32sim" / "m1-hello-s3"
    first_rep = check.Report("first")
    second_rep = check.Report("second")
    first = check.artifact_manifest(run_dir, first_rep)
    second = check.artifact_manifest(run_dir, second_rep)
    assert first_rep.ok and second_rep.ok
    assert first == second
    assert first["format"] == "agent-sim-artifacts/1"
    assert all(len(entry["sha256"]) == 64 and entry["bytes"] >= 0 for entry in first["artifacts"])
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
