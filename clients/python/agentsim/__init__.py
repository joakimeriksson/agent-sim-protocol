"""agentsim: a minimal batch client for the Agent Simulation Protocol (agent-sim/0.3, provisional).

Only the batch form exists yet: run a scenario through a simulator's `run` verb and read the
run directory back. The streaming session (hello / run_until / action) arrives with M6.

    import agentsim
    caps = agentsim.capabilities(["cooja-ng"])
    r = agentsim.run(["cooja-ng"], "experiment.yaml", run_dir="out/exp1")
    r.exit_code, r.result["verdict"], list(r.events())
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Optional, Sequence

import yaml

PROTOCOL = "agent-sim/0.3"


@dataclass
class RunResult:
    exit_code: int
    run_dir: Path
    result: Optional[dict]
    stdout: str
    stderr: str

    @property
    def verdict(self) -> Optional[str]:
        return self.result.get("verdict") if self.result else None

    @property
    def termination_reason(self) -> Optional[str]:
        return self.result.get("termination_reason") if self.result else None

    def events(self) -> Iterator[dict]:
        return iter_events(self.run_dir, self.result)

    def replay(self) -> Optional[dict]:
        return read_replay(self.run_dir, self.result)

    def artifact(self, name: str) -> Path:
        return self.run_dir / self.result["artifacts"][name]


def capabilities(cmd: Sequence[str], timeout: float = 30) -> dict:
    """`<cmd> capabilities --json` parsed. Must work with no firmware and no ROM."""
    p = subprocess.run([*cmd, "capabilities", "--json"], capture_output=True, text=True, timeout=timeout, check=False)
    if p.returncode != 0:
        raise RuntimeError(f"{cmd[0]} capabilities failed ({p.returncode}): {p.stderr.strip()}")
    return json.loads(p.stdout)


def run(cmd: Sequence[str], scenario: str | Path, run_dir: str | Path,
        wall_timeout: Optional[float] = None, extra_args: Sequence[str] = ()) -> RunResult:
    """`<cmd> run SCENARIO --run-dir RUN_DIR [--wall-timeout S]`; never raises on a nonzero exit,
    the exit code is the protocol's answer."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    argv = [*cmd, "run", str(scenario), "--run-dir", str(run_dir), *extra_args]
    if wall_timeout is not None:
        argv += ["--wall-timeout", str(int(wall_timeout))]
    p = subprocess.run(argv, capture_output=True, text=True, check=False,
                       timeout=None if wall_timeout is None else wall_timeout + 30)
    return RunResult(p.returncode, run_dir, read_result(run_dir), p.stdout, p.stderr)


def read_result(run_dir: str | Path) -> Optional[dict]:
    p = Path(run_dir) / "result.json"
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def iter_events(run_dir: str | Path, result: Optional[dict] = None) -> Iterator[dict]:
    run_dir = Path(run_dir)
    result = result or read_result(run_dir) or {}
    rel = result.get("artifacts", {}).get("events", "events.ndjson")
    with open(run_dir / rel, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def read_replay(run_dir: str | Path, result: Optional[dict] = None) -> Optional[dict]:
    run_dir = Path(run_dir)
    result = result or read_result(run_dir) or {}
    rel = result.get("artifacts", {}).get("replay", "scenario.replay.yaml")
    p = run_dir / rel
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def failed_conditions(result: dict) -> list:
    return [c for c in result.get("conditions", []) if not c["ok"]]
