import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import type { CollaborationItem, MyCollaborationItem, CollaborationGroup } from '../../types';
import { collaborationApi } from '../../api/collaborationApi';
import { fileApi } from '../../api/fileApi';
import { folderApi } from '../../api/folderApi';
import { Users, UserPlus, FileText, Trash2, Edit3 } from 'lucide-react';

function CollaborationPage({ layoutClass = '' }: { layoutClass?: string }) {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<'my' | 'owned'>('my');
  const [myCollabs, setMyCollabs] = useState<MyCollaborationItem[]>([]);
  const [ownedCollabs, setOwnedCollabs] = useState<CollaborationGroup[]>([]);
  const [fileList, setFileList] = useState<any[]>([]);
  const [selectedFile, setSelectedFile] = useState<string>('');
  const [inviteName, setInviteName] = useState('');
  const [inviteEmail, setInviteEmail] = useState('');
  const [message, setMessage] = useState('');
  const [messageType, setMessageType] = useState<'success' | 'error'>('success');
  const [popupItemUuid, setPopupItemUuid] = useState<string | null>(null);

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

  async function loadFileList() {
    try {
      const homeRes = await folderApi.getHome();
      const homeUuid = homeRes?.uuid;
      if (!homeUuid) return;
      const res = await fileApi.list(homeUuid);
      const files = res?.files || [];
      setFileList(Array.isArray(files) ? files : []);
    } catch (e) {
      console.error('Failed to load file list', e);
    }
  }

  function showMessage(msg: string, type: 'success' | 'error') {
    setMessage(msg);
    setMessageType(type);
    setTimeout(() => setMessage(''), 3000);
  }

  async function handleAddCollaborator() {
    if (!selectedFile || !inviteName || !inviteEmail) {
      showMessage('請填寫完整所有資訊', 'error');
      return;
    }
    try {
      const res = await collaborationApi.addCollaborator(selectedFile, inviteName, inviteEmail);
      showMessage(res.data.message || '邀請成功', 'success');
      setInviteName('');
      setInviteEmail('');
      loadOwnedCollaborations();
    } catch (e: any) {
      showMessage(e.response?.data?.detail || '邀請失敗', 'error');
    }
  }

  async function handleRemoveCollaborator(fileUuid: string, collaboratorId: number) {
    try {
      await collaborationApi.removeCollaborator(fileUuid, collaboratorId);
      showMessage('已移除共編成員', 'success');
      loadOwnedCollaborations();
    } catch (e: any) {
      showMessage(e.response?.data?.detail || '移除失敗', 'error');
    }
  }

  return (
    <div className={`flex w-full h-full flex-col justify-center items-center ${layoutClass}`}>
      <div className="w-[95vw] sm:w-[90vw] md:w-[80vw] lg:w-[75vw] xl:w-[70vw] mx-auto mt-[2%]">
        <h1 className="text-2xl font-bold text-white mb-6 flex items-center gap-2">
          <Users className="w-8 h-8" />
          Collaboration
        </h1>

        <div className="flex mb-6 border-b border-gray-700">
          <button className={`px-6 py-3 text-lg font-medium cursor-pointer transition-colors ${activeTab === 'my' ? 'text-blue-400 border-b-2 border-blue-400' : 'text-gray-400 hover:text-white'}`} onClick={() => setActiveTab('my')}>
            📂 與我共編
          </button>
          <button className={`px-6 py-3 text-lg font-medium cursor-pointer transition-colors ${activeTab === 'owned' ? 'text-blue-400 border-b-2 border-blue-400' : 'text-gray-400 hover:text-white'}`} onClick={() => setActiveTab('owned')}>
            ✏️ 我發起的共編
          </button>
        </div>

        {message && (
          <div className={`mb-4 p-3 rounded-lg ${messageType === 'success' ? 'bg-green-600 text-white' : 'bg-red-600 text-white'}`}>
            {message}
          </div>
        )}

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
                      <tr key={item.id} className="text-white border-b border-gray-700">
                        <td className="p-2 flex items-center gap-2">
                          <FileText className="w-5 h-5 text-blue-400" />
                          {item.file_name}
                        </td>
                        <td className="p-2">{item.owner_name}</td>
                        <td className="p-2">
                          <span className="px-2 py-1 bg-blue-900 text-blue-300 rounded text-sm">{item.permission}</span>
                        </td>
                        <td className="p-2 text-gray-400">{item.created_at}</td>
                        <td className="p-2">
                          <button onClick={() => navigate(`/collab/edit/${item.file_uuid}`)} className="flex items-center gap-1 px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors cursor-pointer text-xs">
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

        {activeTab === 'owned' && (
          <div className="space-y-6">
            <div className="bg-gray-800 rounded-lg p-6">
              <h2 className="text-xl font-semibold text-white mb-4 flex items-center gap-2">
                <UserPlus className="w-5 h-5" />
                邀請成員
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <div>
                  <label className="block text-gray-400 mb-1">選擇檔案</label>
                  <select value={selectedFile} onChange={(e) => setSelectedFile(e.target.value)} className="w-full p-2 bg-gray-700 text-white rounded border border-gray-600">
                    <option value="">請選擇...</option>
                    {fileList.filter(f => f.type === 'file').map((file) => (
                      <option key={file.uuid} value={file.uuid}>{file.name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-gray-400 mb-1">使用者名稱 / Email</label>
                  <input type="text" value={inviteName} onChange={(e) => { setInviteName(e.target.value); if (e.target.value.includes('@')) setInviteEmail(e.target.value); else if (!e.target.value) setInviteEmail(''); }} placeholder="輸入使用者名稱 或 Email" className="w-full p-2 bg-gray-700 text-white rounded border border-gray-600" />
                </div>
              </div>
              <button onClick={handleAddCollaborator} className="px-6 py-2 bg-gradient-to-r from-blue-400 to-cyan-400 text-white rounded-lg hover:shadow-xl transition-all cursor-pointer">邀請成員</button>
            </div>

            <div className="bg-gray-800 rounded-lg p-6">
              <h2 className="text-xl font-semibold text-white mb-4">成員列表</h2>
              {ownedCollabs.length === 0 ? (
                <p className="text-gray-400">目前沒有發起任何共編</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left">
                    <thead>
                      <tr className="text-gray-500 border-b border-gray-700">
                        <th className="p-2 text-center">檔案</th>
                        <th className="p-2 text-center">成員</th>
                        <th className="p-2 text-center">Email</th>
                        <th className="p-2 text-center">權限</th>
                        <th className="p-2 text-center">加入時間</th>
                        <th className="p-2 text-center"></th>
                      </tr>
                    </thead>
                    <tbody>
                      {ownedCollabs.map((group) => (
                        group.members.map((m, idx) => (
                          <tr key={`${group.file_uuid}-${m.collaborator_id}`} className="text-white border-b border-gray-700">
                            {idx === 0 && (
                              <td className="p-2 text-center align-middle" rowSpan={group.members.length}>
                                <div className="flex items-center justify-center gap-1">
                                  <span>{group.file_name}</span>
                                  <button
                                    onClick={() => navigate(`/collab/edit/${group.file_uuid}`)}
                                    className="flex items-center gap-1 px-2 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors cursor-pointer text-xs"
                                  >
                                    <Edit3 className="w-3 h-3" />
                                  </button>
                                </div>
                              </td>
                            )}
                            <td className="p-2 text-left">
                              <div className="flex items-center gap-2">
                                <div className="w-6 h-6 rounded-full bg-blue-500 flex items-center justify-center text-xs font-bold">
                                  {m.collaborator_name.charAt(0).toUpperCase()}
                                </div>
                                <span>{m.collaborator_name}</span>
                              </div>
                            </td>
                            <td className="p-2 text-center text-gray-400 text-xs">{m.collaborator_email}</td>
                            <td className="p-2 text-center">
                              <span className="px-1.5 py-0.5 bg-blue-900 text-blue-300 rounded text-xs">{m.permission}</span>
                            </td>
                            <td className="p-2 text-center text-gray-400 text-xs">{m.created_at}</td>
                            <td className="p-2 text-center">
                              <button
                                onClick={() => handleRemoveCollaborator(group.file_uuid, m.collaborator_id)}
                                className="text-red-400 hover:text-red-300 cursor-pointer"
                                title="踢除成員"
                              >
                                <Trash2 className="w-3 h-3" />
                              </button>
                            </td>
                          </tr>
                        ))
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