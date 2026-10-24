# private-cloud 壓力測試與資料一致性驗證最終計劃

## Summary

本計劃為 `private-cloud` 專案建立一套可直接交付 AI 實作的壓力測試規格，涵蓋：

- 一般 HTTP 混合負載測試
- WebSocket 即時共編壓力測試
- 多使用者檔案操作 race condition 測試
- 資料一致性與完整性驗證
- Grafana 視覺化輸出
- 測試矩陣、人數測試、Race 測試與一致性檢查報告輸出

本文件是實作規格。交付給 AI 時，AI 應依本文件建立 `load-tests/` 相關壓測檔案、Grafana/InfluxDB 設定、測試資料生成腳本與報告輸出工具，但不得修改 backend/frontend 業務邏輯，也不得為了讓測試通過而降低測試標準。

## 0. AI 執行指令與本機前置資料生成

### 0.1 AI 實作邊界

AI 接手實作時只允許新增或修改下列壓測相關檔案：

```txt
load-tests/
  README.md
  k6.js
  test-matrix.md
  docker-compose.observability.yml
  data/
  scripts/
  grafana/
  reports/
```

不得修改：

```txt
backend/
frontend/
db/docker-compose.yaml
alembic/
```

若測試發現後端 race condition、cookie、WebSocket 權限或資料一致性問題，只能在報告中記錄，不可直接修後端。

AI 不得執行下列行為：

```txt
1. 不得修改 backend/frontend 程式碼來讓測試通過。
2. 不得修改 alembic migration 或資料表結構來讓一致性檢查通過。
3. 不得放寬 PASS/FAIL 標準來隱藏問題。
4. 不得刪除或跳過失敗的測試矩陣案例。
5. 不得把實際 FAIL 報告成 PASS。
6. 不得使用正式資料作為 race 測試資料。
```

若遇到測試失敗，AI 必須保留失敗結果，並在報告中輸出：

```txt
失敗測試 ID
失敗 API 或 WebSocket 操作
預期結果
實際結果
Grafana metric
可能原因
後續改善建議
```

### 0.2 本機測試入口固定設定

本計劃預設轉為本機測試，不使用 cloudflared 作為正式壓測入口。

固定測試入口：

```txt
BASE_URL=http://localhost:8000
WS_BASE_URL=ws://localhost:8000
GRAFANA_URL=http://localhost:3000
INFLUXDB_URL=http://localhost:8086
K6_OUT=influxdb=http://localhost:8086/k6
```

保留目前後端 cookie 設定現狀：

```txt
session cookie: secure=True
session cookie: httponly=True
session cookie: samesite=none
```

由於本機測試使用 HTTP 且後端仍會設定 `Secure` cookie，k6 實作不得要求修改 backend。k6 登入 function 必須：

```txt
1. 呼叫 POST /api/accounts/login。
2. 從 response headers 的 Set-Cookie 解析 session 值。
3. 後續 HTTP request 明確帶入 header：Cookie: session=<session_value>。
4. 不依賴瀏覽器或 k6 cookie jar 是否願意在 HTTP localhost 回送 Secure cookie。
```

WebSocket 目前使用 `?user_id=`，不使用 session cookie 驗證；測試仍需在報告中標示此限制。

### 0.3 測試帳號生成邏輯

AI 必須實作 `load-tests/scripts/seed-load-test-data.py`，用於建立可登入的測試帳號、Home folder、一般測試檔案、共編檔案、分享檔案與 race 專用檔案。

執行方式：

```bash
cd backend
uv run ../load-tests/scripts/seed-load-test-data.py \
  --users 100 \
  --files-per-user 5 \
  --race-files 200 \
  --password LoadTest123!
```

生成帳號規則：

```txt
username: load_user_001, load_user_002, ...
email: load_user_001@example.test, load_user_002@example.test, ...
password: 預設 LoadTest123!
email_verified_at: 目前時間
enable: true
delete_date: null
identity: 一般使用者
signal_file_size: 使用系統預設值
total_file_size: 使用系統預設值
used_size: 依假檔案大小加總
```

帳號數量建議：

```txt
Smoke: 5 users
Baseline: 20 users
Load: 100 users
Stress: 200 users
```

