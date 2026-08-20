import sys
import os
import time
import asyncio
import re
import json
import urllib.request
import urllib.parse
import difflib
from threading import Thread, Lock
import numpy as np
import mss
import winocr
import keyboard
from PIL import Image, ImageEnhance
from PyQt6 import QtCore, QtGui, QtWidgets
import google.generativeai as genai
from dotenv import load_dotenv

import warnings
warnings.filterwarnings("ignore")

# ==========================================================
# CẤU HÌNH BẢO MẬT: TỰ ĐỘNG LẤY API KEY TỪ FILE .env
# ==========================================================
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

if GEMINI_API_KEY and len(GEMINI_API_KEY) > 10:
    genai.configure(api_key=GEMINI_API_KEY)
    
    sys_instruct = (
        "Bạn là một dịch giả game RPG giả tưởng chuyên nghiệp. "
        "Đầu vào là văn bản OCR từ game (thỉnh thoảng có lẫn chữ rác ở viền màn hình như 'LOG', 'AUTO', hoặc số đếm). "
        "NHIỆM VỤ TỐI THƯỢNG:\n"
        "1. CHỦ ĐỘNG BỎ QUA các ký tự rác vô nghĩa.\n"
        "2. Tự động sửa lỗi chính tả tiếng Anh do OCR (ví dụ: 'witn' -> 'with', 'propneaes' -> 'prophecies').\n"
        "3. DỊCH THOÁT Ý THEO NGỮ CẢNH: Không dịch word-by-word. (Ví dụ: 'make sense' / 'in that sense' dịch là 'có lý' / 'theo nghĩa đó', không dịch là 'cảm nhận').\n"
        "4. Văn phong tự nhiên, mượt mà đậm chất tiểu thuyết kỳ ảo.\n"
        "5. CHỈ TRẢ VỀ BẢN DỊCH TIẾNG VIỆT. Tuyệt đối không giải thích, không bình luận."
    )
    
    gemini_model = genai.GenerativeModel(
        model_name='gemini-1.5-flash',
        system_instruction=sys_instruct
    )
else:
    gemini_model = None

def fast_translate_fallback(text: str) -> str:
    if not text.strip():
        return ""
    try:
        url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=vi&dt=t&q=" + urllib.parse.quote(text)
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            translated_parts = [part[0] for part in data[0] if part and part[0]]
            return "".join(translated_parts)
    except Exception:
        return text

def ai_smart_translate(text: str) -> str:
    if not text.strip():
        return ""
    if not gemini_model:
        return "🤖 " + fast_translate_fallback(text)
        
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
    ]
    
    try:
        response = gemini_model.generate_content(
            text, 
            generation_config={"temperature": 0.15}, 
            safety_settings=safety_settings
        )
        if response.parts:
            result = response.text.strip().strip('"').strip("'")
            return "✨ " + result
        else:
            return "🤖 " + fast_translate_fallback(text)
    except Exception as e:
        return "🤖 " + fast_translate_fallback(text)


