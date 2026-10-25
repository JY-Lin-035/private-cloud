import { announcementApi } from '../api/announcementApi';

type Listener = (items: string[]) => void;

const POLL_MS = 60_000;

let items: string[] = [];
let subscribers = new Set<Listener>();
let timer: ReturnType<typeof setInterval> | null = null;
let started = false;

function notify() {
  subscribers.forEach(fn => fn(items));
}

async function refresh() {
  try {
    const list = await announcementApi.active();
    if (list.join('\u0000') !== items.join('\u0000')) {
      items = list;
      notify();
    }
  } catch {
    if (items.length) {
      items = [];
      notify();
    }
  }
}

/** Start polling (idempotent). Call when a ticker becomes visible. */
export function startAnnouncementPolling() {
  if (!started) {
    started = true;
    refresh();
  }
  if (!timer) {
    timer = setInterval(refresh, POLL_MS);
  }
}

export function stopAnnouncementPolling() {
  if (timer) {
    clearInterval(timer);
    timer = null;
  }
}

/** Force immediate refresh (after admin CRUD). */
export function invalidateAnnouncements() {
  void refresh();
}

/** Subscribe; also ensures polling is active while any subscriber exists. */
export function subscribeAnnouncements(fn: Listener): () => void {
  subscribers.add(fn);
  fn(items);
  startAnnouncementPolling();
  return () => {
    subscribers.delete(fn);
    if (subscribers.size === 0) stopAnnouncementPolling();
  };
}
