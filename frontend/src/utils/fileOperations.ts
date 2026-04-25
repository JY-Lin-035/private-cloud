import { fileApi } from '../api/fileApi';
import { shareApi } from '../api/shareApi';



// 下載
export function downloadFile(dir: string, fileName: string): [string | string[], string, boolean] {
  try {
    const url = `http://localhost:8000/api/files/download?dir=${encodeURIComponent(dir)}&filename=${encodeURIComponent(fileName)}`;

    const tempLink = document.createElement("a");
    tempLink.href = url;
    tempLink.download = fileName;

    document.body.appendChild(tempLink);
    tempLink.click();
    document.body.removeChild(tempLink);

    return ["", "", false];
  } catch (e) {
    console.error(e);
    return [["檔案不存在!"], "text-red-500", true];
  }
}

// 刪除
export async function deleteFile(dir: string, fileName: string, deleteItem: any, fileList: any[], storage: any): Promise<[string | string[], string, boolean, any[]]> {
  try {
    const fl = fileList;
    const check = confirm("確定要刪除嗎?");
    if (!check) {
      return [["操作已取消!"], "text-red-500", false, fileList];
    }

    const r = await fileApi.deleteFile(dir, fileName);

    const index = fl.findIndex((item) => item === deleteItem);
    if (index !== -1) {
      fl.splice(index, 1);
    }

    storage.addUsedStorage(-Number(r.size));

    return [["刪除成功！"], "text-red-500", true, fl];
  } catch (e) {
    console.error(e);
    return [["檔案或資料夾不存在!"], "text-red-500", true, fileList];
  }
}

// 檔案分享
export async function getShareFileLink(dir: string, fileName: string): Promise<[string | string[], string, boolean, string, boolean]> {
  try {
    const data = {
      dir: dir,
      filename: fileName,
    };
    const r = await shareApi.getLink(data);

    // response className showMode shareLink copyShow
    return [fileName, "text-green-500", false, r, true];
  } catch (e) {
    console.error(e);
    return [["連結生成失敗, 請稍後再試!"], "text-red-500", true, "", false];
  }
}

// 移除檔案分享
export async function deleteShareFileLink(dir: string, fileName: string): Promise<[string | string[], string, boolean]> {
  try {
    await shareApi.deleteLink_by_filename(dir, fileName);

    return [['移除成功!'], "text-red-500", true];
  } catch (e) {
    console.error(e);
    return [["連結移除失敗, 請稍後再試!"], "text-red-500", true];
  }
}
