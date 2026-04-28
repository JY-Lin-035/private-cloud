// File and Folder Items (Legacy - path-based)
export interface FileItem {
  name: string;
  type: 'file';
  date: string;
  size: string;
}

export interface FolderItem {
  name: string;
  type: 'folder';
  date: string;
}

export type FileOrFolderItem = FileItem | FolderItem;

// New UUID-based File and Folder Items
export interface FileItemUUID {
  uuid: string;
  name: string;
  type: 'file';
  size: number;
  date: string;
  mime_type?: string;
  shared?: string;
  deleted_at?: string;
}

export interface FolderItemUUID {
  uuid: string;
  name: string;
  type: 'folder';
  size: number;
  date: string;
  shared?: string;
  deleted_at?: string;
}

export type FileOrFolderItemUUID = FileItemUUID | FolderItemUUID;

// Storage State
export interface StorageState {
  signalStorage: number;
  usedStorage: number;
  availableStorage: number;
  totalStorage: number;
  percentage: string;
}

// API Response Types
export interface StorageResponse {
  signalStorage: number;
  totalStorage: number;
  usedStorage: number;
}

export interface FileListResponse {
  file: FileOrFolderItem[];
}

export interface ShareLinkResponse {
  link: string;
}

export interface ShareItem {
  date: string;
  name: string;
  path: string;
  link: string;
}

export interface ShareListResponse {
  share: ShareItem[];
}

export interface FileInfoResponse {
  name: string;
  size: string;
}

export interface DeleteResponse {
  size: number;
}

export interface CreateFolderResponse {
  date: string;
}

// New UUID-based API Response Types
export interface FolderResponse {
  uuid: string;
  owner_id: number;
  parent_id: string | null;
  name: string;
  size: number;
  shared: string | null;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export interface FileResponse {
  uuid: string;
  owner_id: number;
  parent_folder_id: string | null;
  name: string;
  size: number;
  mime_type: string | null;
  storage_path: string;
  shared: string | null;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export interface FileListResponseUUID {
  files: FileOrFolderItemUUID[];
}

export interface FolderListResponse {
  folders: FolderItemUUID[];
}

export interface DeleteResponseUUID {
  uuid: string;
  size: number;
  permanent: boolean;
}

export interface RestoreResponse {
  uuid: string;
  restored: boolean;
}

// User Types
export interface User {
  email?: string;
  username?: string;
}

// API Request Types
export interface ShareLinkRequest {
  dir: string;
  filename: string;
}

export interface CreateFolderRequest {
  dir: string;
  folderName: string;
}

export interface RenameFolderRequest {
  dir: string;
  originName: string;
  folderName: string;
}

// New UUID-based API Request Types
export interface CreateFolderRequestUUID {
  parent_folder_uuid?: string;
  name: string;
}

export interface RenameFolderRequestUUID {
  folder_uuid: string;
  name: string;
}

export interface DeleteFolderRequestUUID {
  folder_uuid: string;
  permanent: boolean;
}

export interface RestoreFolderRequestUUID {
  folder_uuid: string;
}

export interface DeleteFileRequestUUID {
  file_uuid: string;
  permanent: boolean;
}

export interface RestoreFileRequestUUID {
  file_uuid: string;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
}

export interface ResetPasswordRequest {
  email: string;
  code: string;
  password: string;
}

export interface ModifyEmailRequest {
  email: string;
  check_email: string;
  code: string;
}

export interface ModifyPasswordRequest {
  now_pw: string;
  new_pw: string;
}

// Component Props Types
export interface BreadcrumbProps {
  PATH: string;
}

export interface NoticeProps {
  inputShow: boolean;
  folderName: string;
  notices: string | string[];
  showMode: boolean;
  className: string;
}

export interface UpLoadProps {
  PATH: string;
}

// Utility Types
export type SortType = 'date' | 'name' | 'size' | 'path';

export interface PaginationState {
  page: number;
  perPage: number;
  totalPages: number;
}

export interface FilterState {
  search: string;
  sortType: SortType;
  sortUpDown: boolean;
}
