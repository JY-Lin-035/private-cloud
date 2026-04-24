import { useState } from 'react';
import Mail from './ModifyOptions/Mail';
import Password from './ModifyOptions/Password';



function Account() {
  const [mode, setMode] = useState(true);

  return (
    <div className="h-screen w-screen flex justify-center items-center">
      <div className="min-h-[70vh] w-[70vw] flex justify-center items-center">
        <div className="flex flex-col mr-6">
          <button
            type="button"
            onClick={() => setMode(true)}
            className="text-white bg-gradient-to-r from-cyan-500 to-blue-500 hover:bg-gradient-to-bl font-medium rounded-lg text-sm px-5 py-2.5 text-center me-2 mb-2"
          >
            信箱地址
          </button>
          <button
            type="button"
            onClick={() => setMode(false)}
            className="text-white bg-gradient-to-r from-cyan-500 to-blue-500 hover:bg-gradient-to-bl font-medium rounded-lg text-sm px-5 py-2.5 text-center me-2 mb-2"
          >
            密碼
          </button>
        </div>

        <div className="w-[50%]">
          <ol className="relative border-s border-gray-700">
            {mode ? <Mail /> : <Password />}
          </ol>
        </div>
      </div>
    </div>
  );
}

export default Account;
