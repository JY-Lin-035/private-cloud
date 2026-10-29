import { createBrowserRouter, Navigate } from 'react-router-dom';
import { lazy } from 'react';
import RouteError from '../components/RouteError';
import Nav from '../components/Nav';
import Footer from '../components/Footer';
import Home from '../pages/Home/Home';
const LoginRegisterPage = lazy(() => import('../pages/LoginRegister/LoginRegisterPage'));
const ResetPW = lazy(() => import('../pages/ResetPW/ResetPW'));
const FileList = lazy(() => import('../pages/File/FileList'));
const ShareList = lazy(() => import('../pages/File/ShareList'));
const DownloadShareFile = lazy(() => import('../pages/File/DownloadShareFile'));
const Account = lazy(() => import('../pages/Setting/Account'));
const FunctionControl = lazy(() => import('../pages/Setting/FunctionControl'));
const AnnouncementManagement = lazy(() => import('../pages/Setting/AnnouncementManagement'));
const IPManagement = lazy(() => import('../pages/Setting/IPManagement'));
const AdminPage = lazy(() => import('../pages/AdminManagement/AdminManagement'));
const Trash = lazy(() => import('../pages/File/Trash'));
const CollaborationPage = lazy(() => import('../pages/Collaboration/CollaborationPage'));
const CollabEditor = lazy(() => import('../pages/Collaboration/CollabEditor'));

