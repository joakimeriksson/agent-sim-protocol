#!/usr/bin/env python3
"""Build contiki-ng-tests.md from the extracted scripts and classification.json.

    python3 conformance/corpus/extract.py /tmp/scripts.json      # needs ~/work/contiki-ng
    python3 conformance/corpus/report.py /tmp/scripts.json > conformance/corpus/contiki-ng-tests.md
"""
import json, sys
from collections import Counter
from pathlib import Path
here = Path(__file__).parent
d = json.load(open(sys.argv[1]))
cl = json.load(open(here / "classification.json"))
cats = cl.pop("_categories")
missing = [h for h in d["scripts"] if h not in cl]
assert not missing, f"unclassified scripts: {missing}"
per_test = [(t["test"], t["script"], *cl[t["script"]]) for t in d["tests"]]
count = Counter(c for _, _, c, _ in per_test)
total = len(per_test); insim = total - count["D"]
print("# Corpus check: the upstream Contiki-NG Cooja tests against the closed condition set\n")
print(f"{total} simulation tests, {len(d['scripts'])} distinct scripts (Contiki-NG `{sys.argv[2] if len(sys.argv) > 2 else 'HEAD'}`).")
print("Each script was read and classified by hand; `classification.json` holds the verdict and the")
print("reason per script, `extract.py` and `report.py` regenerate this file.\n")
print("| category | tests | share of in-simulator tests | meaning |\n| --- | --- | --- | --- |")
for c, meaning in cats.items():
    share = "" if c == "D" else f"{100 * count[c] / insim:.0f}%"
    print(f"| {c} | {count[c]} | {share} | {meaning} |")
fits = count["A"]; with_add = fits + sum(count[c] for c in ("B1", "B2", "B3", "B4"))
print(f"\nOf the {insim} tests whose verdict is decided inside the simulator, **{fits} ({100*fits/insim:.0f}%) fit the")
print(f"closed set as written** and **{with_add} ({100*with_add/insim:.0f}%) fit with four additions** (B1–B4). "
      f"{count['B5'] + count['C']} need the JS escape hatch.")
print(f"{count['D']} tests are real-time runs judged by an external driver and are outside `expect` altogether.\n")
print("## Per test\n\n| test | script | category | how it maps |\n| --- | --- | --- | --- |")
for test, h, c, note in per_test:
    print(f"| `{test}` | `{h}` | {c} | {note} |")
