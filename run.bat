@echo off
title Game Subtitle Translator
cd /d "%~dp0"

echo ===================================================
echo   1. DANG KIEM TRA VA CAI DAT THU VIEN...
echo ===================================================

py -m pip install -r requirements.txt 2>nul || python -m pip install -r requirements.txt

if not exist .env (
    echo GEMINI_API_KEY=> .env
    echo Da tao file .env. Vui long mo file .env va dien API Key!
)

echo.
echo ===================================================
echo   2. DANG KHOI CHAY UNG DUNG...
echo ===================================================

:: Dùng 'start' và 'pyw/pythonw' để chạy ngầm giao diện UI mà không cần giữ cửa sổ CMD
start "" pyw game_video_sub_translator.py 2>nul || start "" pythonw game_video_sub_translator.py

:: Tự động thoát cửa sổ CMD ngay lập tức
exit