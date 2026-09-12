"""The checker against its own vectors: every recorded or hand-written vector passes,
every negative vector trips exactly the rule it names."""
from pathlib import Path

import pytest

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