seed 腳本必須可重複執行：

```txt
若 load_user_xxx 已存在，更新為 enable=true 且 email_verified_at 不為 null。
若 Home folder 不存在，建立 Home folder。
若測試檔案已存在，依 deterministic filename 更新或重建。
不得刪除非 load_user_ 前綴的正式資料。
```

### 0.4 假測試檔案生成邏輯

AI 必須在 seed 腳本中建立實體檔案與 DB record，確保 API、download、share、collab 都能使用真實 file_uuid。

每個使用者至少生成：

```txt
一般檔案：load-normal-{user_index}-{n}.txt
下載檔案：load-download-{user_index}-{n}.txt
分享檔案：load-share-{user_index}-{n}.txt
共編檔案：load-collab-{user_index}-{n}.txt
```

Race 專用檔案命名：

```txt
load-race-{sequence}.txt
load-race-hard-delete-{sequence}.txt
load-race-soft-delete-{sequence}.txt
load-race-share-{sequence}.txt
load-race-overwrite-{sequence}.txt
```

檔案內容規則：

```txt
小檔案：1 KB，用於列表、分享、race。
中檔案：64 KB，用於下載。
上傳樣本：1 KB、64 KB、1 MB 三種，用於 upload scenario。
共編檔案：純文字 UTF-8，內容包含檔案 UUID 與 seed timestamp。
```

storage 實體檔案規則：

```txt
路徑使用 backend 設定的 STORAGE_BASE_PATH。
DB files.storage_path 必須指向實際檔案。
DB files.uuid 與 storage 檔名需符合現有 FileService 慣例。
active file 必須 deleted_at=null。
race-files.json 內檔案必須是專用可刪除資料。
```

seed 腳本必須輸出：

```txt
load-tests/data/users.json
load-tests/data/files.json
load-tests/data/race-files.json
load-tests/data/share-files.json
load-tests/data/collab-files.json
load-tests/data/upload-sample-1kb.txt
load-tests/data/upload-sample-64kb.txt
load-tests/data/upload-sample-1mb.bin
```

JSON 輸出必須包含：

```json
{
  "user_id": 1,
  "username": "load_user_001",
  "password": "LoadTest123!",
  "email": "load_user_001@example.test",
  "home_folder_uuid": "..."
}
```

檔案資料需包含：

```json
{
  "file_uuid": "...",
  "owner_user_id": 1,
  "owner_username": "load_user_001",
  "filename": "load-download-001-001.txt",
  "size": 65536,
  "purpose": "download",
  "safe_for_delete_race": false
}
```

Race 檔案資料需包含：

```json
{
  "file_uuid": "...",
  "owner_user_id": 1,
  "owner_username": "load_user_001",
  "filename": "load-race-soft-delete-0001.txt",
  "purpose": "race_soft_delete",
  "delete_mode": "soft"
}
```

## 1. 專案背景與測試目標

`private-cloud` 是前後端分離的檔案管理系統。

實際架構：

- Backend：FastAPI
- Frontend：React/Vite
- Database：MySQL
- Cache/Session/Collaboration state：Redis
- Auth：登入後由後端設定 `session` cookie，不使用 Bearer token
- File storage：後端本機 storage path
- Realtime collaboration：WebSocket，路徑為 `/ws/collab/{file_uuid}?user_id={user_id}`

測試目標：

- 驗證系統在多人同時操作下是否穩定。
- 驗證檔案下載、刪除、上傳覆寫、分享連結在併發下是否一致。
- 驗證 WebSocket 共編在多人連線與斷線重連下是否穩定。
- 驗證 race condition 不會造成 500 error、DB 狀態錯亂、storage 殘留或分享連結失效不一致。
- 將 k6 結果輸出到 InfluxDB，並用 Grafana dashboard 視覺化。
- 產出可直接放入報告的 Markdown/JSON 結果檔。

## 2. private-cloud 實際 API 對照

### Auth

```txt
POST /api/accounts/login
```

登入成功後後端設定 `session` cookie。k6 必須使用 cookie jar，不使用 Authorization Bearer header。

### 檔案 API

