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
      <div className='flex flex-col items-center justify-center min-h-[75vh] px-6 py-12 text-center'>
        <h1 className='text-5xl md:text-7xl font-extrabold text-white tracking-tight'>
          <span className='bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-cyan-300'>
            Meow Cloud
          </span>
        </h1>
        <div className='mt-6 h-8 md:h-10'>
          <span className='text-lg text-cyan-300 font-mono tracking-wide'>
            {currentText.slice(0, charPos)}
            <span className='animate-pulse inline-block w-[2px] h-5 bg-cyan-300 ml-0.5 align-middle'>&nbsp;</span>
          </span>
        </div>
        <div className='mt-8 flex flex-col sm:flex-row gap-4'>
          {session.authenticated ? (
            <button
              onClick={() => navigate('/')}
              className='px-8 py-3 bg-gradient-to-r from-blue-400 to-cyan-400 text-white rounded-xl font-semibold shadow-lg hover:shadow-xl transition-all cursor-pointer'
            >
              Enter Dashboard <ArrowRight className='inline ml-2 w-4 h-4' />
            </button>
          ) : (
            <button
              onClick={() => navigate('/login')}
              className='px-8 py-3 bg-gradient-to-r from-blue-400 to-cyan-400 text-white rounded-xl font-semibold shadow-lg hover:shadow-xl transition-all cursor-pointer'
            >
              Login Now <ArrowRight className='inline ml-2 w-4 h-4' />
            </button>
          )}
          <a
            href='https://github.com/JY-Lin-035'
            target='_blank'
            rel='noopener noreferrer'
            className='px-8 py-3 bg-gray-700/60 border border-gray-500 text-gray-200 rounded-xl font-semibold
            hover:bg-gray-700 transition-all inline-flex items-center gap-2 cursor-pointer'
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="10"/></svg>
            GitHub
          </a>
          <a
            href='mailto:JY@junmail.abrdns.com'
            className='px-8 py-3 bg-gray-700/60 border border-gray-500 text-gray-200 rounded-xl font-semibold
            hover:bg-gray-700 transition-all inline-flex items-center gap-2 cursor-pointer'
          >
            <Mail className='w-5 h-5' />
            Contact
          </a>
        </div>
      </div>
    </div>
  );
}

export default Home;
