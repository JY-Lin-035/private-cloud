import { useState, useMemo, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { folderApi } from '../../api/folderApi';



interface BreadcrumbProps {
  currentFolderUuid: string | null;
}

function Breadcrumb({ currentFolderUuid }: BreadcrumbProps) {
  const navigate = useNavigate();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [folderPath, setFolderPath] = useState<Array<{uuid: string, name: string}>>([]);

  useEffect(() => {
    async function fetchFolderPath(retries = 3) {
      if (currentFolderUuid) {
        let lastError;
        for (let i = 0; i < retries; i++) {
          try {
            const response = await folderApi.getPath(currentFolderUuid);
            if (response.path && response.path.length > 0) {
              setFolderPath(response.path);
              return;
            }
          } catch (e) {
            lastError = e;
            console.error(`Failed to fetch folder path (attempt ${i + 1}/${retries}):`, e);
            if (i < retries - 1) {
              await new Promise(resolve => setTimeout(resolve, 200));
            }
          }
        }
        // Fallback: show just the current folder UUID if all retries fail
        console.error('All retries failed for folder path:', lastError);
        setFolderPath([{ uuid: currentFolderUuid, name: 'Current Folder' }]);
      } else {
        setFolderPath([]);
      }
    }
    fetchFolderPath();
  }, [currentFolderUuid]);

  const breadcrumb = useMemo(() => {
    if (!folderPath || folderPath.length === 0) {
      return [{ name: 'Home', path: '/fileList' }];
    }

    return folderPath.map((folder) => ({
      name: folder.name,
      path: `/fileList/${folder.uuid}`,
    }));
  }, [folderPath]);

  const hiddenBreadcrumbs = useMemo(() => {
    if (currentFolderUuid) {
      localStorage.setItem('previousFolderUuid', currentFolderUuid);
    }

    if (breadcrumb.length <= 5) return [];
    return breadcrumb.slice(1, breadcrumb.length - 3);
  }, [breadcrumb, currentFolderUuid]);

  const visibleEndBreadcrumbs = useMemo(() => {
    if (breadcrumb.length <= 5) return breadcrumb.slice(1);
    return breadcrumb.slice(breadcrumb.length - 3);
  }, [breadcrumb]);

  function handleDropdown() {
    setDropdownOpen(!dropdownOpen);
  }

  function breadcrumbClick(index: number) {
    const newBreadcrumb = breadcrumb.slice(0, index + 1);
    const path = newBreadcrumb[newBreadcrumb.length - 1].path;
    setDropdownOpen(false);

    navigate(path);
  }

  return (
    <nav className="flex w-[95%] mt-[2%] text-[2rem]" aria-label="Breadcrumb">
      <ol className="inline-flex items-center space-x-1 md:space-x-2 rtl:space-x-reverse">
        <li className="inline-flex items-center">
          <a
            href="#"
            className="inline-flex items-center font-medium text-gray-700 hover:text-blue-200"
            onClick={(e) => { e.preventDefault(); breadcrumbClick(0); }}
          >
            Home
          </a>
        </li>

        {hiddenBreadcrumbs.length > 0 && (
          <li className="relative inline-flex items-center">
            <div className="flex items-center">
              <svg
                className="rtl:rotate-180 w-3 h-3 text-gray-400 mx-1"
                aria-hidden="true"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 6 10"
              >
                <path
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="m1 9 4-4-4-4"
                />
              </svg>

              <button
                onClick={handleDropdown}
                className="ms-1 font-medium text-gray-700 hover:text-blue-200 md:ms-2"
              >
                ...
              </button>

              {dropdownOpen && (
                <ul
                  className="absolute max-h-[50vh] hide-scrollbar overflow-x-auto overflow-y-auto w-fit top-full left-0 mt-2 bg-gray-300 border border-blue-300 rounded-[1rem] shadow-md z-10"
                  onMouseLeave={() => setDropdownOpen(false)}
                >
                  {hiddenBreadcrumbs.map((item, index) => (
                    <li
                      key={index}
                      className="px-4 py-2 hover:bg-blue-200 hover:rounded-[1rem] cursor-pointer whitespace-nowrap"
                      onClick={() => breadcrumbClick(index + 1)}
                    >
                      {item.name}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </li>
        )}

        {visibleEndBreadcrumbs.map((item, index) => (
          <li key={index} aria-current="page">
            <div className="flex items-center">
              <svg
                className="rtl:rotate-180 w-3 h-3 text-gray-400 mx-1"
                aria-hidden="true"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 6 10"
              >
                <path
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="m1 9 4-4-4-4"
                />
              </svg>
              <a
                href="#"
                className="ms-1 font-medium text-gray-700 hover:text-blue-200 md:ms-2"
                onClick={(e) => {
                  e.preventDefault();
                  breadcrumbClick(
                    breadcrumb.length - visibleEndBreadcrumbs.length + index
                  );
                }}
              >
                {item.name}
              </a>
            </div>
          </li>
        ))}
      </ol>
    </nav>
  );
}

export default Breadcrumb;
