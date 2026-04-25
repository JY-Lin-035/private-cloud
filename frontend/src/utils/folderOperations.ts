import { folderApi } from "../api/folderApi";



export async function createFolder(dir: string, folderName: string, fileList: any[]): Promise<[string | string[], string, any[]]> {
  try {
    const data = {
      dir: dir,
      folderName: folderName,
    };
    const r = await folderApi.createFolder(data);

    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    const seconds = String(now.getSeconds()).padStart(2, '0');
    const localDate = `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;

    const date = r.data?.date || r.data?.time || r.data || localDate;

    fileList.unshift({
      name: folderName,
      type: "folder",
      date: date,
    });

    return [['新增成功!'], "text-green-500", fileList];
  } catch (e) {
    // console.error(e);
    return [["新增失敗, 請稍後再試!"], "text-red-500", fileList];
  }
}

export async function renameFolder(dir: string, originName: string, folderName: string, fileList: any[]): Promise<[string | string[], string, any[]]> {
  try {
    const data = {
      dir: dir,
      originName: originName,
      folderName: folderName
    };
    const r = await folderApi.renameFolder(data);

    const date = r.data?.date || r.data?.time || r.data;

    const folder = fileList.find(
      (item) =>
        item.type === "folder" && item.name === originName
    );

    if (folder) {
      folder.name = folderName;
      if (date) {
        folder.date = date;
      }
    }

    return [['改名成功!'], "text-green-500", fileList];
  } catch (e) {
    console.error(e);
    return [["改名失敗, 請稍後再試!"], "text-red-500", fileList];
  }
}

export async function deleteFolder(dir: string, folderName: string, fileList: any[], storage: any): Promise<[string | string[], string, boolean, any[]]> {
  try {
    const check = confirm("確定要刪除嗎?");
    if (!check) {
      return [["操作已取消!"], "text-red-500", false, fileList];
    }

    const doubleCheck = confirm("此操作將會一併刪除所有子項目，確定嗎?");
    if (!doubleCheck) {
      return [["操作已取消!"], "text-red-500", false, fileList];
    }

    const r = await folderApi.deleteFolder(dir, folderName);

    storage.addUsedStorage(-Number(r.size));

    const folderIndex = fileList.findIndex(
      (item) => item.type === "folder" && item.name === folderName
    );

    if (folderIndex !== -1) {
      fileList.splice(folderIndex, 1);
    }

    return [['刪除成功!'], "text-red-500", true, fileList];
  } catch (e) {
    console.error(e);
    return [["刪除失敗, 請稍後再試!"], "text-red-500", true, fileList];
  }
}
