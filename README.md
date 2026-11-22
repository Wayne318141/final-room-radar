# RoomRadar

大學生智慧租屋媒合平台。前端提供房源搜尋、篩選、收藏比較、費用試算與含圖片上傳的刊登表單；FastAPI 提供 REST API，SQLite 儲存房源、使用者、收藏與圖片資訊。介面使用響應式排版，並以 Unsplash 圖片 CDN 顯示示意房間照片；資料庫房源與照片不是實際租屋承諾。

## 本機啟動

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload
```

開啟 `http://127.0.0.1:8000`。資料管理頁面在 `/admin`，API 文件在 `/docs`。本機未設定 `ROOMRADAR_ADMIN_KEY` 時，管理 API 會關閉；用 `.env` 或終端環境變數設定後才能使用。

## 正式部署架構

- `static/`：純靜態網站，可同時部署至 GitHub Pages 與 Cloudflare Pages。
- `main.py`：FastAPI API，使用 Render Blueprint 部署；Render persistent disk 保存 SQLite 與已上傳圖片。磁碟服務需選擇支援 persistent disk 的方案。
- `static/config.js`：前端 API 位址；先部署 API，再將空字串改為 API 網址（例：`https://roomradar-api.onrender.com`），然後推送變更。

### 發布順序

1. 將 `RoomRadar` 資料夾內容推送到 GitHub 新儲存庫的 `main` 分支。請不要把管理密鑰、`.env`、資料庫檔案或上傳照片提交到 Git。
2. 在 Render 建立 Blueprint，選取儲存庫並套用 `render.yaml`。部署後，在 Render 環境設定中確認 `ROOMRADAR_ADMIN_KEY` 已產生，並複製 API 網址。
3. 將 `static/config.js` 的 `ROOMRADAR_API_BASE` 設成 Render API 網址並推送。此網站有匿名瀏覽者 ID；瀏覽器要允許網站向 API 網址送出跨網域請求。
4. 在 GitHub 儲存庫 `Settings → Pages` 選擇 GitHub Actions。推送 `static/` 內容時，`.github/workflows/pages.yml` 會自動部署靜態網站。
5. 在 Cloudflare `Workers & Pages → Create application → Pages → Connect to Git` 匯入同一個 GitHub 儲存庫；Build command 設 `exit 0`，Build output directory 設 `static`。以後推送會自動更新 Cloudflare Pages。
6. 待兩個網站網址建立後，把 Render 的 `ROOMRADAR_ALLOWED_ORIGINS` 改成實際前端來源，以逗號分隔（GitHub Pages 與 Cloudflare Pages 網址），不要保留萬用 `*`；重新部署 API。

GitHub Pages 和 Cloudflare Pages 只能提供靜態前端，不能直接執行本專案的 Python/FastAPI API。兩個網站共用同一個 Render API 與資料庫；Render 的磁碟服務可能產生費用，SQLite 設定以單一 API instance 為前提。管理員密鑰只設定在 Render，不要寫進 `config.js` 或 GitHub。

## 功能及 API

- `GET /api/listings`：依地區、租金、房型、設備與關鍵字篩選房源。
- `POST /api/cost-estimates`：試算租金、管理費、水電、網路與使用者自填補助。
- `POST /api/users` 與 `/api/users/{id}/favorites`：匿名展示使用者與收藏。
- `POST /api/listings`：驗證 multipart 表單並刊登房源；海報支援 JPG、PNG、WebP，上限 2 MB。
- `/api/admin/*` 與海報替換／刪除：必須帶 `X-Admin-Key`，由 Render 的 `ROOMRADAR_ADMIN_KEY` 驗證。
- `GET /docs`：FastAPI 互動式 API 文件。

表單包含必填欄位、前後端驗證、錯誤提示、圖片預覽及上傳限制。資料庫由應用啟動時建立，首次無房源資料時加入示範房源。

## 正式公開前仍須注意

這是課程專題原型，不是已完成法遵、房東驗證或交易服務的租屋市場。正式招募真實租客前，仍應補上服務條款與隱私權告知、個資刪除／申訴方式、刊登審核與濫用處理、資料備份與監控；目前匿名帳號存在瀏覽器本機，尚無正式登入及身分驗證。示意房源及照片不可冒充真實出租物件。正式公開前也必須由帳號持有人完成 GitHub、Cloudflare、Render 權限授權與部署設定；本資料夾提供部署設定，並未代替帳號發布或產生公開網址。