```txt
GET    /api/files/list
GET    /api/files/storage
POST   /api/files/uploadFile
GET    /api/files/downloadToken?file_uuid={file_uuid}
GET    /api/files/download?file_uuid={file_uuid}&token={token}
DELETE /api/files/delete
GET    /api/files/trash
POST   /api/files/restore
```

刪除 body：

```json
{
  "file_uuid": "...",
  "permanent": false
}
```

### 分享 API

```txt
POST   /api/share/getLink
GET    /api/share/getList
DELETE /api/share/deleteLink?item_uuid={uuid}&item_type=file
GET    /api/share/downloadFile?link={share_link}
```

### 共編 API

```txt
POST   /api/collaboration/addCollaborator
DELETE /api/collaboration/removeCollaborator
GET    /api/collaboration/ownedCollaborations
GET    /api/collaboration/myCollaborations
```

### WebSocket

```txt
/ws/collab/{file_uuid}?user_id={user_id}
```

主要 WebSocket 訊息：

```json
{ "type": "y_update", "update": "base64-yjs-update" }
{ "type": "y_projection", "content": "...", "state_update": "base64-yjs-state" }
{ "type": "persist_text", "content": "...", "create_snapshot": false }
{ "type": "cursor", "cursor": { "lineNumber": 1, "column": 10 } }
{ "type": "get_snapshots" }
```

## 3. 測試資料需求

需準備：

```txt
load-tests/data/users.json
load-tests/data/files.json
load-tests/data/race-files.json
load-tests/data/share-files.json
load-tests/data/collab-files.json
load-tests/data/upload-sample-1kb.txt
load-tests/data/upload-sample-64kb.txt
load-tests/data/upload-sample-1mb.bin
```

上述資料必須由 `load-tests/scripts/seed-load-test-data.py` 產生，不得手工硬編正式資料 UUID。

`users.json`：

```json
[
  {
    "user_id": 1,
    "username": "load_user_001",
    "password": "LoadTest123!",
    "email": "load_user_001@example.test",
    "home_folder_uuid": "home-folder-uuid"
  }
]
```

`files.json`：

```json
[
  {
    "file_uuid": "existing-file-uuid",
    "owner_user_id": 1,
    "owner_username": "load_user_001",
    "filename": "load-download-001-001.txt",
    "size": 65536,
    "purpose": "download",
    "collab_enabled": true,
    "safe_for_delete_race": false
  }
]
```

`race-files.json`：

```json
[
  {
    "file_uuid": "dedicated-race-file-uuid",
    "owner_user_id": 1,
    "owner_username": "load_user_001",
    "filename": "load-race-soft-delete-0001.txt",
    "purpose": "race_soft_delete",
    "delete_mode": "soft"
  }
]
```

資料規則：

- `files.json` 用於瀏覽、下載、共編，不可被刪除。
- `share-files.json` 用於分享連結建立、分享下載與分享刪除測試。
- `collab-files.json` 用於 WebSocket 共編測試。
- `race-files.json` 必須是可被刪除的專用測試資料。
- Race 測試不得使用正式資料。
- 測試帳號需事先啟用，避免 email verification 影響登入。
- 高併發 race 測試應準備足夠多的 file UUID，避免第一輪刪除後後續只剩 404。
- 所有測試帳號必須使用 `load_user_` 前綴，所有測試檔案必須使用 `load-` 前綴，方便清理與避免誤傷正式資料。
- seed 腳本必須輸出 `seed-summary.json`，記錄生成帳號數、檔案數、race 檔案數、總大小與執行時間。

## 4. 壓測檔案結構建議

建議後續實作時新增：

```txt
private-cloud/
  load-tests/
    README.md
    k6.js
    test-matrix.md
    docker-compose.observability.yml
    data/
      users.json.example
      files.json.example
      race-files.json.example
      share-files.json.example
      collab-files.json.example
      upload-sample-1kb.txt
      upload-sample-64kb.txt
      upload-sample-1mb.bin
      seed-summary.json
    scripts/
      seed-load-test-data.py
      verify-consistency.py
      generate-report.js
    grafana/
      provisioning/
        datasources/
          influxdb.yml
        dashboards/
          dashboards.yml
      dashboards/
        private-cloud-k6-dashboard.json
    reports/
      latest/
        summary.md
        summary.json
        test-matrix-result.md
        vu-load-result.md
        race-condition-result.md
        consistency-result.md
        grafana-dashboard-screenshots/
          overview.png
          http-performance.png
          race-condition.png
          websocket.png
          consistency.png
```

