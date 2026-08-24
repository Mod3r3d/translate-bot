# 🎮 Real-time Game Subtitle Translator (AI Gemini)

Ứng dụng hỗ trợ nhận diện chữ trên màn hình (OCR) và dịch phụ đề/hội thoại game theo thời gian thực sang tiếng Việt bằng **Google Gemini AI** (tích hợp Google Translate dự phòng).

---

## ✨ Tính năng nổi bật
* **OCR Thời gian thực**: Nhận diện vùng phụ đề tự động bằng `winocr`.
* **Dịch thông minh qua Gemini Flash**: Tự động sửa lỗi chính tả OCR, dịch thoát ý theo ngữ cảnh game RPG/Anime, hạn chế tối đa dịch word-by-word.
* **Bộ lọc tối ưu & Debounce**: Nhận diện tốt trên nền video mờ và chờ kết thúc câu thoại mới gửi yêu cầu, tránh spam API.
* **Giao diện tiện lợi**: Ghim đè lên game, hỗ trợ ẩn viền và phím tắt khóa chuột (`F9`).
* **Tự động hóa 1-Click**: Tự động cài đặt thư viện và khởi chạy bằng file `run.bat`.

---

## 🚀 Hướng dẫn cài đặt & Chạy ứng dụng

### Yêu cầu hệ thống
* **Hệ điều hành**: Windows 10/11 (Bắt buộc vì dùng `winocr`).
* **Python**: Phiên bản 3.9 trở lên.

### Cách 1: Khởi chạy 1-Click (Khuyên dùng)
1. Tải toàn bộ mã nguồn về máy hoặc clone qua Git:
   git clone https://github.com/Mod3r3d/translate-bot.git
   cd translate-bot
2. Mở file `.env` và dán API Key của bạn vào:
   GEMINI_API_KEY=dán_mã_api_key_của_bạn_vào_đây
3. Nhấp đúp vào file `run.bat` để tự động cài đặt và mở phần mềm.

### Cách 2: Cài đặt và chạy thủ công
1. Cài đặt toàn bộ thư viện:
   pip install -r requirements.txt
2. Khởi chạy ứng dụng:
   python game_video_sub_translator.py

---

## 🕹 Hướng dẫn sử dụng
1. Bấm nút **🎯 Quét Vùng** trên thanh công cụ và kéo chọn vùng hiển thị phụ đề của game.
2. Bấm nút **🔒 Khóa [F9]** (hoặc nhấn phím `F9`) để khóa chuột, giúp click xuyên qua bảng dịch vào game.
3. Nhấn lại `F9` khi cần mở khóa để di chuyển hoặc chỉnh kích thước bảng dịch.
4. Bấm **⏸ Tạm dừng** hoặc **❌ Thoát** để kết thúc phiên làm việc.
