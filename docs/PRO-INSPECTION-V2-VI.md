# MacBook Verify 2.0 — Bộ kiểm định MacBook tiếng Việt

## Điểm mới

- **Thông tin hệ thống đầy đủ:** system-information.html, system-information.json,
  giữ nguyên tất cả trường macOS System Information về CPU, GPU, RAM, SSD,
  APFS, pin, nguồn, Thunderbolt, USB, mạng, âm thanh, camera, firmware.
  Nếu macOS không cung cấp clock GPU, số nhân GPU hay sensor thì ghi N/A.
- **CPU / GPU Metal:** helper Swift chạy phép tính số học GPU, so sánh toàn bộ
  kết quả, phát hiện mismatch/command-buffer errors. Thời gian test GPU:
  Quick 3s, Full 10s, Deep 30s, Burn-in 90s. Yêu cầu Swift compiler;
  thiếu compiler/Metal là SKIP, không phải PASS. Không kiểm tra ANE thật.
- **RAM 4 pattern:** address-XOR, inverse, checkerboard, deterministic random;
  Deep/Burn-in tối đa 8 GiB hoặc 12,5% tổng RAM (mức nào thấp hơn).
  Đây là RAM được cấp phát, không thể quét hết bộ nhớ OS đang sử dụng.
- **Nhiệt độ, bảo mật, MDM, firmware, Sleep/Wake, Repair Evidence:**
  phân tích dữ liệu macOS, phân biệt cảnh báo và chỉ dẫn kiểm tra thủ công.
  Dữ liệu không có được ghi INFO/UNKNOWN, không chuyển thành PASS.
- **SSD APFS:** đọc container/volume metadata; chỉ chạy lệnh xác minh
  cấu trúc APFS nếu người dùng bật --verify-apfs, tuyệt đối không repair.
- **Battery Discharge:** quan sát pin khi rút sạc, ghi điện áp, dòng điện,
  công suất và phần trăm theo thời gian. Chỉ chạy với --battery-discharge N,
  tối đa 30 phút, tự dừng khi pin yếu hoặc cắm sạc.
- **Màn hình/ngoại vi:** wizard có RGB, gradient, ô caro, dải màu, phím,
  trackpad, camera, loa, mic, từng cổng. Thử bằng mắt/thiết bị thật.
- **So sánh hai máy:** compare-macs.html đọc hai tệp summary.json trên
  trình duyệt, so cấu hình/SSD/pin và tính giá tiền cần bù khi trade-in.

## Hướng dẫn chạy

Cài các dependency tùy chọn và chạy từ thư mục source:

    brew install python smartmontools
    ./MacBookVerify.command --full
    ./MacBookVerify.command --deep
    ./MacBookVerify.command --deep --verify-apfs
    ./MacBookVerify.command --deep --battery-discharge 3
    ./MacBookVerify.command --burn-in
    ./MacBookVerify.command --static-only

Yêu cầu Xcode Command Line Tools nếu muốn test GPU Metal và RAM native.
Chế độ --static-only không làm tải CPU/GPU hoặc ghi tệp test SSD.

## Thông số CPU và GPU

System Information sẽ giữ đầy đủ các trường nguyên gốc.
Màn hình tổng hợp hiển thị chip CPU, số lõi vật lý, P-cores/E-cores (nếu có),
tên GPU, số GPU cores mà macOS báo, RAM, SSD và firmware.

Không suy luận GPU clocks, nhiệt độ SSD, memory bandwidth thực tế hoặc số
counters ẩn không được Apple công khai. Với M1 Max 24 GPU và 32 GPU cần
dùng số cores được hệ thống báo, không suy luận từ tên chip.

## Xác minh rủi ro

- Một SSD SMART PASS không chứng minh SSD không thể hỏng.
- Pin 100% và 5 cycles vẫn có thể là pin đã thay, không xác định linh kiện zin.
- Kiểm tra ADE/MDM khi máy đang chạy không bảo đảm không hiện Remote Management
  sau khi khởi tạo lại. Người mua phải kiểm tra xóa và kích hoạt online.
- Apple Diagnostics trên M1 yêu cầu tắt máy, giữ nút nguồn đến Startup Options,
  sau đó Command-D. Lịch sử Parts & Service macOS 26+ tùy model và linh kiện.
- Đèn màn hình, bàn phím, trackpad, Touch ID, HDMI/SD/USB/Thunderbolt
  cần kiểm tra thực tế; chỉ nhận diện thiết bị không chứng minh còn tốt.

## Các báo cáo

- report.html: kết luận và điều hướng tiếng Việt
- system-information.html: toàn bộ thông số phần cứng
- system-information.json: dữ liệu gốc macOS System Information
- ssd-report.html: phân tích SMART/SSD Deep
- battery-report.html: pin, controller, Qmax, điện áp cell
- battery-discharge.html: lịch sử xả pin, nếu đã bật
- apple-coverage.html: xác minh bảo hành Apple
- compare-macs.html: so hai báo cáo và tính số tiền cần bù

Đối với máy bán lại, lưu ý báo cáo gốc có thể chứa serial/MAC/network.
Kiểm tra trước khi chia sẻ file ZIP.

## Chất lượng / kiểm thử

    python3 -m unittest discover -s tests -v
    bash -n scripts/verify.sh scripts/report.sh scripts/tests/active.sh

CI trên macOS kiểm tra cú pháp và chạy thử báo cáo mà không stress máy.
Phần cứng M1 Pro/M1 Max thực tế vẫn phải xác nhận trên máy người dùng.
