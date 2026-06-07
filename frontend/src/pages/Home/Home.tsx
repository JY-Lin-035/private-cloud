import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Mail, ArrowRight } from 'lucide-react';
import { authApi } from '../../api/authApi';
import githubIcon from '../../assets/github.svg';

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
                                        href='https://github.com/JY-Lin-035/private-cloud'
                                        target='_blank'
                                        rel='noopener noreferrer'
                                        className='p-3 bg-gray-700/60 border border-gray-500 text-gray-200 rounded-full hover:bg-gray-700 transition-all inline-flex items-center justify-center cursor-pointer'
                                      >
                                                                              <img src={githubIcon} alt='GitHub' className='w-6 h-6 brightness-0 invert' />
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
