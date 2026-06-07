import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Github, Mail, ArrowRight } from 'lucide-react';
import { authApi } from '../../api/authApi';

function Home({ layoutClass = '' }: { layoutClass?: string }) {
  const navigate = useNavigate();
  const [session, setSession] = useState({ authenticated: false });

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
        <p className='mt-4 text-lg text-gray-400 max-w-2xl'>
          A modern, self-hosted personal cloud storage solution.
          <br />
          Secure, fast, and fully under your control.
        </p>
        <div className='mt-8 flex flex-col sm:flex-row gap-4'>
          {session.authenticated ? (
            <button
              onClick={() => navigate('/file-list')}
              className='px-8 py-3 bg-gradient-to-r from-blue-600 to-cyan-500 text-white rounded-xl font-semibold shadow-lg hover:shadow-xl transition-all'
            >
              Enter Dashboard <ArrowRight className='inline ml-2 w-4 h-4' />
            </button>
          ) : (
            <button
              onClick={() => navigate('/login')}
              className='px-8 py-3 bg-gradient-to-r from-blue-600 to-cyan-500 text-white rounded-xl font-semibold shadow-lg hover:shadow-xl transition-all'
            >
              Login Now <ArrowRight className='inline ml-2 w-4 h-4' />
            </button>
          )}
          <a
            href='https://github.com/JY-Lin-035'
            target='_blank'
            rel='noopener noreferrer'
            className='px-8 py-3 border border-gray-500 text-gray-300 rounded-xl font-semibold
            hover:bg-gray-800 transition-all inline-flex items-center gap-2'
          >
            <Github className='w-5 h-5' />
            GitHub
          </a>
          <a
            href='mailto:JY@junmail.abrdns.com'
            className='px-8 py-3 border border-gray-500 text-gray-300 rounded-xl font-semibold
            hover:bg-gray-800 transition-all inline-flex items-center gap-2'
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
