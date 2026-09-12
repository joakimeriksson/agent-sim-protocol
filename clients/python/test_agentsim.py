"""The client against the recorded vectors (no simulator needed)."""
import sys
from pathlib import Path

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
