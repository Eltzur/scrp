import { useState } from 'react';
import { X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { IOS_APP_URL, PLAY_STORE_URL } from '../config/apps';
import { detectPlatform, type AppPlatform } from '../utils/platform';

/**
 * Slim, dismissible app banner at the top of the super pages (SU11A-53).
 *
 *   Android        "available on Android" + a link to Google Play
 *   iPhone / iPad  "coming soon for iPhone" (no link while IOS_APP_URL is null)
 *   desktop        nothing (the home section and the footer carry the badge)
 *
 * Never an interstitial: it sits in the page flow above the header. The
 * platform is read synchronously from the user agent, so the banner is in the
 * first render with a fixed min-height and nothing shifts after load. Closing
 * it is remembered in localStorage (wrapped: storage can be blocked); one
 * banner at most, shown once per visit until dismissed.
 */
const DISMISS_KEY = 'xxl_app_banner_dismissed';

function isDismissed(): boolean {
  try { return localStorage.getItem(DISMISS_KEY) === '1'; }
  catch { return false; }
}

export default function AppBanner() {
  const { t } = useTranslation();
  const [platform] = useState<AppPlatform>(() =>
    typeof navigator === 'undefined' ? 'desktop' : detectPlatform(navigator.userAgent, navigator.maxTouchPoints ?? 0));
  const [open, setOpen] = useState<boolean>(() => !isDismissed());

  if (platform === 'desktop' || !open) return null;
  // Once the iOS app is live the iPhone banner becomes a store link too.
  const iosLive = platform === 'ios' && !!IOS_APP_URL;

  const dismiss = () => {
    setOpen(false);
    try { localStorage.setItem(DISMISS_KEY, '1'); } catch { /* blocked storage: closed for this page view only */ }
  };

  return (
    <div
      role="region"
      aria-label={t('apps.banner_label')}
      dir="rtl"
      className="bg-emerald-50 border-b border-emerald-200 text-emerald-950"
    >
      <div className="max-w-6xl mx-auto px-4 min-h-[44px] py-2 flex items-center gap-3 text-sm">
        <p className="flex-1 min-w-0">
          {platform === 'android' || iosLive ? (
            <>
              {t(platform === 'android' ? 'apps.banner_android' : 'apps.banner_ios_live')}{' '}
              <a
                href={platform === 'android' ? PLAY_STORE_URL : (IOS_APP_URL as string)}
                target="_blank"
                rel="noopener"
                className="font-semibold text-emerald-800 underline underline-offset-2 rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-700"
              >
                {t(platform === 'android' ? 'apps.banner_android_link' : 'apps.banner_ios_link')}
              </a>
            </>
          ) : (
            <>
              <span className="font-medium">{t('apps.banner_ios')}</span>{' '}
              <span className="text-emerald-900">{t('apps.banner_ios_sub')}</span>
            </>
          )}
        </p>
        <button
          type="button"
          onClick={dismiss}
          aria-label={t('apps.banner_close')}
          className="shrink-0 p-2 -m-1 rounded-md text-emerald-900 hover:bg-emerald-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-700"
        >
          <X size={18} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
