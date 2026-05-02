import { API_BASE_URL } from '../config';
import { supabase } from '../supabase';

type FetchOptions = Omit<RequestInit, 'headers'> & {
  headers?: HeadersInit;
  json?: unknown;
};

export async function getAccessToken(): Promise<string | null> {
  try {
    const { data } = await supabase.auth.getSession();
    const token = data?.session?.access_token ?? null;
    return token;
  } catch (e) {
    console.warn('Failed to get access token', e);
    return null;
  }
}

export async function apiFetch(path: string, options: FetchOptions = {}) {
  // Normalize path to backend routing. The pipeline mounts routers under /api/v1,
  // so transform caller paths like `/v1/...` to `/api/v1/...` to avoid widespread edits.
  const buildUrl = (p: string) => {
    if (p.startsWith('http')) return p;
    // Already has /api prefix
    if (p.startsWith('/api/')) return `${API_BASE_URL}${p}`;
    if (p.startsWith('/v1/')) return `${API_BASE_URL}${p.replace(/^\/v1/, '/api/v1')}`;
    if (p.startsWith('v1/')) return `${API_BASE_URL}/api/${p}`;
    // Default to api v1
    return `${API_BASE_URL}/api/v1${p.startsWith('/') ? '' : '/'}${p}`;
  };

  const url = buildUrl(path);
  const headers = new Headers({
    'Content-Type': 'application/json',
  });

  if (options.headers) {
    new Headers(options.headers).forEach((value, key) => {
      headers.set(key, value);
    });
  }

  const token = await getAccessToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);

  const fetchOptions: RequestInit = {
    method: options.method || 'GET',
    headers,
    body: options.json ? JSON.stringify(options.json) : undefined,
  };

  const res = await fetch(url, fetchOptions);
  const contentType = res.headers.get('content-type') || '';
  let body: any = null;
  if (contentType.includes('application/json')) {
    body = await res.json();
  } else {
    body = await res.text();
  }

  if (!res.ok) {
    // Attempt a single retry for 401 using refreshed session
    if (res.status === 401) {
      try {
        // Try to refresh session by re-reading Supabase session
        await supabase.auth.getSession();
        const token2 = await getAccessToken();
        if (token2) {
          headers.set('Authorization', `Bearer ${token2}`);
          const retryRes = await fetch(url, { ...fetchOptions, headers });
          const ct2 = retryRes.headers.get('content-type') || '';
          const body2 = ct2.includes('application/json') ? await retryRes.json() : await retryRes.text();
          if (retryRes.ok) return body2;
          const err2: any = new Error('API error after retry');
          err2.status = retryRes.status;
          err2.body = body2;
          throw err2;
        }
      } catch (refreshErr) {
        // proceed to throw original error below
        console.warn('Session refresh attempt failed', refreshErr);
      }
    }

    const err: any = new Error('API error');
    err.status = res.status;
    err.body = body;
    throw err;
  }

  return body;
}
