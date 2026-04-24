// File and Folder Items
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
