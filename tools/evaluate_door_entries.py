"""Score reviewed ESP32 entry decisions, retaining missing and unresolved cases."""
import argparse
import json
import math
from pathlib import Path


def evaluate(rows, truth):
    if truth.get("camera") != "esp32" or truth.get("reviewed") is not True:
        raise ValueError("reviewed ESP32 entry truth required")
    expected = truth.get("entries", [])
    if not expected:
        raise ValueError("nonempty entry truth required")
    by_id = {}
    for row in rows:
        key = row["entry_id"]
        if key in by_id:
            raise ValueError("duplicate logged entry")
        if row["decision"] not in ("authorized", "queued", "unresolved", "interrupted"):
            raise ValueError("unknown entry decision")
        by_id[key] = row
    seen = set()
    known = strangers = correct_accepts = false_accepts = false_queues = correct_queues = 0
    unresolved = missing = wrong_identity = 0
    decided_known = decided_strangers = 0
    latencies = []
    for item in expected:
        key, enrolled = item["entry_id"], item["enrolled"]
        if not isinstance(key, str) or not key or key in seen or type(enrolled) is not bool:
            raise ValueError("unique entry IDs and boolean enrolled labels required")
        if enrolled and not item.get("identity"):
            raise ValueError("enrolled entry requires reviewed identity")
        seen.add(key)
        known += enrolled
        strangers += not enrolled
        row = by_id.get(key)
        if row is None:
            missing += 1
            continue
        decision = row["decision"]
        unresolved += decision in ("unresolved", "interrupted")
        accepted = decision == "authorized"
        decided_known += enrolled and decision in ("authorized", "queued")
        decided_strangers += not enrolled and decision in ("authorized", "queued")
        same_identity = enrolled and row.get("authorized_id") == item.get("identity")
        correct_accepts += enrolled and accepted and same_identity
        wrong_identity += enrolled and accepted and not same_identity
        false_accepts += not enrolled and accepted
        false_queues += enrolled and decision == "queued"
        correct_queues += not enrolled and decision == "queued"
        if decision == "queued":
            latency = row.get("latency_s")
            if not isinstance(latency, (int, float)) or not math.isfinite(latency) or latency < 0:
                raise ValueError("queued entry needs a finite nonnegative latency")
            latencies.append(latency)
    unexpected = sorted(set(by_id) - seen)
    if unexpected:
        raise ValueError("log entries missing from reviewed truth: " + ", ".join(unexpected))
    return dict(expected_entries=len(expected), enrolled_entries=known, impostor_entries=strangers,
                correct_authorizations=correct_accepts, wrong_identity_authorizations=wrong_identity,
                false_accepts=false_accepts, false_queues=false_queues, correct_intruder_queues=correct_queues,
                missing_entries=missing, unresolved_entries=unresolved,
                tar=correct_accepts / known if known else None,
                far=false_accepts / decided_strangers if decided_strangers else None,
                far_all_attempts=false_accepts / strangers if strangers else None,
                decided_enrolled_entries=decided_known, decided_impostor_entries=decided_strangers,
                decision_coverage=(len(expected) - missing - unresolved) / len(expected),
                observed_entry_checks_pass=(known > 0 and strangers > 0
                    and correct_accepts == known and correct_queues == strangers
                    and missing == 0 and unresolved == 0),
                queued_latency_s=latencies, threshold_selected=None, t1_passed=False,
                note="Entry-level descriptive results; retain coverage and all reviewed attempts. "
                     "Independent calibration and live protocol acceptance still require owner review.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--entries", type=Path, required=True)
    ap.add_argument("--truth", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    rows = [json.loads(line) for line in a.entries.read_text(encoding="utf-8").splitlines() if line.strip()]
    result = evaluate(rows, json.loads(a.truth.read_text(encoding="utf-8")))
    # Aggregate-only output may go under reports/. Private inputs stay local.
    with a.out.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
