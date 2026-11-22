# RoomRadar

RoomRadar 是給大學生使用的租屋媒合課程專題。此版本採用免費部署組合：Cloudflare Pages 提供網站與 Functions API，Cloudflare D1 保存房源、使用者、收藏和小型房源圖片。GitHub Pages 可保留作為靜態展示，但資料寫入功能請使用 Cloudflare Pages 網址。

## 功能

- 房源搜尋、地區／租金／房型／設備篩選與排序。
- 每月租屋費用試算。
- 建立匿名訪客 ID，收藏房源並保存到 D1。
- 房東透過 multipart 表單刊登房源，含必填驗證、同意欄位及可選圖片上傳。
- 管理頁可檢視、編輯、刪除房源、使用者、收藏和圖片資料。
- `/api/health` 檢查 API 與 D1 連線。

## Cloudflare 免費部署

### 1. 把本資料夾內容更新到 GitHub

將本資料夾內的檔案與資料夾上傳到 `Wayne318141/final-room-radar` 儲存庫根目錄，遇到同名檔案選擇覆蓋。確認有上傳 `functions/`（內含 `api/[[path]].js`）、`schema.sql`，以及 `static/_routes.json`。不要上傳 `__pycache__`、`.env` 或管理密鑰。

### 2. 建立 Cloudflare Pages 網站

1. 登入 Cloudflare，進入 **Workers & Pages → Create application → Pages → Connect to Git**。
2. 選 `Wayne318141/final-room-radar`。
3. Build command 輸入 `exit 0`，Build output directory 輸入 `static`，其餘保持預設後部署。
4. Pages 會從儲存庫根目錄讀取 `functions/`，網站上線後複製 `*.pages.dev` 網址。

### 3. 建立並初始化持久資料庫

1. Cloudflare 左側進入 **Storage & databases → D1 SQL Database → Create database**，名稱輸入 `roomradar-db`。
2. 開啟資料庫的 **Console**，把本儲存庫 `schema.sql` 全部內容貼上並執行一次。這會建立資料表並加入示範房源。
3. 回到 **Workers & Pages → RoomRadar Pages 專案 → Settings → Functions → D1 database bindings → Add binding**。
4. Variable name 輸入 `DB`，Database 選 `roomradar-db`，儲存後重新部署最新版本。
5. 到 **Settings → Variables and Secrets** 新增 Secret：名稱 `ADMIN_KEY`，值設定成自己記得住的長密碼。不要把密碼寫進 GitHub 檔案或傳到聊天。
6. 再觸發一次部署，讓 Function 讀到 Secret。開啟 `https://你的專案.pages.dev/api/health`，應看到 `{"ok":true,"database":"D1"}`。

### 4. 使用網站

- 請用 Cloudflare Pages 網址測試搜尋、收藏、費用試算和刊登表單；提交測試房源後重新整理，資料仍應存在。
- 管理頁在 Cloudflare 網站網址後加 `/admin.html`。第一次操作會詢問 `ADMIN_KEY`，只存在該瀏覽器分頁的 sessionStorage。
- GitHub Pages（`https://wayne318141.github.io/final-room-radar/`）目前是靜態展示網址，不會連到 Cloudflare D1；若需它也能寫入資料，部署好 Cloudflare 後再把 `static/config.js` 的 API 位址改成 Cloudflare 網址，並重新上傳。

## API

| 方法 | 路徑 | 用途 |
| --- | --- | --- |
| GET | `/api/health` | API 與 D1 健康狀態 |
| GET | `/api/listings` | 搜尋／篩選房源 |
| GET | `/api/listings/{id}` | 單筆房源 |
| POST | `/api/listings` | multipart 表單刊登房源 |
| POST | `/api/users` | 建立匿名訪客 |
| GET | `/api/users/{id}/favorites` | 讀取收藏 |
| POST／DELETE | `/api/users/{id}/favorites/{listing_id}` | 新增／移除收藏 |
| POST | `/api/cost-estimates` | 費用試算 |
| GET | `/api/admin/overview` | 管理資料總覽（需 `X-Admin-Key`） |
| PUT／DELETE | `/api/admin/listings/{id}` | 編輯／刪除房源（需管理密鑰） |
| PUT／DELETE | `/api/admin/users/{id}` | 編輯／刪除使用者（需管理密鑰） |
| DELETE | `/api/admin/favorites/{id}` | 刪除收藏（需管理密鑰） |
| GET／PUT／DELETE | `/api/listings/{id}/poster` | 查看圖片；管理操作需管理密鑰 |

## 免費方案限制

- 房源圖片直接存為 D1 BLOB，單張限制 1.5 MB；不使用可能產生額外費用的圖片儲存服務。
- Cloudflare Workers／Pages Functions 與 D1 免費額度有每日請求、讀取及寫入上限，適合課堂展示與小型 MVP；超出免費上限時請求會受限。
- D1 是持久化資料庫；請在 Cloudflare D1 Console 管理資料。`main.py` 是本機 FastAPI＋SQLite 示範版，不是 Cloudflare Pages 的線上執行後端。
- 示範房源不是實際租屋承諾。正式面向公眾前應加上資料隱私告知、房源審核、檢舉和備份流程。
