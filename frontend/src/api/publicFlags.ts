import { api } from './api';

export interface PublicFlags {
  allow_registration: boolean;
  enable_verification_email: boolean;
}

let pending: Promise<PublicFlags> | null = null;
let cached: PublicFlags | null = null;

export function fetchPublicFlags(): Promise<PublicFlags> {
  if (cached) return Promise.resolve(cached);
  if (!pending) {
    pending = api
      .get('/api/accounts/settings/public')
      .then(r => {
        cached = r.data;
        return r.data;
      })
      .catch(e => {
        pending = null;
        throw e;
      });
  }
  return pending;
}

// Fire as soon as this module loads so the login page gets the
// state before its first interactive paint.
fetchPublicFlags().catch(() => { /* retried when components read it */ });
