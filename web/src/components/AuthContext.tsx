import {
  createContext, useContext, useEffect, useState,
  type ReactNode,
} from 'react';
import type { User } from '@supabase/supabase-js';
import { supabase } from '../lib/supabase';

interface AuthContextType {
  user:         User | null;
  isLoading:    boolean;
  accessToken:  string | null;
  signUp:   (email: string, password: string) => Promise<{ error?: string }>;
  signIn:   (email: string, password: string) => Promise<{ error?: string }>;
  signOut:  () => Promise<void>;
  /** SU11A-31: re-enter the password; returns a FRESH access token for DELETE /account. */
  reauthenticate: (password: string) => Promise<ReauthResult>;
  /** SU11A-31: after the account was deleted on the server - drop the local session only. */
  finishAccountDeletion: () => Promise<void>;
}

export type ReauthResult =
  | { ok: true; accessToken: string }
  | { ok: false; reason: 'invalid_credentials' | 'network' | 'other' };

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user,        setUser]        = useState<User | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [isLoading,   setIsLoading]   = useState(true);

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setUser(session?.user ?? null);
      setAccessToken(session?.access_token ?? null);
      setIsLoading(false);
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (_event, session) => {
        setUser(session?.user ?? null);
        setAccessToken(session?.access_token ?? null);
      },
    );

    return () => subscription.unsubscribe();
  }, []);

  const signUp = async (email: string, password: string) => {
    const { error } = await supabase.auth.signUp({ email, password });
    return error ? { error: error.message } : {};
  };

  const signIn = async (email: string, password: string) => {
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    return error ? { error: error.message } : {};
  };

  const signOut = async () => {
    await supabase.auth.signOut();
  };

  const reauthenticate = async (password: string): Promise<ReauthResult> => {
    const email = user?.email;
    if (!email) return { ok: false, reason: 'other' };
    if (typeof navigator !== 'undefined' && navigator.onLine === false) {
      return { ok: false, reason: 'network' };
    }
    try {
      const { data, error } = await supabase.auth.signInWithPassword({ email, password });
      if (error || !data.session) {
        const m = (error?.message ?? '').toLowerCase();
        if (m.includes('invalid login credentials')) return { ok: false, reason: 'invalid_credentials' };
        if (error?.name === 'AuthRetryableFetchError' || m.includes('fetch') || m.includes('network')) {
          return { ok: false, reason: 'network' };
        }
        return { ok: false, reason: 'other' };
      }
      return { ok: true, accessToken: data.session.access_token };
    } catch {
      return { ok: false, reason: 'network' };
    }
  };

  const finishAccountDeletion = async () => {
    // scope 'local': a global sign-out asks Supabase to revoke every session of
    // a user that no longer exists. auth-js 2.105 still sends one logout call:
    // on 404/401/403 (deleted user) it removes the stored session, but on a
    // network error or 5xx it returns the error and KEEPS it - so in that case
    // the stored session is removed here, or a reload would bring it back.
    let failed = false;
    try {
      const { error } = await supabase.auth.signOut({ scope: 'local' });
      failed = !!error;
    } catch {
      failed = true;
    }
    if (failed) {
      try {
        for (const key of Object.keys(localStorage)) {
          if (/^sb-.+-auth-token(-code-verifier)?$/.test(key)) localStorage.removeItem(key);
        }
      } catch {
        // Storage blocked: nothing persisted to remove.
      }
    }
    setUser(null);
    setAccessToken(null);
  };

  return (
    <AuthContext.Provider
      value={{ user, isLoading, accessToken, signUp, signIn, signOut, reauthenticate, finishAccountDeletion }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be inside AuthProvider');
  return ctx;
}
