import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { Loader2, ShieldCheck } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../components/AuthContext';
import { supabase } from '../lib/supabase';
import { errorCode, getMe } from './api';
import { Button, ErrorBox, Loading } from './ui';

/**
 * Admin sign-in (SU11A-54): email + password, then TOTP. The order of checks
 * comes from GET /admin/me, which tests the allowlist BEFORE the second factor:
 *   200            -> the console
 *   admin_required -> "no access" (a non-admin is never offered TOTP setup)
 *   mfa_required   -> enrolment (no verified TOTP factor yet) or the 6-digit check
 * After a successful verify Supabase upgrades the session to aal2; the new
 * access token re-runs the check. The session is per origin: signing in here
 * does not sign anyone in on super.xxl.co.il, and the other way round.
 */
type Phase =
  | { kind: 'loading' }
  | { kind: 'signed_out' }
  | { kind: 'no_access' }
  | { kind: 'enroll' }
  | { kind: 'challenge'; factorId: string }
  | { kind: 'error'; error: unknown }
  | { kind: 'ready' };

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <main className="min-h-screen bg-gray-50 flex items-center justify-center px-4 py-8" dir="rtl">
      <div className="w-full max-w-sm bg-white rounded-2xl shadow-sm border border-gray-200 p-6 sm:p-8">
        <p className="flex items-center justify-center gap-2 text-sm font-semibold text-emerald-800 mb-2">
          <ShieldCheck size={18} aria-hidden="true" /> XXL Admin
        </p>
        <h1 className="text-xl font-bold text-gray-900 mb-5 text-center">{title}</h1>
        {children}
      </div>
    </main>
  );
}

const inputCls = `w-full min-h-[48px] px-3 border border-gray-300 rounded-lg text-base
  focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent`;

function SignInForm() {
  const { t } = useTranslation();
  const { signIn } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    const r = await signIn(email.trim(), password);
    setBusy(false);
    if (r.error) setError(r.error);
  };

  return (
    <Panel title={t('admin.auth.sign_in_title')}>
      <form onSubmit={submit} className="space-y-4">
        <div>
          <label htmlFor="admin-email" className="block text-sm font-medium text-gray-700 mb-1">{t('admin.auth.email')}</label>
          <input id="admin-email" type="email" required autoComplete="username" dir="ltr"
            value={email} onChange={e => setEmail(e.target.value)} className={inputCls} />
        </div>
        <div>
          <label htmlFor="admin-password" className="block text-sm font-medium text-gray-700 mb-1">{t('admin.auth.password')}</label>
          <input id="admin-password" type="password" required autoComplete="current-password" dir="ltr"
            value={password} onChange={e => setPassword(e.target.value)} className={inputCls} />
        </div>
        {error && <p role="alert" className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2">{error}</p>}
        <Button type="submit" tone="primary" className="w-full" disabled={busy} aria-busy={busy}>
          {busy && <Loader2 size={16} className="animate-spin" aria-hidden="true" />}
          {busy ? t('admin.auth.signing_in') : t('admin.auth.sign_in')}
        </Button>
      </form>
    </Panel>
  );
}

function CodeForm({ factorId, onDone }: { factorId: string; onDone: () => void }) {
  const { t } = useTranslation();
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy || !/^\d{6}$/.test(code)) return;
    setBusy(true);
    setError(null);
    const { error: err } = await supabase.auth.mfa.challengeAndVerify({ factorId, code });
    setBusy(false);
    if (err) {
      setError(t('admin.auth.code_invalid'));
      setCode('');
      return;
    }
    onDone();
  };

  return (
    <form onSubmit={submit} className="space-y-4">
      <div>
        <label htmlFor="admin-code" className="block text-sm font-medium text-gray-700 mb-1">{t('admin.auth.code')}</label>
        <input id="admin-code" inputMode="numeric" autoComplete="one-time-code" pattern="\d{6}" maxLength={6}
          required dir="ltr" value={code} autoFocus
          onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
          className={`${inputCls} text-center tracking-[0.4em] font-mono`} />
      </div>
      {error && <p role="alert" className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2">{error}</p>}
      <Button type="submit" tone="primary" className="w-full" disabled={busy || code.length !== 6} aria-busy={busy}>
        {busy && <Loader2 size={16} className="animate-spin" aria-hidden="true" />}
        {busy ? t('admin.auth.verifying') : t('admin.auth.verify')}
      </Button>
    </form>
  );
}

