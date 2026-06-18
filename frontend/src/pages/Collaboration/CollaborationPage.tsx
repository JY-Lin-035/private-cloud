import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import type { MyCollaborationItem, CollaborationGroup } from '../../types';
import { collaborationApi } from '../../api/collaborationApi';
import { fileApi } from '../../api/fileApi';
import { folderApi } from '../../api/folderApi';
import { ChevronDown, ChevronRight, Users, UserPlus, FileText, Trash2, Edit3 } from 'lucide-react';

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
  const [collapsedFiles, setCollapsedFiles] = useState<Set<string>>(new Set());

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
      const items = res.data.items || [];
      setOwnedCollabs(items);
      setCollapsedFiles(new Set(items.map((item: CollaborationGroup) => item.file_uuid)));
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
    const inviteQuery = inviteName.trim();
    const inviteEmailValue = inviteEmail.trim();
    if (!selectedFile || !inviteQuery) {
      showMessage('請選擇檔案並輸入使用者名稱或 Email', 'error');
      return;
    }
    try {
      const res = await collaborationApi.addCollaborator(selectedFile, inviteQuery, inviteEmailValue);
      showMessage(res.data.message || '邀請成功', 'success');
      setInviteName('');
      setInviteEmail('');
      loadOwnedCollaborations();
    } catch (e: any) {
      const errorMessage = e?.message || e.response?.data?.detail || '邀請失敗';
      showMessage(
        errorMessage.includes('已經在共編名單') ? '已經邀請過此成員' : errorMessage,
        'error'
      );
    }
  }

  async function handleRemoveCollaborator(fileUuid: string, collaboratorId: number) {
    try {
      await collaborationApi.removeCollaborator(fileUuid, collaboratorId);
      showMessage('已移除共編成員', 'success');
      loadOwnedCollaborations();
    } catch (e: any) {
      showMessage(e?.message || e.response?.data?.detail || '移除失敗', 'error');
    }
  }

  function toggleFileMembers(fileUuid: string) {
    setCollapsedFiles((prev) => {
      const next = new Set(prev);
      if (next.has(fileUuid)) {
        next.delete(fileUuid);
      } else {
        next.add(fileUuid);
      }
      return next;
    });
  }

  return (
    <div className={`flex w-full min-h-full flex-col justify-start items-center pb-10 ${layoutClass}`}>
      <div className="w-[95vw] sm:w-[90vw] md:w-[80vw] lg:w-[75vw] xl:w-[70vw] mx-auto mt-[2%] mb-10">
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
                <div className="space-y-3">
                  {ownedCollabs.map((group) => {
                    const isCollapsed = collapsedFiles.has(group.file_uuid);
                    return (
                      <div key={group.file_uuid} className="border border-gray-700 rounded-md overflow-hidden">
                        <div className="flex flex-col gap-3 bg-gray-900/50 px-4 py-3 md:flex-row md:items-center md:justify-between">
                          <div className="flex min-w-0 items-center gap-3">
                            <button
                              onClick={() => toggleFileMembers(group.file_uuid)}
                              className="shrink-0 text-gray-300 hover:text-white cursor-pointer"
                              title={isCollapsed ? '展開成員' : '收合成員'}
                            >
                              {isCollapsed ? <ChevronRight className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                            </button>
                            <FileText className="w-5 h-5 shrink-0 text-blue-400" />
                            <div className="min-w-0">
                              <p className="truncate text-white font-semibold">{group.file_name}</p>
                              <p className="text-xs text-gray-400">{group.members.length} 位成員</p>
                            </div>
                          </div>
                          <button
                            onClick={() => navigate(`/collab/edit/${group.file_uuid}`)}
                            className="flex w-fit items-center gap-1 px-3 py-1.5 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors cursor-pointer text-xs"
                            title="線上編輯"
                          >
                            <Edit3 className="w-3 h-3" />
                            線上編輯
                          </button>
                        </div>

                        {!isCollapsed && (
                          <div className="max-h-72 overflow-y-auto">
                            <div className="hidden grid-cols-[minmax(140px,1.2fr)_minmax(180px,1.2fr)_80px_120px_40px] gap-3 border-b border-gray-700 px-4 py-2 text-xs text-gray-500 md:grid">
                              <span>成員</span>
                              <span>Email</span>
                              <span className="text-center">權限</span>
                              <span className="text-center">加入時間</span>
                              <span></span>
                            </div>
                            {group.members.map((m) => (
                              <div
                                key={`${group.file_uuid}-${m.collaborator_id}`}
                                className="grid gap-3 border-b border-gray-700 px-4 py-3 text-white last:border-b-0 md:grid-cols-[minmax(140px,1.2fr)_minmax(180px,1.2fr)_80px_120px_40px] md:items-center"
                              >
                                <div className="flex min-w-0 items-center gap-2">
                                  <div className="w-7 h-7 shrink-0 rounded-full bg-blue-500 flex items-center justify-center text-xs font-bold">
                                    {m.collaborator_name.charAt(0).toUpperCase()}
                                  </div>
                                  <span className="truncate">{m.collaborator_name}</span>
                                </div>
                                <div className="truncate text-sm text-gray-400">{m.collaborator_email}</div>
                                <div className="md:text-center">
                                  <span className="px-1.5 py-0.5 bg-blue-900 text-blue-300 rounded text-xs">{m.permission}</span>
                                </div>
                                <div className="text-sm text-gray-400 md:text-center">{m.created_at}</div>
                                <div className="md:text-center">
                                  <button
                                    onClick={() => handleRemoveCollaborator(group.file_uuid, m.collaborator_id)}
                                    className="text-red-400 hover:text-red-300 cursor-pointer"
                                    title="踢除成員"
                                  >
                                    <Trash2 className="w-4 h-4" />
                                  </button>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
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
