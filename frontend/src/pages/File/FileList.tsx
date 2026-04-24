import { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Base64 } from 'js-base64';
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
import UpLoad from './UpLoad';

import {
  Folder,
  FileText,
  Download,
  Share2,
  Trash2,
  Edit3,
  Plus,
  Upload,
  ChevronLeft,
  ChevronRight
} from 'lucide-react';



function FileList() {
  const navigate = useNavigate();
  const { folderName } = useParams();
  const storage = useStorage();
  const [showUpLoad, setShowUpLoad] = useState(false);
  const [PATH, setPATH] = useState('');
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
  const [folderNameInput, setFolderNameInput] = useState('');
  const [inputShow, setInputShow] = useState(false);
  const [waitFolderName, setWaitFolderName] = useState<any[]>([]);

  async function getFileList(base: string) {
    try {
      const r = await fileApi.getFileList(base);
      setFileList(r.file);
      setPATH(Base64.decode(base));
    } catch (e) {
      localStorage.clear();
      navigate('/');
    }
  }

  useEffect(() => {
    if (folderName) {
      getFileList(folderName);
    }
  }, [folderName]);

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

      if (sortType === 'size' && a.type === 'file' && b.type === 'file') {
        const aSplit = a['size'].split(' ');
        const bSplit = b['size'].split(' ');

        if (aSplit[1].localeCompare(bSplit[1]) === 0) {
          return sortUpDown
            ? Number(aSplit[0]) - Number(bSplit[0])
            : Number(bSplit[0]) - Number(aSplit[0]);
        } else {
          const units: { [key: string]: number } = { B: 0, KB: 1, MB: 2, GB: 3, TB: 4 };
          const A = units[aSplit[1]];
          const B = units[bSplit[1]];

          return sortUpDown ? A - B : B - A;
        }
      }

      return sortUpDown
        ? a[sortType].localeCompare(b[sortType])
        : b[sortType].localeCompare(a[sortType]);
    });

    return fList;
  }, [fileList, search, sortType, sortUpDown]);

  function changeSortType(type: string) {
    if (sortType === type) {
      setSortUpDown(!sortUpDown);
    } else {
      setSortType(type);
      setSortUpDown(true);
    }
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

  function callDownloadFile(dir: string, fileName: string) {
    const [res, cn, show] = downloadFile(dir, fileName);
    setResponse(res);
    setClassName(cn);
    setShowMode(show);
  }

  async function callDeleteFile(dir: string, fileName: string, item: any) {
    const [res, cn, show, fl] = await deleteFile(dir, fileName, item, fileList, storage);
    setResponse(res);
    setClassName(cn);
    setShowMode(show);
    setFileList(fl);
  }

  async function callShareFileLink(dir: string, fileName: string) {
    const [res, cn, show, link, copy] = await getShareFileLink(dir, fileName);
    setResponse(res);
    setClassName(cn);
    setShowMode(show);
    setShareFileLink(link);
    setCopyShow(copy);
  }

  async function callDeleteShareFileLink(dir: string, fileName: string) {
    const [res, cn, show] = await deleteShareFileLink(dir, fileName);
    setResponse(res);
    setClassName(cn);
    setShowMode(show);
  }

  const copyFunc = (m: string) => {
    navigator.clipboard.writeText(window.location.origin + '/share/' + m);
    setCopyShow(false);
  };

  async function emitFolderName() {
    if (waitFolderName[2] === 'rename') {
      const [res, cn, fl] = await renameFolder(
        waitFolderName[0],
        waitFolderName[1],
        folderNameInput,
        fileList
      );
      setResponse(res);
      setClassName(cn);
      setFileList(fl);
    } else if (waitFolderName[2] === 'create') {
      const [res, cn, fl] = await createFolder(
        waitFolderName[0],
        folderNameInput,
        fileList
      );
      setResponse(res);
      setClassName(cn);
      setFileList(fl);
    }

    setShowMode(true);
  }

  async function callDeleteFolder(dir: string, itemName: string) {
    const [res, cn, show, fl] = await deleteFolder(dir, itemName, fileList, storage);
    setResponse(res);
    setClassName(cn);
    setShowMode(show);
    setFileList(fl);
  }

  return (
    <div
      onClick={() => setCopyShow(false)}
      className="flex w-full h-full flex-col justify-center items-center"
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

      {showUpLoad && (
        <>
          {/* 原生上傳 UI (已註解) */}
          {/* <div className="fixed inset-0 z-20 flex items-center justify-center">
            <div
              className="absolute inset-0 bg-black bg-opacity-50"
              onClick={() => setShowUpLoad(false)}
            ></div>
            <div className="relative z-10 bg-white p-6 rounded-lg">
              <h3 className="text-lg font-bold mb-4">上傳檔案</h3>
              <input
                type="file"
                multiple
                onChange={async (e) => {
                  const files = e.target.files;
                  if (!files || files.length === 0) return;

                  const formData = new FormData();
                  for (let i = 0; i < files.length; i++) {
                    formData.append('file', files[i]);
                  }
                  formData.append('dir', PATH);

                  try {
                    const r = await fileApi.uploadFile(formData);
                    setResponse([r.message]);
                    setClassName('text-green-500');
                    setShowMode(true);
                    getFileList(folderName || '');
                  } catch (e) {
                    setResponse([e.message]);
                    setClassName('text-red-500');
                    setShowMode(true);
                  }
                  setShowUpLoad(false);
                }}
                className="mb-4"
              />
              <button
                onClick={() => setShowUpLoad(false)}
                className="px-4 py-2 bg-gray-500 text-white rounded"
              >
                取消
              </button>
            </div>
          </div> */}

          {/* 使用 Uppy 上傳組件 */}
          <UpLoad
            PATH={PATH}
            onHidden={() => setShowUpLoad(false)}
            onRefresh={() => getFileList(folderName || '')}
            onComplete={(res, cn) => {
              setResponse(res);
              setClassName(cn);
              setShowMode(true);
            }}
          />
        </>
      )}

      <Breadcrumb PATH={PATH} />

      <div
        className={`w-[80vw] mx-auto mt-[1%] flex-1 transition-all duration-[900ms] ease-in-out ${IN ? 'opacity-100' : 'opacity-0'}`}
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

            <Plus
              className="w-9 h-9 ml-6 mr-4 text-yellow-300 inline cursor-pointer"
              onClick={() => {
                setResponse('');
                setClassName('text-white');
                setInputShow(true);
                setShowMode(true);
                setWaitFolderName([`${Base64.encodeURI(PATH)}`, null, 'create']);
              }}
            />

            <Upload
              className="w-9 h-9 text-green-600 inline cursor-pointer"
              onClick={() => setShowUpLoad(true)}
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
          className="max-h-[60vh] hide-scrollbar overflow-x-auto overflow-y-auto shadow-[0.8rem_0.8rem_2.5rem_white] rounded-[2rem] border-2 border-white"
        >
          <table className="w-full table-fixed text-left border border-white border-collapse rounded-[2rem]">
            <thead>
              <tr className="bg-blue-200 text-[1.5rem] text-center">
                <th
                  onClick={() => changeSortType('date')}
                  className="cursor-pointer p-2 w-[10%] border border-white"
                >
                  <span className="inline-flex items-center gap-1">
                    時間
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
                  className="cursor-pointer p-2 w-[45%] border border-white"
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
                  className="cursor-pointer p-2 w-[25%] border border-white"
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
                <th className="p-2 w-[20%] border border-white">操作</th>
              </tr>
            </thead>
            <tbody>
              {pageList.map((item) => (
                <tr
                  key={PATH + item.name + item.date}
                  className={`bg-gray-300 hover:bg-blue-200 ${item.type === 'folder' ? 'cursor-pointer' : ''}`}
                  onClick={() => {
                    if (item.type === 'folder') {
                      navigate(`/fileList/${Base64.encodeURI(PATH + '-' + item.name)}`);
                    }
                  }}
                >
                  <td className="p-2 text-[1.2rem] text-center border border-white break-words whitespace-normal">
                    {item.date}
                  </td>
                  <td className="p-2 text-[1.2rem] border border-white break-words whitespace-normal">
                    {item.type === 'folder' ? (
                      <Folder className="inline w-6 h-6 ml-5 text-yellow-200" />
                    ) : (
                      <FileText className="inline w-6 h-6 ml-5 text-white" />
                    )}
                    {item.name}
                  </td>
                  <td
                    className={`p-2 text-[1.2rem] border border-white break-words whitespace-normal ${item.type === 'folder' ? 'text-center' : 'text-right'}`}
                  >
                    {item.size || '-'}
                  </td>
                  <td className="p-2 text-[1.2rem] text-center border border-white break-words whitespace-normal">
                    <span className="flex justify-center sm:gap-2 md:gap-6 lg:gap-10">
                      {item.type === 'file' && (
                        <Download
                          className="w-6 h-6 text-green-600 cursor-pointer"
                          onClick={(e) => {
                            e.stopPropagation();
                            callDownloadFile(`${Base64.encodeURI(PATH)}`, item.name);
                          }}
                        />
                      )}

                      {item.type === 'folder' && (
                        <Edit3
                          className="w-6 h-6 text-green-600 cursor-pointer"
                          onClick={(e) => {
                            e.stopPropagation();
                            setResponse('');
                            setClassName('text-white');
                            setInputShow(true);
                            setShowMode(true);
                            setWaitFolderName([
                              `${Base64.encodeURI(PATH)}`,
                              item.name,
                              'rename',
                            ]);
                          }}
                        />
                      )}

                      {item.type === 'file' && (
                        <div className="relative group">
                          <Share2
                            className="w-6 h-6 text-blue-500 cursor-pointer"
                            onClick={(e) => {
                              e.stopPropagation();
                              callShareFileLink(`${Base64.encodeURI(PATH)}`, item.name);
                            }}
                          />

                          {response === item.name && copyShow && (
                            <div
                              className="absolute bottom-full left-1/2 transform -translate-x-1/2 mt-2 w-max px-2 py-1 text-sm text-white rounded opacity-100 transition-opacity duration-300"
                            >
                              <span>
                                <button
                                  className="mr-2 p-2 rounded-[0.5rem] bg-blue-400"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    copyFunc(shareFileLink);
                                  }}
                                >
                                  複製
                                </button>
                                <button
                                  className="p-2 rounded-[0.5rem] bg-red-400"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    callDeleteShareFileLink(`${Base64.encodeURI(PATH)}`, item.name);
                                    setCopyShow(false);
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
                        className="w-6 h-6 text-red-500 cursor-pointer"
                        onClick={(e) => {
                          e.stopPropagation();
                          if (item.type === 'file') {
                            callDeleteFile(`${Base64.encodeURI(PATH)}`, item.name, item);
                          } else {
                            callDeleteFolder(`${Base64.encodeURI(PATH)}`, item.name);
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
