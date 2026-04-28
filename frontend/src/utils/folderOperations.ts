import { folderApi } from "../api/folderApi";



export async function createFolder(parent_folder_uuid: string | null, folderName: string, fileList: any[]): Promise<[string | string[], string, any[]]> {
  try {
    const data = {
      parent_folder_uuid: parent_folder_uuid,
      name: folderName,
    };
    const r = await folderApi.create(data);

    const newFolder = {
      uuid: r.uuid,
      name: folderName,
      type: "folder",
      date: r.created_at,
      size: 0,
    };

    fileList.unshift(newFolder);

    return [['新增成功!'], "text-green-500", fileList];
  } catch (e) {
    console.error('Create folder error:', e);
    return [["新增失敗, 請稍後再試!"], "text-red-500", fileList];
  }
}

export async function renameFolder(folder_uuid: string, folderName: string, fileList: any[]): Promise<[string | string[], string, any[]]> {
  try {
    const data = {
      folder_uuid: folder_uuid,
      name: folderName
    };
    const r = await folderApi.rename(data);

    const date = r.data?.date || r.data?.time || r.data;

    const folder = fileList.find(
      (item) =>
        item.type === "folder" && item.uuid === folder_uuid
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

export async function deleteFolder(folder_uuid: string, fileList: any[]): Promise<[string | string[], string, boolean, any[]]> {
  try {
    const check = confirm("確定要刪除嗎?");
    if (!check) {
      return [["操作已取消!"], "text-red-500", false, fileList];
    }

    const doubleCheck = confirm("此操作將會一併刪除所有子項目，確定嗎?");
    if (!doubleCheck) {
      return [["操作已取消!"], "text-red-500", false, fileList];
    }

    await folderApi.delete({ folder_uuid, permanent: false });

    const folderIndex = fileList.findIndex(
      (item) => item.type === "folder" && item.uuid === folder_uuid
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
