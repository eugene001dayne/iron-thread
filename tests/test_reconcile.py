import copy

from attestation import GENESIS, generate_keypair, make_entry
from reconcile import reconcile

SCHEMA = {"type": "object", "required": ["n"]}


def make(n=3):
    priv, _ = generate_keypair()
    runs, entries, prev = [], [], GENESIS
    for i in range(1, n + 1):
        raw, out = f'{{"n": {i}}}', {"n": i}
        created = f"2026-10-18T10:00:0{i}+00:00"
        e = make_entry(priv, chain_id="c", seq=i, prev_hash=prev, run_id=f"r{i}", status="passed",
                       raw_input=raw, output=out, schema_definition=SCHEMA, created_at=created)
        entries.append(e)
        prev = e["entry_hash"]
        runs.append({"id": f"r{i}", "status": "passed", "raw_ai_output": raw, "validated_output": out,
                     "created_at": created})
    return runs, entries


def problems(result):
    return sorted(f["problem"] for f in result["findings"])


def test_everything_matches():
    runs, entries = make()
    r = reconcile(runs, entries, SCHEMA)
    assert r["ok"] is True and r["findings"] == [] and r["runs_checked"] == 3


def test_each_kind_of_edit_is_named():
    for field, value, expected in [
        ("status", "failed", "status_mismatch"),
        ("raw_ai_output", '{"n": 99}', "input_mismatch"),
        ("validated_output", {"n": 99}, "output_mismatch"),
        ("validated_output", None, "output_mismatch"),
        ("created_at", "2020-01-01T00:00:00+00:00", "timestamp_mismatch"),
    ]:
        runs, entries = make()
        runs[1][field] = value
        r = reconcile(runs, entries, SCHEMA)
        assert problems(r) == [expected] and r["findings"][0]["run_id"] == "r2"


def test_a_changed_schema_is_flagged_on_every_run():
    runs, entries = make()
    r = reconcile(runs, entries, {**SCHEMA, "required": []})
    assert problems(r) == ["schema_mismatch"] * 3


def test_schema_check_is_skipped_when_the_schema_is_gone():
    runs, entries = make()
    assert reconcile(runs, entries, None)["ok"] is True


def test_run_without_attestation_and_attestation_without_run():
    runs, entries = make()
    assert problems(reconcile(runs, entries[:2], SCHEMA)) == ["unattested_run"]
    assert problems(reconcile(runs[:2], entries, SCHEMA)) == ["orphan_attestation"]


def test_equivalent_timestamp_formats_are_not_an_alarm():
    runs, entries = make()
    runs[0]["created_at"] = "2026-10-18T10:00:01Z"
    assert reconcile(runs, entries, SCHEMA)["ok"] is True


def test_findings_are_capped_but_counted():
    runs, entries = make(3)
    big_runs = [{"id": f"x{i}", "status": "passed", "raw_ai_output": "", "validated_output": None,
                 "created_at": "t"} for i in range(150)]
    r = reconcile(big_runs, entries, SCHEMA)
    assert r["findings_total"] == 153 and len(r["findings"]) == 100