## 5. k6 測試場景設計

使用 `options.scenarios`，不可只用單一 `stages`。

k6 實作必須包含以下共用 helper：

```txt
login(user): 回傳 sessionCookie 字串，不只回傳 response。
authHeaders(sessionCookie): 回傳 { Cookie: "session=..." }。
getFileList(sessionCookie, parentFolderUuid)
getDownloadToken(sessionCookie, fileUuid)
downloadFile(sessionCookie, fileUuid, token)
uploadFile(sessionCookie, samplePath, parentFolderUuid)
deleteFile(sessionCookie, fileUuid, permanent)
createShareLink(sessionCookie, fileUuid)
deleteShareLink(sessionCookie, fileUuid)
runCollabWs(user, file)
```

因本機測試保留後端 `secure=True` cookie，所有需要登入的 HTTP request 都必須手動帶入：

```js
headers: {
  Cookie: `session=${sessionCookie}`
}
```

不可假設 k6 cookie jar 會在 `http://localhost:8000` 自動回送 Secure cookie。

### 場景 A：mixed_load

模擬一般使用者操作。

操作比例：

```txt
檔案列表：40%
檔案下載：25%
檔案上傳：20%
分享/刪除分享：10%
storage 查詢：5%
```

每個 request 必須有：

- `check`
- `test_id` tag
- `operation` tag
- `resource` tag
- 5xx 自訂 metric

### 場景 B：collab_ws

模擬 WebSocket 共編。

要求：

- 連線 `/ws/collab/{file_uuid}?user_id={user_id}`
- 每秒送出 2 次共編訊息
- 維持連線 60 秒
- 隨機 5% 到 10% 連線提前中斷並重連
- 必須記錄連線成功、失敗、訊息送出、訊息接收、非正常關閉

### 場景 C：download_delete_race

測試下載與刪除同一檔案。

流程：

```txt
1. login
2. GET /api/files/downloadToken
3. 使用 http.batch 同時送出：
   - GET /api/files/download
   - DELETE /api/files/delete
4. 驗證不可出現 500
5. 驗證刪除後不可再取得新的 downloadToken
```

### 場景 D：duplicate_delete_race

多個 VU 同時刪除同一檔案。

預期：

```txt
一次 200，其餘 404 或可預期錯誤
不可 500
used_size 不可重複扣減
```

### 場景 E：same_name_upload_overwrite_race

多個 VU 同時上傳同名檔案到同一資料夾。

預期：

```txt
同 owner + parent_folder_id + filename 最多一筆 active file
used_size 不可錯誤累加
storage 不應殘留大量孤兒檔案
```

### 場景 F：share_link_delete_race

分享下載與刪除同時發生。

預期：

```txt
刪除後分享連結不可繼續下載該檔案
/api/share/getList 不應列出已刪除檔案的有效分享
不可 500
```

### 場景 G：collab_persist_delete_race

WebSocket 共編保存與檔案刪除同時發生。

預期：

```txt
刪除後不可持續寫回已刪除檔案
新的 WebSocket 連線應被拒絕或不應能正常 persist
Redis collab state 應有清理或一致性檢查
```

## 6. 測試矩陣

需建立 `load-tests/test-matrix.md`，且每個測試 ID 必須對應到 k6 tag 與 Grafana metric。

