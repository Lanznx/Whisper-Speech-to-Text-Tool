# Whisper Speech-to-Text Tool

簡單好用的語音轉文字工具，使用 OpenAI 的 Whisper 模型，搭配 React 前端和 FastAPI 後端。

*Built with AI Vibe Coding*

* **Python 3.8+**
* **Node.js 18+**
* **ffmpeg**: 用於音訊處理 
  * macOS: `brew install ffmpeg`
  * Ubuntu: `sudo apt update && sudo apt install ffmpeg`
  * Windows: 使用 [FFmpeg 官網](https://ffmpeg.org/download.html) 或 `choco install ffmpeg`

## 快速開始

### 後端設定

```bash
# 進入後端目錄
cd backend

# 建立虛擬環境並安裝依賴
python -m venv .venv
source .venv/bin/activate  # Windows 使用: .venv\Scripts\activate
pip install -r requirements.txt

# 啟動後端服務器
python main.py
```

### 前端設定

```bash
# 進入前端目錄
cd frontend

# 安裝依賴
npm install

# 啟動開發伺服器
PORT=4001 npm start
```

前端將在 `http://localhost:4001` 運行。

## 使用方法

1. 確保後端和前端都已啟動運行
2. 打開瀏覽器，訪問 `http://localhost:4001`
3. 使用界面上傳音訊檔案或直接錄音
4. 錄音完成後，系統會自動進行轉錄
5. 轉錄結果將顯示在頁面上

## 功能特點

* 支援上傳音訊檔案或直接錄音
* 即時音訊波形視覺化顯示
* 使用 Whisper "medium" 模型提供準確的語音識別
* 現代化 UI 設計 (Tailwind CSS + shadcn/ui)
