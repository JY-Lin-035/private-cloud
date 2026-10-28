import { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Breadcrumb from './Breadcrumb';
import {
  downloadFile,
  deleteFile,
  getShareFileLink,
  deleteShareFileLink,
} from '../../utils/fileOperations';
import {
  createFolder,
  renameFolder,
  deleteFolder,
} from '../../utils/folderOperations';
import Notices from '../../components/Notices';
import { useStorage } from '../../store/storage';
import { fileApi } from '../../api/fileApi';
import { folderApi } from '../../api/folderApi';
import UpLoad from './UpLoad';

import {
  FolderOpen,
  FileText,
  Download,
  Share2,
  Link2,
  Trash2,
  Edit3,
  Plus,
  Upload,
  ChevronLeft,
  ChevronRight,
  ListChecks,
  FolderDown,
  FilePlus
} from 'lucide-react';
import { lazy, Suspense } from 'react';
const FileOpener = lazy(() => import('../../components/preview/FileOpener'));
import { previewApi } from '../../api/previewApi';
import { isEditable } from '../../utils/fileClass';



function parseSize(v: any): number {
  if (typeof v === 'number') return v;
  if (typeof v !== 'string' || !v.trim()) return 0;
  const [num, unit] = v.trim().split(' ');
  const n = Number(num);
  if (Number.isNaN(n)) return 0;
  const units: { [key: string]: number } = { B: 0, KB: 1, MB: 2, GB: 3, TB: 4 };
  const exp = units[(unit ?? 'B').toUpperCase()];
  return exp === undefined ? n : n * Math.pow(1024, exp);
}

function parseTime(v: any): number {
  if (typeof v === 'number') return v;
  const t = Date.parse(String(v ?? '').replace(' ', 'T'));
  return Number.isNaN(t) ? 0 : t;
}

function FileList({ layoutClass = "" }: { layoutClass?: string }) {
  const navigate = useNavigate();
  const { folderUuid } = useParams();
  const storage = useStorage();
  const [showUpLoad, setShowUpLoad] = useState(false);
  const [fileList, setFileList] = useState<any[]>([]);
  const [IN, setIN] = useState(false);
  const [search, setSearch] = useState('');
  const [sortType, setSortType] = useState('name');
  const [sortUpDown, setSortUpDown] = useState(true);
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(10);
  const [previousPerPage, setPreviousPerPage] = useState(10);
  const [showMode, setShowMode] = useState(false);
  const [className, setClassName] = useState('');
  const [response, setResponse] = useState<string | string[]>([]);
  const [shareFileLink, setShareFileLink] = useState('');
  const [copyShow, setCopyShow] = useState(false);
  const [popupItemUuid, setPopupItemUuid] = useState<string | null>(null);
  const [folderNameInput, setFolderNameInput] = useState('');
  const [inputShow, setInputShow] = useState(false);
  const [waitFolderName, setWaitFolderName] = useState<any[]>([]);
  const [currentFolderUuid, setCurrentFolderUuid] = useState<string | null>(null);
  const [previewOn, setPreviewOn] = useState(false);
  const [opener, setOpener] = useState<{ uuid: string; name: string } | null>(null);
  const [newFileModal, setNewFileModal] = useState(false);
  const [newFileName, setNewFileName] = useState('');

  // Share modal state
  const [showShareModal, setShowShareModal] = useState(false);
  const [shareItemUuid, setShareItemUuid] = useState<string | null>(null);
  const [shareItemType, setShareItemType] = useState<string>('');
  const [shareLimitedDate, setShareLimitedDate] = useState<string>('');
  const [shareIsLimited, setShareIsLimited] = useState(false);
  const [shareUsePassword, setShareUsePassword] = useState(false);
  const [sharePassword, setSharePassword] = useState('');

  // Selection mode state (checkboxes only visible when active)
  const [selectionMode, setSelectionMode] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [moveOpen, setMoveOpen] = useState(false);
  const [movePath, setMovePath] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    previewApi.authedFlags().then((f) => setPreviewOn(!!f?.enable_file_preview));
  }, []);

  async function newTextFile() {
    const name = newFileName.trim();
    if (!name) return;
    try {
      const res = await previewApi.createText(name, currentFolderUuid);
      setNewFileModal(false);
      setNewFileName('');
      await getFileList(currentFolderUuid);
      setOpener({ uuid: res.uuid, name: res.name });
    } catch (e: any) {
      setResponse([e?.message ?? '建立失敗']);
      setClassName('text-red-500');
      setShowMode(true);
    }
  }

  async function getFileList(parent_folder_uuid: string | null) {
    try {
      const r = await fileApi.list(parent_folder_uuid || undefined);
      setFileList(r.files || []);
      setCurrentFolderUuid(parent_folder_uuid);
    } catch (e) {
      try {
        const homeFolder = await folderApi.getHome();
        setCurrentFolderUuid(homeFolder.uuid);
        navigate(`/file-list/${homeFolder.uuid}`, { replace: true });
      } catch {
        localStorage.clear();
        navigate('/');
      }
    }
  }

  useEffect(() => {
    async function loadInitialFolder() {
      if (folderUuid !== undefined) {
        await getFileList(folderUuid || null);
      } else {
        // Load Home folder when no UUID provided
        try {
          const homeFolder = await folderApi.getHome();
          getFileList(homeFolder.uuid);
          navigate(`/file-list/${homeFolder.uuid}`, { replace: true });
        } catch (e) {
          localStorage.clear();
          navigate('/');
        }
      }
    }
    loadInitialFolder();
  }, [folderUuid]);

  useEffect(() => {
    setTimeout(() => {
      setIN(true);
    }, 200);
  }, []);

  const filterList = useMemo(() => {
    setPage(1);
    let fList = fileList.filter((f) =>
      f.name.toLowerCase().includes(search.toLowerCase())
    );

    fList.sort((a, b) => {
      if (a.type === 'folder' && b.type !== 'folder') return -1;
      if (a.type !== 'folder' && b.type === 'folder') return 1;

      const dir = sortUpDown ? 1 : -1;

      if (sortType === 'size') {
        return (parseSize(a.size) - parseSize(b.size)) * dir;
      }

      if (sortType === 'date') {
        return (parseTime(a.date) - parseTime(b.date)) * dir;
      }

      return String(a[sortType] ?? '')
        .localeCompare(String(b[sortType] ?? ''), 'zh-CN', { numeric: true }) * dir;
    });

    return fList;
  }, [fileList, search, sortType, sortUpDown]);

  function changeSortType(type: string) {
    if (sortType === type) {
      setSortUpDown(!sortUpDown);
    } else {
      setSortType(type);
      setSortUpDown(type !== 'date');
    }
  }

  const selectedFiles = selected.filter(k => k.startsWith('file:')).map(k => k.slice(5));
  const selectedFolders = selected.filter(k => k.startsWith('folder:')).map(k => k.slice(7));

  function toggleSelectionMode() {
    setSelectionMode(v => !v);
    setSelected([]);
  }

  function toggleItem(item: any) {
    const key = `${item.type}:${item.uuid}`;
    setSelected(prev => prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]);
  }

  const allSelected = filterList.length > 0 && selected.length === filterList.length;

  function toggleSelectAll() {
    setSelected(allSelected ? [] : filterList.map(i => `${i.type}:${i.uuid}`));
  }

  async function batchDelete() {
    if (!selected.length || busy) return;
    if (!window.confirm(`確定要將選取的 ${selected.length} 項目移入資源回收筒？`)) return;
    setBusy(true);
    try {
      const res = await fileApi.batchOp({ folders: selectedFolders, files: selectedFiles, mode: 'soft' });
      setResponse([`已將 ${res.folders + res.files} 個項目移入資源回收筒`,
                   ...(res.skipped.length ? [`跳過 ${res.skipped.length} 項`] : [])]);
      setClassName('text-green-500');
      setShowMode(true);
      await getFileList(currentFolderUuid);
    } catch (e: any) {
      setResponse([e?.message ?? '批次刪除失敗']);
      setClassName('text-red-500');
      setShowMode(true);
    }
    setSelected([]);
    setSelectionMode(false);
    setBusy(false);
  }

  async function batchDownload() {
    if (!selected.length || busy) return;
    setBusy(true);
    try {
      if (selectedFiles.length === 1 && !selectedFolders.length) {
        await fileApi.download(selectedFiles[0]);
      } else if (selectedFolders.length === 1 && !selectedFiles.length) {
        const it = filterList.find(i => `folder:${i.uuid}` === selected[0]);
        await fileApi.downloadFolderZip(selectedFolders[0], it?.name ?? 'folder');
      } else {
        await fileApi.downloadBulk(selectedFiles, selectedFolders);
      }
    } catch (e: any) {
      setResponse([e?.message ?? '下載失敗']);
      setClassName('text-red-500');
      setShowMode(true);
    }
    setBusy(false);
  }

  async function confirmMove() {
    const target = movePath.trim();
    if (!target || busy) return;
    setBusy(true);
    try {
      let renamed = 0;
      const failed: { name: string; reason: string }[] = [];
      if (selectedFiles.length) {
        const r = await fileApi.moveFiles({ file_uuids: selectedFiles, target_path: target });
        renamed += Object.keys(r.renamed || {}).length;
        failed.push(...(r.failed || []));
      }
      if (selectedFolders.length) {
        const r = await fileApi.moveFolders({ folder_uuids: selectedFolders, target_path: target });
        renamed += Object.keys(r.renamed || {}).length;
        failed.push(...(r.failed || []));
      }
      const movedCount = selectedFiles.length + selectedFolders.length - failed.length;
      if (failed.length) {
        setResponse([`已移動 ${movedCount} 項；失敗：`, ...failed.map(f => `${f.name}（${f.reason}）`)]);
        setClassName('text-red-500');
      } else {
        setResponse([`已移動 ${movedCount} 項到 ${target}`, ...(renamed ? [`其中 ${renamed} 項因名稱重複已自動改名`] : [])]);
        setClassName('text-green-500');
      }
      setShowMode(true);
      setMoveOpen(false);
      setMovePath('');
      await getFileList(currentFolderUuid);
      setSelected([]);
      setSelectionMode(false);
    } catch (e: any) {
      setResponse([e?.message ?? '移動失敗']);
      setClassName('text-red-500');
      setShowMode(true);
    }
    setBusy(false);
  }

  const totalPages = useMemo(() =>
    Math.ceil(filterList.length / perPage),
    [filterList.length, perPage]
  );

  const pageList = useMemo(() => {
    if (perPage > previousPerPage) {
      setPage(1);
      setPreviousPerPage(perPage);
    } else {
      setPreviousPerPage(perPage);
    }
    const start = (page - 1) * perPage;
    return filterList.slice(start, start + perPage);
  }, [perPage, previousPerPage, page, filterList]);

  async function callDownloadFile(file_uuid: string) {
    const [res, cn, show] = await downloadFile(file_uuid);
    setResponse(res);
    setClassName(cn);
    setShowMode(show);
    setInputShow(false);
  }

  async function callDeleteFile(item_uuid: string, _item_type: string, item: any) {
    const [res, cn, show, fl] = await deleteFile(item_uuid, item, fileList);
    setResponse(res);
    setClassName(cn);
    setShowMode(show);
    setInputShow(false);
    setFileList([...fl]);
  }

  // Open share modal
  function openShareModal(item_uuid: string, item_type: string) {
    setShareItemUuid(item_uuid);
    setShareItemType(item_type);
    setShareIsLimited(false);
    setShareLimitedDate('');
    setShareUsePassword(false);
    setSharePassword('');
    setShowShareModal(true);
  }

  // Confirm share from modal
  async function confirmShare() {
    console.log('confirmShare called', { shareItemUuid, shareItemType, shareIsLimited, shareLimitedDate });
    if (!shareItemUuid) {
      console.error('shareItemUuid is null');
      return;
    }

    let limitedDateStr: string | null = null;
    let displayLimitedDate: string | null = null;
    if (shareIsLimited && shareLimitedDate) {
      // Send the raw datetime-local value (YYYY-MM-DDTHH:MM) and let backend parse it
      limitedDateStr = shareLimitedDate + ':00';  // Add seconds: YYYY-MM-DDTHH:MM:SS
      // Format for display: YYYY-MM-DD HH:MM:SS
      const [datePart, timePart] = shareLimitedDate.split('T');
      displayLimitedDate = `${datePart} ${timePart}:00`;
    }
    
    console.log('Calling getShareFileLink with:', { shareItemUuid, shareItemType, limitedDateStr });

    if (shareUsePassword && !sharePassword) {
      setResponse(['請輸入密碼，或取消勾選密碼保護。']);
      setClassName('text-red-500');
      setShowMode(true);
      return;
    }
    const passwordToSend = shareUsePassword ? sharePassword : '';

    const [res, cn, show, link, copy] = await getShareFileLink(shareItemUuid, shareItemType, limitedDateStr, passwordToSend);
    console.log('getShareFileLink returned', { res, cn, show, link, copy });
    
    setResponse(res);
    setClassName(cn);
    setShowMode(show);
    setInputShow(false);
    setShareFileLink(link);
    setCopyShow(copy);
    setPopupItemUuid(shareItemUuid);
    setShowShareModal(false);
    if (link) {
      setFileList(prev => prev.map(f => f.uuid === shareItemUuid ? { ...f, shared: link, limited_date: displayLimitedDate } : f));
    }
  }

  async function callShareFileLink(item_uuid: string, item_type: string, existingLink?: string | null, limitedDate?: string | null) {
    // Check if link is expired (has limited_date that has passed)
    const isExpired = limitedDate ? new Date(limitedDate) < new Date() : false;
    
    if (existingLink && !isExpired) {
      // Has a valid share link → show copy/remove popup directly
      setShareFileLink(existingLink);
      setCopyShow(true);
      setPopupItemUuid(item_uuid);
    } else {
      // No link or link is expired → open modal to let user choose limited/unlimited
      openShareModal(item_uuid, item_type);
    }
  }

  async function callDeleteShareFileLink(item_uuid: string, item_type: string) {
    const [res, cn, show] = await deleteShareFileLink(item_uuid, item_type);
    setResponse(res);
    setClassName(cn);
    setShowMode(show);
    setInputShow(false);
    setCopyShow(false);
    setPopupItemUuid(null);
    setFileList(prev => prev.map(f => f.uuid === item_uuid ? { ...f, shared: null } : f));
  }

  const copyFunc = (m: string) => {
    const text = window.location.origin + '/share/' + m;
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    try {
      document.execCommand('copy');
      setResponse(['連結已複製!']);
      setClassName('text-green-500');
      setShowMode(true);
    } catch {
      setResponse(['複製失敗，請手動複製']);
      setClassName('text-red-500');
      setShowMode(true);
    }
    document.body.removeChild(textarea);
  };

  async function emitFolderName() {
    if (waitFolderName[2] === 'rename') {
      const [res, cn, fl] = await renameFolder(
        waitFolderName[1], // folder_uuid
        folderNameInput,
        fileList
      );
      setResponse(res);
      setClassName(cn);
      setFileList([...fl]);
    } else if (waitFolderName[2] === 'create') {
      const [res, cn, fl] = await createFolder(
        waitFolderName[0] || null, // parent_folder_uuid
        folderNameInput,
        fileList
      );
      setResponse(res);
      setClassName(cn);
      setFileList([...fl]);
    }

    setShowMode(true);
  }

  async function callDeleteFolder(folder_uuid: string) {
    const [res, cn, show, fl] = await deleteFolder(folder_uuid, fileList);
    setResponse(res);
    setClassName(cn);
    setShowMode(show);
    setInputShow(false);
    setFileList([...fl]);
  }

  return (
    <div
      onClick={() => { setCopyShow(false); setPopupItemUuid(null); }}
      className={`flex w-full h-full flex-col justify-center items-center ${layoutClass}`}
    >
      <Notices
        inputShow={inputShow}
        folderName={folderNameInput}
        notices={response}
        showMode={showMode}
        className={className}
        onUpdateFolderName={setFolderNameInput}
        onClose={() => { setShowMode(false); setFolderNameInput(''); setWaitFolderName([]); }}
        onEmitFolderName={() => { setShowMode(false); setInputShow(false); emitFolderName(); }}
      />

      {/* Share Modal */}
      {showShareModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="fixed inset-0 bg-black/50"
            onClick={() => setShowShareModal(false)}
          ></div>
          <div className="relative z-10 w-full max-w-[40vw] max-h-[80vh] overflow-y-auto p-6 rounded-lg shadow-xl bg-gray-800">
            <button
              onClick={() => setShowShareModal(false)}
              className="absolute top-3 right-2.5 text-gray-400 bg-transparent hover:bg-gray-700 hover:text-white rounded-lg text-sm w-8 h-8 flex items-center justify-center"
            >
              <svg className="w-3 h-3" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 14 14">
                <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="m1 1 6 6m0 0 6 6M7 7l6-6M7 7l-6 6" />
              </svg>
            </button>

            <div className="p-4 text-center md:p-5 text-white">
              <div className="w-12 h-12 mx-auto mb-6 flex items-center justify-center">
                <span className="text-3xl">🔗</span>
              </div>

              <h3 className="mb-5 text-xl font-normal text-white">分享設定</h3>

              <div className="mb-4 text-left">
                <label className="flex items-center gap-2 cursor-pointer text-white">
                  <input
                    type="radio"
                    name="shareType"
                    checked={!shareIsLimited}
                    onChange={() => setShareIsLimited(false)}
                  />
                  <span>不限時分享（永久有效）</span>
                </label>
              </div>

              <div className="mb-4 text-left">
                <label className="flex items-center gap-2 cursor-pointer text-white">
                  <input
                    type="radio"
                    name="shareType"
                    checked={shareIsLimited}
                    onChange={() => setShareIsLimited(true)}
                  />
                  <span>限時分享</span>
                </label>
                {shareIsLimited && (
                  <div className="mt-2 ml-6 text-left">
                    <label className="block text-sm text-gray-400 mb-1">到期日期與時間</label>
                    <input
                      type="datetime-local"
                      value={shareLimitedDate}
                      onChange={(e) => setShareLimitedDate(e.target.value)}
                      className="w-full px-3 py-2 mt-2 mb-2 border rounded bg-white text-gray-900 border-gray-300"
                      min={new Date().toISOString().slice(0, 16)}
                    />
                  </div>
                )}
              </div>

              <div className="mb-4 text-left">
                <label className="flex items-center gap-2 cursor-pointer text-white">
                  <input
                    type="checkbox"
                    checked={shareUsePassword}
                    onChange={(e) => setShareUsePassword(e.target.checked)}
                  />
                  <span>密碼保護</span>
                </label>
                {shareUsePassword && (
                  <div className="mt-2 ml-6 text-left">
                    <label className="block text-sm text-gray-400 mb-1">訪客需輸入此密碼才能下載</label>
                    <input
                      type="password"
                      value={sharePassword}
                      onChange={(e) => setSharePassword(e.target.value)}
                      placeholder="設定分享密碼"
                      className="w-full px-3 py-2 mt-2 mb-2 border rounded bg-white text-gray-900 border-gray-300"
                      autoComplete="new-password"
                    />
                  </div>
                )}
                <p className="mt-1 ml-6 text-xs text-gray-500">
                  取消勾選並重新產生連結，將移除既有密碼。
                </p>
              </div>

              <button
                onClick={confirmShare}
                type="button"
                className="text-white bg-blue-600 hover:bg-blue-500 focus:ring-4 focus:outline-none focus:ring-blue-300 font-medium rounded-lg text-lg inline-flex items-center justify-center px-5 py-2.5 mt-6 text-center"
              >
                產生分享連結
              </button>
            </div>
          </div>
        </div>
      )}

      {newFileModal && (
        <Notices
          inputShow
          folderName={newFileName}
          notices={['新建文字檔案']}
          showMode
          className=""
          placeholder="例：notes.md"
          extraValidate={(v) => (isEditable(v) ? null : '請使用支援的副檔名（.txt .md .py .json .html .css ...）')}
          onClose={() => { setNewFileModal(false); setNewFileName(''); }}
          onUpdateFolderName={setNewFileName}
          onEmitFolderName={newTextFile}
        />
      )}

      {opener && (
        <Suspense fallback={<div className="fixed inset-0 z-[80] bg-black/70 flex items-center justify-center text-gray-300">載入編輯器…</div>}>
          <FileOpener
            uuid={opener.uuid}
            filename={opener.name}
            onClose={() => setOpener(null)}
            onSaved={() => { void getFileList(currentFolderUuid); }}
          />
        </Suspense>
      )}

      {showUpLoad && (
        <>
          {/* 使用 Uppy 上傳組件 */}
          <UpLoad
            parentFolderUuid={currentFolderUuid}
            onHidden={() => setShowUpLoad(false)}
            onRefresh={() => getFileList(currentFolderUuid)}
            onComplete={(res, cn) => {
              setResponse(res);
              setClassName(cn);
              setShowMode(true);
              setInputShow(false);
            }}
          />
        </>
      )}

      {selectionMode && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-40 flex items-center gap-2 px-4 py-3 rounded-xl bg-gray-800 text-white shadow-2xl border border-gray-600 w-[92vw] max-w-[560px] justify-between">
          <span className="text-sm whitespace-nowrap">已選 {selected.length} 項</span>
          <span className="flex gap-2">
            <button
              onClick={toggleSelectAll}
              className="px-3 py-1.5 rounded text-sm bg-gray-600 hover:bg-gray-500 cursor-pointer"
            >
              {allSelected ? '取消全選' : '一鍵全選'}
            </button>
            <button
              onClick={() => selected.length && setMoveOpen(true)}
              disabled={!selected.length || busy}
              className="px-3 py-1.5 rounded text-sm bg-blue-600 hover:bg-blue-500 disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed"
            >
              移動
            </button>
            <button
              onClick={batchDownload}
              disabled={!selected.length || busy}
              className="px-3 py-1.5 rounded text-sm bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed"
            >
              下載
            </button>
            <button
              onClick={batchDelete}
              disabled={!selected.length || busy}
              className="px-3 py-1.5 rounded text-sm bg-red-600 hover:bg-red-500 disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed"
            >
              刪除
            </button>
            <button
              onClick={toggleSelectionMode}
              className="px-3 py-1.5 rounded text-sm bg-gray-600 hover:bg-gray-500 cursor-pointer"
            >
              離開
            </button>
          </span>
        </div>
      )}

      {moveOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="fixed inset-0 bg-black/50" onClick={() => setMoveOpen(false)}></div>
          <div className="relative z-10 w-full max-w-[420px] p-6 rounded-lg shadow-xl bg-gray-800 text-white">
            <h3 className="text-lg font-semibold mb-2">移動 {selected.length} 個項目</h3>
            <p className="text-sm text-gray-400 mb-3">
              輸入相對 Home 的目標路徑（例：照片/2026/台東）。
              不存在的資料夾會自動建立；名稱重複的項目將自動改名。
            </p>
            <input
              type="text"
              value={movePath}
              onChange={(e) => setMovePath(e.target.value)}
              placeholder="目標路徑"
              className="w-full px-3 py-2 rounded bg-white text-gray-900 border border-gray-300"
              autoFocus
            />
            <div className="mt-5 flex justify-end gap-2">
              <button
                onClick={() => { setMoveOpen(false); setMovePath(''); }}
                className="px-4 py-2 rounded bg-gray-600 hover:bg-gray-500 cursor-pointer"
              >
                取消
              </button>
              <button
                onClick={confirmMove}
                disabled={!movePath.trim() || busy}
                className="px-4 py-2 rounded bg-blue-600 hover:bg-blue-500 disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed"
              >
                {busy ? '處理中…' : '移動'}
              </button>
            </div>
          </div>
        </div>
      )}

      <Breadcrumb currentFolderUuid={currentFolderUuid} />

      <div
        className={`w-[95vw] sm:w-[90vw] md:w-[80vw] lg:w-[75vw] xl:w-[70vw] mx-auto mt-[1%] flex-1 transition-all duration-[900ms] ease-in-out ${IN ? 'opacity-100' : 'opacity-0'}`}
      >
        <div className="mb-4 flex justify-between items-center">
          <span>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              type="text"
              placeholder="搜尋"
              className="border border-white rounded px-3 py-1 w-full sm:w-64"
            />

            <Plus
              className="w-9 h-9 ml-6 mr-4 text-yellow-300 inline cursor-pointer"
              onClick={() => {
                setResponse('');
                setClassName('text-white');
                setInputShow(true);
                setShowMode(true);
                setFolderNameInput('');
                setWaitFolderName([currentFolderUuid, null, 'create']);
              }}
            />

            {previewOn && (
              <span title="新建文字檔案" className="inline">
                <FilePlus
                  className="w-9 h-9 ml-3 text-cyan-300 inline cursor-pointer"
                  onClick={() => { setNewFileName(''); setNewFileModal(true); }}
                />
              </span>
            )}

            <Upload
              className="w-9 h-9 text-green-600 inline cursor-pointer"
              onClick={() => setShowUpLoad(true)}
            />

            <ListChecks
              className={`w-9 h-9 ml-4 inline cursor-pointer ${selectionMode ? 'text-blue-400' : 'text-gray-100'}`}
              onClick={toggleSelectionMode}
            />
          </span>

          <span className="text-sm text-gray-500">
            共 {filterList.length} 筆, 每頁 &nbsp;
            <select
              value={perPage}
              onChange={(e) => setPerPage(Number(e.target.value))}
              className="border border-white rounded px-1 py-1"
            >
              {[5, 10, 15, 20, 50].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
            &nbsp; 筆
          </span>
        </div>

        <div
          className="max-h-[60vh] scrollbar-hide overflow-x-auto overflow-y-auto shadow-[0.8rem_0.8rem_2.5rem_white] rounded-[2rem] border-2 border-white"
        >
          <table className="w-full table-fixed text-left border border-white border-collapse rounded-[2rem]">
            <thead>
              <tr className="bg-blue-200 text-xs sm:text-sm md:text-base lg:text-lg xl:text-xl text-center">
                {selectionMode && (
                  <th className="p-2 w-[5%] border border-white">
                    <input type="checkbox" checked={allSelected} onChange={toggleSelectAll} className="w-5 h-5 cursor-pointer" />
                  </th>
                )}
                <th
                  onClick={() => changeSortType('date')}
                  className="cursor-pointer p-2 w-[10%] border border-white hidden sm:table-cell"
                >
                  <span className="inline-flex items-center gap-1">
                    時間
                    <svg
                      className="w-4 h-4 sm:w-5 sm:h-5 text-gray-800"
                      aria-hidden="true"
                      xmlns="http://www.w3.org/2000/svg"
                      width="24"
                      height="24"
                      fill="none"
                      viewBox="0 0 24 24"
                    >
                      <path
                        stroke="currentColor"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2"
                        d="m8 10 4-6 4 6H8Zm8 4-4 6-4-6h8Z"
                      />
                    </svg>
                  </span>
                </th>
                <th
                  onClick={() => changeSortType('name')}
                  className="cursor-pointer p-2 w-[55%] sm:w-[45%] border border-white"
                >
                  <span className="inline-flex items-center gap-1">
                    名稱
                    <svg
                      className="w-4 h-4 sm:w-5 sm:h-5 text-gray-800 inline-block"
                      aria-hidden="true"
                      xmlns="http://www.w3.org/2000/svg"
                      width="24"
                      height="24"
                      fill="none"
                      viewBox="0 0 24 24"
                    >
                      <path
                        stroke="currentColor"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2"
                        d="m8 10 4-6 4 6H8Zm8 4-4 6-4-6h8Z"
                      />
                    </svg>
                  </span>
                </th>
                <th
                  onClick={() => changeSortType('size')}
                  className="cursor-pointer p-2 w-[25%] border border-white hidden md:table-cell"
                >
                  <span className="inline-flex items-center gap-1">
                    大小
                    <svg
                      className="w-4 h-4 sm:w-5 sm:h-5 text-gray-800 inline-block"
                      aria-hidden="true"
                      xmlns="http://www.w3.org/2000/svg"
                      width="24"
                      height="24"
                      fill="none"
                      viewBox="0 0 24 24"
                    >
                      <path
                        stroke="currentColor"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2"
                        d="m8 10 4-6 4 6H8Zm8 4-4 6-4-6h8Z"
                      />
                    </svg>
                  </span>
                </th>
                <th className="p-2 w-[45%] sm:w-[35%] md:w-[20%] border border-white text-xs sm:text-sm md:text-base lg:text-lg">操作</th>
              </tr>
            </thead>
            <tbody>
              {pageList.map((item) => (
                <tr
                  key={item.uuid + item.name + item.date}
                  className={`bg-gray-300 hover:bg-blue-200 ${item.type === 'folder' ? 'cursor-pointer' : ''}`}
                  onClick={() => {
                    if (item.type === 'folder') {
                      navigate(`/file-list/${item.uuid}`);
                    }
                  }}
                  onDoubleClick={() => {
                    if (previewOn && item.type === 'file' && isEditable(item.name)) {
                      setOpener({ uuid: item.uuid, name: item.name });
                    }
                  }}
                  title={previewOn && item.type === 'file' && isEditable(item.name) ? '雙擊開啟預覽／編輯' : undefined}
                >
                  {selectionMode && (
                    <td
                      className="p-2 text-center border border-white"
                      onClick={(e) => { e.stopPropagation(); toggleItem(item); }}
                    >
                      <input type="checkbox" checked={selected.includes(`${item.type}:${item.uuid}`)} readOnly className="w-5 h-5 cursor-pointer pointer-events-none" />
                    </td>
                  )}
                  <td className="p-2 text-xs sm:text-sm md:text-base text-center border border-white break-words whitespace-normal hidden sm:table-cell">
                    {item.date}
                  </td>
                  <td className="p-2 text-xs sm:text-sm md:text-base border border-white break-words whitespace-normal">
                    {item.type === 'folder' ? (
                      <FolderOpen className="inline w-6 h-6 ml-5 mr-2 text-yellow-200" />
                    ) : (
                      <FileText className="inline w-6 h-6 ml-5 mr-2 text-white" />
                    )}
                    {item.name}
                  </td>
                  <td
                    className={`p-2 text-xs sm:text-sm md:text-base border border-white break-words whitespace-normal hidden md:table-cell ${item.type === 'folder' ? 'text-center' : 'text-right'}`}
                  >
                    {(() => {
                      const [value, unit] = storage.format(item.size);
                      return `${value} ${unit}`;
                    })()}
                  </td>
                  <td className="p-2 text-xs sm:text-sm md:text-base text-center border border-white break-words whitespace-normal">
                    <span className="flex justify-center gap-1 sm:gap-2 md:gap-4 lg:gap-6 xl:gap-10">
                      {item.type === 'file' && (
                        <Download
                          className="w-5 h-5 sm:w-6 sm:h-6 text-green-600 cursor-pointer"
                          onClick={(e) => {
                            e.stopPropagation();
                            callDownloadFile(item.uuid);
                          }}
                        />
                      )}

                      {item.type === 'folder' && !selectionMode && (
                        <FolderDown
                          className="w-5 h-5 sm:w-6 sm:h-6 text-cyan-300 cursor-pointer"
                          onClick={async (e) => {
                            e.stopPropagation();
                            try {
                              await fileApi.downloadFolderZip(item.uuid, item.name);
                            } catch (err: any) {
                              setResponse([err?.message ?? '資料夾下載失敗']);
                              setClassName('text-red-500');
                              setShowMode(true);
                            }
                          }}
                        />
                      )}

                      {item.type === 'folder' && (
                        <Edit3
                          className="w-5 h-5 sm:w-6 sm:h-6 text-green-600 cursor-pointer"
                          onClick={(e) => {
                            e.stopPropagation();
                            setResponse('');
                            setClassName('text-white');
                            setInputShow(true);
                            setShowMode(true);
                            setFolderNameInput(item.name);
                            setWaitFolderName([
                              null, // parent_folder_uuid (not used for rename)
                              item.uuid, // folder_uuid
                              'rename',
                            ]);
                          }}
                        />
                      )}

                      {!selectionMode && (
                        <div className="relative">
                          {(() => {
                            const hasValidLink = item.shared && (!item.limited_date || new Date(item.limited_date) > new Date());
                            const IconComponent = hasValidLink ? Link2 : Share2;
                            return (
                              <IconComponent
                                className="w-5 h-5 sm:w-6 sm:h-6 text-blue-500 cursor-pointer"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  callShareFileLink(item.uuid, item.type, item.shared, item.limited_date);
                                }}
                              />
                            );
                          })()}

                          {popupItemUuid === item.uuid && copyShow && (
                            <div
                              className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-1 w-max px-2 py-1 text-xs sm:text-sm text-white rounded"
                            >
                              <span className="flex gap-1">
                                <button
                                  className="px-2 py-1 rounded bg-blue-400 cursor-pointer"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    copyFunc(shareFileLink);
                                  }}
                                >
                                  複製連結
                                </button>
                                <button
                                  className="px-2 py-1 rounded bg-red-400 cursor-pointer"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    callDeleteShareFileLink(item.uuid, item.type);
                                  }}
                                >
                                  移除
                                </button>
                              </span>
                            </div>
                          )}
                        </div>
                      )}

                      <Trash2
                        className="w-5 h-5 sm:w-6 sm:h-6 text-red-500 cursor-pointer"
                        onClick={(e) => {
                          e.stopPropagation();
                          if (item.type === 'file') {
                            callDeleteFile(item.uuid, 'file', item);
                          } else {
                            callDeleteFolder(item.uuid);
                          }
                        }}
                      />
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="mt-auto mb-4 flex justify-center items-center gap-2">
        <button
          disabled={page === 1}
          onClick={() => setPage(page - 1)}
          className="px-3 py-1 border border-white rounded disabled:opacity-50"
        >
          <ChevronLeft className="w-5 h-5 rtl:rotate-180" />
        </button>
        <span>第 {page} / {totalPages} 頁</span>
        <button
          disabled={page === totalPages || totalPages === 0}
          onClick={() => setPage(page + 1)}
          className="px-3 py-1 border border-white rounded disabled:opacity-50"
        >
          <ChevronRight className="w-5 h-5 rtl:rotate-180" />
        </button>
      </div>
    </div>
  );
}

export default FileList;
