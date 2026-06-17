import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import type { CollaborationItem, MyCollaborationItem } from '../../types';
import { collaborationApi } from '../../api/collaborationApi';
import { fileApi } from '../../api/fileApi';
import { folderApi } from '../../api/folderApi';
import { Users, UserPlus, FileText, Trash2, Download, Edit3, ExternalLink } from 'lucide-react';

function CollaborationPage({ layoutClass = '' }: { layoutClass?: string }) {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<'my' | 'owned'>('my');
  const [myCollabs, setMyCollabs] = useState<MyCollaborationItem[]>([]);
  const [ownedCollabs, setOwnedCollabs] = useState<CollaborationItem[]>([]);
  const [fileList, setFileList] = useState<any[]>([]);
  const [selectedFile, setSelectedFile] = useState<string>('');
  const [inviteName, setInviteName] = useState('');
  const [inviteEmail, setInviteEmail] = useState('');
  const [message, setMessage] = useState('');
  const [messageType, setMessageType] = useState<'success' | 'error'>('success');

  useEffect(() => {
    loadMyCollaborations();
    loadOwnedCollaborations();
    loadFileList();
  }, []);

  async function loadMyCollaborations() {
    try {
      const res = await collaborationApi.getMyCollaborations();
      setMyCollabs(res.data.items || []);
    } catch (e) {
      console.error('Failed to load my collaborations', e);
    }
  }

  async function loadOwnedCollaborations() {
    try {
      const res = await collaborationApi.getOwnedCollaborations();
      setOwnedCollabs(res.data.items || []);
    } catch (e) {
      console.error('Failed to load owned collaborations', e);
    }
  }

  async function downloadCollaborationFile(fileUuid: string) {
    try {
      const res = await fileApi.download(fileUuid);
      console.log('Download result:', res);
    } catch (e) {
      console.error('Download failed', e);
    }
  }

  async function loadFileList() {
    try {
      // First get the home folder UUID
      const homeRes = await folderApi.getHome();
      const homeUuid = homeRes?.uuid;
      if (!homeUuid) {
        console.error('No home folder found');
        return;
      }
      // Then list files in the home folder
      const res = await fileApi.list(homeUuid);
      console.log('File list API response:', res);
      const files = res?.files || [];
      setFileList(Array.isArray(files) ? files : []);
    } catch (e) {
      console.error('Failed to load file list', e);
    }
  }

  async function handleAddCollaborator() {
    if (!selectedFile || !inviteName || !inviteEmail) {
      setMessage('請填寫完整所有資訊');
      setMessageType('error');
      return;
    }

    try {
      const res = await collaborationApi.addCollaborator(
        selectedFile,
        inviteName,
        inviteEmail
      );
      setMessage(res.data.message || '邀請成功');
      setMessageType('success');
      setInviteName('');
      setInviteEmail('');
      loadOwnedCollaborations();
    } catch (e: any) {
      setMessage(e.response?.data?.detail || '邀請失敗');
      setMessageType('error');
    }
  }

  async function handleRemoveCollaborator(fileUuid: string, collaboratorId: number) {
    try {
      await collaborationApi.removeCollaborator(fileUuid, collaboratorId);
      setMessage('已移除共編成員');
      setMessageType('success');
      loadOwnedCollaborations();
    } catch (e: any) {
      setMessage(e.response?.data?.detail || '移除失敗');
      setMessageType('error');
    }
  }

  return (
    <div className={`flex w-full h-full flex-col justify-center items-center ${layoutClass}`}>
      <div className="w-[95vw] sm:w-[90vw] md:w-[80vw] lg:w-[75vw] xl:w-[70vw] mx-auto mt-[2%]">
        <h1 className="text-2xl font-bold text-white mb-6 flex items-center gap-2">
          <Users className="w-8 h-8" />
          Collaboration
        </h1>

        {/* Tab Switcher */}
        <div className="flex mb-6 border-b border-gray-700">
          <button
            className={`px-6 py-3 text-lg font-medium cursor-pointer transition-colors ${
              activeTab === 'my'
                ? 'text-blue-400 border-b-2 border-blue-400'
                : 'text-gray-400 hover:text-white'
            }`}
            onClick={() => setActiveTab('my')}
          >
            📂 與我共編
          </button>
          <button
            className={`px-6 py-3 text-lg font-medium cursor-pointer transition-colors ${
              activeTab === 'owned'
                ? 'text-blue-400 border-b-2 border-blue-400'
                : 'text-gray-400 hover:text-white'
            }`}
            onClick={() => setActiveTab('owned')}
          >
            ✏️ 我發起的共編
          </button>
        </div>

        {/* Message */}
        {message && (
          <div className={`mb-4 p-3 rounded-lg ${
            messageType === 'success' ? 'bg-green-600 text-white' : 'bg-red-600 text-white'
          }`}>
            {message}
          </div>
        )}

        {/* Tab 1: My Collaborations (Invitee View) */}
        {activeTab === 'my' && (
          <div className="bg-gray-800 rounded-lg p-6">
            <h2 className="text-xl font-semibold text-white mb-4">與我共編的檔案</h2>
            {myCollabs.length === 0 ? (
              <p className="text-gray-400">目前沒有被邀請共編的檔案</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left">
                  <thead>
                    <tr className="text-gray-500 border-b border-gray-700">
                      <th className="p-2">檔案名稱</th>
                      <th className="p-2">擁有者</th>
                      <th className="p-2">權限</th>
                      <th className="p-2">加入時間</th>
                      <th className="p-2">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {myCollabs.map((item) => (
                      <tr key={item.id} className="text-white text-b border-gray-700 hover:bg-gray-700">
                        <td className="p-2 flex items-center gap-2">
                          <FileText className="w-5 h-5 text-blue-400" />
                          {item.file_name}
                        </td>
                        <td className="p-2">{item.owner_name}</td>
                        <td className="p-2">
                          <span className="px-2 py-1 bg-blue-900 text-blue-300 rounded text-sm">
                            {item.permission}
                          </span>
                        </td>
                        <td className="p-2 text-gray-400">{item.created_at}</td>
                        <td className="p-2 flex gap-1">
                          <button
                            onClick={() => downloadCollaborationFile(item.file_uuid)}
                            className="flex items-center gap-1 px-3 py-1 bg-green-600 text-white rounded hover:bg-green-700 transition-colors cursor-pointer text-xs"
                          >
                            <Download className="w-3 h-3" />
                            下載
                          </button>
                          <button
                            onClick={() => navigate(`/collab/edit/${item.file_uuid}`)}
                            className="flex items-center gap-1 px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors cursor-pointer text-xs"
                          >
                            <Edit3 className="w-3 h-3" />
                            線上編輯
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* Tab 2: Owned Collaborations (Inviter View) */}
        {activeTab === 'owned' && (
          <div className="space-y-6">
            {/* Invite Form */}
            <div className="bg-gray-800 rounded-lg p-6">
              <h2 className="text-xl font-semibold text-white mb-4 flex items-center gap-2">
                <UserPlus className="w-5 h-5" />
                邀請成員
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <div>
                  <label className="block text-gray-400 mb-1">選擇檔案</label>
                  <select
                    value={selectedFile}
                    onChange={(e) => setSelectedFile(e.target.value)}
                    className="w-full p-2 bg-gray-700 text-white rounded border border-gray-600"
                  >
                    <option value="">請選擇...</option>
                    {fileList.filter(f => f.type === 'file').map((file) => (
                      <option key={file.uuid} value={file.uuid}>
                        {file.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-gray-400 mb-1">使用者名稱 / Email</label>
                  <input
                    type="text"
                    value={inviteName}
                    onChange={(e) => {
                      const val = e.target.value;
                      setInviteName(val);
                      // Auto-detect email if input contains @
                      if (val.includes('@')) {
                        setInviteEmail(val);
                      } else {
                        // Keep existing email or clear if name field is empty
                        if (!val) setInviteEmail('');
                      }
                    }}
                    placeholder="輸入使用者名稱 或 Email"
                    className="w-full p-2 bg-gray-700 text-white rounded border border-gray-600"
                  />
                </div>
              </div>
              <button
                onClick={handleAddCollaborator}
                className="px-6 py-2 bg-gradient-to-r from-blue-400 to-cyan-400 text-white rounded-lg hover:shadow-xl transition-all cursor-pointer"
              >
                邀請成員
              </button>
            </div>

            {/* Member List */}
            <div className="bg-gray-800 rounded-lg p-6">
              <h2 className="text-xl font-semibold text-white mb-4">成員列表</h2>
              {ownedCollabs.length === 0 ? (
                <p className="text-gray-400">目前沒有發起任何共編</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left">
                    <thead>
                      <tr className="text-gray-500 border-b border-gray-700">
                        <th className="p-2">檔案</th>
                        <th className="p-2">成員名稱</th>
                        <th className="p-2">Email</th>
                        <th className="p-2">權限</th>
                        <th className="p-2">加入時間</th>
                        <th className="p-2">操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {ownedCollabs.map((item) => (
                        <tr key={item.id} className="text-white border-b border-gray-700 hover:bg-gray-700">
                          <td className="p-2">{item.file_name}</td>
                          <td className="p-2">{item.collaborator_name}</td>
                          <td className="p-2">{item.collaborator_email}</td>
                          <td className="p-2">
                            <span className="px-2 py-1 bg-blue-900 text-blue-300 rounded text-sm">
                              {item.permission}
                            </span>
                          </td>
                          <td className="p-2 text-gray-400">{item.created_at}</td>
                          <td className="p-2 flex gap-1">
                            <button
                              onClick={() => navigate(`/collab/edit/${item.file_uuid}`)}
                              className="flex items-center gap-1 px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors cursor-pointer text-xs"
                            >
                              <Edit3 className="w-3 h-3" />
                              編輯
                            </button>
                            <button
                              onClick={() => handleRemoveCollaborator(item.file_uuid, item.collaborator_id)}
                              className="flex items-center gap-1 px-3 py-1 bg-red-600 text-white rounded hover:bg-red-700 transition-colors cursor-pointer text-xs"
                            >
                              <Trash2 className="w-3 h-3" />
                              踢除
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default CollaborationPage;