"""The run-directory to web-UI replay converter, against the recorded Cooja-NG chain run."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import rundir2ui  # noqa: E402

VEC = Path(__file__).resolve().parents[1] / "conformance" / "vectors" / "cooja-ng" / "m1-chain-4node-sky"


def test_converts_recorded_chain_run():
    doc = rundir2ui.convert(VEC, 100)
    assert doc["format"] == "cooja-ng-ui-replay/1"
    full, deltas = doc["full"], doc["deltas"]
    assert full["type"] == "full" and [n["id"] for n in full["nodes"]] == [1, 2, 3, 4]
    assert full["radio"]["tx_range"] == 55.0
    assert full["radio"]["neighbors"] == [[1], [0, 2], [1, 3], [2]]  # a chain 50 m apart, 55 m range
    assert deltas and all("0" in d for d in deltas)
    times = [d["0"] for d in deltas]
    assert times == sorted(times) and len(set(times)) == len(times)
    events = [json.loads(l) for l in (VEC / "events.ndjson").read_text().splitlines() if l.strip()]
    n_log = sum(1 for e in events if e["type"] == "log")
    n_tx = sum(1 for e in events if e["type"] == "tx")
    assert sum(len(v) for d in deltas for v in d.get("5", {}).values()) == n_log
    frames = [e for d in deltas for e in d.get("6", []) if e[2] == rundir2ui.TL["frame"]]
    assert len(frames) == n_tx and all(e[3] == 1 and isinstance(e[4], str) for e in frames)
    assert all(e[2] in range(9) for d in deltas for e in d.get("6", []))
    assert deltas[-1]["1"][5] is True  # the replay ends paused


def test_frame_summary_decodes_contiki_long_addresses():
    # DATA, PAN compressed, long dst + long src, Contiki-NG Sky style addresses
    fcf = (1 | (1 << 6) | (3 << 10) | (3 << 14)).to_bytes(2, "little")
    dst = bytes.fromhex("0012740400040404")[::-1]
    src = bytes.fromhex("0012740100010101")[::-1]
    frame = fcf + b"\x07" + b"\xcd\xab" + dst + src + b"\x00" * 10
    s = rundir2ui.frame_summary(frame.hex(), len(frame), 26)
    assert s.startswith("DATA N1 -> N4 seq 7")
    bcast = fcf[:1] + bytes([fcf[1] & ~0x0C | 0x08]) + b"\x08" + b"\xcd\xab" + b"\xff\xff" + src + b"\x00" * 4
    assert "-> bcast" in rundir2ui.frame_summary(bcast.hex(), len(bcast), 26)
