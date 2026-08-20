@'
# 🎮 Real-time Game Subtitle Translator (AI Gemini)

Ứng dụng hỗ trợ nhận diện chữ trên màn hình (OCR) và dịch phụ đề/hội thoại game theo thời gian thực sang tiếng Việt bằng **Google Gemini AI**.

---

## ✨ Tính năng nổi bật
* **OCR Thời gian thực**: Nhận diện vùng phụ đề tự động bằng `winocr`.
* **Dịch thông minh qua Gemini 1.5 Flash**: Tự động sửa lỗi chính tả OCR, dịch mượt theo ngữ cảnh game, hạn chế dịch word-by-word.
* **Bộ lọc Nhị phân hóa (Binarization)**: Giảm thiểu tối đa nhiễu nền, nút bấm (`LOG`, `AUTO`) hay hiệu ứng sáng bóng của font chữ.
* **Cơ chế Debounce**: Chờ kết thúc câu thoại mới gửi yêu cầu, tránh spam API.
* **Giao diện tiện lợi**: Ghim đè lên game, hỗ trợ ẩn viền và phím tắt khóa chuột (`F9`).

---

## 🚀 Hướng dẫn cài đặt & Chạy ứng dụng

### Yêu cầu hệ thống
* **Hệ điều hành**: Windows 10/11 (Bắt buộc vì dùng `winocr`).
* **Python**: Phiên bản 3.9 trở lên.

### Bước 1: Tải mã nguồn
Mở Terminal/PowerShell và clone repository về máy:
git clone [https://github.com/Mod3r3d/translate-bot.git](https://github.com/Mod3r3d/translate-bot.git)
cd translate-bot

### Bước 2: Cài đặt thư viện phụ thuộc
Chạy lệnh sau để cài đặt toàn bộ gói cần thiết:
pip install PyQt6 mss winocr keyboard Pillow numpy google-generativeai python-dotenv

### Bước 3: Cấu hình Gemini API Key
1. Truy cập [https://aistudio.google.com/](https://aistudio.google.com/) và đăng nhập bằng tài khoản Google.
2. Bấm "Create API Key" và sao chép mã Key vừa tạo.
3. Tạo một file tên `.env` ngay tại thư mục gốc của dự án.
4. Mở file `.env` và dán nội dung:
GEMINI_API_KEY=dán_mã_api_key_của_bạn_vào_đây

### Bước 4: Khởi chạy ứng dụng
Chạy lệnh sau:
python game_video_sub_translator.py

---

## 🕹 Hướng dẫn sử dụng
1. Bấm nút **🎯 Quét Vùng** trên thanh công cụ và kéo chọn vùng hiển thị phụ đề của game.
2. Bấm nút **🔒 Khóa [F9]** (hoặc nhấn phím `F9`) để khóa chuột, giúp click xuyên qua bảng dịch vào game.
3. Nhấn lại `F9` khi cần mở khóa để di chuyển hoặc chỉnh kích thước bảng dịch.
4. Bấm **⏸ Tạm dừng** hoặc **❌ Thoát** để kết thúc phiên làm việc.
'@ | Out-File -FilePath README.md -Encoding utf8