| ID | 類型 | 場景 | 操作 A | 操作 B | 測試資料 | 預期 HTTP 結果 | 一致性驗證 | Grafana Metrics |
|---|---|---|---|---|---|---|---|---|
| RACE-001 | Race | 下載 vs 軟刪除 | download | delete permanent=false | race-files.json | download 200/404/401，delete 200/404，不可 500 | list 不可見、trash 可見、不可再取得新 token | race_5xx_rate |
| RACE-002 | Race | 下載 vs 永久刪除 | download | delete permanent=true | race-files.json | download 200/404/401，delete 200/404，不可 500 | list/trash 不可見、storage 不殘留 | orphan_storage_file_count |
| RACE-003 | Race | 重複軟刪除 | delete | delete | race-files.json | 一次 200，其餘 404，不可 500 | used_size 不變、trash 狀態正確 | delete_failure_rate |
| RACE-004 | Race | 重複永久刪除 | hard delete | hard delete | race-files.json | 一次 200，其餘 404，不可 500 | used_size 不可重複扣減 | used_size_mismatch_count |
| RACE-005 | Race | 同名上傳覆寫 | upload same name | upload same name | upload sample | 200 或 409，不可 500 | 最多一筆 active file | duplicate_active_file_count |
| RACE-006 | Race | 分享下載 vs 刪除 | share download | delete | share files | 200/404，不可 500 | 分享不得指向已刪檔案 | invalid_share_link_count |
| RACE-007 | Race | downloadToken vs 刪除 | token issued | delete then download | race-files.json | old token download 404/401，不可 500 | token 不可繞過刪除狀態 | race_expected_error_count |
| RACE-008 | Race | 共編保存 vs 刪除 | WS persist_text | delete | collab files | WS 不可造成 500 | 不可寫回已刪檔案 | ws_abnormal_close_count |
| CONS-001 | Consistency | active file vs storage | DB active files | storage check | seeded files | N/A | active file 必須有實體檔案 | consistency_check_fail_count |
| CONS-002 | Consistency | permanent delete cleanup | permanent delete | DB/storage/share check | race files | delete 200/404 | DB 無 active、storage 無殘留、share 無效 | orphan_storage_file_count |
| CONS-003 | Consistency | soft delete visibility | soft delete | list/trash/token | race files | list 不可見、trash 可見、token 404 | soft delete 規則正確 | consistency_check_pass_count |

k6 request tag 格式：

```js
{
  tags: {
    test_id: 'RACE-001',
    operation: 'download',
    resource: 'file'
  }
}
```

Grafana dashboard 必須能用 `test_id` 篩選單一測試案例。

## 7. 每次請求人數與 VU 分層設計

採用分層測試，不直接從高壓開始。

| 等級 | 目的 | mixed_load | collab_ws | race_condition | 持續時間 |
|---|---:|---:|---:|---:|---:|
| Smoke | 驗證腳本/API 可跑 | 1-3 VU | 1-2 WS | 1-2 VU | 1-2 分鐘 |
| Baseline | 建立基準數據 | 10 VU | 5 WS | 5 VU | 3-5 分鐘 |
| Load | 預期正常負載 | 50 VU | 20 WS | 20 VU | 5-10 分鐘 |
| Stress | 找瓶頸 | 100-200 VU | 50-100 WS | 20-50 VU | 10-20 分鐘 |

正式預設：

```txt
一般 HTTP mixed load：50 VU 起，最高 100 VU
WebSocket 共編：20 條連線起，最高 50 條連線
Race condition：每個資源 2-5 個 VU，同時測 10-20 個資源，總 VU 20-50
```

WebSocket 共編人數矩陣：

| 模式 | 房間數 | 每房人數 | 總 WS |
|---|---:|---:|---:|
| 小型共編 | 5 | 4 | 20 |
| 中型共編 | 10 | 5 | 50 |
| 單房熱點 | 1 | 50 | 50 |
| 分散壓力 | 20 | 5 | 100 |

Race 測試人數矩陣：

| 測試 | 單檔案併發 | 同時檔案數 | 總 VU |
|---|---:|---:|---:|
| download vs delete | 2 | 10 | 20 |
| duplicate delete | 5 | 10 | 50 |
| same-name upload | 5 | 5 | 25 |
| share download vs delete | 3 | 10 | 30 |
| collab persist vs delete | 5 WS + 1 deleter | 5 | 約 30 |

## 7.1 AI 實作順序

AI 必須依下列順序實作，不可跳過前置資料與報告輸出：

