# Wego 過磅系統 - GitHub 部署與開發指南

本專案已成功備份並託管於 GitHub：[wego-weight](https://github.com/chao1014/wego-weight)。本指南旨在說明如何管理此專案的 Git/GitHub 流程、日常開發、打包以及執行方式。

---

## 📌 目錄
1. [環境準備](#1-環境準備)
2. [日常開發與執行](#2-日常開發與執行)
3. [專案打包與授權](#3-專案打包與授權)
4. [GitHub 備份與同步流程](#4-github-備份與同步流程)
5. [Git 忽略規則 (.gitignore)](#5-git-忽略規則-gitignore)

---

## 1. 環境準備
在開始開發或執行前，請確保您的系統已安裝：
- **Python 3.11**（或其他相容版本）
- **Git**

### 安裝相依套件
開啟終端機（PowerShell 或 CMD），進入專案目錄並執行：
```bash
pip install -r requirements.txt
```

---

## 2. 日常開發與執行
本專案為跆拳道選手過磅系統，包含選手秤重、結果判定與標籤列印等功能：

- **啟動主要過磅程式**：
  雙擊執行 `開啟過磅.bat` 或在終端機執行：
  ```bash
  python main.py
  ```
- **啟動授權產生器**：
  雙擊執行 `開啟過磅授權產生器.bat` 或在終端機執行：
  ```bash
  python packaging_tools/license_generator.py
  ```

---

## 3. 專案打包與授權
若需要將過磅系統打包成免安裝的 `.exe` 執行檔，可以使用內建的打包指令：

1. 執行打包指令：
   ```bash
   python packaging_tools/build_all.py
   ```
2. 打包完成後，輸出檔案會存放在 `dist/` 目錄中。
3. 詳細的打包邏輯與授權碼產生方式，請參考 [打包與授權說明.md](file:///D:/taekwondo-suite/weight/打包與授權說明.md)。

---

## 4. GitHub 備份與同步流程
當您在本地修改了專案程式碼，並希望同步備份到 GitHub 時，請按照以下步驟操作：

### 📥 步驟 A：開始工作前（拉取最新雲端版本）
若您在其他電腦上也修改了代碼，建議在開始編輯前先同步最新版本：
```bash
git pull origin main
```

### 📤 步驟 B：修改程式碼後（提交並推送至 GitHub）
當您修改了程式碼並確認測試無誤後，執行以下指令將備份推送到 GitHub：

1. **查看目前的變更狀態**：
   ```bash
   git status
   ```
2. **將變更加入暫存區**：
   ```bash
   git add .
   ```
3. **提交變更並加上說明**：
   ```bash
   git commit -m "您的修改說明（例如：修復秤重資料庫讀取問題）"
   ```
4. **推送到 GitHub 雲端**：
   ```bash
   git push origin main
   ```

---

## 5. Git 忽略規則 (.gitignore)
為了保持 GitHub 倉庫的乾淨與安全性，我們設定了 `.gitignore` 檔案，以下檔案或目錄**不會**被上傳至 GitHub：
- **安裝執行檔**：`python-3.11.9-amd64.exe`、`msys2-x86_64-20250622.exe` 等大型安裝檔（這些應下載後執行，無須放入 Git）。
- **`*.lic`**：已產生的授權許可檔案。
- **`weigh_in.db`**：本地測試或過磅產生的 SQLite 資料庫檔案。
- **`build/`、`dist/`、`*.spec`**：打包產生的暫存與輸出檔案，每次打包皆可重新產生。
- **`*.log`**：系統產生的除錯日誌（如 `app.log`、`pyarmor.bug.log`）。
- **`photos/*`**：除 `.gitkeep` 以外的暫存照片檔案。

如果您有其他需要忽略的檔案，請直接編輯 [`.gitignore`](file:///D:/taekwondo-suite/weight/.gitignore)。
