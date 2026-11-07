import { useTranslation } from 'react-i18next';
import { appStoreBadgeSrc, IOS_APP_URL, PLAY_BADGE_SRC, PLAY_STORE_URL } from '../config/apps';

/**
 * App Store + Google Play badges (SU11A-53; App Store since SU11A-70), both
 * official artwork, unaltered (public/badges/SOURCE.txt).
 *
 * Apple's rules (App Store Marketing Guidelines): the App Store badge FIRST in
 * the lineup (first in DOM and reading order: the right-hand one in RTL), the
 * black badge next to other store badges, at least 40 px tall on screen, and
 * clear space of one quarter of its height on every side: p-[10px] around a
 * 40 px badge, inside the link, so the focus ring sits outside it.
 * Same visual height: the Play PNG carries its own clear space (the black badge
 * is 168 / 250 of the image), so at 60 px its visible badge is ~40 px, as tall
 * as the App Store badge; both links are 60 px boxes. Apple's 40 px minimum is
 * why there is a single size (the old 32 px "sm" would be below it).
 * Both are real links, keyboard-focusable with a visible focus ring.
 */
const LINK = 'inline-block rounded-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 ' +
  'focus-visible:outline-emerald-700';

export default function AppBadges({ className = '' }: { className?: string }) {
  const { t, i18n } = useTranslation();
  return (
    <div className={`flex items-center justify-center gap-2 flex-wrap ${className}`} dir="rtl">
      <a href={IOS_APP_URL} target="_blank" rel="noopener" className={`${LINK} p-[10px]`}>
        <img src={appStoreBadgeSrc(i18n.language || 'he')} alt={t('apps.ios_store_alt')}
          height={40} className="h-10 w-auto" />
      </a>
      <a href={PLAY_STORE_URL} target="_blank" rel="noopener" className={LINK}>
        {/* width / height attributes reserve the box before the image loads (no layout shift) */}
        <img src={PLAY_BADGE_SRC} alt={t('apps.play_alt')} width={646} height={250} className="h-[60px] w-auto" />
      </a>
    </div>
  );
}
