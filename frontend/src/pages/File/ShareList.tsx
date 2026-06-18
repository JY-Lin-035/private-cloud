import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import Notices from '../../components/Notices';
import { FileText, FolderOpen, ChevronLeft, ChevronRight } from 'lucide-react';
import { shareApi } from '../../api/shareApi';



function ShareList({ layoutClass = "" }: { layoutClass?: string }) {
  const navigate = useNavigate();
  const [shareList, setShareList] = useState<any[]>([]);
  const [search, setSearch] = useState('');
  const [sortType, setSortType] = useState('name');
  const [sortUpDown, setSortUpDown] = useState(true);
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(10);
  const [previousPerPage, setPreviousPerPage] = useState(10);
  const [showMode, setShowMode] = useState(false);
  const [className, setClassName] = useState('');
  const [response, setResponse] = useState<string | string[]>([]);
  const [IN, setIN] = useState(false);
  const [_copyShow, setCopyShow] = useState(false);

  async function getShareList() {
    try {
      const r = await shareApi.getList();
      setShareList(r.share);
      localStorage.setItem('previousFolderUuid', '');
    } catch (e) {
      localStorage.clear();
      navigate('/');
    }
  }

  useEffect(() => {
    getShareList();
  }, []);

  useEffect(() => {
    setTimeout(() => {
      setIN(true);
    }, 200);
  }, []);

  const filterShareList = useMemo(() => {
    setPage(1);
    let fList = shareList.filter((f) =>
      f.name.toLowerCase().includes(search.toLowerCase())
    );

    fList.sort((a, b) => {
      return sortUpDown
        ? a[sortType].localeCompare(b[sortType])
        : b[sortType].localeCompare(a[sortType]);
    });

    return fList;
  }, [shareList, search, sortType, sortUpDown]);

  function changeSortType(type: string) {
    if (sortType === type) {
      setSortUpDown(!sortUpDown);
    } else {
      setSortType(type);
      setSortUpDown(true);
    }
  }

  const totalPages = useMemo(() =>
    Math.ceil(shareList.length / perPage),
    [shareList.length, perPage]
  );

  const pageList = useMemo(() => {
    if (perPage > previousPerPage) {
      setPage(1);
      setPreviousPerPage(perPage);
    } else {
      setPreviousPerPage(perPage);
    }
    const start = (page - 1) * perPage;
    return filterShareList.slice(start, start + perPage);
  }, [perPage, previousPerPage, page, filterShareList]);

  async function deleteLink(item: any) {
    try {
      await shareApi.deleteLink(item.uuid, item.type);

      const shareIndex = shareList.findIndex(
        (listItem) => listItem.link === item.link
      );

      if (shareIndex !== -1) {
        const newList = [...shareList];
        newList.splice(shareIndex, 1);
        setShareList(newList);
      }

      setResponse(['移除成功!']);
    } catch (e: any) {
      setResponse([e.message]);
    }

    setClassName('text-red-500');
    setShowMode(true);
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
    setCopyShow(false);
  };

  return (
    <div
      onClick={() => setCopyShow(false)}
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
        <div className="mb-4 flex justify-between items-center">
          <span>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              type="text"
              placeholder="搜尋"
              className="border border-white rounded px-3 py-1 w-full sm:w-64"
            />
          </span>

          <span className="text-sm text-gray-500">
            共 {shareList.length} 筆, 每頁 &nbsp;
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
                  className="cursor-pointer p-2 w-[45%] sm:w-[30%] border border-white"
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
                  onClick={() => changeSortType('path')}
                  className="cursor-pointer p-2 w-[35%] border border-white hidden md:table-cell"
                >
                  <span className="inline-flex items-center gap-1">
                    路徑
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
                <th className="p-2 w-[15%] border border-white hidden md:table-cell text-xs sm:text-sm md:text-base lg:text-lg">
                  <span className="inline-flex items-center gap-1">
                    到期日
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
                <th className="p-2 w-[55%] sm:w-[35%] md:w-[20%] border border-white text-xs sm:text-sm md:text-base lg:text-lg">操作</th>
              </tr>
            </thead>
            <tbody>
              {pageList.map((item) => (
                <tr
                  key={item.link}
                  className="bg-gray-300 hover:bg-blue-200"
                >
                  <td className="p-2 text-xs sm:text-sm md:text-base text-center border border-white break-words whitespace-normal hidden sm:table-cell">
                    {item.date}
                  </td>
                  <td className="p-2 text-xs sm:text-sm md:text-base border border-white break-words whitespace-normal">
                    {item.type === 'folder' ? (
                      <FolderOpen className="inline w-5 h-5 sm:w-6 sm:h-6 ml-2 sm:ml-5 text-yellow-200" />
                    ) : (
                      <FileText className="inline w-5 h-5 sm:w-6 sm:h-6 ml-2 sm:ml-5 text-white" />
                    )}
                    {item.name}
                  </td>
                  <td className="p-2 text-xs sm:text-sm md:text-base border border-white break-words whitespace-normal hidden md:table-cell">
                    {item.path}
                  </td>
                  <td className="p-2 text-xs sm:text-sm md:text-base text-center border border-white break-words whitespace-normal hidden md:table-cell">
                    {item.limited_date ? (
                      <span className="text-orange-500">{item.limited_date}</span>
                    ) : (
                      <span className="text-gray-400">-</span>
                    )}
                  </td>
                  <td className="p-2 text-xs sm:text-sm md:text-base text-center border border-white break-words whitespace-normal">
                    <span className="flex justify-center gap-1 sm:gap-2 md:gap-4">
                      <div className="relate w-max text-xs sm:text-sm text-white rounded">
                        <span>
                          <button
                            className="mr-2 sm:mr-4 p-1 sm:p-2 rounded-[0.5rem] bg-blue-400 cursor-pointer"
                            onClick={() => copyFunc(item.link)}
                          >
                            複製連結
                          </button>
                          <button
                            className="p-1 sm:p-2 rounded-[0.5rem] bg-red-400 cursor-pointer"
                            onClick={() => deleteLink(item)}
                          >
                            移除
                          </button>
                        </span>
                      </div>
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

export default ShareList;
