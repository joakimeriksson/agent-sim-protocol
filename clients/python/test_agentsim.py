"""The client against the recorded vectors (no simulator needed)."""
import sys
import json
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import agentsim  # noqa: E402

VECTORS = Path(__file__).resolve().parents[2] / "conformance" / "vectors"


def test_reads_cooja_vector():
    vec = VECTORS / "cooja-ng" / "m1-chain-4node-sky"
    r = agentsim.read_result(vec)
    assert r["verdict"] == "pass"
    evs = list(agentsim.iter_events(vec, r))
    assert evs and all("node" in e for e in evs)
    rp = agentsim.read_replay(vec, r)
    assert rp["seed"] == r["seed"]


def test_reads_esp32sim_vector():
    vec = VECTORS / "esp32sim" / "m1-hello-s3"
    r = agentsim.read_result(vec)
    assert r["seed"] is None and r["deterministic"] is True
    assert agentsim.failed_conditions(r) == []


def test_result_rejects_a_different_protocol(tmp_path):
    (tmp_path / "result.json").write_text(json.dumps({"protocol": "agent-sim/0.2"}), encoding="utf-8")
    with pytest.raises(agentsim.ProtocolError, match="implements 'agent-sim/0.3'"):
        agentsim.read_result(tmp_path)


def test_artifact_rejects_path_outside_run_dir(tmp_path):
    run = agentsim.RunResult(
        exit_code=0,
        run_dir=tmp_path,
        result={"artifacts": {"events": "../events.ndjson"}},
        stdout="",
        stderr="",
    )
    with pytest.raises(agentsim.ProtocolError, match="escapes run directory"):
        run.artifact("events")


def test_run_removes_stale_result(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "result.json").write_text('{"verdict": "pass"}')
    # a "simulator" that exits 2 and writes nothing
    r = agentsim.run(["sh", "-c", "exit 2"], "x.yaml", run_dir)
    assert r.exit_code == 2 and r.result is None
