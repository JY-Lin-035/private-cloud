import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Mail, ArrowRight } from 'lucide-react';
import { authApi } from '../../api/authApi';

function Home({ layoutClass = '' }: { layoutClass?: string }) {
  const navigate = useNavigate();
  const [session, setSession] = useState({ authenticated: false });

  const TYPING_TEXTS = [
    '現代、自架，完全由你掌控的個人雲端儲存方案。',
    '安全、快速，穩定在你手中。',
    '告別第三方，擁抱真正的資料自主權。',
  ];

  const [textIndex, setTextIndex] = useState(0);
  const [charPos, setCharPos] = useState(0);
  const [isDeleting, setIsDeleting] = useState(false);

  const currentText = TYPING_TEXTS[textIndex];

  const tick = useCallback(() => {
    if (!isDeleting) {
      if (charPos < currentText.length) {
        setCharPos((p) => p + 1);
      } else {
        setTimeout(() => setIsDeleting(true), 1500);
      }
    } else {
      if (charPos > 0) {
        setCharPos((p) => p - 1);
      } else {
        setIsDeleting(false);
        setTextIndex((prev) => (prev + 1) % TYPING_TEXTS.length);
      }
    }
  }, [charPos, isDeleting, currentText.length]);

  useEffect(() => {
    const timer = setInterval(tick, 100);
    return () => clearInterval(timer);
  }, [tick]);

  useEffect(() => {
    (async () => {
      try {
        const data = await authApi.checkSession();
        setSession(data);
      } catch {
        setSession({ authenticated: false });
      }
    })();
  }, []);

  return (
    <div className={layoutClass}>
      <div className='flex flex-col items-center justify-center min-h-[75vh] px-6 py-12 text-center animate-fadeIn duration-1000'>
        <h1 className='text-6xl md:text-8xl font-extrabold text-white tracking-tight'>
          <span className='bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-cyan-300'>
            Meow Cloud
          </span>
        </h1>
        <div className='mt-8 h-10 md:h-12'>
          <span className='text-xl md:text-2xl text-cyan-300 tracking-wide'>
            {currentText.slice(0, charPos)}
            <span className='ml-1 align-middle inline-block w-[3px] h-6 bg-cyan-300 animate-pulse'>&nbsp;</span>
          </span>
        </div>
        <div className='mt-8 flex flex-col items-center gap-6'>
                  <div className='flex flex-col sm:flex-row gap-4'>
                    {session.authenticated ? (
                      <button
                        onClick={() => navigate('/file-list')}
                        className='px-10 py-4 text-lg font-semibold bg-gradient-to-r from-blue-400 to-cyan-400 text-white rounded-xl shadow-lg hover:shadow-xl transition-all cursor-pointer'
                      >
                        Enter Cloud <ArrowRight className='inline ml-2 w-5 h-5' />
                      </button>
                    ) : (
                      <button
                        onClick={() => navigate('/login')}
                        className='px-10 py-4 text-lg font-semibold bg-gradient-to-r from-blue-400 to-cyan-400 text-white rounded-xl shadow-lg hover:shadow-xl transition-all cursor-pointer'
                      >
                        Login Now <ArrowRight className='inline ml-2 w-5 h-5' />
                      </button>
                    )}
                  </div>
                  <div className='flex flex-row gap-4'>
                                      <a
                                        href='https://github.com/JY-Lin-035'
                                        target='_blank'
                                        rel='noopener noreferrer'
                                        className='p-3 bg-gray-700/60 border border-gray-500 text-gray-200 rounded-full hover:bg-gray-700 transition-all inline-flex items-center justify-center cursor-pointer'
                                      >
                                        <svg className='w-6 h-6' viewBox='0 0 24 24' fill='currentColor'>
                                            <path d='M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.552-1.23 3. 23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.906-.015 3.286 3.286 0 .315.21.69.825.57C20.57 20.565 22.092 24 17.592 24 24.297c0-6.627-5.373-12-12-12'/>
                                        /></svg>
                                      </a>
                                      <a
                                        href='mailto:JY@junmail.abrdns.com'
                                        className='p-3 bg-gray-700/60 border border-gray-500 text-gray-200 rounded-full hover:bg-gray-700 transition-all inline-flex items-center justify-center cursor-pointer'
                                      >
                                        <Mail className='w-6 h-6' />
                                      </a>
                                    </div>
                </div>
      </div>
    </div>
  );
}

export default Home;
