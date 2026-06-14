import { createClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || '';
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY || '';

function getAuthStorageKey(url: string) {
  try {
    const hostname = new URL(url).hostname;
    const projectRef = hostname.split('.')[0];
    return `sb-${projectRef}-auth-token`;
  } catch {
    return 'sb-auth-token';
  }
}

function getSessionStorage() {
  if (typeof window === 'undefined') return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function removeLegacyLocalStorageSession(storageKey: string) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(storageKey);
    window.localStorage.removeItem(`${storageKey}-user`);
    window.localStorage.removeItem(`${storageKey}-code-verifier`);
  } catch {
    // Ignore storage access errors from restricted browser modes.
  }
}

export const supabaseAuthStorageKey = getAuthStorageKey(supabaseUrl);

export const browserSessionStorage = {
  getItem(key: string) {
    return getSessionStorage()?.getItem(key) ?? null;
  },
  setItem(key: string, value: string) {
    getSessionStorage()?.setItem(key, value);
  },
  removeItem(key: string) {
    getSessionStorage()?.removeItem(key);
  },
};

removeLegacyLocalStorageSession(supabaseAuthStorageKey);

export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    storageKey: supabaseAuthStorageKey,
    storage: browserSessionStorage,
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
});
