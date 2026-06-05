import { useState } from 'react';
import Mail from './ModifyOptions/Mail';
import Password from './ModifyOptions/Password';



function Account({ layoutClass = "" }: { layoutClass?: string }) {
  const [mode, setMode] = useState(true);

  return (
    <div className={`h-screen w-screen flex justify-center items-center ${layoutClass}`}>
      <div className="min-h-[70vh] w-[90vw] sm:w-[80vw] md:w-[70vw] lg:w-[60vw] flex flex-col md:flex-row justify-center items-center">
        <div className="flex flex-row md:flex-col mb-4 md:mb-0 md:mr-6 gap-2">
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

        <div className="w-full md:w-[50%]">
          <ol className="relative border-s border-gray-700">
            {mode ? <Mail /> : <Password />}
          </ol>
        </div>
      </div>
    </div>
  );
}

export default Account;
