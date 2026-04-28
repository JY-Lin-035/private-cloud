import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Menu, Cloud, Settings, LogOut, Folder, Share2, User } from 'lucide-react';
import Dashboard from '../pages/Dashboard/Dashboard';
import { authApi } from '../api/authApi';


function Drawer() {
  const [isOpen, setIsOpen] = useState(false);
  const [cloudOpen, setCloudOpen] = useState(false);
  const [settingOpen, setSettingOpen] = useState(false);
  const navigate = useNavigate();

  async function signOut() {
    try {
      await authApi.signOut();

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

      <div className={`fixed inset-0 z-50 flex justify-end transition-opacity duration-300 ${isOpen ? 'opacity-100' : 'opacity-0 pointer-events-none'}`}>
        <div
          className={`fixed inset-0 bg-black/50 transition-opacity duration-300 ${isOpen ? 'opacity-100' : 'opacity-0'}`}
          onClick={() => setIsOpen(false)}
        />
        <div className={`relative z-10 fixed h-full w-80 bg-gray-800 shadow-xl transition-transform duration-300 ease-in-out ${isOpen ? 'translate-x-0' : 'translate-x-[20rem]'}`} style={{ position: 'fixed', top: 0, right: 0, left: 'auto' }}>
          <div className="flex items-center justify-between p-4 border-b border-gray-700">
            <h2 className="text-lg font-semibold text-white">Menu</h2>
            <button
              onClick={() => setIsOpen(false)}
              className="p-2 text-gray-400 bg-transparent hover:bg-gray-600 hover:text-white rounded-lg text-sm w-8 h-8 inline-flex items-center justify-center"
            >
              <svg className="w-3 h-3" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 14 14">
                <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="m1 1 6 6m0 0 6 6M7 7l6-6M7 7l-6 6" />
              </svg>
            </button>
          </div>

          <div className="flex flex-col h-[100vh] px-4">
            <div className="flex-grow overflow-y-auto">
              <ul className="space-y-2">
                <li>
                  <button
                    onClick={() => setCloudOpen(!cloudOpen)}
                    className="flex items-center justify-between w-full p-2 text-base text-white transition duration-75 rounded-lg group hover:bg-gray-700 cursor-pointer"
                  >
                    <div className="flex items-center">
                      <Cloud className="w-6 h-6 mr-3 text-white" />
                      <span className="flex-1 text-left font-medium">Cloud</span>
                    </div>
                    <svg className={`w-3 h-3 transition-transform ${cloudOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 10 6">
                      <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="m1 1 4 4 4-4" />
                    </svg>
                  </button>

                  {cloudOpen && (
                    <ul className="py-2 space-y-2">
                      <li>
                        <button
                          onClick={() => { navigate('/fileList'); setIsOpen(false); }}
                          className="flex items-center w-full p-2 text-white transition duration-75 rounded-lg pl-11 group hover:bg-gray-700 cursor-pointer"
                        >
                          <Folder className="w-6 h-6 mr-2 text-white" />
                          <span>File</span>
                        </button>
                      </li>

                      <li>
                        <button
                          onClick={() => { navigate('/shareList'); setIsOpen(false); }}
                          className="flex items-center w-full p-2 text-white transition duration-75 rounded-lg pl-11 group hover:bg-gray-700 cursor-pointer"
                        >
                          <Share2 className="w-6 h-6 mr-2 text-white" />
                          <span>Share List</span>
                        </button>
                      </li>
                    </ul>
                  )}
                </li>

                <li>
                  <button
                    onClick={() => setSettingOpen(!settingOpen)}
                    className="flex items-center justify-between w-full p-2 text-base text-white transition duration-75 rounded-lg group hover:bg-gray-700 cursor-pointer"
                  >
                    <div className="flex items-center">
                      <Settings className="w-6 h-6 mr-3 text-white" />
                      <span className="flex-1 text-left font-medium">Setting</span>
                    </div>
                    <svg className={`w-3 h-3 transition-transform ${settingOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 10 6">
                      <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="m1 1 4 4 4-4" />
                    </svg>
                  </button>

                  {settingOpen && (
                    <ul className="py-2 space-y-2">
                      <li>
                        <button
                          onClick={() => { navigate('/setting/account'); setIsOpen(false); }}
                          className="flex items-center w-full p-2 text-white transition duration-75 rounded-lg pl-11 group hover:bg-gray-700 cursor-pointer"
                        >
                          <User className="w-6 h-6 mr-2 text-white" />
                          <span>Account</span>
                        </button>
                      </li>
                    </ul>
                  )}
                </li>

                <li>
                  <button
                    onClick={signOut}
                    className="flex items-center w-full p-2 text-red-600 border border-red-600 rounded-lg hover:bg-gray-700 group cursor-pointer"
                  >
                    <LogOut className="w-6 h-6 mr-3" />
                    <span className="flex-1 whitespace-nowrap font-medium text-left">Sign Out</span>
                  </button>
                </li>
              </ul>
            </div>
            <Dashboard layoutClass="mt-auto" />
          </div>
        </div>
      </div>
    </>
  );
}

export default Drawer;
