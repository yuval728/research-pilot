import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock supabase client used by api/http
vi.mock('../src/lib/supabase', () => {
  return {
    supabase: {
      auth: {
        getSession: async () => ({ data: { session: null } }),
        onAuthStateChange: () => ({ data: null }),
      },
    },
  };
});

import { apiFetch } from '../src/lib/api/http';

globalThis.fetch = vi.fn();

describe('apiFetch', () => {
  beforeEach(() => {
    (globalThis.fetch as any).mockReset();
  });

  it('returns json body for 200 responses', async () => {
    (globalThis.fetch as any).mockResolvedValueOnce({
      ok: true,
      headers: { get: (k: string) => (k === 'content-type' ? 'application/json' : null) },
      json: async () => ({ hello: 'world' }),
    });

    const res = await apiFetch('/test');
    expect(res).toEqual({ hello: 'world' });
  });
});
