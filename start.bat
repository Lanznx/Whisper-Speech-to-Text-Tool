@echo off
setlocal enabledelayedexpansion

:: 顯示彩色標題
echo =================================== 
echo    Whisper Speech-to-Text Tool     
echo =================================== 

:: 檢查是否安裝了必要的依賴
where node >nul 2>nul
if %errorlevel% neq 0 (
    echo Error: Node.js is not installed.
    exit /b 1
)

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo Error: Python is not installed.
    exit /b 1
)

where ffmpeg >nul 2>nul
if %errorlevel% neq 0 (
    echo Warning: ffmpeg is not installed. This may affect audio processing.
)

:: 啟動後端服務
echo.
echo [1/2] 啟動後端服務 (FastAPI + Whisper)...
cd backend

if exist .venv\ (
    echo 使用現有虛擬環境...
    call .venv\Scripts\activate.bat
    if !errorlevel! neq 0 (
        echo 無法啟用虛擬環境，請確保它存在並正確設置
        exit /b 1
    )
) else (
    echo 建立新的虛擬環境...
    :: 嘗試使用 uv (如果可用)，否則使用標準 venv
    where uv >nul 2>nul
    if !errorlevel! equ 0 (
        uv venv
        if !errorlevel! neq 0 (
            echo 無法使用 uv 建立虛擬環境
            exit /b 1
        )
        call .venv\Scripts\activate.bat
        if !errorlevel! neq 0 (
            echo 無法啟用虛擬環境
            exit /b 1
        )
        uv pip install -r requirements.txt
        if !errorlevel! neq 0 (
            echo 無法安裝依賴
            exit /b 1
        )
    ) else (
        python -m venv .venv
        if !errorlevel! neq 0 (
            echo 無法使用 venv 建立虛擬環境
            exit /b 1
        )
        call .venv\Scripts\activate.bat
        if !errorlevel! neq 0 (
            echo 無法啟用虛擬環境
            exit /b 1
        )
        pip install -r requirements.txt
        if !errorlevel! neq 0 (
            echo 無法安裝依賴
            exit /b 1
        )
    )
)

:: 在背景中啟動後端
echo 啟動 FastAPI 服務器...
start /B cmd /c "python main.py"

:: 等待後端啟動
echo 等待後端初始化...
timeout /t 5 /nobreak > nul

:: 回到根目錄
cd ..

:: 啟動前端服務
echo.
echo [2/2] 啟動前端服務 (React)...
cd frontend
if not exist node_modules\ (
    echo 安裝前端依賴...
    call npm install
    if !errorlevel! neq 0 (
        echo 無法安裝前端依賴
        exit /b 1
    )
)

:: 啟動前端
echo 啟動 React 開發伺服器...
set PORT=4001
call npm start

:: 注意：由於前端在前台執行，以下代碼只會在用戶關閉前端後執行
echo.
echo 停止所有服務...
taskkill /f /im node.exe >nul 2>nul
taskkill /f /im python.exe >nul 2>nul
