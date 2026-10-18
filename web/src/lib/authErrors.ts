import type { AuthError } from '@supabase/supabase-js';

/**
 * SU11A-41: Hebrew messages for Supabase auth errors, so raw English never
 * reaches the UI. Same approach as toHebrewError in the mobile app
 * (xxl-super-mobile/src/lib/auth-context.tsx): match on the error code first,
 * then on the distinguishing substring of the message, and fall back to a
 * generic message. No message may reveal whether an account exists.
 */
export const AUTH_MSG = {
  invalidCredentials: 'האימייל או הסיסמה שגויים.',
  emailNotConfirmed:  'יש לאשר את כתובת האימייל. בדקו את תיבת הדואר שלכם.',
  badCode:            'הקוד שגוי או שפג תוקפו. אפשר לבקש קוד חדש.',
  rateLimited:        'בוצעו יותר מדי ניסיונות. נסו שוב בעוד דקה.',
  emailTaken:         'כתובת האימייל כבר רשומה במערכת.',
  weakPassword:       'הסיסמה חייבת להכיל לפחות 6 תווים.',
  invalidEmail:       'כתובת האימייל אינה תקינה.',
  samePassword:       'הסיסמה החדשה חייבת להיות שונה מהקודמת.',
  passwordMismatch:   'הסיסמאות אינן תואמות.',
  network:            'לא ניתן לגשת לשרת',
  generic:            'משהו השתבש. נסו שוב.',
} as const;

function isRateLimited(error: AuthError): boolean {
  const m = error.message.toLowerCase();
  return (
    error.status === 429 ||
    (error.code ?? '').startsWith('over_') || // over_email_send_rate_limit, over_request_rate_limit
    m.includes('rate limit') ||
    m.includes('only request this')
  );
}

function isNetwork(error: AuthError): boolean {
  const m = error.message.toLowerCase();
  return error.name === 'AuthRetryableFetchError' || m.includes('network') || m.includes('fetch');
}

/** Sign-in, sign-up, reset request and password update. */
export function toHebrewAuthError(error: AuthError): string {
  const m = error.message.toLowerCase();
  const code = error.code ?? '';

  if (code === 'invalid_credentials' || m.includes('invalid login credentials')) {
    return AUTH_MSG.invalidCredentials;
  }
  if (code === 'email_not_confirmed' || m.includes('email not confirmed')) {
    return AUTH_MSG.emailNotConfirmed;
  }
  if (isRateLimited(error)) return AUTH_MSG.rateLimited;
  if (code === 'same_password' || m.includes('should be different from the old password')) {
    return AUTH_MSG.samePassword;
  }
  if (m.includes('already registered') || m.includes('already been registered')) {
    return AUTH_MSG.emailTaken;
  }
  if (code === 'weak_password' || m.includes('password should be at least') || m.includes('weak password')) {
    return AUTH_MSG.weakPassword;
  }
  if (m.includes('unable to validate email') || m.includes('invalid email')) {
    return AUTH_MSG.invalidEmail;
  }
  if (isNetwork(error)) return AUTH_MSG.network;
  return AUTH_MSG.generic;
}

/**
 * verifyOtp fails the same way for a wrong code, an expired one and an address
 * with no account, so all of those get one message.
 */
export function toHebrewCodeError(error: AuthError): string {
  if (isRateLimited(error)) return AUTH_MSG.rateLimited;
  if (isNetwork(error)) return AUTH_MSG.network;
  return AUTH_MSG.badCode;
}
