#!/usr/bin/env python3
"""Fold an agent-sim run directory into a Cooja-NG web-UI replay file.

    python3 tools/rundir2ui.py RUN_DIR -o ui-replay.json [--interval-ms 100]

The output is the web UI's own wire protocol as one JSON document, so the page in Cooja-NG's
`ui/index.html` can play it from a static file (`index.html?replay=ui-replay.json`) with no
simulator and no server:

    { "format": "cooja-ng-ui-replay/1",
      "run":    { simulator, version, commit, seed, verdict, scenario, simulation_time_ns },
      "full":   <the `full` state message at t = 0>,
      "deltas": [ <one `delta` per interval that had events, in the CBOR key layout>, ... ] }

A delta uses the numeric keys the page's `handleCBORDelta` reads, as strings:
  "0" sim_time_ms, "1" stats [rf_bytes, uart_bytes, rx_queued, rx_collided, speed_x10, paused],
  "2" {node: radio_enum}, "3" {node: [r,g,b]}, "4" {node: last_tx_ms},
  "5" {node: [console lines]}, "6" [[t_us, node, tl_type, value, summary?], ...]
with radio_enum off=0 on=1 tx=2 rx=3 intf=4 and tl_type off,on,tx,rx,intf,led_on,led_off,frame,log = 0..8.

Inputs are `result.json`, `events.ndjson` and `scenario.replay.yaml` (positions, mote types,
medium) from the run directory. Only standard library plus PyYAML.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import yaml

RADIO_ENUM = {"off": 0, "on": 1, "tx": 2, "rx": 3, "intf": 4}
TL = {"off": 0, "on": 1, "tx": 2, "rx": 3, "intf": 4, "led_on": 5, "led_off": 6, "frame": 7, "log": 8}


def _addr(b: bytes, mode: int) -> str:
    """Render an 802.15.4 address the way the page's packet log expects: N<id>, bcast, or 4 hex."""
    if mode == 2:
        v = int.from_bytes(b, "little")
        return "bcast" if v == 0xFFFF else f"{v:04X}"
    if mode == 3:
        le = b[::-1]  # on-air little-endian -> canonical order
        # Contiki-NG's Cooja/Sky addressing: 00:12:74:xx:00:xx:xx:xx with the node id in the last byte
        if le[0:3] == b"\x00\x12\x74" and le[3] == le[7] and le[5] == le[7]:
            return f"N{le[7]}"
        return le[-2:].hex().upper()
    return ""


def frame_summary(hexframe: str, length: int, ch: int) -> str:
    """A one-line summary of a MAC frame: type, src -> dst, length, channel.  Best effort."""
    try:
        f = bytes.fromhex(hexframe)
        fcf = int.from_bytes(f[0:2], "little")
        ftype = fcf & 7
        pan_comp = (fcf >> 6) & 1
        dmode = (fcf >> 10) & 3
        smode = (fcf >> 14) & 3
        seq = f[2]
        i = 3
        dst = src = ""
        if dmode:
            i += 2  # dst PAN
            n = 2 if dmode == 2 else 8
            dst = _addr(f[i:i + n], dmode); i += n
        if smode:
            if not pan_comp:
                i += 2
            n = 2 if smode == 2 else 8
            src = _addr(f[i:i + n], smode); i += n
        name = {0: "BEACON", 1: "DATA", 2: "ACK", 3: "CMD"}.get(ftype, f"T{ftype}")
        if ftype == 2:
            return f"ACK seq {seq} len {length} ch {ch}"
        return f"{name} {src or '?'} -> {dst or '?'} seq {seq} len {length} ch {ch}"
    except (ValueError, IndexError):
        return f"frame len {length} ch {ch}"


