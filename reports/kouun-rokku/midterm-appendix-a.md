# Phụ lục A — Bàn giao mã nguồn (Huỳnh Hữu Lộc, 18/11/2026)

Render `python -m tools.render_midterm_report` để tạo PDF 14 trang; chỉ commit PDF tại freeze tag.
Bảng dưới là chỉ mục chi tiết cho reviewer, không cộng thêm vào số trang PDF.

| Module | Owner | Tests / bằng chứng |
| :-- | :-- | :-- |
| `sentry/app/state_machine.py`, `target_queue.py` | Huỳnh Hữu Lộc | `tests/test_state_machine.py`, `tests/test_target_queue.py` |
| `sentry/app/phase3_runner.py` | Huỳnh Hữu Lộc | `tests/test_phase3_runner.py`; freshness, handoff, stall recovery, nonfinite commands |
| `sentry/nav/hold_detector.py`, `controllers.py`, `tower_avoid.py` | Huỳnh Hữu Lộc / Đoàn Quốc Kiên | `tests/test_hold_detector.py`, `tests/test_controllers.py`, `tests/test_tower_avoid.py`; T0/simulation |
| `sentry/nav/localization.py` | Huỳnh Hữu Lộc / Đoàn Quốc Kiên | `tests/test_localization.py`; real T2 chưa đủ lượt |
| `sentry/perception/entrance.py`, `sector.py` | Huỳnh Hữu Lộc / Đoàn Quốc Kiên | `tests/test_entrance.py`, `tests/test_sector.py` |
| `sentry/perception/{obstacle,face,reid,tracker}.py` | Huỳnh Nguyễn Hoài Lộc | các test module tương ứng; T1/T2 theo protocol riêng |
| Phase 2 live / door monitor | Huỳnh Nguyễn Hoài Lộc; Huỳnh Hữu Lộc nối queue/Phase3 | phase2_live, phase2_reid, phase2_replay |
| `sentry/net/`, ESP32 receivers | Huỳnh Nguyễn Hoài Lộc / Huỳnh Hữu Lộc | camera/clock/mjpeg/espcam tests |
| `jetson/`, `esp32/` | Đoàn Quốc Kiên / Huỳnh Hữu Lộc | compatibility, e-stop và HIL theo điều kiện thật |
| `tools/{check_midterm_package,build_midterm_package}.py` | Huỳnh Hữu Lộc | `tests/test_midterm_package.py`; committed-tree/ZIP/hash guards |
| report renderer / audit / sources | Huỳnh Hữu Lộc | `tests/test_midterm_page_budget.py`; PDF source hash và 10–15 trang |

## Cài đặt và tái hiện

Theo [Setup](../../docs/Setup.md) cho Python hỗ trợ và dependencies CPU/GPU.
Lệnh `check_env.py --cpu-ok` vẫn kiểm các model packages; CPU pytest PASS
không biến môi trường thiếu InsightFace/torchreid thành full inference setup.
Môi trường được dùng, thành phần thiếu và exit code được ghi nguyên trong
`week-07/environment_check.log` và `clean_checkout_pytest.log`.

```bash
python tools/check_env.py --cpu-ok
python -m tools.run_cpu_tests
python -m tools.replay_phase3 --out /tmp/phase3.json
python -m pip install -r requirements-report.txt
python -m tools.render_midterm_report
python -m tools.check_midterm_page_budget --pdf reports/midterm_report.pdf
python -m tools.check_midterm_sources
python -m tools.check_midterm_package --ref HEAD
python -m tools.build_midterm_package --ref HEAD --out /tmp/submission.zip
```

Linux renderer dùng DejaVu Sans mặc định; máy khác truyền `--font-dir` chứa
`DejaVuSans.ttf`, `DejaVuSans-Bold.ttf`. CPU launcher cung cấp shim `winsound`
chỉ trong test trên Linux; production không bị thay. Socket loopback cần được phép.

## Repo, bản nộp và lịch sử

[Repository](https://github.com/DoanQuocKien/Autonomous-Collaborative-Sentry-Robot),
nhánh `kouun-rokku/w07-midterm-package`. Nguồn PR #101 đã sửa nằm trong nhánh.
Tag `midterm` trên **main** chờ peer review/freeze theo lịch 21/11; không dùng
một tag khác để giả nhận bước chốt của nhóm đã hoàn tất.

ZIP xuất từ commit được ghi trong `SUBMISSION-MANIFEST.json`; checksum từng
file không phụ thuộc uncommitted workspace. `.git`, dữ liệu trong `data/`, raw
recordings, weights và archive D2 bị loại khỏi ZIP bằng pathspec. D5 và ZIP D2
vẫn tracked trong repo theo quyết định nhóm; default password được giữ.
Checker chỉ kiểm path, không tuyên bố đã audit mọi byte hoặc làm sạch lịch sử.

## Video — shot list và người phụ trách

| Shot | Chủ trì | Nguồn / trạng thái |
| :-- | :-- | :-- |
| Phần cứng JetBot/gamepad/ESP32 | Đoàn Quốc Kiên / Huỳnh Hữu Lộc | Chờ cut cuối và URL video |
| Phase 1: cửa, sweet spot, prompt, handshake | Đoàn Quốc Kiên / Huỳnh Hữu Lộc | Chỉ dùng clip thật có nguồn; ghi rõ pilot |
| Phase 2: whitelist, intruder queue | Huỳnh Nguyễn Hoài Lộc / Huỳnh Hữu Lộc | Phase 2 live do Huỳnh Nguyễn Hoài Lộc chủ trì (#115); replay ghi REPLAY |
| Phase 3: pursuit, HOLD, queue handoff | Đoàn Quốc Kiên / Huỳnh Hữu Lộc | Tách clip robot có giám sát với SIMULATION |
| Edge/FP16 | Đoàn Quốc Kiên / Huỳnh Nguyễn Hoài Lộc | Ghi thiết bị, có/không người, scope timing |

Chưa có link video cuối trong nguồn; không tự tạo URL giả. Video là optional
theo report plan, vẫn là mốc nội bộ của nhóm. Pin/consent/blur và người giữ R1
phải theo quy trình hiện hành; replay không được mô tả thành T2.
