import { useEffect, useState } from 'react';
import { subscribeAnnouncements } from '../store/announcements';

const HANDOFF_MS = 1800;
const HOLD_MS = 2000;
const HOLD_SOLO_MS = 5000;

/**
 * Dual-track ticker: while the current line glides out to the right edge,
 * the next line glides in from the left edge simultaneously.
 * Both travel the same distance in the same time, so their centres are
 * always exactly one container-width apart -> they can never overlap,
 * and there is zero dead air between lines (left -> right direction).
 */
function AnnouncementTicker({ visible }: { visible: boolean }) {
  const [items, setItems] = useState<string[]>([]);
  const [idx, setIdx] = useState(-1);
  const [phase, setPhase] = useState<'hold' | 'handoff'>('hold');

  useEffect(() => {
    if (!visible) {
      setItems([]);
      setIdx(-1);
      setPhase('hold');
      return;
    }
    return subscribeAnnouncements(list => {
      setItems(list);
    });
  }, [visible]);

  const count = items.length;

  useEffect(() => {
    if (!count) return;
    let t: ReturnType<typeof setTimeout>;
    const schedule = () => {
      if (document.hidden) {
        t = setTimeout(schedule, 1000);
        return;
      }
      if (phase === 'hold') {
        t = setTimeout(() => setPhase('handoff'), count === 1 ? HOLD_SOLO_MS : HOLD_MS);
      } else {
        t = setTimeout(() => {
          setIdx(i => (i + 1) % count);
          setPhase('hold');
        }, HANDOFF_MS);
      }
    };
    schedule();
    return () => clearTimeout(t);
  }, [phase, count, idx]);

  if (!count) return null;

  const cur = idx >= 0 ? items[idx] : '';
  const next = items[((idx + 1) % count + count) % count];

  const curOffset = phase === 'handoff' ? '100%' : '0%';
  const nextOffset = phase === 'handoff' ? '0%' : '-100%';
  const transition = phase === 'handoff' ? `transform ${HANDOFF_MS}ms ease-in-out` : 'none';

  const spanCls = "absolute inset-0 flex items-center justify-center text-cyan-300 text-sm lg:text-base font-medium whitespace-nowrap px-4";

  return (
    <div className="hidden md:flex flex-1 min-w-0 justify-center overflow-hidden mx-6 h-10 relative" aria-label="網站公告" role="status">
      <span className={spanCls} style={{ transform: `translateX(${curOffset})`, transition }}>
        {cur && <span className="truncate max-w-full px-2">📢 {cur}</span>}
      </span>
      <span className={spanCls} style={{ transform: `translateX(${nextOffset})`, transition }}>
        <span className="truncate max-w-full px-2">📢 {next}</span>
      </span>
    </div>
  );
}

export default AnnouncementTicker;
