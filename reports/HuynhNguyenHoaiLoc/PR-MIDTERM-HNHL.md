# HNHL midterm: evidence-backed Chapter 5 and Week 5 acceptance audit

## Result

HNHL's tracking/GPU code was merged in #92, but D3 identity/re-lock and combined RTX4050 acceptance are still missing. This PR packages the existing measurements into an editable three-page Chapter5 Word and matching Markdown, F9/F10/F13, Chapter7 rows, code appendix and an explicit continuation checklist. It updates the W5 report to distinguish merged implementation from full Definition of Done.

The 03/11 addendum supplies RTX4050/5060 single-model baselines, full D5 precision/recall, real-camera link/watchdog/e-stop scope, Jetson/ESP32 runtime/freshness and the measured endpoint F15 from merged #94. It preserves failed/pending results, null re-ID/tracking accuracy, the 01/11 Word snapshot and the shared chapter page budget. Sources E01–E20 carry SHA256 with CRLF→LF canonicalization. PR #93 review notes are archived at their reviewed SHA; its later revised head is explicitly not accepted by this report.

## Validation

```powershell
.venv/Scripts/python.exe -m tools.build_midterm_hnhl_update
.venv/Scripts/python.exe -m tools.check_midterm_hnhl --out reports/HuynhNguyenHoaiLoc/midterm/update-verification.json
git diff --check
```

- Verified 20 source hashes, both saved metrics snapshots, missing-acceptance guards, local document links, and 29 Word/Markdown narrative blocks.
- All three Word pages were exported through Microsoft Word and rendered/visually checked; its binary hash is unchanged in the 03/11 update. F9/F10/F13 and new single-model F9 reviewed for layout/units.
- No application/model changes, new inference claims, motor commands, raw faces/crops/embeddings, private predictions or weights. W5 logs of 584 CPU/4 GPU tests are historical evidence, not rerun by document tooling. The 605-test #93 review belongs to a separate checkout.

Entry point: `reports/HuynhNguyenHoaiLoc/midterm/README.md`. Base: main `63c63ba`. Reviewer: DQK. Remaining D3/gallery, F7 raw samples, F11 map truth, F18 paired accuracy and robot trials are listed, not marked complete. KR/DQK must consolidate their contributions with this draft in the shared 3.5-page Chapter5 budget.
