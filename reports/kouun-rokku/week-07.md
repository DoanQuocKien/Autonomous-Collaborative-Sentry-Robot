# Week 07 — kouun-rokku (16–22/11/2026)

KR editor/package handoff prepared on 14/11 from the available evidence.

## Delivered

- Consolidated [Markdown](../midterm_report_draft.md) and [14-page PDF](../midterm_report.pdf),
  Chapters 1–8 plus Appendix A. Actual page count, current-source/PDF hashes,
  all nine chapters and 11 image assets are checked; word-count estimate is separate.
- Current KR chapters 1/2/6/7 and [code appendix](midterm-appendix-a.md), with
  modules, owners, tests, setup/reproduction commands and video shot list.
- Source reconciliation from HNHL's current chapter/addenda and DQK's newer
  drafts/RTX4050/edge evidence at `054d2adc` (PR108 open, explicitly attributed).
  [Source index](week-07/editor-sources.md) and 45-file SHA256 registry prevent
  silently replacing historical data. No code from PR108 was adopted.
- Package checker reads a committed tree by default; `--index` is only pre-commit.
  Development data, recordings, private archive and weights are excluded from
  the submission tree. Local originals remain available; Git history is unchanged.
- ZIP builder archives an audited commit without `.git`, adds per-file SHA256
  manifest and refuses to overwrite an earlier package. CPU test launcher records
  commit/tree, dirty status, interpreter/packages and the Linux test-only beep shim.

## Validation results

- **773 passed, 5 skipped, 4 deselected in 46.61 s** from clean clone of
  `c90c2440c2e228de1e88d490e0eff46dc8ff0674` (tree `3d7bbeb9f36dfed5c7ded52ee36875dc423c94c0`).
- PDF: **14 actual pages**, matching current-source/PDF SHA256; reproduced
  byte-for-byte. Visual spot checks: pages 6, 12 and 14.
- All nine chapters, 11 image assets, 45 registered source hashes: **PASS**.
- Current committed package paths, manifest hashes and repeated ZIP bytes: **PASS**.
- Full-model `check_env.py --cpu-ok`: **FAIL** for missing `insightface` and
  `torchreid`; retained verbatim. CPU/replay validation uses installed test
  packages and does not certify full inference readiness.

## Validation handoff

The committed candidate is cloned to a new empty directory without hard links.
CPU/replay tests and diagnostics are run there using the installed test environment;
no local datasets, weights or virtualenv are copied into the clone.

- [Checkout, command and pytest output](week-07/clean_checkout_pytest.log)
- [Model environment diagnostics](week-07/environment_check.log)
- [Package, source and rendered-page checks](week-07/contents_check.txt)
- [Candidate commit, tree and validation summary](week-07/validation.json)

The final evidence commit only adds these validation artifacts. Candidate and final
SHAs are kept distinct; a future `midterm` tag needs its own freeze-time check.

## Final team gates

The report records pending acceptance instead of inventing T1/T2 outcomes. D3,
independent D5, impostor FAR, robot pursuit/HOLD/whole-loop and edge/video gates
remain scoped in Chapters 7–8. Video final URL and owner signoff are still team
handoffs; replay/simulation shots must be labelled. Video is optional under the
report plan, though the group has an internal video milestone.

Tag `midterm` on **main** is scheduled for 21/11 after peer review, with final
PDF/video on 22/11 and submission on 23/11. This branch is the completed KR
editor/package contribution for review, not a claim that those future group gates
have occurred. Historical archive/password remain in earlier Git commits;
current-tree cleanup and ZIP export do not sanitize repository history.
