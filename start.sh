#!/bin/bash

# 顯示彩色標題
echo -e "\033[1;36m===================================\033[0m"
echo -e "\033[1;36m   Whisper Speech-to-Text Tool    \033[0m"
echo -e "\033[1;36m===================================\033[0m"

# 檢查是否安裝了必要的依賴
command -v node >/dev/null 2>&1 || { echo -e "\033[31mError: Node.js is not installed.\033[0m"; exit 1; }
command -v python >/dev/null 2>&1 || { echo -e "\033[31mError: Python is not installed.\033[0m"; exit 1; }
command -v ffmpeg >/dev/null 2>&1 || { echo -e "\033[31mWarning: ffmpeg is not installed. This may affect audio processing.\033[0m"; }

# 如果用戶按下 Ctrl+C，確保停止所有進程
trap 'echo -e "\n\033[33mStopping all services...\033[0m"; kill $(jobs -p) 2>/dev/null; exit' INT

# 啟動後端服務
echo -e "\n\033[32m[1/2] 啟動後端服務 (FastAPI + Whisper)...\033[0m"
cd backend
if [ -d ".venv" ]; then
  echo "使用現有虛擬環境..."
  source .venv/bin/activate || { echo -e "\033[31m無法啟用虛擬環境，請確保它存在並正確設置\033[0m"; exit 1; }
else
  echo "建立新的虛擬環境..."
  # 嘗試使用 uv (如果可用)，否則使用標準 venv
  if command -v uv >/dev/null 2>&1; then
    uv venv || { echo -e "\033[31m無法使用 uv 建立虛擬環境\033[0m"; exit 1; }
    source .venv/bin/activate || { echo -e "\033[31m無法啟用虛擬環境\033[0m"; exit 1; }
    uv pip install -r requirements.txt || { echo -e "\033[31m無法安裝依賴\033[0m"; exit 1; }
  else
    python -m venv .venv || { echo -e "\033[31m無法使用 venv 建立虛擬環境\033[0m"; exit 1; }
    source .venv/bin/activate || { echo -e "\033[31m無法啟用虛擬環境\033[0m"; exit 1; }
    pip install -r requirements.txt || { echo -e "\033[31m無法安裝依賴\033[0m"; exit 1; }
  fi
fi

# 在背景中啟動後端
echo "啟動 FastAPI 服務器..."
python main.py &
BACKEND_PID=$!
cd ..

# 等待後端啟動
echo -e "\033[33m等待後端初始化...\033[0m"
sleep 5

# 啟動前端服務
echo -e "\n\033[32m[2/2] 啟動前端服務 (React)...\033[0m"
cd frontend
if [ ! -d "node_modules" ]; then
  echo "安裝前端依賴..."
  npm install || { echo -e "\033[31m無法安裝前端依賴\033[0m"; kill $BACKEND_PID; exit 1; }
fi

# 在前台啟動前端 (這樣才能看到日誌輸出)
echo "啟動 React 開發伺服器..."
PORT=4001 npm start

# 注意：由於 npm start 在前台運行，
# 下面的代碼只會在 npm start 被中斷後執行

# 腳本結束時，確保停止後端進程
echo -e "\n\033[33m停止所有服務...\033[0m"
kill $BACKEND_PID 2>/dev/null
