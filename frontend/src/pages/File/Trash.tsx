import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import Notices from '../../components/Notices';
import { FileText, FolderOpen, ChevronLeft, ChevronRight, RotateCcw, Trash2 } from 'lucide-react';
import { folderApi } from '../../api/folderApi';
import { fileApi } from '../../api/fileApi';

interface TrashItem {
  uuid: string;
  name: string;
  size: number;
  type: 'folder' | 'file';
  mime_type?: string;
  deleted_at: string;
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

  async function getTrashList() {
    try {
      const [foldersRes, filesRes] = await Promise.all([
        folderApi.trash(),
        fileApi.trash()
      ]);

      const folders = foldersRes.folders?.map((f: any) => ({
        uuid: f.uuid,
        name: f.name,
        size: f.size,
        type: 'folder' as const,
        deleted_at: f.deleted_at
      })) || [];

      const files = filesRes.files?.map((f: any) => ({
        uuid: f.uuid,
        name: f.name,
        size: f.size,
        type: 'file' as const,
        mime_type: f.mime_type,
        deleted_at: f.deleted_at
      })) || [];

      setTrashList([...folders, ...files]);
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
      return sortUpDown
        ? a[sortType as keyof TrashItem].toString().localeCompare(b[sortType as keyof TrashItem].toString())
        : b[sortType as keyof TrashItem].toString().localeCompare(a[sortType as keyof TrashItem].toString());
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
    }
  }

  async function hardDeleteItem(item: TrashItem) {
    try {
      if (item.type === 'folder') {
        await folderApi.delete({ folder_uuid: item.uuid, permanent: true });
      } else {
        await fileApi.delete({ file_uuid: item.uuid, permanent: true });
      }

      const newList = trashList.filter((i) => i.uuid !== item.uuid);
      setTrashList(newList);
      setResponse(['永久刪除成功!']);
      setClassName('text-green-500');
      setShowMode(true);
    } catch (e: any) {
      setResponse([e.message]);
      setClassName('text-red-500');
      setShowMode(true);
    }
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
        className={`w-[80vw] mx-auto mt-[5%] flex-1 transition-all duration-[900ms] ease-in-out ${IN ? 'opacity-100' : 'opacity-0'}`}
      >
        <div className="mb-4 flex justify-between items-center">
          <span>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              type="text"
              placeholder="搜尋"
              className="border border-white rounded px-3 py-1 w-64"
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
          className="max-h-[60vh] hide-scrollbar overflow-x-auto overflow-y-auto shadow-[0.8rem_0.8rem_2.5rem_white] rounded-[2rem] border-2 border-white"
        >
          <table className="w-full table-fixed text-left border border-white border-collapse rounded-[2rem]">
            <thead>
              <tr className="bg-blue-200 text-[1.5rem] text-center">
                <th
                  onClick={() => changeSortType('deleted_at')}
                  className="cursor-pointer p-2 w-[15%] border border-white"
                >
                  <span className="inline-flex items-center gap-1">
                    刪除時間
                    <svg
                      className="w-6 h-6 text-gray-800"
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
                  className="cursor-pointer p-2 w-[35%] border border-white"
                >
                  <span className="inline-flex items-center gap-1">
                    名稱
                    <svg
                      className="w-6 h-6 text-gray-800 inline-block"
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
                  className="cursor-pointer p-2 w-[20%] border border-white"
                >
                  <span className="inline-flex items-center gap-1">
                    大小
                    <svg
                      className="w-6 h-6 text-gray-800 inline-block"
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
                <th className="p-2 w-[30%] border border-white">操作</th>
              </tr>
            </thead>
            <tbody>
              {pageList.map((item) => (
                <tr
                  key={item.uuid}
                  className="bg-gray-300 hover:bg-blue-200"
                >
                  <td className="p-2 text-[1.2rem] text-center border border-white break-words whitespace-normal">
                    {formatDate(item.deleted_at)}
                  </td>
                  <td className="p-2 text-[1.2rem] border border-white break-words whitespace-normal">
                    {item.type === 'folder' ? (
                      <FolderOpen className="inline w-6 h-6 ml-5 mr-2 text-yellow-200" />
                    ) : (
                      <FileText className="inline w-6 h-6 ml-5 mr-2 text-white" />
                    )}
                    {item.name}
                  </td>
                  <td className="p-2 text-[1.2rem] text-right border border-white break-words whitespace-normal">
                    {formatSize(item.size)}
                  </td>
                  <td className="p-2 text-[1.2rem] text-center border border-white break-words whitespace-normal">
                    <span className="flex justify-center sm:gap-2 md:gap-6 lg:gap-10">
                      <RotateCcw
                        className="w-6 h-6 text-green-600 cursor-pointer"
                        onClick={() => restoreItem(item)}
                      />
                      <Trash2
                        className="w-6 h-6 text-red-500 cursor-pointer"
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
    </div>
  );
}

export default TrashList;