class SubtitleWorker(QtCore.QThread):
    new_subtitle_ready = QtCore.pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.running = True
        self.paused = False
        self.region = None
        self.accumulated_text = ""
        self.last_translated = ""
        
        # Biến phục vụ logic chống Spam (Debounce)
        self.accumulated_text_raw = ""
        self.last_change_time = 0
        
        self.cache = {}
        self.lock = Lock()
        self.req_id = 0

    def update_region(self, r):
        with self.lock:
            self.region = r
            self.accumulated_text = ""
            self.last_translated = ""
            self.accumulated_text_raw = ""

    def set_paused(self, state: bool):
        self.paused = state

    def clean_text(self, text: str) -> str:
        text = re.sub(r'\d+:\d+\s*/\s*\d+:\d+', '', text)
        text = re.sub(r'\d+\s*/\s*\d+', '', text)
        text = re.sub(r'[^a-zA-Z0-9\s.,!?\'"-]', '', text) 
        text = text.replace('\n', ' ').replace('\r', ' ')
        text = text.strip()
        if text and text[0].islower():
            text = text[0].upper() + text[1:]
        return text

    def are_words_similar(self, w1: str, w2: str) -> bool:
        w1_clean = re.sub(r'[^\w]', '', w1.lower())
        w2_clean = re.sub(r'[^\w]', '', w2.lower())
        if not w1_clean or not w2_clean:
            return w1_clean == w2_clean
        if w1_clean == w2_clean:
            return True
        return difflib.SequenceMatcher(None, w1_clean, w2_clean).ratio() >= 0.85

    def merge_rolling_dialogue(self, accumulated: str, current_screen: str) -> str:
        if not accumulated:
            return current_screen
        if not current_screen:
            return accumulated

        acc_words = accumulated.split()
        scr_words = current_screen.split()

        best_acc_idx = -1
        best_scr_idx = -1
        max_overlap = 0
        search_start = max(0, len(acc_words) - 16)
        
        for scr_start in range(min(5, len(scr_words))):
            for acc_i in range(search_start, len(acc_words)):
                match_len = 0
                while (acc_i + match_len < len(acc_words) and 
                       scr_start + match_len < len(scr_words) and 
                       self.are_words_similar(acc_words[acc_i + match_len], scr_words[scr_start + match_len])):
                    match_len += 1
                
                if match_len >= 2 and match_len > max_overlap:
                    max_overlap = match_len
                    best_acc_idx = acc_i
                    best_scr_idx = scr_start

        if max_overlap >= 2:
            merged_list = acc_words[:best_acc_idx] + scr_words[best_scr_idx:]
            return " ".join(merged_list)
        else:
            if accumulated.rstrip().endswith(('.', '!', '?')) and current_screen != accumulated:
                return current_screen
            return current_screen

    def translate_task(self, text, current_id):
        if text in self.cache:
            vi = self.cache[text]
        else:
            vi = ai_smart_translate(text)
            self.cache[text] = vi

        if current_id == self.req_id and self.running:
            self.new_subtitle_ready.emit(vi)

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        with mss.MSS() as sct:
            while self.running:
                if self.paused or not self.region:
                    time.sleep(0.04)
                    continue

                try:
                    target_box = {
                        'top': int(self.region['top']),
                        'left': int(self.region['left']),
                        'width': int(self.region['width']),
                        'height': int(self.region['height'])
                    }

                    sct_img = sct.grab(target_box)
                    raw_pil = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                    
                    # 1. NHỊ PHÂN HÓA HÌNH ẢNH (Binarization) KHỬ RÁC
                    gray_pil = raw_pil.convert('L')
                    enhanced_pil = ImageEnhance.Contrast(gray_pil).enhance(3.0)
                    # Ép mọi điểm mờ/nút bấm thành đen (0), chỉ chữ sáng (>160) mới thành trắng (255)
                    binary_pil = enhanced_pil.point(lambda p: 255 if p > 160 else 0)

                    ocr_result = loop.run_until_complete(winocr.recognize_pil(binary_pil, lang='en'))
                    raw_text = ocr_result.text if hasattr(ocr_result, 'text') else str(ocr_result)
                    clean_screen = self.clean_text(raw_text)

                    now = time.time()
                    if len(clean_screen) >= 3:
                        # 2. CHỐNG SPAM (Debounce 0.25s)
                        if clean_screen != self.accumulated_text_raw:
                            self.accumulated_text_raw = clean_screen
                            self.last_change_time = now
                        else:
                            # Đợi chữ trên màn hình dừng hẳn 0.25s rồi mới dịch
                            if now - self.last_change_time >= 0.25:
                                full_sentence = self.merge_rolling_dialogue(self.accumulated_text, clean_screen)
                                
                                if full_sentence != self.last_translated:
                                    self.accumulated_text = full_sentence
                                    self.last_translated = full_sentence
                                    self.req_id += 1
                                    
                                    Thread(
                                        target=self.translate_task,
                                        args=(full_sentence, self.req_id),
                                        daemon=True
                                    ).start()
                    else:
                        if self.accumulated_text:
                            self.accumulated_text = ""
                            self.accumulated_text_raw = ""
                            self.last_translated = ""
                            self.new_subtitle_ready.emit("")
                except Exception:
                    pass

                time.sleep(0.04)

        loop.close()

    def stop(self):
        self.running = False
        self.wait()


