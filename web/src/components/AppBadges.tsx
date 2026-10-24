import { useTranslation } from 'react-i18next';
import { APP_STORE_BADGE_SRC, IOS_APP_URL, PLAY_BADGE_SRC, PLAY_STORE_URL } from '../config/apps';

/**
 * Google Play badge + the iPhone label (SU11A-53).
 *
 * The Play image is Google's official Hebrew badge (public/badges/SOURCE.txt),
 * shown unaltered: its PNG already carries Google's clear space, so it is only
 * scaled by height (never below 40 px). The iPhone element is plain text, not
 * a link or a button, sized like the visible badge body (the black rectangle
 * is about 2/3 of the PNG's height). It becomes Apple's App Store badge only
 * when IOS_APP_URL is set (config/apps.ts).
 */
const SIZES = {
  md: { img: 'h-[60px]', pill: 'h-10 px-4 text-sm' },
  sm: { img: 'h-12', pill: 'h-8 px-3 text-xs' },
} as const;

export default function AppBadges({ size = 'md', className = '' }: { size?: keyof typeof SIZES; className?: string }) {
  const { t } = useTranslation();
  const s = SIZES[size];
  return (
    <div className={`flex items-center justify-center gap-3 flex-wrap ${className}`} dir="rtl">
      <a
        href={PLAY_STORE_URL}
        target="_blank"
        rel="noopener"
        className="inline-block rounded-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700"
      >
        {/* width / height attributes reserve the box before the image loads (no layout shift) */}
        <img src={PLAY_BADGE_SRC} alt={t('apps.play_alt')} width={646} height={250} className={`${s.img} w-auto`} />
      </a>
      {IOS_APP_URL ? (
        <a href={IOS_APP_URL} target="_blank" rel="noopener" className="inline-block">
          <img src={APP_STORE_BADGE_SRC} alt={t('apps.ios_store_alt')} className={`${s.img} w-auto`} />
        </a>
      ) : (
        <span
          className={`inline-flex items-center rounded-lg border border-gray-300 bg-gray-100 text-gray-700 font-medium whitespace-nowrap ${s.pill}`}
        >
          {t('apps.ios_soon')}
        </span>
      )}
    </div>
  );
}