def load_run(run_dir: Path):
    result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    arts = result.get("artifacts", {})
    replay = yaml.safe_load((run_dir / arts.get("replay", "scenario.replay.yaml")).read_text(encoding="utf-8"))
    events = []
    with open(run_dir / arts.get("events", "events.ndjson"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return result, replay, events


def build_full(result, replay, events):
    cfg = replay.get("config", {}) or {}
    types = {m.get("name"): m for m in cfg.get("mote_types", []) or []}
    nodes = []
    for n in cfg.get("nodes", []) or []:
        mt = types.get(n.get("type"), {})
        label = mt.get("board") or mt.get("cpu") or n.get("type") or Path(n.get("firmware", "node")).suffix.lstrip(".") or "node"
        nodes.append({"id": n["id"], "type": str(label), "x": float(n.get("x", 0.0)), "y": float(n.get("y", 0.0)),
                      "cycles": 0, "freq": 0, "last_tx_ms": 0, "console": [], "radio": "off", "leds": [0, 0, 0]})
    # nodes that only appear in the event stream (added at runtime)
    known = {n["id"] for n in nodes}
    for ev in events:
        if ev["node"] >= 1 and ev["node"] not in known:
            nodes.append({"id": ev["node"], "type": "node", "x": 0.0, "y": 0.0, "cycles": 0, "freq": 0,
                          "last_tx_ms": 0, "console": [], "radio": "off", "leds": [0, 0, 0]})
            known.add(ev["node"])
    nodes.sort(key=lambda n: n["id"])
    medium = cfg.get("medium") or cfg.get("radiomedium") or {}
    tx_range = float(medium.get("tx_range", 50.0))
    neighbors = []
    for a in nodes:
        row = []
        for j, b in enumerate(nodes):
            if a is not b and math.hypot(a["x"] - b["x"], a["y"] - b["y"]) <= tx_range:
                row.append(j)
        neighbors.append(row)
    return {"type": "full", "sim_time_ms": 0, "nodes": nodes,
            "radio": {"type": str(medium.get("type", "udgm")), "tx_range": tx_range, "neighbors": neighbors},
            "stats": {"rf_bytes": 0, "uart_bytes": 0, "rx_frames_queued": 0, "rx_frames_collided": 0,
                      "speed": 1.0, "paused": False},
            "timeline": []}


def build_deltas(events, interval_ms: int):
    interval_ns = interval_ms * 1_000_000
    deltas = []
    stats = {"rf": 0, "uart": 0, "q": 0, "c": 0}
    leds = {}
    cur = None  # (bucket index, delta)

    def flush():
        if cur is not None:
            deltas.append(cur[1])

    for ev in events:
        b = ev["t"] // interval_ns
        if cur is None or cur[0] != b:
            flush()
            cur = (b, {"0": int((b + 1) * interval_ms), "1": None, "2": {}, "3": {}, "4": {}, "5": {}, "6": []})
        d = cur[1]
        node = ev["node"]
        t_us = ev["t"] // 1000
        kind = ev["type"]
        if kind == "radio":
            st = ev.get("state", "off")
            d["2"][str(node)] = RADIO_ENUM.get(st, 0)
            d["6"].append([t_us, node, TL.get(st, 0), 0])
        elif kind == "led":
            new = [int(bool(v)) for v in ev.get("leds", [])][:3] + [0] * max(0, 3 - len(ev.get("leds", [])))
            old = leds.get(node, [0, 0, 0])
            for i in range(3):
                if new[i] != old[i]:
                    d["6"].append([t_us, node, TL["led_on"] if new[i] else TL["led_off"], i])
            leds[node] = new
            d["3"][str(node)] = new
        elif kind in ("tx", "rx"):
            length = int(ev.get("len", 0))
            stats["rf"] += length
            stats["q"] += 1  # the header's frame counter: every frame seen on the air
            summary = frame_summary(ev.get("frame", ""), length, int(ev.get("ch", 0)))
            if kind == "rx" and ev.get("from"):
                summary = summary.replace(" ? ->", f" N{ev['from']} ->")
            d["6"].append([t_us, node, TL["frame"], 1 if kind == "tx" else 0, summary])
            if kind == "tx":
                d["4"][str(node)] = t_us // 1000
        elif kind == "interference":
            stats["c"] += 1
            d["6"].append([t_us, node, TL["intf"], 0])
        elif kind == "log":
            line = ev.get("line", "")
            stats["uart"] += len(line) + 1
            d["5"].setdefault(str(node), []).append(line)
            d["6"].append([t_us, node, TL["log"], 0, line])
        # mote_added / mote_removed / action: no UI representation yet
        d["1"] = [stats["rf"], stats["uart"], stats["q"], stats["c"], 10, False]
    flush()
    for d in deltas:  # drop empty maps so the file stays small
        for k in ("2", "3", "4", "5"):
            if not d[k]:
                del d[k]
        if not d["6"]:
            del d["6"]
    return deltas


def convert(run_dir: Path, interval_ms: int = 100) -> dict:
    result, replay, events = load_run(run_dir)
    full = build_full(result, replay, events)
    deltas = build_deltas(events, interval_ms)
    if deltas:
        last = deltas[-1]
        last["1"] = (last.get("1") or [0, 0, 0, 0, 10, False])[:5] + [True]  # ends paused
    cfg = replay.get("config", {}) or {}
    return {"format": "cooja-ng-ui-replay/1",
            "run": {"simulator": result.get("simulator"), "version": result.get("version"), "commit": result.get("commit"),
                    "seed": result.get("seed"), "verdict": result.get("verdict"),
                    "termination_reason": result.get("termination_reason"),
                    "scenario": cfg.get("title"), "simulation_time_ns": result.get("simulation_time_ns"),
                    "interval_ms": interval_ms, "source": str(run_dir)},
            "full": full, "deltas": deltas}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("-o", "--output", type=Path, help="default: <run_dir>/ui-replay.json")
    ap.add_argument("--interval-ms", type=int, default=100, help="delta interval in simulation ms (default 100)")
    args = ap.parse_args(argv)
    if not (args.run_dir / "result.json").exists():
        print(f"{args.run_dir}: no result.json", file=sys.stderr)
        return 2
    doc = convert(args.run_dir, args.interval_ms)
    out = args.output or (args.run_dir / "ui-replay.json")
    out.write_text(json.dumps(doc, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{out}: {len(doc['full']['nodes'])} nodes, {len(doc['deltas'])} deltas, {out.stat().st_size // 1024} KiB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
