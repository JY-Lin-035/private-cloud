/**
 * Batch-level 429 cooldown for the resumable upload queue (round 24, PR②).
 *
 * A 429 from the API is a statement about the *window* (30 creations / 300s
 * for the upload endpoint), not about one file. Retrying per file with the
 * previous 0/1/3/5s ladder meant a whole batch marched into the same closed
 * window and every file died with its own error dialog.
 *
 * This module owns the policy:
 *   - the first 429 cools the entire batch down; later 429s inside the same
 *     episode are merged (one notice, not N)
 *   - each new episode waits longer, up to a capped schedule
 *   - when the automatic budget is spent the queue freezes and asks for an
 *     explicit manual resume, which still has to respect a cooldown floor
 *   - any success proves the limiter released us and resets the budget
 *
 * Pure state machine (no DOM, no timers captured from the environment other
 * than the injected clock), so the escalation rules are directly testable.
 */

export const DEFAULT_SCHEDULE_MS = [30_000, 60_000, 120_000, 300_000, 600_000];

export interface CooldownSnapshot {
  /** A local cooldown is in effect: nothing new should be dispatched. */
  cooling: boolean;
  /** The automatic backoff budget is spent — a human has to resume. */
  exhausted: boolean;
  /** Rate-limit episodes seen since the last success. */
  episodes: number;
  /** Epoch ms when the current cooldown ends (Infinity while frozen). */
  resumeAt: number;
  /** Epoch ms of the most recent 429 (for copy/telemetry only). */
  lastSeenAt: number;
}

export type Decision =
  | { action: 'episode'; delayMs: number }
  | { action: 'merged'; delayMs: number }
  | { action: 'exhausted' };

export class UploadCooldown {
  private schedule: number[];
  private now: () => number;
  private episodes = 0;
  private resumeAt = 0;
  private lastSeenAt = 0;
  private listeners = new Set<() => void>();
  private waiters: Array<() => void> = [];
  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor(schedule: number[] = DEFAULT_SCHEDULE_MS, now: () => number = () => Date.now()) {
    this.schedule = schedule;
    this.now = now;
  }

  snapshot(): CooldownSnapshot {
    return {
      cooling: this.resumeAt > this.now(),
      exhausted: this.episodes > this.schedule.length,
      episodes: this.episodes,
      resumeAt: this.resumeAt,
      lastSeenAt: this.lastSeenAt,
    };
  }

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  /** Record a 429 and report what the queue should do about it. */
  noteRateLimited(): Decision {
    this.lastSeenAt = this.now();
    if (this.resumeAt > this.now()) {
      // Already cooling: same episode, do not spend another step.
      this.emit();
      return {
        action: 'merged',
        delayMs: this.resumeAt - this.now(),
      };
    }
    this.episodes += 1;
    if (this.episodes > this.schedule.length) {
      this.freeze();
      this.emit();
      return { action: 'exhausted' };
    }
    const delayMs = this.schedule[this.episodes - 1];
    this.arm(this.now() + delayMs);
    this.emit();
    return { action: 'episode', delayMs };
  }

  /** A request went through: the limiter is open again. */
  noteSuccess(): void {
    if (this.episodes === 0 && this.resumeAt === 0) return;
    this.episodes = 0;
    this.arm(0);
    this.releaseWaiters();
    this.emit();
  }

  /**
   * Freeze until `resumeManually()` is called (budget spent). Kept separate
   * from `arm()` because a frozen queue must not auto-open.
   */
  freeze(): void {
    this.arm(Number.POSITIVE_INFINITY);
  }

  /**
   * Human pressed "繼續上傳". The local cooldown does NOT disappear: we still
   * hold the gate for the longest step of the schedule and send a trickle.
   * Returns the floor delay in ms.
   */
  resumeManually(): number {
    const delayMs = this.capMs();
    this.episodes = 0;
    this.arm(this.now() + delayMs);
    this.emit();
    return delayMs;
  }

  isCooling(): boolean {
    return this.resumeAt > this.now();
  }

  /** Resolves once dispatch is allowed again (immediately when not cooling). */
  wait(): Promise<void> {
    if (!this.isCooling()) return Promise.resolve();
    return new Promise<void>((resolve) => this.waiters.push(resolve));
  }

  private capMs(): number {
    return this.schedule[this.schedule.length - 1] ?? 0;
  }

  private arm(at: number): void {
    this.resumeAt = at;
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    if (Number.isFinite(at)) {
      this.timer = setTimeout(() => {
        this.timer = null;
        if (this.resumeAt !== 0 && this.resumeAt <= this.now()) {
          this.resumeAt = 0;
        }
        this.releaseWaiters();
        this.emit();
      }, Math.max(at - this.now(), 0));
    }
  }

  private releaseWaiters(): void {
    if (this.isCooling()) return;
    const ready = this.waiters;
    this.waiters = [];
    ready.forEach((resolve) => resolve());
  }

  private emit(): void {
    this.listeners.forEach((listener) => listener());
  }
}

/** HTTP status behind a @uppy/tus error (or any XHR-shaped error), if any. */
export function statusOf(error: unknown): number | null {
  // tus-js-client wraps errors thrown by its response hook in DetailedError.
  for (let depth = 0; error && depth < 4; depth++) {
    const err = error as { originalResponse?: { getStatus: () => number }; status?: number; causingError?: unknown };
    if (err.originalResponse) return err.originalResponse.getStatus();
    if (typeof err.status === 'number') return err.status;
    error = err.causingError;
  }
  return null;
}

export const isRateLimited = (error: unknown): boolean => statusOf(error) === 429;
