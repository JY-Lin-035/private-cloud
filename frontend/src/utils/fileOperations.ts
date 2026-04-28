import { fileApi } from '../api/fileApi';
import { shareApi } from '../api/shareApi';



// 下載
export async function downloadFile(file_uuid: string): Promise<[string | string[], string, boolean]> {
  try {
    await fileApi.download(file_uuid);
    return ["", "", false];
  } catch (e) {
    console.error(e);
    return [["檔案不存在!"], "text-red-500", true];
  }
}

// 刪除
export async function deleteFile(item_uuid: string, item_type: string, deleteItem: any, fileList: any[], storage: any): Promise<[string | string[], string, boolean, any[]]> {
  try {
    const fl = fileList;
    const check = confirm("確定要刪除嗎?");
    if (!check) {
      return [["操作已取消!"], "text-red-500", false, fileList];
    }

    const r = await fileApi.delete({ file_uuid: item_uuid, permanent: false });

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
export async function getShareFileLink(item_uuid: string, item_type: string): Promise<[string | string[], string, boolean, string, boolean]> {
  try {
    const data = {
      item_uuid: item_uuid,
      item_type: item_type,
    };
    const r = await shareApi.getLink(data);

    // response className showMode shareLink copyShow
    return ["分享連結已生成", "text-green-500", false, r, true];
  } catch (e) {
    console.error(e);
    return [["連結生成失敗, 請稍後再試!"], "text-red-500", true, "", false];
  }
}

// 移除檔案分享
export async function deleteShareFileLink(item_uuid: string, item_type: string): Promise<[string | string[], string, boolean]> {
  try {
    await shareApi.deleteLink(item_uuid, item_type);

    return [['移除成功!'], "text-red-500", true];
  } catch (e) {
    console.error(e);
    return [["連結移除失敗, 請稍後再試!"], "text-red-500", true];
  }
}
