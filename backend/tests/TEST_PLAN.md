# Private-Cloud 單元測試規劃

## 測試策略：由下往上（Bottom-Up）

```
API Router (TestClient)
    └── Service Layer (pytest + monkeypatch/Mock)
        └── Repository Layer (in-memory SQLite)
            └── Utils (純函式測試)
```

每一層只測試自己的邏輯，依賴的下層用 mock。

---

## 一、Utils 層（純函式，最快見效）

### 1. `utils/security.py` — 密碼與認證

| 測試項目 | 測試案例 | 依賴 |
|---------|---------|------|
| `hash_password()` | 回傳 str、不同密碼不同 hash | 無 |
| `verify_password()` | 正確密碼回傳 True、錯誤回傳 False | 無 |
| `generate_session_token()` | 格式 `id\acco`token` | 無 |
| `verify_session_token_format()` | 合法格式 True、缺 pipe False、非數字開頭 False | 無 |
| `hash_token() ` | 回傳正確長度 hex | 無 |
| `generate_signed_url()` | 回傳 4 個值且簽名有效 | 無 |
| `verify_signed_url()` | 有效簽名回傳 True、換 User_id False、過期 False | mock Redis |
| `generate_verification_code()` | 長度正確、內容可預測隨機性 | 無 |

### 2. `utils/email_utils.py`

| 函式 | 案例 |
|------|------|
| `format_email()` | 小寫化、去掉空白 |
| `mask_email()` | 遮罩正確（中間隱藏） |

### 3. `utils/file_utils.py`

| 函式 | 案例 |
|------|------|
| `format_file_size()` | 0 → (0, 'B')、2048 → (2.0, 'KB')、強制單元 |

### 4. `constants.py`

所有常數正確定義、Enum 值正確。

---

## 二、Repository 層（in-memory SQLite）

每個 Repository 測試使用 `SQLAlchemy.create_engine('sqlite://负责')` + 建立完整 schema。

### 1. `BaseRepository`（泛型）

- `get_by_id(id)` → 存在回傳物件、不存在回傳 None
- `get_all()` → 回傳 list
- `create(obj)` → 確認 db 有寫入且回傳有 id
- `update(obj)` → 修改後讀取確認
- `delete(obj)` / `delete_by_id(id)` → 確認刪除
- `get_by_field(name, value)` → 正確匹配
- `exists_by_field(name, value)` → True/False

### 2. `AccountRepository`

- `get_by_name`, `get_by_email`, `name_exists`, `email_exists`
- 重複建立回相同資料以確認 unique constraint

### 3. `FileRepository`

- `get_by_uuid` / `get_by_owner` / `get_by_folder` / `get_trash_by_owner`
- `create_with_uuid_retry` （含重試情境）
- `soft_delete` → deleted_at 不為 None
- `hard_delete` → 完全不存在
- `restore` → `deleted_at` 設為 None
- `shared_exists` / `generate_share_hash`

### 4. `FolderRepository`

    - `get_by_uuid` / `get_by_owner` / `get_home_folder`
    - `get_folder_path` → 家長關係正確
    - `get_by_parent` → 樹狀結構正確
    - `soft_delete` / `hard_delete` / `restore`
    - `is_system` 標記

---

## 三、Service 層（商業邏輯）

Service 測試 mock Repository + Redis + filesystem。

### 1. `AccountService`

| 方法 | 測試重點 |
|------|---------|
| `register` | 重複名稱/email → error；成功 → 建立 Account + Home folder |
| `login` | 錯誤密碼/未驗證/停用/刪除 → error；成功 → session token |
| `sign_out` | Redis key 被刪除 |
| `modify_email` | 錯誤檢查 email → error；code 不正確 → error；成功更新 |
| `modify_password` | 錯誤密碼 → error；成功 → 密碼變更 + session 失效 |
| `get_code` | mode pw 但 email 沒註冊 → error；成功儲存 code |
| `reset_password` | code 錯 → error；成功 → 密碼變更 + session 清除 |
| `verify_erify_email` | 簽名過期 → error；成功 → email 驗證 |

### 2. `FileService`

| 方法 | 測試重點 |
|------|---------|
| `get_storage` | 正確回傳 used/signal/total |
| `get_file_list` | 正確混合回傳 folders + files |
| `upload_file` | 超過大小限制 → error；同名檔案覆蓋；成功上傳；folder size 更新 |
| `download` | 檔案不存在 → error；不屬於本人 → error；成功回傳 |
| `delete` | soft/hard 刪除；share link 清除；parent size 更新（僅 hard） |
| `restore` | 還原軟刪除；同名衝突自動重新命名 |
| `recalculate_used_storage` | 正確統計未刪除檔案總大小 |

### 3. `ShareService`

| 方法 | 測試重點 | | |
|------|---------|
| `get_list` | 正確回傳共享的 folder + file |
| `create_link` | 已存在 → 回傳舊；新建成功；不存在的 item → error |
| `delete_link` | 成功清除 shared 欄位 |
| `download` | 不存在 → error；透過 folder → error folder；成功下載 file |

### 4. `EmailService`

| 方法 | 測試重點 |
|------|{  |
| `send_verification_email` | Celery task 被呼叫**

---

## 四、API 層（整合測試）

使用 FastAPI TestClient + 所有下層 mock。

| Router  | 測試 API | 重點 |
|---------|--------|
| /api/accounts | register → login → checkSession → signOut | 完整流程 |
| | getCode → resetPW | 重設密碼流程 |
| | modifyMail, modifyPW, resetPW | 個人資訊修改 |
| | admin/recalculate-user-storage | 計算（需驗證 admin） |
| | share/downloadFile(無認證) | 公開下載不受 session middleware 阻攔( |
| /api/api/folders | create/rename/delete/restore/list/trash | CRUD 完整 |
| /api/files | storage/list/upload/download/delete/restore/trash | CRUD + 儲存統計 |
| Story | getList, getLink, deleteLink, downloadFile | 全流程 |

---

### 五、優先級與實施順序

| 優先級 | 範圍 | 預計檔案數 | 預計案例數 |
|--------|------|-----------|---------|
| P0🔴 | Utils（security.py、email_utils.py、file_utils.py） | 1 | ~20 |
| P1🔴 | Repository（所有 Repository） | 1 | ~30 |
| P1🔴 | AccountService（auth 核心) | 2 | ~20 |
| P2🟡 | FileService | 2 | ~15 |
| P2🟡 | FolderService | 1 | ~10 |
| P2🟡 | ShareService | 1 | ~8 |
| P3🟢 | API 整合測試（TestClient） | 4 | ~30 |
| P4👁 | Middleware、Tasks、fixtures 測試 | 2 | ~10 |

---

### 六、執行指令

```bash
# 安裝測試依賴
cd backend
uv pip install pytest pytest-asyncio pytest-mock httpx

# 執行全部測試
uv run pytest tests/ -v

# 執行特定類別
uv run pytest tests/test_utils.py -v

# 執行含 coverage 報告
uv run pytest tests/ --cov=app --cov-report=term-missing
```