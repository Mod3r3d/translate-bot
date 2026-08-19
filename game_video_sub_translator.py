import sys
import time
import asyncio
import re
from threading import Thread, Lock
import numpy as np
import mss
import winocr
import keyboard
from PIL import Image
from deep_translator import GoogleTranslator
from PyQt6 import QtCore, QtGui, QtWidgets

import warnings
warnings.filterwarnings("ignore")

translator = GoogleTranslator(source='en', target='vi')

class SubtitleWorker(QtCore.QThread):
    new_subtitle_ready = QtCore.pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.running = True
        self.paused = False
        self.region = None
        self.last_en_buffer = ""
        self.last_translated_vi = ""
        self.pending_text = ""
        self.last_seen_time = 0
        self.cache = {}
        self.lock = Lock()
        self.req_id = 0

    def update_region(self, r):
        with self.lock:
            self.region = r
            self.last_en_buffer = ""
            self.pending_text = ""

    def set_paused(self, state: bool):
        self.paused = state

    def clean_text(self, text: str) -> str:
        text = re.sub(r'\d+:\d+\s*/\s*\d+:\d+', '', text)
        text = re.sub(r'\d+\s*/\s*\d+', '', text)
        text = text.replace('\n', ' ').replace('\r', ' ')
        corrections = {
            "|": "I", "  ": " ", "1ll": "I'll", "Tll": "I'll", 
            "’": "'", "`": "'", "“": '"', "”": '"'
        }
        for k, v in corrections.items():
            text = text.replace(k, v)
        return text.strip()

    def merge_rolling_text(self, accumulated: str, current_screen: str) -> str:
        """Thuật toán ghép chữ khi game cuộn dòng (Rolling Scroll)"""
        if not accumulated:
            return current_screen

        # Nếu màn hình là câu mới hoàn toàn (bắt đầu bằng chữ in hoa và câu cũ đã kết thúc bằng dấu chấm)
        if accumulated.endswith(('.', '!', '?')) and current_screen and current_screen[0].isupper() and not current_screen.lower().startswith(accumulated[-15:].lower()):
            # Kiểm tra xem có từ nào trùng lặp không
            words_acc = accumulated.split()
            words_curr = current_screen.split()
            overlap = 0
            for i in range(min(len(words_acc), len(words_curr)), 0, -1):
                if [w.lower() for w in words_acc[-i:]] == [w.lower() for w in words_curr[:i]]:
                    overlap = i
                    break
            if overlap == 0:
                # Đây là câu hội thoại mới hoàn toàn
                return current_screen

        # Tìm chuỗi từ gối đầu trùng nhau giữa đoạn cũ và đoạn mới trên màn hình
        words_acc = accumulated.split()
        words_curr = current_screen.split()

        best_overlap = 0
        for i in range(min(len(words_acc), len(words_curr)), 0, -1):
            if [w.lower() for w in words_acc[-i:]] == [w.lower() for w in words_curr[:i]]:
                best_overlap = i
                break

        if best_overlap > 0:
            # Ghép phần chữ mới xuất hiện ở đuôi
            return accumulated + " " + " ".join(words_curr[best_overlap:])
        elif current_screen in accumulated:
            return accumulated
        else:
            # Nếu là dòng tiếp diễn
            if current_screen and (current_screen[0].islower() or not accumulated.endswith(('.', '!', '?'))):
                return accumulated + " " + current_screen
            return current_screen

    def translate_task(self, text, current_id):
        if text in self.cache:
            vi = self.cache[text]
        else:
            try:
                vi = translator.translate(text)
                self.cache[text] = vi
            except Exception:
                vi = text

        if current_id == self.req_id and self.running:
            self.new_subtitle_ready.emit(vi)

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        with mss.MSS() as sct:
            while self.running:
                if self.paused or not self.region:
                    time.sleep(0.06)
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

                    ocr_result = loop.run_until_complete(winocr.recognize_pil(raw_pil, lang='en'))
                    raw_text = ocr_result.text if hasattr(ocr_result, 'text') else str(ocr_result)
                    clean_en = self.clean_text(raw_text)

                    now = time.time()
                    if len(clean_en) >= 3:
                        if clean_en != self.pending_text:
                            self.pending_text = clean_en
                            self.last_seen_time = now
                        else:
                            # Chữ đã ổn định (dừng gõ ~0.15s)
                            if now - self.last_seen_time >= 0.15:
                                full_text = self.merge_rolling_text(self.last_en_buffer, clean_en)
                                
                                if full_text != self.last_en_buffer:
                                    self.last_en_buffer = full_text
                                    self.req_id += 1
                                    
                                    Thread(
                                        target=self.translate_task,
                                        args=(full_text, self.req_id),
                                        daemon=True
                                    ).start()
                    else:
                        if self.last_en_buffer:
                            self.last_en_buffer = ""
                            self.pending_text = ""
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
        self.worker.stop()
        QtCore.QCoreApplication.quit()

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

        # Chữ dịch màu vàng
        painter.setPen(QtGui.QColor(255, 238, 88))
        painter.drawText(text_rect, flags, self.translated_text)

    def closeEvent(self, event):
        self.worker.stop()
        event.accept()


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = SubtitleViewer()
    window.show()
    sys.exit(app.exec())