```txt
1. 建立 load-tests/ 目錄結構。
2. 實作 seed-load-test-data.py，產生 users/files/race/share/collab JSON 與 upload samples。
3. 實作 verify-consistency.py，用於 DB/storage/share/used_size 後置檢查。
4. 實作 k6.js，包含 mixed_load、collab_ws、race scenarios 與 test_id tags。
5. 實作 docker-compose.observability.yml，啟動 InfluxDB + Grafana。
6. 實作 Grafana provisioning 與 private-cloud-k6-dashboard.json。
7. 實作 generate-report.js 或 k6 handleSummary，輸出 reports/latest/*.md 與 summary.json。
8. 執行 Smoke profile 驗證 seed、login、Cookie header、InfluxDB、Grafana。
9. 執行 Baseline/Load profile。
10. 若任一階段出現 500 或 consistency FAIL，停止升壓並輸出報告。
```

AI 實作完成後必須在 README.md 提供一條完整本機執行路徑：

```bash
cd backend
uv run ../load-tests/scripts/seed-load-test-data.py --users 100 --files-per-user 5 --race-files 200

cd ../load-tests
docker compose -f docker-compose.observability.yml up -d
K6_OUT=influxdb=http://localhost:8086/k6 BASE_URL=http://localhost:8000 WS_BASE_URL=ws://localhost:8000 k6 run k6.js
```

## 8. Grafana 視覺化輸出要求

必須提供可直接給 Grafana 使用的檔案：

```txt
load-tests/grafana/provisioning/datasources/influxdb.yml
load-tests/grafana/provisioning/dashboards/dashboards.yml
load-tests/grafana/dashboards/private-cloud-k6-dashboard.json
```

Grafana 必備 Panels：

```txt
HTTP Request Rate
HTTP Response Time avg / p90 / p95 / p99
HTTP Status Code 分佈
HTTP Error Rate
Race Condition 測試結果
WebSocket 連線結果
檔案 upload/download/delete/share 成功失敗數
一致性檢查 pass/fail 數量
```

必要 k6 metrics：

```js
api_5xx_rate
race_5xx_rate
race_conflict_count
race_expected_error_count
race_unexpected_error_count
ws_connect_failure_rate
ws_message_send_count
ws_message_receive_count
ws_abnormal_close_count
upload_failure_rate
download_failure_rate
delete_failure_rate
share_failure_rate
consistency_check_pass_count
consistency_check_fail_count
duplicate_active_file_count
invalid_share_link_count
used_size_mismatch_count
orphan_storage_file_count
```

Grafana 匯入方式：

```txt
方式 A：Docker Compose 啟動後自動讀取 provisioning
方式 B：手動 Import private-cloud-k6-dashboard.json
```

Docker Compose 掛載需求：

```yaml
grafana:
  image: grafana/grafana:latest
  ports:
    - "3000:3000"
  volumes:
    - ./grafana/provisioning:/etc/grafana/provisioning
    - ./grafana/dashboards:/var/lib/grafana/dashboards
```

k6 輸出方式：

```bash
K6_OUT=influxdb=http://localhost:8086/k6 \
BASE_URL=http://localhost:8000 \
WS_BASE_URL=ws://localhost:8000 \
k6 run k6.js
```

不可將 cloudflared URL 作為正式壓測入口。若需驗證 cloudflared，只能新增獨立 smoke profile，不得混入正式 Load/Stress 結果。

## 9. 報告輸出交付要求

壓測完成後必須產出：

```txt
load-tests/reports/latest/
  seed-result.md
  summary.md
  summary.json
  test-matrix-result.md
  vu-load-result.md
  race-condition-result.md
  consistency-result.md
  grafana-dashboard-screenshots/
    overview.png
    http-performance.png
    race-condition.png
    websocket.png
    consistency.png
```

`summary.md` 必須包含：

```txt
測試資料 seed 結果
測試日期
測試環境
Backend URL
DB/Redis/Storage 環境
k6 測試參數
總測試時間
總請求數
平均 RPS
HTTP p90/p95/p99
5xx 錯誤率
WebSocket 成功/失敗數
Race condition 成功/失敗數
Consistency check 成功/失敗數
最終結論 PASS / FAIL
```

`seed-result.md` 必須包含：

```txt
seed 執行時間
生成 users 數量
生成 normal files 數量
生成 share files 數量
生成 collab files 數量
生成 race files 數量
生成 upload samples 清單
所有測試帳號是否 enable=true
所有測試帳號是否 email_verified_at 不為 null
active file 是否皆有 storage 實體檔
seed 結論 PASS / FAIL
```

