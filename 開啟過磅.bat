@echo off
:: 啟動過磅系統 (使用 pythonw.exe 隱藏命令視窗)

:: 切換到批次檔所在的目錄
cd /d "%~dp0"

:: 【修改 1】立即啟動 Splash Screen
START "Splash" pythonw.exe splash.py

:: 【修改 2】接著啟動主程式
START "Weigh In System" pythonw.exe main.py

exit