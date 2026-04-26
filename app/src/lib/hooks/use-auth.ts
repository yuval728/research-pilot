import { create } from 'zustand';

interface AuthState {
  user: { email: string; name: string } | null;
  isLoading: boolean;
  signIn: () => Promise<void>;
  signOut: () => Promise<void>;
}

export const useAuth = create<AuthState>((set) => ({
  user: { email: 'yuvalmehta.728@gmail.com', name: 'Yuval Mehta' }, // Mocked logged in user
  isLoading: false,
  signIn: async () => {
    set({ isLoading: true });
    // Simulate sign in
    setTimeout(() => set({ user: { email: 'yuvalmehta.728@gmail.com', name: 'Yuval Mehta' }, isLoading: false }), 1000);
  },
  signOut: async () => {
    set({ user: null });
  }
}));
