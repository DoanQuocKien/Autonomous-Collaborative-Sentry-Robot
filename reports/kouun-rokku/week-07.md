# Week 07 — kouun-rokku (16–22/11/2026)

Editor/package revision for PR #113, 18–20/11/2026 (integrated `#130` and `#131` on `main`).

- Rebased onto main. D5 training files, D2 archive, ignore exceptions and the main version of Team Data Sharing are retained. The recorded default password is restored with CLI/environment overrides.
- Submission export excludes data/team_data/recordings/weights using the same Git pathspecs in its audit and archive. It never removes development data. Manifest hashes every exported file; repeated builds must be byte-identical.
- Report uses merged evidence: seven counted T2 door runs; one valid handshake accept and reject; door-camera TAR 822/877 and FAR 0/1754 (three people, one session; TAR target not established); measured 14/11 and 16/11 stop timings; HNHL Phase 2 ownership and pilot; 16/11 pursuit did not meet the distance gate.
- Classroom measurements retain 5 W assumption, glossy floor, pre-audit robot code (before evening 16/11 redeploy) and unsigned packets. 16/11 pursuit had no tower avoidance; post-freeze 18/11 dorm trial adds marker-based `TowerSteer` with general obstacle detector disabled (ping-pong near tower and floor-wide avoidance remain open); DR gains remain Week 2; IMU repair is not expected before submission.
- Sources are pinned as commit:path plus SHA256 in [registry](week-07/editor-source-registry.json) (60 entries), with no duplicate source tree. PR #108, #130 and #131 have merged into main.
- Generate PDF with `python -m tools.render_midterm_report`; PDF and renderer metadata are ignored until the freeze tag. Page verification is separate from visual review.

Validation evidence: [clean-checkout test output](week-07/clean_checkout_pytest.log), [contents checks](week-07/contents_check.txt), [summary](week-07/validation.json). Each result applies only to the exact candidate commit named there. No GPU/hardware acceptance is claimed.

Owner signoff, final video URL, freeze tag on main and submission remain team gates. The current source does not claim completion of those gates.
