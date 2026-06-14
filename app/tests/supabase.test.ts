import { beforeEach, describe, expect, it, vi } from 'vitest';

const createClient = vi.fn(() => ({ auth: {} }));

vi.mock('@supabase/supabase-js', () => ({
  createClient,
}));

function makeStorage() {
  const values = new Map<string, string>();
  return {
    getItem: vi.fn((key: string) => values.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => {
      values.set(key, value);
    }),
    removeItem: vi.fn((key: string) => {
      values.delete(key);
    }),
  };
}

describe('supabase client auth storage', () => {
  beforeEach(() => {
    vi.resetModules();
    createClient.mockClear();
  });

  it('uses sessionStorage instead of default localStorage persistence', async () => {
    const sessionStorage = makeStorage();
    const localStorage = makeStorage();
    vi.stubGlobal('window', { sessionStorage, localStorage });

    const { browserSessionStorage, supabaseAuthStorageKey } = await import(
      '../src/lib/supabase'
    );

    browserSessionStorage.setItem('auth-key', 'session-value');
    expect(sessionStorage.setItem).toHaveBeenCalledWith(
      'auth-key',
      'session-value',
    );
    expect(localStorage.setItem).not.toHaveBeenCalled();

    const options = createClient.mock.calls[0][2] as any;
    expect(options.auth).toMatchObject({
      storageKey: supabaseAuthStorageKey,
      storage: browserSessionStorage,
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
    });
  });

  it('removes old localStorage auth entries from the previous default client', async () => {
    const sessionStorage = makeStorage();
    const localStorage = makeStorage();
    vi.stubGlobal('window', { sessionStorage, localStorage });

    const { supabaseAuthStorageKey } = await import('../src/lib/supabase');

    expect(localStorage.removeItem).toHaveBeenCalledWith(supabaseAuthStorageKey);
    expect(localStorage.removeItem).toHaveBeenCalledWith(
      `${supabaseAuthStorageKey}-user`,
    );
    expect(localStorage.removeItem).toHaveBeenCalledWith(
      `${supabaseAuthStorageKey}-code-verifier`,
    );
  });
});
