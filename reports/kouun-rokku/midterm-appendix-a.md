# Phụ lục A — Bàn giao mã nguồn (KR, 14/11/2026)

Bản ghép có phụ lục gọn trong [PDF 14 trang](../midterm_report.pdf).
Bảng dưới là chỉ mục chi tiết cho reviewer, không cộng thêm vào số trang PDF.

| Module | Owner | Tests / bằng chứng |
| :-- | :-- | :-- |
| `sentry/app/state_machine.py`, `target_queue.py` | KR | `tests/test_state_machine.py`, `tests/test_target_queue.py` |
| `sentry/app/phase3_runner.py` | KR | `tests/test_phase3_runner.py`; freshness, handoff, stall recovery, nonfinite commands |
| `sentry/nav/hold_detector.py`, `controllers.py` | KR / DQK | `tests/test_hold_detector.py`, `tests/test_controllers.py`; T0/simulation |
| `sentry/nav/localization.py` | KR / DQK | `tests/test_localization.py`; real T2 chưa đủ lượt |
| `sentry/perception/entrance.py`, `sector.py` | KR / DQK | `tests/test_entrance.py`, `tests/test_sector.py` |
| `sentry/perception/{obstacle,face,reid,tracker}.py` | HNHL | các test module tương ứng; T1/T2 theo protocol riêng |
| `sentry/net/`, ESP32 receivers | HNHL / KR | camera/clock/mjpeg/espcam tests |
| `jetson/`, `esp32/` | DQK / KR | compatibility, e-stop và HIL theo điều kiện thật |
| `tools/{check_midterm_package,build_midterm_package}.py` | KR | `tests/test_midterm_package.py`; committed-tree/ZIP/hash guards |
| report renderer / audit / sources | KR | `tests/test_midterm_page_budget.py`; PDF source hash và 10–15 trang |

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
recordings, weights và archive D2 không nằm trong cây/gói hiện tại. Xóa khỏi
cây không xóa bản cũ: lịch sử vẫn có archive/password theo protocol cũ.
Checker chỉ kiểm path, không tuyên bố đã audit mọi byte hoặc làm sạch lịch sử.

## Video — shot list và người phụ trách

| Shot | Chủ trì | Nguồn / trạng thái |
| :-- | :-- | :-- |
| Phần cứng JetBot/gamepad/ESP32 | DQK / KR | Chờ cut cuối và URL do DQK bàn giao |
| Phase 1: cửa, sweet spot, prompt, handshake | DQK / KR | Chỉ dùng clip thật có nguồn; ghi rõ pilot |
| Phase 2: whitelist, intruder queue | HNHL / KR | Replay được nếu chưa có live, caption REPLAY |
| Phase 3: pursuit, HOLD, queue handoff | DQK / KR | Tách clip robot có giám sát với SIMULATION |
| Edge/FP16 | DQK / HNHL | Ghi thiết bị, có/không người, scope timing |

Chưa có link video cuối trong nguồn; không tự tạo URL giả. Video là optional
theo report plan, vẫn là mốc nội bộ của nhóm. Pin/consent/blur và người giữ R1
phải theo quy trình hiện hành; replay không được mô tả thành T2.
