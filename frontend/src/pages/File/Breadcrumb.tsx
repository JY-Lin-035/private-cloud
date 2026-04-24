import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Base64 } from 'js-base64';



interface BreadcrumbProps {
  PATH: string;
}

function Breadcrumb({ PATH }: BreadcrumbProps) {
  const navigate = useNavigate();
  const [dropdownOpen, setDropdownOpen] = useState(false);

  const breadcrumb = useMemo(() => {
    const splitPath = PATH.split('-');
    return splitPath.map((p, index) => {
      return {
        name: p,
        path:
          '/fileList/' +
          Base64.encodeURI(splitPath.slice(0, index + 1).join('-')),
      };
    });
  }, [PATH]);

  const hiddenBreadcrumbs = useMemo(() => {
    localStorage.setItem(
      'previousPath',
      breadcrumb[breadcrumb.length - 1]['path']
    );

    if (breadcrumb.length <= 5) return [];
    return breadcrumb.slice(1, breadcrumb.length - 3);
  }, [breadcrumb]);

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
