# Autonomous Collaborative Sentry Robot

CS532 • DQK / HNHL / KR. Laptop perception and control with a JetBot and
ESP32 door camera. [Specification](docs/Project%20Specification.md),
[implementation plan](docs/Implementation%20Plan.md), [setup](docs/Setup.md).

Midterm review: [PDF](reports/midterm_report.pdf),
[editable report](reports/midterm_report_draft.md),
[code appendix](reports/kouun-rokku/midterm-appendix-a.md),
[Week 7 validation and provenance](reports/kouun-rokku/week-07.md).

```bash
python -m tools.run_cpu_tests
python -m tools.check_midterm_package --ref HEAD
python -m tools.build_midterm_package --ref HEAD --out /tmp/submission.zip
```

For PDF reproduction install `requirements-report.txt`, then run
`python -m tools.render_midterm_report`. Report sources distinguish CPU tests,
pilot/dev-val data and hardware measurements. Pending acceptance remains explicit.
The submission ZIP contains the committed tree without `.git`; old repository
history is not sanitized by building a ZIP.
