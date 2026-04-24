import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Base64 } from 'js-base64';
import { Menu, Cloud, Settings, LogOut, Folder, Share2, User } from 'lucide-react';
import Dashboard from '../pages/Dashboard/Dashboard';

function Drawer() {
  const [isOpen, setIsOpen] = useState(false);
  const [cloudOpen, setCloudOpen] = useState(false);
  const [settingOpen, setSettingOpen] = useState(false);
  const navigate = useNavigate();

  async function signOut() {
    try {
      await axios.post(
        `http://localhost:8000/api/accounts/signOut`,
        {},
        { withCredentials: true }
      );

      localStorage.clear();
      window.location.href = "/";
    } catch (e) {
      localStorage.clear();
      window.location.href = "/";
    }
  }

  return (
    <>
      <div className="text-center">
        <button
          className="px-3 py-2 mb-2 text-sm font-medium text-white bg-blue-500 rounded-lg hover:bg-blue-600"
          type="button"
          onClick={() => setIsOpen(true)}
        >
          <Menu className="w-5 h-5" />
        </button>
      </div>

      {isOpen && (
        <div className="fixed inset-0 z-50 flex">
          <div
            className="fixed inset-0 bg-black bg-opacity-50"
            onClick={() => setIsOpen(false)}
          />
          <div className="relative z-10 fixed top-0 right-0 h-full w-80 bg-white shadow-xl">
            <div className="flex items-center justify-between p-4 border-b">
              <h2 className="text-lg font-semibold">Menu</h2>
              <button
                onClick={() => setIsOpen(false)}
                className="p-2 text-gray-500 hover:text-gray-700"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4">
              <ul className="space-y-2">
                <li>
                  <button
                    onClick={() => setCloudOpen(!cloudOpen)}
                    className="flex items-center justify-between w-full p-3 text-left bg-gray-100 rounded-lg hover:bg-gray-200"
                  >
                    <div className="flex items-center">
                      <Cloud className="w-5 h-5 mr-3 text-gray-600" />
                      <span className="font-medium">Cloud</span>
                    </div>
                    <svg className={`w-4 h-4 transition-transform ${cloudOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>

                  {cloudOpen && (
                    <ul className="mt-2 ml-4 space-y-1">
                      <li>
                        <button
                          onClick={() => { navigate(`/fileList/${Base64.encodeURI('Home')}`); setIsOpen(false); }}
                          className="flex items-center w-full p-2 text-left rounded-lg hover:bg-gray-100"
                        >
                          <Folder className="w-5 h-5 mr-3 text-gray-600" />
                          <span>File</span>
                        </button>
                      </li>

                      <li>
                        <button
                          onClick={() => { navigate('/shareList'); setIsOpen(false); }}
                          className="flex items-center w-full p-2 text-left rounded-lg hover:bg-gray-100"
                        >
                          <Share2 className="w-5 h-5 mr-3 text-gray-600" />
                          <span>Share List</span>
                        </button>
                      </li>
                    </ul>
                  )}
                </li>

                <li>
                  <button
                    onClick={() => setSettingOpen(!settingOpen)}
                    className="flex items-center justify-between w-full p-3 text-left bg-gray-100 rounded-lg hover:bg-gray-200"
                  >
                    <div className="flex items-center">
                      <Settings className="w-5 h-5 mr-3 text-gray-600" />
                      <span className="font-medium">Setting</span>
                    </div>
                    <svg className={`w-4 h-4 transition-transform ${settingOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>

                  {settingOpen && (
                    <ul className="mt-2 ml-4 space-y-1">
                      <li>
                        <button
                          onClick={() => { navigate('/setting/account'); setIsOpen(false); }}
                          className="flex items-center w-full p-2 text-left rounded-lg hover:bg-gray-100"
                        >
                          <User className="w-5 h-5 mr-3 text-gray-600" />
                          <span>Account</span>
                        </button>
                      </li>
                    </ul>
                  )}
                </li>

                <li className="pt-4 border-t">
                  <button
                    onClick={signOut}
                    className="flex items-center w-full p-3 text-left rounded-lg hover:bg-red-50 text-red-600"
                  >
                    <LogOut className="w-5 h-5 mr-3" />
                    <span className="font-medium">Sign Out</span>
                  </button>
                </li>
              </ul>
            </div>

            <div className="p-4 border-t">
              <Dashboard />
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default Drawer;
