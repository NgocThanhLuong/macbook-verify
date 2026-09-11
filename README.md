# MacBook Verify

**MacBook Verify** là tool **one-click, offline** để kiểm tra nhanh MacBook cũ trước khi mua/bán hoặc sau khi sửa chữa. Tool thu thập dữ liệu trực tiếp từ macOS, tự phân tích và mở một báo cáo HTML dễ đọc.

> Mục tiêu là tìm **dấu hiệu bất thường có thể thấy bằng phần mềm**. Tool không giả vờ đưa ra điểm “100% zin”: không có lệnh macOS nào có thể chứng minh tuyệt đối máy chưa từng mở, sửa main hoặc thay một linh kiện chính hãng khác.

## Chạy một click

Clone/pull repo về Mac, sau đó double-click:

```text
MacBookVerify.command
```

Tool sẽ tự chạy, tạo report theo timestamp trên Desktop và tự mở `report.html`.

Nếu macOS chặn file `.command` lần đầu vì tải từ Internet, hãy **Right-click → Open** một lần rồi xác nhận mở.

## Cài thành app

Double-click:

```text
Install.command
```

Installer tạo app tại:

```text
~/Applications/MacBook Verify.app
```

Sau đó chỉ cần mở **MacBook Verify** như app bình thường. App chạy local, không cần Homebrew/Python/Node và không upload serial hay dữ liệu máy lên server.

## Tự động kiểm tra gì?

- Model, Model Identifier, Model Number, chip/CPU, CPU/GPU cores, RAM
- Đối chiếu system serial giữa `system_profiler` và IOKit
- Đối chiếu Model Identifier với `sysctl hw.model`
- Pin: serial, Cycle Count, Condition, Maximum Capacity, design-cycle reference
- Raw battery flags như `PermanentFailureStatus` và `BatteryCellDisconnectCount`
- Màn hình built-in: loại panel, độ phân giải, trạng thái online/internal
- SSD/NVMe: model, dung lượng, TRIM, SMART, detachable/removable
- Kiểm tra Apple SSD identity trên Apple Silicon
- SIP, FileVault, Activation Lock
- MDM / DEP / Automated Device Enrollment — rất quan trọng khi mua Mac cũ từ công ty/trường học
- Power-On Self Test / diagnostics khi macOS expose dữ liệu
- Tự dò Repair/Parts data type nếu phiên bản macOS hiện tại expose qua `system_profiler`

Parser hiện đã được đối chiếu với dữ liệu **MacBook Pro 16-inch 2021 / MacBookPro18,1 / M1 Pro**.

## Report

Mỗi lần chạy tạo thư mục dạng:

```text
~/Desktop/MacBook-Verify-20260911-104500/
├── report.html
├── summary.txt
├── summary.json
├── manifest.sha256
└── raw/
    ├── hardware.txt
    ├── platform-ioreg.txt
    ├── sysctl.txt
    ├── battery-system.txt
    ├── battery-raw.txt
    ├── display.txt
    ├── storage.txt
    ├── memory.txt
    ├── security.txt
    ├── mdm.txt
    ├── diagnostics.txt
    └── repair-history.txt
```

Trong `report.html` có dashboard PASS/WARN/FAIL/INFO, bảng evidence, ô nhập **serial khắc dưới đáy máy để so sánh trực tiếp**, và bộ test fullscreen White/Black/Red/Green/Blue/Gray để soi dead/stuck pixel và độ đồng đều màn hình.

## Ý nghĩa trạng thái

- **PASS** — dữ liệu hiện tại khỏe/nhất quán đối với check đó.
- **WARN** — cần xem kỹ hoặc kiểm tra thủ công thêm.
- **FAIL** — phát hiện mismatch hoặc trạng thái lỗi rõ ràng.
- **INFO** — dữ liệu tham khảo, không đủ cơ sở để tự kết luận.

Kết luận tổng thể được thiết kế theo hướng thận trọng; số lượng PASS **không phải phần trăm “zin”**.

## Những thứ vẫn phải kiểm tra vật lý

Software không thể chắc chắn phát hiện: dấu tháo ốc/cạy đáy, bottom case bị đổi, sửa main cấp linh kiện, liquid damage đã vệ sinh, màn chính hãng từng được thay đúng quy trình, hoặc lịch sử sửa mà macOS không expose.

Report vì vậy luôn nhắc kiểm tra serial mặt đáy, ốc/chassis, màn hình, keyboard/Touch ID/trackpad/ports/camera/mic/loa và chạy Apple Diagnostics trong môi trường boot riêng.

Chi tiết logic và giới hạn: [`docs/CHECKS.md`](docs/CHECKS.md).

## Apple Diagnostics

- **Apple Silicon:** tắt máy → giữ nút nguồn đến Startup Options → nhấn `Command-D`.
- **Intel:** bật máy và giữ `D`.

Apple Diagnostics cần reboot nên không thể hoàn toàn tự động hóa từ một macOS session đang chạy.

## CLI

```bash
./MacBookVerify.command
./scripts/verify.sh --no-open
./scripts/verify.sh --output ~/Documents
```

## Privacy

MacBook Verify chạy hoàn toàn local. Report có thể chứa serial number và hardware identifiers. Hãy che/redact các thông tin này nếu đăng report công khai.

## License

MIT
