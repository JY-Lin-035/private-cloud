import { create } from 'zustand';
import axios from 'axios';

interface StorageState {
  signalStorage: number;
  usedStorage: number;
  availableStorage: number;
  totalStorage: number;
  percentage: string;
  getFromAPI: () => Promise<void>;
  format: (bytes: number, Type?: string | null) => [number, string | null];
  addUsedStorage: (fileSize: number) => void;
  saveToLocalStorage: () => void;
  loadFromLocalStorage: () => boolean;
}

export const useStorage = create<StorageState>((set, get) => ({
  signalStorage: 0,
  usedStorage: 0,
  availableStorage: 0,
  totalStorage: 0,
  percentage: '0',

  getFromAPI: async () => {
    try {
      const r = await axios.get(`http://localhost:8000/api/files/getStorage`, { withCredentials: true });
      const signalStorage = r.data['signalStorage'];
      const totalStorage = r.data['totalStorage'];
      const usedStorage = r.data['usedStorage'];
      const availableStorage = totalStorage - usedStorage;
      const percentage = (usedStorage / totalStorage * 100).toFixed(2);

      set({
        signalStorage,
        totalStorage,
        usedStorage,
        availableStorage,
        percentage,
      });

      get().saveToLocalStorage();
    } catch (e) {
      // console.error(e);
    }
  },

  format: (bytes: number, Type: string | null = null) => {
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let i = 0;

    if (Type) {
      while (units[i] !== Type && i < units.length - 1) {
        bytes /= 1024;
        i++;
      }
      return [Math.round(bytes * 100) / 100, null];
    } else {
      while (bytes >= 1024 && i < units.length - 1) {
        bytes /= 1024;
        i++;
      }
      return [Math.round(bytes * 100) / 100, units[i]];
    }
  },

  addUsedStorage: (fileSize: number) => {
    const state = get();
    const newUsedStorage = state.usedStorage + fileSize;
    const newAvailableStorage = state.availableStorage - fileSize;
    const newPercentage = (newUsedStorage / state.totalStorage * 100).toFixed(2);

    set({
      usedStorage: newUsedStorage,
      availableStorage: newAvailableStorage,
      percentage: newPercentage,
    });

    get().saveToLocalStorage();
  },

  saveToLocalStorage: () => {
    const state = get();
    const data = {
      availableStorage: state.availableStorage,
      signalStorage: state.signalStorage,
      usedStorage: state.usedStorage,
      totalStorage: state.totalStorage,
      percentage: state.percentage,
    };
    localStorage.setItem('storage', JSON.stringify(data));
  },

  loadFromLocalStorage: () => {
    const saved = localStorage.getItem('storage');
    if (saved) {
      const data = JSON.parse(saved);
      const signalStorage = data.signalStorage || 0;
      const usedStorage = data.usedStorage || 0;
      const availableStorage = data.availableStorage || 0;
      const totalStorage = data.totalStorage || 0;
      const percentage = (usedStorage / totalStorage * 100).toFixed(2) || '0';

      set({
        signalStorage,
        usedStorage,
        availableStorage,
        totalStorage,
        percentage,
      });
      return true;
    }
    return false;
  },
}));
