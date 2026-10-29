import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import Notices from '../../components/Notices';
import { FileText, FolderOpen, ChevronLeft, ChevronRight, RotateCcw, Trash2, ListChecks } from 'lucide-react';
import { folderApi } from '../../api/folderApi';
import { fileApi } from '../../api/fileApi';
import { useStorage } from '../../store/storage';

interface TrashItem {
  uuid: string;
  name: string;
  size: number;
  type: 'folder' | 'file';
  mime_type?: string;
  deleted_at: string;
  path?: string;
}

function TrashList({ layoutClass = "" }: { layoutClass?: string }) {
  const navigate = useNavigate();
  const [trashList, setTrashList] = useState<TrashItem[]>([]);
  const [search, setSearch] = useState('');
  const [sortType, setSortType] = useState('deleted_at');
  const [sortUpDown, setSortUpDown] = useState(true);
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(10);
  const [previousPerPage, setPreviousPerPage] = useState(10);
  const [showMode, setShowMode] = useState(false);
  const [className, setClassName] = useState('');
  const [response, setResponse] = useState<string | string[]>([]);
  const [IN, setIN] = useState(false);
  const [retentionDays, setRetentionDays] = useState<number | null>(null);
  const [selectionMode, setSelectionMode] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const storage = useStorage();

  async function getTrashList() {
    try {
      const [foldersRes, filesRes] = await Promise.all([
        folderApi.trash(),
        fileApi.trash()
      ]);

      setRetentionDays(filesRes?.retention_days ?? null);

      const folders = foldersRes.folders?.map((f: any) => ({        uuid: f.uuid,
        name: f.name,
        size: f.size,
        type: 'folder' as const,
        deleted_at: f.deleted_at,
        parent_id: f.parent_id,
        path: f.path
      })) || [];

      const files = filesRes.files?.map((f: any) => ({
        uuid: f.uuid,
        name: f.name,
        size: f.size,
        type: 'file' as const,
        mime_type: f.mime_type,
        deleted_at: f.deleted_at,
        parent_folder_id: f.parent_folder_id,
        path: f.path
      })) || [];

      // Filter out files whose parent folder is also deleted
      const deletedFolderUuids = new Set(folders.map((f: { uuid: string }) => f.uuid));
      const filteredFiles = files.filter((f: { parent_folder_id?: string | null }) => !f.parent_folder_id || !deletedFolderUuids.has(f.parent_folder_id));

      const filteredFolders = folders.filter((f: { parent_id?: string | null }) => !f.parent_id || !deletedFolderUuids.has(f.parent_id));

      setTrashList([...filteredFolders, ...filteredFiles]);
      localStorage.setItem('previousFolderUuid', '');
    } catch (e) {
      localStorage.clear();
      navigate('/');
    }
  }

  useEffect(() => {
    getTrashList();
  }, []);

  useEffect(() => {
    setTimeout(() => {
      setIN(true);
    }, 200);
  }, []);

  const filterTrashList = useMemo(() => {
    setPage(1);
    let fList = trashList.filter((f) =>
      f.name.toLowerCase().includes(search.toLowerCase())
    );

    fList.sort((a, b) => {
      const aVal = (a[sortType as keyof TrashItem] ?? '').toString();
      const bVal = (b[sortType as keyof TrashItem] ?? '').toString();
      return sortUpDown
        ? aVal.localeCompare(bVal)
        : bVal.localeCompare(aVal);
    });

    return fList;
  }, [trashList, search, sortType, sortUpDown]);

  function changeSortType(type: string) {
    if (sortType === type) {
      setSortUpDown(!sortUpDown);
    } else {
      setSortType(type);
      setSortUpDown(true);
    }
  }

  const totalPages = useMemo(() =>
    Math.ceil(filterTrashList.length / perPage),
    [filterTrashList.length, perPage]
  );

  const pageList = useMemo(() => {
    if (perPage > previousPerPage) {
      setPage(1);
      setPreviousPerPage(perPage);
    } else {
      setPreviousPerPage(perPage);
    }
    const start = (page - 1) * perPage;
    return filterTrashList.slice(start, start + perPage);
  }, [perPage, previousPerPage, page, filterTrashList]);

  async function restoreItem(item: TrashItem) {
    try {
      if (item.type === 'folder') {
        await folderApi.restore({ folder_uuid: item.uuid });
      } else {
        await fileApi.restore({ file_uuid: item.uuid });
      }

      const newList = trashList.filter((i) => i.uuid !== item.uuid);
      setTrashList(newList);
      setResponse(['還原成功!']);
      setClassName('text-green-500');
      setShowMode(true);
    } catch (e: any) {
      setResponse([e.message]);
      setClassName('text-red-500');
      setShowMode(true);
    } finally {
      setBusy(false);
    }
  }

  async function hardDeleteItem(item: TrashItem) {
    try {
      const firstConfirmMessage = item.type === 'folder'
        ? '此操作將永久刪除資料夾且無法還原'
        : '此操作將永久刪除檔案且無法還原';

      const firstCheck = confirm(firstConfirmMessage);
      if (!firstCheck) {
        setBusy(false);
        return;
      }

      if (item.type === 'folder') {
        const secondCheck = confirm('此操作將一併永久刪除所有子項目');
        if (!secondCheck) {
          setBusy(false);
          return;
        }
        await folderApi.delete({ folder_uuid: item.uuid, permanent: true });
      } else {
        await fileApi.delete({ file_uuid: item.uuid, permanent: true });
      }

      // Immediate local update for instant user feedback
      storage.addUsedStorage(-item.size);

      // Background sync with backend
      storage.getFromAPI();

      const newList = trashList.filter((i) => i.uuid !== item.uuid);
      setTrashList(newList);
      setResponse(['永久刪除成功!']);
      setClassName('text-green-500');
      setShowMode(true);
    } catch (e: any) {
      setResponse([e.message]);
      setClassName('text-red-500');
      setShowMode(true);
    } finally {
      setBusy(false);
    }
  }

  const selectedItems = trashList.filter(i => selected.includes(`${i.type}:${i.uuid}`));

  function toggleSelectionMode() {
    setSelectionMode(v => !v);
    setSelected([]);
  }

  function toggleItem(item: TrashItem) {
    const key = `${item.type}:${item.uuid}`;
    setSelected(prev => prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]);
  }

  const allSelected = filterTrashList.length > 0 && filterTrashList.every(i => selected.includes(`${i.type}:${i.uuid}`));

  function toggleSelectAll() {
    setSelected(allSelected
      ? []
      : filterTrashList.map(i => `${i.type}:${i.uuid}`));
  }

  async function batchRestore() {
    if (!selectedItems.length || busy) return;
    setBusy(true);
    try {
      const res = await fileApi.batchOp({
        folders: selectedItems.filter(i => i.type === 'folder').map(i => i.uuid),
        files: selectedItems.filter(i => i.type === 'file').map(i => i.uuid),
        mode: 'restore',
      });
      await getTrashList();
      setSelected([]);
      setSelectionMode(false);
      const skipNote = res.skipped.length ? [`跳過 ${res.skipped.length} 項：` + res.skipped.map(x => x.reason).join('、')] : [];
      setResponse([`已還原 ${res.folders + res.files} 項`, ...skipNote]);
      setClassName('text-green-500');
    } catch (e: any) {
      setResponse([e.message ?? '還原失敗']);
      setClassName('text-red-500');
    }
    setShowMode(true);
    setBusy(false);
  }

  async function batchPermanentDelete() {
    if (!selectedItems.length || busy) return;
    if (!window.confirm(`確定要永久刪除選取的 ${selectedItems.length} 個項目？此操作無法還原。`)) return;
    setBusy(true);
    try {
      const res = await fileApi.batchOp({
        folders: selectedItems.filter(i => i.type === 'folder').map(i => i.uuid),
        files: selectedItems.filter(i => i.type === 'file').map(i => i.uuid),
        mode: 'permanent',
      });
      storage.addUsedStorage(-res.freed_bytes);
      storage.getFromAPI();
      await getTrashList();
      setSelected([]);
      setSelectionMode(false);
      const skipNote = res.skipped.length ? [`跳過 ${res.skipped.length} 項`] : [];
      setResponse([`已永久刪除 ${res.folders + res.files} 項`, ...skipNote]);
      setClassName('text-green-500');
    } catch (e: any) {
      setResponse([e.message ?? '刪除失敗']);
      setClassName('text-red-500');
    }
    setShowMode(true);
    setBusy(false);
  }

  function formatSize(size: number): string {
    if (size === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(size) / Math.log(k));
    return Math.round(size / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
  }

  function formatDate(dateString: string): string {
    const date = new Date(dateString);
    return date.toLocaleString('zh-TW', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    });
  }

  return (
    <div
      className={`flex w-full h-full flex-col justify-center items-center ${layoutClass}`}
    >
      <Notices
        notices={response}
        showMode={showMode}
        className={className}
        onClose={() => setShowMode(false)}
        onEmitFolderName={() => setShowMode(false)}
      />

      <div
        className={`w-[95vw] sm:w-[90vw] md:w-[80vw] lg:w-[75vw] xl:w-[70vw] mx-auto mt-[5%] flex-1 transition-all duration-[900ms] ease-in-out ${IN ? 'opacity-100' : 'opacity-0'}`}
      >
        {retentionDays != null && (
          <p className="mb-3 text-center text-sm sm:text-base lg:text-lg font-semibold text-red-400">
            ⚠ 垃圾桶中的項目會在 {retentionDays} 天後自動永久清除
          </p>
        )}
        <div className="mb-4 flex justify-between items-center">
          <span>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              type="text"
              placeholder="搜尋"
              className="border border-white rounded px-3 py-1 w-full sm:w-64"
            />

            <ListChecks
              className={`w-9 h-9 ml-4 inline cursor-pointer ${selectionMode ? 'text-blue-400' : 'text-gray-100'}`}
              onClick={toggleSelectionMode}
            />
          </span>

          <span className="text-sm text-gray-500">
            共 {trashList.length} 筆, 每頁 &nbsp;
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
                  onClick={() => changeSortType('deleted_at')}
                  className="cursor-pointer p-2 w-[12%] border border-white hidden sm:table-cell"
                >
                  <span className="inline-flex items-center gap-1">
                    刪除時間
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
                  className="cursor-pointer p-2 w-[35%] sm:w-[25%] border border-white"
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
                <th className="p-2 w-[30%] sm:w-[25%] border border-white hidden sm:table-cell">原始位置</th>
                <th
                  onClick={() => changeSortType('size')}
                  className="cursor-pointer p-2 w-[15%] border border-white hidden md:table-cell"
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
                <th className="p-2 w-[65%] sm:w-[40%] md:w-[23%] border border-white text-xs sm:text-sm md:text-base lg:text-lg">操作</th>
              </tr>
            </thead>
            <tbody>
              {pageList.map((item) => (
                <tr
                  key={item.uuid}
                  className="bg-gray-300 hover:bg-blue-200"
                >
                  {selectionMode && (
                    <td
                      className="p-2 text-center border border-white"
                      onClick={(e) => { e.stopPropagation(); toggleItem(item); }}
                    >
                      <input type="checkbox" checked={selected.includes(`${item.type}:${item.uuid}`)} readOnly className="w-5 h-5 pointer-events-none" />
                    </td>
                  )}
                  <td className="p-2 text-xs sm:text-sm md:text-base text-center border border-white break-words whitespace-normal hidden sm:table-cell">
                    {formatDate(item.deleted_at)}
                  </td>
                  <td className="p-2 text-xs sm:text-sm md:text-base border border-white break-words whitespace-normal">
                    {item.type === 'folder' ? (
                      <FolderOpen className="inline w-5 h-5 sm:w-6 sm:h-6 ml-2 sm:ml-5 mr-1 sm:mr-2 text-yellow-200" />
                    ) : (
                      <FileText className="inline w-5 h-5 sm:w-6 sm:h-6 ml-2 sm:ml-5 mr-1 sm:mr-2 text-white" />
                    )}
                    {item.name}
                  </td>
                  <td className="p-2 text-xs sm:text-sm md:text-base text-center border border-white break-words whitespace-normal hidden sm:table-cell">
                    {item.path || '-'}
                  </td>
                  <td className="p-2 text-xs sm:text-sm md:text-base text-right border border-white break-words whitespace-normal hidden md:table-cell">
                    {formatSize(item.size)}
                  </td>
                  <td className="p-2 text-xs sm:text-sm md:text-base text-center border border-white break-words whitespace-normal">
                    <span className="flex justify-center gap-1 sm:gap-2 md:gap-4 lg:gap-6">
                      <RotateCcw
                        className="w-5 h-5 sm:w-6 sm:h-6 text-green-600 cursor-pointer"
                        onClick={() => restoreItem(item)}
                      />
                      <Trash2
                        className="w-5 h-5 sm:w-6 sm:h-6 text-red-500 cursor-pointer"
                        onClick={() => hardDeleteItem(item)}
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

      {selectionMode && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-40 flex items-center gap-2 px-4 py-3 rounded-xl bg-gray-800 text-white shadow-2xl border border-gray-600 w-[92vw] max-w-[520px] justify-between">
          <span className="text-sm whitespace-nowrap">已選 {selected.length} 項</span>
          <span className="flex gap-2">
            <button
              onClick={toggleSelectAll}
              className="px-3 py-1.5 rounded text-sm bg-gray-600 hover:bg-gray-500 cursor-pointer"
            >
              {allSelected ? '取消全選' : '一鍵全選'}
            </button>
            <button
              onClick={batchRestore}
              disabled={!selected.length || busy}
              className="px-3 py-1.5 rounded text-sm bg-green-600 hover:bg-green-500 disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed"
            >
              {busy ? '處理中…' : '還原'}
            </button>
            <button
              onClick={batchPermanentDelete}
              disabled={!selected.length || busy}
              className="px-3 py-1.5 rounded text-sm bg-red-600 hover:bg-red-500 disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed"
            >
              {busy ? '處理中…' : '永久刪除'}
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
    </div>
  );
}

export default TrashList;
