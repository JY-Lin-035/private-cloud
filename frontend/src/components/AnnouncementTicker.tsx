import { useEffect, useState } from 'react';
import { subscribeAnnouncements } from '../store/announcements';

const SLIDE_MS = 2000;
const HOLD_MS = 1500;
const HOLD_SOLO_MS = 4000;
const JUMP_MS = 60;

type Phase = 'idle' | 'slideIn' | 'hold' | 'slideOut' | 'reset';

function AnnouncementTicker({ visible }: { visible: boolean }) {
  const [items, setItems] = useState<string[]>([]);
  const [idx, setIdx] = useState(0);
  const [phase, setPhase] = useState<Phase>('idle');

  useEffect(() => {
    if (!visible) {
      setItems([]);
      setPhase('idle');
      setIdx(0);
      return;
    }
    return subscribeAnnouncements(list => {
      setItems(list);
      setIdx(i => (list.length ? i % list.length : 0));
      setPhase(p => (p === 'idle' && list.length ? 'slideIn' : p));
    });
  }, [visible]);

  useEffect(() => {
    if (!items.length) return;

    let t: ReturnType<typeof setTimeout>;
    const hold = items.length === 1 ? HOLD_SOLO_MS : HOLD_MS;

    const advance = () => {
      if (document.hidden) {
        // paused: re-check periodically until visible again
        t = setTimeout(advance, 1000);
        return;
      }
      if (phase === 'slideIn') {
        t = setTimeout(() => { setPhase('hold'); advance(); }, SLIDE_MS);
      } else if (phase === 'hold') {
        t = setTimeout(() => { setPhase('slideOut'); advance(); }, hold);
      } else if (phase === 'slideOut') {
        t = setTimeout(() => { setPhase('reset'); advance(); }, SLIDE_MS);
      } else if (phase === 'reset') {
        t = setTimeout(() => {
          setIdx(i => (i + 1) % items.length);
          setPhase('slideIn');
          advance();
        }, JUMP_MS);
      }
    };

    advance();
    return () => clearTimeout(t);
  }, [phase, items.length]);

  if (!items.length) return null;

  // reset: jump back to the right edge without transition, then next item slides in (right -> left, continuously)
  const offset =
    phase === 'slideIn' || phase === 'hold' ? '0%'
    : phase === 'slideOut' ? '-100%'
    : '100%';
  const transition =
    phase === 'slideIn' || phase === 'slideOut'
      ? `transform ${SLIDE_MS}ms ease-in-out`
      : 'none';

  return (
    <div className="hidden md:flex flex-1 min-w-0 justify-center overflow-hidden mx-6 h-10 relative" aria-label="網站公告" role="status">
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
