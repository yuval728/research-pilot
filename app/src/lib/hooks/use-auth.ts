import { create } from 'zustand';
import { supabase } from '../supabase';

interface AuthUser {
  id: string;
  email?: string | null;
  user_metadata?: any;
}

interface AuthState {
  user: AuthUser | null;
  isLoading: boolean;
  signInWithProvider: (provider: 'github' | 'google') => Promise<void>;
  signInWithEmail: (email: string) => Promise<void>;
  signInWithPassword: (email: string, password: string) => Promise<void>;
  signUpWithPassword: (
    email: string,
    password: string,
  ) => Promise<{ sessionCreated: boolean }>;
  signOut: () => Promise<void>;
}

function getAuthRedirectTo() {
  if (typeof window === 'undefined') return undefined;
  return `${window.location.origin}/login`;
}

export const useAuth = create<AuthState>((set) => ({
  user: null,
  isLoading: true,
  signInWithProvider: async (provider: 'github' | 'google') => {
    set({ isLoading: true });
    try {
      await supabase.auth.signInWithOAuth({
        provider,
        options: { redirectTo: getAuthRedirectTo() },
      });
      // redirect handled by Supabase; session change will update state
    } catch (err) {
      console.error('Sign-in error', err);
    } finally {
      set({ isLoading: false });
    }
  },
  signInWithEmail: async (email: string) => {
    set({ isLoading: true });
    try {
      const { error } = await supabase.auth.signInWithOtp({
        email,
        options: { emailRedirectTo: getAuthRedirectTo() },
      });
      if (error) throw error;
    } catch (err) {
      console.error('Magic link error', err);
      throw err;
    } finally {
      set({ isLoading: false });
    }
  },
  signInWithPassword: async (email: string, password: string) => {
    set({ isLoading: true });
    try {
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      if (error) throw error;
    } catch (err) {
      console.error('Password sign-in error', err);
      throw err;
    } finally {
      set({ isLoading: false });
    }
  },
  signUpWithPassword: async (email: string, password: string) => {
    set({ isLoading: true });
    try {
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: { emailRedirectTo: getAuthRedirectTo() },
      });
      if (error) throw error;
      return { sessionCreated: !!data.session };
    } catch (err) {
      console.error('Sign-up error', err);
      throw err;
    } finally {
      set({ isLoading: false });
    }
  },
  signOut: async () => {
    set({ isLoading: true });
    try {
      await supabase.auth.signOut();
      set({ user: null, isLoading: false });
    } catch (err) {
      console.error('Sign-out error', err);
      set({ isLoading: false });
    }
  }
}));

// Subscribe to Supabase auth state changes and initialize current session
const initAuth = async () => {
  const { data: sessionData } = await supabase.auth.getSession();
  if (sessionData?.session?.user) {
    const u = sessionData.session.user;
    useAuth.setState({ user: { id: u.id, email: u.email, user_metadata: u.user_metadata }, isLoading: false });
  } else {
    useAuth.setState({ user: null, isLoading: false });
  }

  supabase.auth.onAuthStateChange((event, session) => {
    if (session?.user) {
      const u = session.user;
      useAuth.setState({ user: { id: u.id, email: u.email, user_metadata: u.user_metadata }, isLoading: false });
    } else {
      useAuth.setState({ user: null, isLoading: false });
    }
  });
};

// initialize once
initAuth().catch((e) => console.error('initAuth failed', e));
