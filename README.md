# MeetBrief

會議語音轉文字摘要工具。上傳錄音檔，自動轉錄、辨識說話者並生成會議摘要。

## 功能

- 語音轉文字（Faster-Whisper，GPU 加速）
- 說話者分離（NeMo Toolkit）
- AI 會議摘要（DeepSeek API）
- 行動項目與決議提取
- Markdown / TXT 匯出

## 快速開始

```bash
# 1. 設定環境變數
cp .env.example .env
# 編輯 .env，填入 DEEPSEEK_API_KEY

# 2. 啟動服務
docker-compose up -d

# 3. 開啟瀏覽器
# http://localhost:21520
```

## 系統需求

- Docker + Docker Compose
- NVIDIA GPU（CUDA 12.1+）
- 至少 16GB RAM（Worker + Diarizer 各需 8GB）

## 架構

```
MeetBrief/
├── backend/                  # FastAPI 後端
│   ├── routers/             # API 路由
│   ├── modules/
│   │   ├── transcription/   # 轉錄協調
│   │   └── analysis/        # 分析管線（摘要、行動項目、決議）
│   └── common/              # 共用模組（LLM 客戶端）
├── worker/                   # Whisper 轉錄服務 (GPU)
├── diarizer/                 # 說話者分離服務 (GPU)
├── shared/                   # 共用模組 (Redis 佇列)
├── frontend/                 # 前端頁面（純 HTML/CSS/JS）
├── data/
│   ├── uploads/             # 上傳的音檔
│   └── results/             # 處理結果
└── docker-compose.yml
```

## 服務

| 服務 | 說明 | 依賴檔案 |
|------|------|----------|
| api | FastAPI 後端 (port 21520) | `requirements-api.txt` |
| worker | Whisper 轉錄 (GPU) | `requirements-worker.txt` |
| diarizer | NeMo 說話者分離 (GPU) | `requirements-diarizer.txt` |
| redis | 任務佇列 | - |

## 環境變數

| 變數 | 說明 | 預設值 |
|------|------|--------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key | 必填 |
| `DEEPSEEK_BASE_URL` | API 端點 | `https://api.deepseek.com` |
| `WHISPER_MODEL` | Whisper 模型 | `medium` |
| `WHISPER_DEVICE` | 運算裝置 | `cuda` |
| `WHISPER_COMPUTE_TYPE` | 精度類型 | `float16` |

## 支援格式

mp3, wav, m4a, ogg, webm, aac, flac, wma（最大 500MB）
