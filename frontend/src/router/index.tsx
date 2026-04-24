import { createBrowserRouter, Navigate } from 'react-router-dom';
import Nav from '../components/Nav';
import Footer from '../components/Footer';
import LoginRegisterPage from '../pages/LoginRegister/LoginRegisterPage';
import ResetPW from '../pages/ResetPW/ResetPW';
import FileList from '../pages/File/FileList';
import ShareList from '../pages/File/ShareList';
import DownloadShareFile from '../pages/File/DownloadShareFile';
import Account from '../pages/Setting/Account';

const router = createBrowserRouter([
  {
    path: '/',
    element: (
      <>
        <div className="fixed top-0 left-0 w-screen h-screen bg-gray-500 z-[-5] opacity-50"></div>
        <div className="flex flex-col h-screen">
          <Nav layoutClass="flex-0" />
          <LoginRegisterPage layoutClass="flex-1 min-h-[700px]" />
          <Footer layoutClass="flex-0" />
        </div>
      </>
    ),
  },
  {
    path: '/forgetPassword',
    element: (
      <>
        <div className="fixed top-0 left-0 w-screen h-screen bg-gray-500 z-[-5] opacity-50"></div>
        <div className="flex flex-col h-screen">
          <div className="flex-0"><Nav /></div>
          <div className="flex-1 min-h-[700px]"><ResetPW /></div>
          <div className="flex-0"><Footer /></div>
        </div>
      </>
    ),
  },
  {
    path: '/fileList/:folderName',
    element: (
      <>
        <div className="fixed top-0 left-0 w-screen h-screen bg-gray-500 z-[-5] opacity-50"></div>
        <div className="flex flex-col h-screen">
          <div className="flex-0"><Nav /></div>
          <div className="flex-1 min-h-[700px]"><FileList /></div>
          <div className="flex-0"><Footer /></div>
        </div>
      </>
    ),
  },
  {
    path: '/shareList',
    element: (
      <>
        <div className="fixed top-0 left-0 w-screen h-screen bg-gray-500 z-[-5] opacity-50"></div>
        <div className="flex flex-col h-screen">
          <div className="flex-0"><Nav /></div>
          <div className="flex-1 min-h-[700px]"><ShareList /></div>
          <div className="flex-0"><Footer /></div>
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
          <div className="flex-0"><Nav /></div>
          <div className="flex-1 min-h-[700px]"><DownloadShareFile /></div>
          <div className="flex-0"><Footer /></div>
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
          <div className="flex-0"><Nav /></div>
          <div className="flex-1 min-h-[700px]"><Account /></div>
          <div className="flex-0"><Footer /></div>
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