class SnippingOverlay(QtWidgets.QWidget):
    area_selected = QtCore.pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            QtCore.Qt.WindowType.FramelessWindowHint | 
            QtCore.Qt.WindowType.WindowStaysOnTopHint |
            QtCore.Qt.WindowType.Tool
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(QtCore.Qt.CursorShape.CrossCursor)
        self.setGeometry(QtGui.QGuiApplication.primaryScreen().geometry())
        self.start_pos = None
        self.end_pos = None

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.start_pos = event.globalPosition().toPoint()
            self.end_pos = self.start_pos
            self.update()

    def mouseMoveEvent(self, event):
        if self.start_pos:
            self.end_pos = event.globalPosition().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton and self.start_pos:
            rect = QtCore.QRect(self.start_pos, event.globalPosition().toPoint()).normalized()
            if rect.width() > 30 and rect.height() > 15:
                self.area_selected.emit({
                    'top': int(rect.top()),
                    'left': int(rect.left()),
                    'width': int(rect.width()),
                    'height': int(rect.height())
                })
            self.close()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor(0, 0, 0, 90))

        if self.start_pos and self.end_pos:
            rect = QtCore.QRect(self.start_pos, self.end_pos).normalized()
            painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(rect, QtCore.Qt.GlobalColor.transparent)
            painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setPen(QtGui.QPen(QtGui.QColor(0, 229, 255), 2))
            painter.drawRect(rect)


