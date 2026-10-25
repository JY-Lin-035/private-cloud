import { useEffect, useRef, useState } from 'react';
import { announcementApi } from '../api/announcementApi';

const SLIDE_MS = 1200;
const HOLD_MS = 2500;
const HOLD_SOLO_MS = 5000;

type Phase = 'idle' | 'slideIn' | 'hold' | 'slideOut';

function AnnouncementTicker({ visible }: { visible: boolean }) {
  const [items, setItems] = useState<string[]>([]);
  const [idx, setIdx] = useState(0);
  const [phase, setPhase] = useState<Phase>('idle');
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!visible) { setItems([]); setPhase('idle'); return; }
    let cancelled = false;
    announcementApi.active()
      .then(list => {
        if (cancelled || !list.length) return;
        setItems(list);
        setPhase('slideIn');
      })
      .catch(() => { /* ticker stays hidden */ });
    return () => { cancelled = true; };
  }, [visible]);

  useEffect(() => {
    if (!items.length) return;
    if (document.hidden) {
      // paused while tab hidden: retry soon without advancing
      timer.current = setTimeout(() => setPhase(p => p), 2000);
      return () => { if (timer.current) clearTimeout(timer.current); };
    }
    const hold = items.length === 1 ? HOLD_SOLO_MS : HOLD_MS;
    if (phase === 'slideIn') {
      timer.current = setTimeout(() => setPhase('hold'), SLIDE_MS);
    } else if (phase === 'hold') {
      timer.current = setTimeout(() => setPhase('slideOut'), hold);
    } else if (phase === 'slideOut') {
      timer.current = setTimeout(() => {
        setIdx(i => (i + 1) % items.length);
        setPhase('slideIn');
      }, SLIDE_MS);
    } else {
      return;
    }
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [phase, items.length, idx]);

  if (!items.length) return null;

  const offset = phase === 'slideIn' ? '0%' : phase === 'idle' ? '100%' : phase === 'hold' ? '0%' : '-100%';
  const transition = phase === 'slideIn' || phase === 'slideOut' ? `transform ${SLIDE_MS}ms ease-in-out` : 'none';

  return (
    <div className="hidden md:flex flex-1 justify-center overflow-hidden mx-6 h-10 relative" aria-label="網站公告" role="status">
      <div
        className="absolute inset-0 flex items-center justify-center text-cyan-300 text-sm lg:text-base font-medium whitespace-nowrap px-4"
        style={{ transform: `translateX(${offset})`, transition }}
      >
        <span className="truncate max-w-full px-2">📢 {items[idx]}</span>
      </div>
    </div>
  );
}

export default AnnouncementTicker;
