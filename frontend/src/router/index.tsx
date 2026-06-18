import { createBrowserRouter, Navigate } from 'react-router-dom';
import Nav from '../components/Nav';
import Footer from '../components/Footer';
import Home from '../pages/Home/Home';
import LoginRegisterPage from '../pages/LoginRegister/LoginRegisterPage';
import ResetPW from '../pages/ResetPW/ResetPW';
import FileList from '../pages/File/FileList';
import ShareList from '../pages/File/ShareList';
import DownloadShareFile from '../pages/File/DownloadShareFile';
import Account from '../pages/Setting/Account';
import AdminPage from '../pages/AdminManagement/AdminManagement';
import Trash from '../pages/File/Trash';
import CollaborationPage from '../pages/Collaboration/CollaborationPage';
import CollabEditor from '../pages/Collaboration/CollabEditor';

const router = createBrowserRouter([
  {
    path: '/',
    element: (
      <>
        <div className="fixed top-0 left-0 w-screen h-screen bg-gray-500 z-[-5] opacity-50"></div>
        <div className="flex flex-col h-screen">
          <Nav layoutClass="flex-0" />
          <Home layoutClass="flex-1 min-h-[calc(100vh-8rem)] md:min-h-[700px]" />
          <Footer layoutClass="flex-0" />
        </div>
      </>
    ),
  },
  {
    path: '/login',
    element: (
      <>
        <div className="fixed top-0 left-0 w-screen h-screen bg-gray-500 z-[-5] opacity-50"></div>
        <div className="flex flex-col h-screen">
          <Nav layoutClass="flex-0" />
          <LoginRegisterPage layoutClass="flex-1 min-h-[calc(100vh-8rem)] md:min-h-[700px]" />
          <Footer layoutClass="flex-0" />
        </div>
      </>
    ),
  },
  {
    path: '/forget-password',
    element: (
      <>
        <div className="fixed top-0 left-0 w-screen h-screen bg-gray-500 z-[-5] opacity-50"></div>
        <div className="flex flex-col h-screen">
          <Nav layoutClass="flex-0" />
          <ResetPW layoutClass="flex-1 min-h-[calc(100vh-8rem)] md:min-h-[700px]" />
          <Footer layoutClass="flex-0" />
        </div>
      </>
    ),
  },
  {
    path: '/file-list/:folderUuid?',
    element: (
      <>
        <div className="fixed top-0 left-0 w-screen h-screen bg-gray-500 z-[-5] opacity-50"></div>
        <div className="flex flex-col h-screen">
          <Nav layoutClass="flex-0" />
          <FileList layoutClass="flex-1 min-h-[calc(100vh-8rem)] md:min-h-[700px]" />
          <Footer layoutClass="flex-0" />
        </div>
      </>
    ),
  },
  {
    path: '/share-list',
    element: (
      <>
        <div className="fixed top-0 left-0 w-screen h-screen bg-gray-500 z-[-5] opacity-50"></div>
        <div className="flex flex-col h-screen">
          <Nav layoutClass="flex-0" />
          <ShareList layoutClass="flex-1 min-h-[calc(100vh-8rem)] md:min-h-[700px]" />
          <Footer layoutClass="flex-0" />
        </div>
      </>
    ),
  },
  {
    path: '/share/:link',
    element: (
      <>
        <div className="fixed top-0 left-0 w-screen h-screen bg-gray-500 z-[-5] opacity-50"></div>
        <div className="flex flex-col h-screen">
          <Nav layoutClass="flex-0" />
          <DownloadShareFile layoutClass="flex-1 min-h-[calc(100vh-8rem)] md:min-h-[700px]" />
          <Footer layoutClass="flex-0" />
        </div>
      </>
    ),
  },
  {
    path: '/shared-with-me',
    element: (
      <>
        <div className="fixed top-0 left-0 w-screen h-screen bg-gray-500 z-[-5] opacity-50"></div>
        <div className="flex flex-col h-screen">
          <Nav layoutClass="flex-0" />
          <ShareList layoutClass="flex-1 min-h-[calc(100vh-8rem)] md:min-h-[700px]" />
          <Footer layoutClass="flex-0" />
        </div>
      </>
    ),
  },
  {
    path: '/trash',
    element: (
      <>
        <div className="fixed top-0 left-0 w-screen h-screen bg-gray-500 z-[-5] opacity-50"></div>
        <div className="flex flex-col h-screen">
          <Nav layoutClass="flex-0" />
          <Trash layoutClass="flex-1 min-h-[calc(100vh-8rem)] md:min-h-[700px]" />
          <Footer layoutClass="flex-0" />
        </div>
      </>
    ),
  },
  {
    path: '/collaboration',
    element: (
      <>
        <div className="fixed top-0 left-0 w-screen h-screen bg-gray-500 z-[-5] opacity-50"></div>
        <div className="flex flex-col h-screen">
          <Nav layoutClass="flex-0" />
          <CollaborationPage layoutClass="flex-1 min-h-[calc(100vh-8rem)] md:min-h-[700px]" />
          <Footer layoutClass="flex-0" />
        </div>
      </>
    ),
  },
  {
    path: '/collab/edit/:fileUuid',
    element: (
      <>
        <div className="fixed top-0 left-0 w-screen h-screen bg-gray-500 z-[-5] opacity-50"></div>
        <div className="flex flex-col h-screen">
          <Nav layoutClass="flex-0" />
          <CollabEditor layoutClass="flex-1 min-h-[calc(100vh-8rem)] md:min-h-[700px]" />
          <Footer layoutClass="flex-0" />
        </div>
      </>
    ),
  },
  {
    path: '/setting/account',
    element: (
      <>
        <div className="fixed top-0 left-0 w-screen h-screen bg-gray-500 z-[-5] opacity-50"></div>
        <div className="flex flex-col h-screen">
          <Nav layoutClass="flex-0" />
          <Account layoutClass="flex-1 min-h-[calc(100vh-8rem)] md:min-h-[700px]" />
                    <Footer layoutClass="flex-0" />
                  </div>
                </>
              ),
            },
            {
              path: '/setting/user-management',
              element: (
                <>
                  <div className="fixed top-0 left-0 w-screen h-screen bg-gray-500 z-[-5] opacity-50"></div>
                  <div className="flex flex-col h-screen">
                    <Nav layoutClass="flex-0" />
                    <AdminPage layoutClass="flex-1 min-h-[calc(100vh-8rem)] md:min-h-[700px]" />
                    <Footer layoutClass="flex-0" />
                  </div>
                </>
              ),
            },
            {
              path: '*',
              element: <Navigate to="/" replace />,
            },
          ]);

          export default router;
