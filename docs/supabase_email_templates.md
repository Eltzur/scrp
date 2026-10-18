# Supabase email templates — SUPER XXL (SU11A-41)

Where: Supabase dashboard → Authentication → Emails → Templates.

**When:** only AFTER both are live:
1. the web with `/reset-password` (SU11A-41) is deployed, and
2. the new Android build with the code-based reset screen is out.

Until then keep the current templates: older app builds and the old web still expect the reset **link**, and a code would mean nothing to them.

Before switching, check in Authentication → Providers → Email that the **Email OTP length is 6** — both the app and the web accept exactly 6 digits.

The app and the web call `resetPasswordForEmail(email)` without `redirectTo`, then `verifyOtp({ email, token, type: 'recovery' })` and `updateUser({ password })`. No redirect URL or allow-list change is needed.

## Reset Password

Subject:

```
קוד לאיפוס הסיסמה ב-SUPER XXL
```

Body (HTML):

```html
<div dir="rtl" style="font-family:Arial,sans-serif;font-size:16px;color:#111">
<h2>איפוס סיסמה</h2>
<p>הקוד שלכם לאיפוס הסיסמה ב-SUPER XXL:</p>
<p style="font-size:30px;font-weight:bold;letter-spacing:6px">{{ .Token }}</p>
<p>הקוד תקף לזמן קצר. אם לא ביקשתם לאפס את הסיסמה, אפשר להתעלם מהודעה זו.</p>
</div>
```

## Confirm Signup (keeps the link)

Subject:

```
אישור הרשמה ל-SUPER XXL
```

Body (HTML):

```html
<div dir="rtl" style="font-family:Arial,sans-serif;font-size:16px;color:#111">
<h2>ברוכים הבאים ל-SUPER XXL</h2>
<p>כדי לאשר את כתובת האימייל, לחצו על הקישור:</p>
<p><a href="{{ .ConfirmationURL }}">אישור כתובת האימייל</a></p>
<p>אם לא נרשמתם, אפשר להתעלם מהודעה זו.</p>
</div>
```

## After switching

- Request a reset on the web and in the app with a real mailbox; the email must show a 6-digit code and no link.
- An old reset link that is already in someone's inbox lands on `#error_code=otp_expired`; the web shows "הקישור אינו תקף יותר. בקשו קוד חדש." with a button to `/reset-password`.