const router = createBrowserRouter([
  {
    errorElement: <RouteError />,
    path: '/',
    element: (
      <>
        <div className="fixed top-0 left-0 w-screen h-screen bg-gray-500 z-[-5] opacity-50"></div>
        <div className="flex flex-col min-h-screen">
          <Nav layoutClass="flex-0" />
          <Home layoutClass="flex-1 min-h-[calc(100vh-8rem)] md:min-h-[700px]" />
          <Footer layoutClass="flex-0" />
        </div>
      </>
    ),
  },
  {
    errorElement: <RouteError />,
    path: '/login',
    element: (
      <>
        <div className="fixed top-0 left-0 w-screen h-screen bg-gray-500 z-[-5] opacity-50"></div>
        <div className="flex flex-col min-h-screen">
          <Nav layoutClass="flex-0" />
          <LoginRegisterPage layoutClass="flex-1 min-h-[calc(100vh-8rem)] md:min-h-[700px]" />
          <Footer layoutClass="flex-0" />
        </div>
      </>
    ),
  },
  {
    errorElement: <RouteError />,
    path: '/forget-password',
    element: (
      <>
        <div className="fixed top-0 left-0 w-screen h-screen bg-gray-500 z-[-5] opacity-50"></div>
        <div className="flex flex-col min-h-screen">
          <Nav layoutClass="flex-0" />
          <ResetPW layoutClass="flex-1 min-h-[calc(100vh-8rem)] md:min-h-[700px]" />
          <Footer layoutClass="flex-0" />
        </div>
      </>
    ),
  },
  {
    errorElement: <RouteError />,
    path: '/file-list/:folderUuid?',
    element: (
      <>
        <div className="fixed top-0 left-0 w-screen h-screen bg-gray-500 z-[-5] opacity-50"></div>
        <div className="flex flex-col min-h-screen">
          <Nav layoutClass="flex-0" />
          <FileList layoutClass="flex-1 min-h-[calc(100vh-8rem)] md:min-h-[700px]" />
          <Footer layoutClass="flex-0" />
        </div>
      </>
    ),
  },
  {
    errorElement: <RouteError />,
    path: '/share-list',
    element: (
      <>
        <div className="fixed top-0 left-0 w-screen h-screen bg-gray-500 z-[-5] opacity-50"></div>
        <div className="flex flex-col min-h-screen">
          <Nav layoutClass="flex-0" />
          <ShareList layoutClass="flex-1 min-h-[calc(100vh-8rem)] md:min-h-[700px]" />
          <Footer layoutClass="flex-0" />
        </div>
      </>
    ),
  },
  {
    errorElement: <RouteError />,
    path: '/share/:link',
    element: (
      <>
        <div className="fixed top-0 left-0 w-screen h-screen bg-gray-500 z-[-5] opacity-50"></div>
        <div className="flex flex-col min-h-screen">
          <Nav layoutClass="flex-0" />
          <DownloadShareFile layoutClass="flex-1 min-h-[calc(100vh-8rem)] md:min-h-[700px]" />
          <Footer layoutClass="flex-0" />
        </div>
      </>
    ),
  },
  {
    errorElement: <RouteError />,
    path: '/shared-with-me',
    element: (
      <>
        <div className="fixed top-0 left-0 w-screen h-screen bg-gray-500 z-[-5] opacity-50"></div>
        <div className="flex flex-col min-h-screen">
          <Nav layoutClass="flex-0" />
          <ShareList layoutClass="flex-1 min-h-[calc(100vh-8rem)] md:min-h-[700px]" />
          <Footer layoutClass="flex-0" />
        </div>
      </>
    ),
  },
  {
    errorElement: <RouteError />,
    path: '/trash',
    element: (
      <>
        <div className="fixed top-0 left-0 w-screen h-screen bg-gray-500 z-[-5] opacity-50"></div>
        <div className="flex flex-col min-h-screen">
          <Nav layoutClass="flex-0" />
          <Trash layoutClass="flex-1 min-h-[calc(100vh-8rem)] md:min-h-[700px]" />
          <Footer layoutClass="flex-0" />
        </div>
      </>
    ),
  },
  {
    errorElement: <RouteError />,
    path: '/collaboration',
    element: (
      <>
        <div className="fixed top-0 left-0 w-screen h-screen bg-gray-500 z-[-5] opacity-50"></div>
        <div className="flex flex-col min-h-screen">
          <Nav layoutClass="flex-0" />
          <CollaborationPage layoutClass="flex-1 min-h-[calc(100vh-8rem)] md:min-h-[700px]" />
          <Footer layoutClass="flex-0" />
        </div>
      </>
    ),
  },
  {
    errorElement: <RouteError />,
    path: '/collab/edit/:fileUuid',
    element: (
      <>
        <div className="fixed top-0 left-0 w-screen h-screen bg-gray-500 z-[-5] opacity-50"></div>
        <div className="flex flex-col h-screen">
          <Nav layoutClass="flex-0" />
          <CollabEditor layoutClass="flex-1 min-h-0" />
          <Footer layoutClass="flex-0" />
        </div>
      </>
    ),
  },
  {
    errorElement: <RouteError />,
    path: '/setting/account',
    element: (
      <>
        <div className="fixed top-0 left-0 w-screen h-screen bg-gray-500 z-[-5] opacity-50"></div>
        <div className="flex flex-col min-h-screen">
          <Nav layoutClass="flex-0" />
          <Account layoutClass="flex-1 min-h-[calc(100vh-8rem)] md:min-h-[700px]" />
                    <Footer layoutClass="flex-0" />
                  </div>
                </>
              ),
            },
            {
              path: '/setting/ip-management',
              element: (
                <>
                  <div className="fixed top-0 left-0 w-screen h-screen bg-gray-500 z-[-5] opacity-50"></div>
                  <div className="flex flex-col min-h-screen">
                    <Nav layoutClass="flex-0" />
                    <IPManagement layoutClass="flex-1 min-h-[calc(100vh-8rem)] md:min-h-[700px]" />
                    <Footer layoutClass="flex-0" />
                  </div>
                </>
              ),
            },
            {
              path: '/setting/announcements',
            element: (
              <>
                <div className="fixed top-0 left-0 w-screen h-screen bg-gray-500 z-[-5] opacity-50"></div>
                <div className="flex flex-col min-h-screen">
                  <Nav layoutClass="flex-0" />
                  <AnnouncementManagement layoutClass="flex-1 min-h-[calc(100vh-8rem)] md:min-h-[700px]" />
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
                  <div className="flex flex-col min-h-screen">
                    <Nav layoutClass="flex-0" />
                    <AdminPage layoutClass="flex-1 min-h-[calc(100vh-8rem)] md:min-h-[700px]" />
                    <Footer layoutClass="flex-0" />
                  </div>
                </>
              ),
            },
            {
              path: '/setting/function-control',
              element: (
                <>
                  <div className="fixed top-0 left-0 w-screen h-screen bg-gray-500 z-[-5] opacity-50"></div>
                  <div className="flex flex-col min-h-screen">
                    <Nav layoutClass="flex-0" />
                    <FunctionControl layoutClass="flex-1 min-h-[calc(100vh-8rem)] md:min-h-[700px]" />
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
