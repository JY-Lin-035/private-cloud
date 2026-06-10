import { useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { Download } from 'lucide-react';
import { API_BASE_URL } from '../../config/api';



function DownloadShareFile({ layoutClass = "" }: { layoutClass?: string }) {
  const { link } = useParams();

  const get = () => {
    try {
      const url = `${API_BASE_URL}/api/share/downloadFile?link=${link}&t=${Date.now()}`;

      const tempLink = document.createElement("a");
      tempLink.href = url;
      tempLink.download = "UnKnown";

      document.body.appendChild(tempLink);
      tempLink.click();
      document.body.removeChild(tempLink);

      return;
    } catch (e) {
      console.error(e);
      return;
    }
  };

  useEffect(() => {
    get();
  }, [link]);

  return (
    <div className={`flex flex-col justify-center items-center bg-gray-300 ${layoutClass}`}>
      <h1 className="text-xl sm:text-2xl md:text-4xl lg:text-5xl xl:text-[5rem] text-blue-400 font-extrabold tracking-tight leading-none text-center px-4">
        若未開始下載請點擊下方按鈕
      </h1>

      <div
        className="mt-[5vh] flex justify-center items-center bg-green-100 rounded-[3rem] sm:rounded-[6rem] p-4 sm:p-6 cursor-pointer"
        onClick={get}
      >
        <Download className="w-[5vh] sm:w-[8vh] md:w-[10vh] h-[5vh] sm:h-[8vh] md:h-[10vh] mr-2 text-green-600 inline-block align-middle" />
        <span className="text-xl sm:text-2xl md:text-[3.2rem] align-middle text-green-600">開始下載</span>
      </div>
    </div>
  );
}

export default DownloadShareFile;