`test-matrix-result.md` 格式：

| ID | 場景 | 測試人數/併發 | 預期結果 | 實際結果 | Grafana Metric | 結論 |
|---|---|---:|---|---|---|---|
| RACE-001 | 下載 vs 軟刪除 | 20 VU | 不可 500，刪除後不可下載 | 實測填入 | race_5xx_rate | PASS/FAIL |

`vu-load-result.md` 格式：

| 等級 | mixed_load VU | collab_ws VU | race VU | 平均 RPS | p95 | p99 | 5xx rate | 結論 |
|---|---:|---:|---:|---:|---:|---:|---:|---|

`race-condition-result.md` 格式：

| ID | 目標資源數 | 單資源併發 | 成功數 | 預期錯誤數 | 非預期錯誤數 | 500 數 | 結論 |
|---|---:|---:|---:|---:|---:|---:|---|

`consistency-result.md` 格式：

| 檢查項目 | 檢查方式 | 預期 | 實際 | 結論 |
|---|---|---|---|---|

`summary.json` 必須為機器可讀格式：

```json
{
  "result": "PASS",
  "duration_seconds": 900,
  "seed": {
    "users": 100,
    "files": 500,
    "race_files": 200,
    "result": "PASS"
  },
  "http": {
    "requests": 120000,
    "rps_avg": 220.4,
    "p95_ms": 780,
    "p99_ms": 1300,
    "five_xx_rate": 0
  },
  "websocket": {
    "connections": 50,
    "connect_failures": 0,
    "abnormal_closes": 0
  },
  "race": {
    "total_cases": 8,
    "passed": 8,
    "failed": 0
  },
  "consistency": {
    "passed": 5,
    "failed": 0,
    "duplicate_active_file_count": 0,
    "orphan_storage_file_count": 0,
    "invalid_share_link_count": 0,
    "used_size_mismatch_count": 0
  }
}
```

## 10. 驗收標準

測試計劃交付驗收：

```txt
1. 有完整 Markdown 計劃文件。
2. 明確列出 AI 實作邊界。
3. 明確列出本機 localhost 測試入口。
4. 明確列出測試帳號與假檔案 seed 邏輯。
5. 明確列出 private-cloud 實際 API 與限制。
6. 明確列出 k6 場景。
7. 明確列出測試矩陣。
8. 明確列出每個場景的人數/VU 設計。
9. 明確列出 Grafana 可直接使用的 dashboard/provisioning 檔案。
10. 明確列出報告輸出格式。
11. 明確列出 PASS/FAIL 判定標準。
```

後續壓測實作驗收：

```txt
seed-load-test-data.py 可重複執行且不刪除正式資料
所有 load_user_* 帳號可登入
本機 HTTP 測試保留 secure=True cookie 現狀，並由 k6 手動帶 Cookie header
HTTP 5xx rate = 0
Race scenario 5xx rate = 0
WebSocket connect failure rate < 2%
一般列表不顯示 soft-deleted file
Trash 顯示 soft-deleted file
Permanent delete 後 storage 不殘留
同名上傳後最多一筆 active file
分享連結不可指向已刪除檔案
download token 不可繞過刪除狀態
used_size 不可小於 0 或重複扣減
每個測試 ID 都能在 Grafana 中篩選
每個測試 ID 都有報告 PASS/FAIL
```

## 11. 已知風險、預期測試失敗點與禁止修復範圍

本章列出的項目是壓測與一致性測試「可能會發現的問題」，目的在於讓測試腳本能正確偵測、記錄並輸出報告。

除非使用者另行明確下達「修復後端」指令，否則 AI 在本計劃實作階段不得修改 backend/frontend 業務邏輯。

### 11.1 已知風險與可能測試失敗點

目前 private-cloud 需特別關注下列風險。這些風險可能造成部分測試案例 FAIL，但 FAIL 本身即為本計劃需要產出的測試發現：