function Enroll({ onDone }: { onDone: () => void }) {
  const { t } = useTranslation();
  const [state, setState] = useState<{ id: string; qr: string; secret: string } | 'failed' | null>(null);
  const started = useRef(false);   // StrictMode runs effects twice; enrol once

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    (async () => {
      // A setup abandoned earlier leaves an unverified factor behind; it would
      // block a new one with the same name. Verified factors are never touched.
      const { data: list } = await supabase.auth.mfa.listFactors();
      for (const f of list?.all ?? []) {
        if (f.factor_type === 'totp' && f.status === 'unverified') {
          await supabase.auth.mfa.unenroll({ factorId: f.id });
        }
      }
      const { data, error } = await supabase.auth.mfa.enroll({
        factorType: 'totp', friendlyName: 'XXL Admin', issuer: 'XXL Admin',
      });
      if (error || !data) { setState('failed'); return; }
      setState({ id: data.id, qr: data.totp.qr_code, secret: data.totp.secret });
    })().catch(() => setState('failed'));
  }, []);

  return (
    <Panel title={t('admin.auth.enroll_title')}>
      <p className="text-sm text-gray-700 mb-4">{t('admin.auth.enroll_intro')}</p>
      {state === null && <Loading />}
      {state === 'failed' && <p role="alert" className="text-sm text-rose-700">{t('admin.auth.enroll_failed')}</p>}
      {state && state !== 'failed' && (
        <>
          <img src={state.qr} alt={t('admin.auth.enroll_qr_alt')} width={200} height={200}
            className="mx-auto mb-3 bg-white" />
          <p className="text-xs text-gray-600 mb-1">{t('admin.auth.enroll_secret')}</p>
          <code dir="ltr" className="block mb-5 break-all select-all rounded-lg bg-gray-100 px-3 py-2 text-sm font-mono text-gray-900">
            {state.secret}
          </code>
          <CodeForm factorId={state.id} onDone={onDone} />
        </>
      )}
    </Panel>
  );
}

// eslint-disable-next-line react-refresh/only-export-components -- the gate hook lives next to its screens
export function useAdminGate() {
  const { user, accessToken, isLoading } = useAuth();
  const [tick, setTick] = useState(0);
  const recheck = useCallback(() => setTick(n => n + 1), []);
  // The result of the last check, tagged with what it checked: a new token
  // (sign-in, TOTP verify, refresh) or a recheck makes it stale -> 'loading'.
  const key = `${accessToken ?? ''}#${tick}`;
  const [result, setResult] = useState<{ key: string; phase: Phase } | null>(null);

  useEffect(() => {
    if (isLoading || !user || !accessToken) return;
    let live = true;
    const done = (phase: Phase) => { if (live) setResult({ key, phase }); };
    getMe()
      .then(() => done({ kind: 'ready' }))
      .catch(async (err) => {
        const code = errorCode(err);
        if (code === 'admin_required') return done({ kind: 'no_access' });
        if (code !== 'mfa_required') return done({ kind: 'error', error: err });
        const { data } = await supabase.auth.mfa.listFactors();
        const verified = data?.totp?.[0];
        done(verified ? { kind: 'challenge', factorId: verified.id } : { kind: 'enroll' });
      })
      .catch(err => done({ kind: 'error', error: err }));
    return () => { live = false; };
  }, [user, accessToken, isLoading, key]);

  let phase: Phase;
  if (isLoading) phase = { kind: 'loading' };
  else if (!user || !accessToken) phase = { kind: 'signed_out' };
  else phase = result?.key === key ? result.phase : { kind: 'loading' };
  return { phase, recheck };
}

export function GateScreen({ phase, recheck }: { phase: Phase; recheck: () => void }) {
  const { t } = useTranslation();
  const { signOut } = useAuth();
  switch (phase.kind) {
    case 'loading':
      return <Panel title={t('admin.auth.checking')}><Loading /></Panel>;
    case 'signed_out':
      return <SignInForm />;
    case 'no_access':
      return (
        <Panel title={t('admin.auth.no_access_title')}>
          <p className="text-sm text-gray-700 mb-5 text-center">{t('admin.auth.no_access_body')}</p>
          <Button className="w-full" onClick={() => void signOut()}>{t('admin.auth.sign_out')}</Button>
        </Panel>
      );
    case 'enroll':
      return <Enroll onDone={recheck} />;
    case 'challenge':
      return (
        <Panel title={t('admin.auth.challenge_title')}>
          <p className="text-sm text-gray-700 mb-4">{t('admin.auth.challenge_intro')}</p>
          <CodeForm factorId={phase.factorId} onDone={recheck} />
          <Button className="w-full mt-3" onClick={() => void signOut()}>{t('admin.auth.sign_out')}</Button>
        </Panel>
      );
    case 'error':
      return <Panel title="XXL Admin"><ErrorBox error={phase.error} onRetry={recheck} /></Panel>;
    default:
      return null;
  }
}