class SubtitleViewer(QtWidgets.QWidget):
    toggle_lock_signal = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()
        self.translated_text = "Bấm [🎯 Quét Vùng] và quét khung thoại game..."
        self.is_locked = False
        self.is_running = True
        self.drag_position = QtCore.QPoint()
        self.resizing = False
        self.snipper = None

        self.setWindowFlags(
            QtCore.Qt.WindowType.FramelessWindowHint |
            QtCore.Qt.WindowType.WindowStaysOnTopHint |
            QtCore.Qt.WindowType.Tool
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        
        self.setGeometry(150, 720, 1150, 160)
        self.setMinimumSize(500, 100)

        self.toggle_lock_signal.connect(self.toggle_lock)
        try:
            keyboard.add_hotkey('f9', self.toggle_lock_signal.emit)
        except Exception:
            pass

        self.worker = SubtitleWorker()
        self.worker.new_subtitle_ready.connect(self.update_sub)
        self.worker.start()

    def start_selection(self):
        self.snipper = SnippingOverlay()
        self.snipper.area_selected.connect(self.on_region_selected)
        self.snipper.show()

    def on_region_selected(self, region):
        self.worker.update_region(region)
        self.translated_text = "Đang nhận diện theo thời gian thực..."
        self.update()

    def toggle_play_pause(self):
        self.is_running = not self.is_running
        self.worker.set_paused(not self.is_running)
        if not self.is_running:
            self.translated_text = "⏸ [Đang tạm dừng dịch]"
        self.update()

    def exit_app(self):
        try:
            self.worker.stop()
        except Exception:
            pass
        
        try:
            parent_pid = os.getppid()
            os.system(f"taskkill /F /PID {parent_pid} >nul 2>&1")
        except Exception:
            pass
            
        os._exit(0)

    def update_sub(self, text):
        self.translated_text = text if text else "..."
        self.update()

    def toggle_lock(self):
        self.is_locked = not self.is_locked
        if self.is_locked:
            self.setWindowFlag(QtCore.Qt.WindowType.WindowTransparentForInput, True)
        else:
            self.setWindowFlag(QtCore.Qt.WindowType.WindowTransparentForInput, False)
        self.show()
        self.update()

    def mousePressEvent(self, event):
        if self.is_locked:
            return
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            x, y = event.position().x(), event.position().y()
            
            if 10 <= x <= 130 and 8 <= y <= 34:
                self.start_selection()
                return
            if 138 <= x <= 250 and 8 <= y <= 34:
                self.toggle_play_pause()
                return
            if 258 <= x <= 348 and 8 <= y <= 34:
                self.toggle_lock()
                return
            if 356 <= x <= 430 and 8 <= y <= 34:
                self.exit_app()
                return

            if x > self.width() - 25 and y > self.height() - 25:
                self.resizing = True
            else:
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self.is_locked:
            return
        if event.position().x() > self.width() - 25 and event.position().y() > self.height() - 25:
            self.setCursor(QtCore.Qt.CursorShape.SizeFDiagCursor)
        else:
            self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)

        if event.buttons() == QtCore.Qt.MouseButton.LeftButton:
            if self.resizing:
                self.resize(max(500, int(event.position().x())), max(100, int(event.position().y())))
            elif not self.drag_position.isNull():
                self.move(event.globalPosition().toPoint() - self.drag_position)

    def mouseReleaseEvent(self, event):
        self.resizing = False
        self.drag_position = QtCore.QPoint()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.RenderHint.TextAntialiasing)
        
        w, h = self.width(), self.height()
        rect = QtCore.QRect(0, 0, w, h)

        bg_alpha = 205 if self.is_locked else 240
        painter.setBrush(QtGui.QColor(8, 12, 18, bg_alpha))
        border_pen = QtGui.QPen(QtGui.QColor(0, 229, 255, 140) if not self.is_locked else QtCore.Qt.GlobalColor.transparent, 1.5)
        painter.setPen(border_pen)
        painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 12, 12)

        top_offset = 14
        if not self.is_locked:
            top_offset = 46
            painter.setBrush(QtGui.QColor(0, 180, 216, 220))
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.drawRoundedRect(10, 8, 120, 26, 5, 5)
            painter.setPen(QtGui.QColor(255, 255, 255))
            painter.setFont(QtGui.QFont("Segoe UI", 9, QtGui.QFont.Weight.Bold))
            painter.drawText(10, 8, 120, 26, QtCore.Qt.AlignmentFlag.AlignCenter, "🎯 Quét Vùng")

            btn_color = QtGui.QColor(40, 167, 69, 220) if not self.is_running else QtGui.QColor(255, 193, 7, 220)
            painter.setBrush(btn_color)
            painter.drawRoundedRect(138, 8, 112, 26, 5, 5)
            painter.setPen(QtGui.QColor(0, 0, 0) if self.is_running else QtGui.QColor(255, 255, 255))
            status_text = "⏸ Tạm dừng" if self.is_running else "▶ Tiếp tục"
            painter.drawText(138, 8, 112, 26, QtCore.Qt.AlignmentFlag.AlignCenter, status_text)

            painter.setBrush(QtGui.QColor(247, 127, 0, 220))
            painter.drawRoundedRect(258, 8, 90, 26, 5, 5)
            painter.setPen(QtGui.QColor(255, 255, 255))
            painter.drawText(258, 8, 90, 26, QtCore.Qt.AlignmentFlag.AlignCenter, "🔒 Khóa [F9]")

            painter.setBrush(QtGui.QColor(220, 53, 69, 220))
            painter.drawRoundedRect(356, 8, 74, 26, 5, 5)
            painter.drawText(356, 8, 74, 26, QtCore.Qt.AlignmentFlag.AlignCenter, "❌ Thoát")

            painter.setPen(QtGui.QColor(160, 175, 190))
            painter.setFont(QtGui.QFont("Segoe UI", 8))
            painter.drawText(445, 25, "✛ Kéo thanh | Kéo góc phải để mở rộng")

            painter.setBrush(QtGui.QColor(0, 229, 255, 200))
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            handle = QtGui.QPainterPath()
            handle.moveTo(w - 14, h - 2)
            handle.lineTo(w - 2, h - 14)
            handle.lineTo(w - 2, h - 2)
            painter.drawPath(handle)

        font = QtGui.QFont("Segoe UI", 16, QtGui.QFont.Weight.DemiBold)
        font.setLetterSpacing(QtGui.QFont.SpacingType.AbsoluteSpacing, 0.5)
        painter.setFont(font)
        
        text_rect = QtCore.QRect(24, top_offset, w - 48, h - top_offset - 14)
        flags = QtCore.Qt.AlignmentFlag.AlignCenter | QtCore.Qt.TextFlag.TextWordWrap

        # Bóng viền đen
        painter.setPen(QtGui.QColor(0, 0, 0, 255))
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1), (-2, 2), (2, 2)]:
            painter.drawText(text_rect.adjusted(dx, dy, dx, dy), flags, self.translated_text)

        # Chữ vàng sáng
        painter.setPen(QtGui.QColor(255, 238, 88))
        painter.drawText(text_rect, flags, self.translated_text)

    def closeEvent(self, event):
        self.exit_app()
        event.accept()


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = SubtitleViewer()
    window.show()
    sys.exit(app.exec())