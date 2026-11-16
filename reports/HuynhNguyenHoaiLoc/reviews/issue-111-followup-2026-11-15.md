HNHL status after the new merges: #115 is approved/merged. #108 now brings #116/#119/#121 into main; I re-reviewed the NaN/Inf/pulse and EOF fixes before merging it, and reviewed/merged #122/#123. #113 remains unchanged and blocked by the tracked D5/D2 deletions.

PR #124 adds the remaining shared queue/tracker handoff and TRACK_LOST producer, and replaces the queue's zero-as-missing timestamp convention with None. Full CPU/replay regression:881 passed,2 data skips,4 GPU deselected. These are code checks, not new T1/T2 measurements.

The current HNHL Chapter5/7 and appendix now cite15 pinned sources for the 14-Nov door-camera scores, RTX4050 workload, earlier live pilot/runtime and DQK's deployment/stop evidence. The checker preserves176 historical sources,240 local links and the frozen Word hash. DQK's new deployment summaries say manual_vantage; they do not establish HNHL's automatic-map/vantage accuracy. The two D2 datasets and the two GPU measurements remain separate.

D3/re-ID calibration, independent D5/per-class/empty-floor tests, map/world truth, RTX4050 precision accuracy and full door T1/body visibility remain pending. Current handoff: https://github.com/DoanQuocKien/Autonomous-Collaborative-Sentry-Robot/pull/124 (all HNHL report material under reports/HuynhNguyenHoaiLoc/).