```txt
1. 本機 HTTP 測試保留 secure=True cookie，k6 必須手動帶 Cookie header。
2. WebSocket 使用 user_id query string，目前未明確套用 session 驗證。
3. WebSocket handler 中有 _check_permission，但目前流程未明確呼叫。
4. 同名上傳覆寫流程若缺少 transaction/lock，可能產生重複 active file 或 used_size 錯誤。
5. hard delete 若併發執行，可能造成 used_size 重複扣減。
6. download token 存於 Redis，需驗證 token 不會繞過 DB file state。
7. permanent delete 後需考慮 Redis collab_content / collab_yupdates / download token 清理。
8. 分享連結需與 file.deleted_at 狀態保持一致。
9. cloudflared 不作為正式壓測入口，只可做 smoke 驗證。
```

### 11.2 測試腳本應如何處理這些風險

測試實作時必須偵測、保留並報告上述風險，不得為了得到 PASS 而修改後端或降低標準。

```txt
1. 測試腳本必須偵測上述風險是否發生。
2. 測試腳本必須將結果寫入 reports/latest/*.md 與 summary.json。
3. 若發現 500、資料不一致、重複 active file、storage orphan、used_size mismatch，應標記為 FAIL。
4. 若發現 WebSocket 權限未驗證、刪除後仍可 persist，應標記為 FAIL 或風險發現。
5. 若 cloudflared smoke 測試被限流或中斷，不可混入本機正式壓測結果。
6. 不得在測試腳本、seed 腳本或 report generator 中修改後端程式來讓測試通過。
7. 不得刪除失敗資料或重跑到 PASS 後才輸出報告；若重跑，需保留重跑前後紀錄。
```

報告中必須用下列分類說明測試結果：

```txt
PASS：行為符合預期。
FAIL：行為不符合預期，例如 500、資料不一致、權限繞過。
EXPECTED_ERROR：404/401/409 等可接受業務錯誤。
ENVIRONMENT_LIMITATION：例如 cloudflared smoke 限流、k6 未安裝、InfluxDB 未啟動。
KNOWN_RISK：測到已知風險，但此輪不修復，只列入改善建議。
```

### 11.3 後續可能的後端改善方向，僅供報告建議

以下內容只可作為測試報告中的「建議改善方向」，不得在本次壓測工具實作中直接執行：

```txt
1. 對 delete / overwrite 使用 DB transaction。
2. 對同一 file_uuid 使用 row-level lock，例如 SELECT ... FOR UPDATE。
3. 對 owner_id + parent_folder_id + filename 建立 active file 唯一性保護。
4. 刪除檔案時同步清理 share link、collaboration state、download token。
5. permanent delete 時加入 DB/storage 補償或一致性檢查。
6. race conflict 應回 404 或 409，不可回 500。
d 

## 12. AI 交付完成定義

AI 完成實作時，必須能交付下列成果：

```txt
load-tests/README.md
load-tests/k6.js
load-tests/test-matrix.md
load-tests/docker-compose.observability.yml
load-tests/scripts/seed-load-test-data.py
load-tests/scripts/verify-consistency.py
load-tests/scripts/generate-report.js 或 k6 handleSummary
load-tests/data/*.json.example
load-tests/grafana/provisioning/datasources/influxdb.yml
load-tests/grafana/provisioning/dashboards/dashboards.yml
load-tests/grafana/dashboards/private-cloud-k6-dashboard.json
load-tests/reports/latest/summary.md
load-tests/reports/latest/summary.json
```

完成後必須能回答：

```txt
1. 測試帳號是否已成功生成並可登入？
2. 假檔案是否同時存在於 DB 與 storage？
3. k6 是否可在 localhost + secure=True cookie 現狀下完成登入後 API？
4. Grafana 是否可直接載入 dashboard 並看到 k6 metrics？
5. 測試矩陣每一列是否都有 PASS / FAIL？
6. 人數測試是否有 Smoke / Baseline / Load / Stress 結果？
7. Race condition 與 consistency failure 是否有明確報告？
8. 是否確認本次實作未修改 backend/frontend/alembic/db docker-compose？
```

交付報告必須附上 scope confirmation：

```txt
本次僅新增/修改 load-tests 相關檔案。
未修改 backend/frontend/alembic/db docker-compose。
測得的後端問題僅列為報告發現與改善建議，未在本次壓測工具實作中修復。
```
