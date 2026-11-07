import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { isPortalHostname } from '../utils/hostname';
import XxlLogo from './XxlLogo';

/**
 * The header logo (SU11A-70). On the Super site (super.xxl.co.il, i.e. every
 * host that is not the portal) it is Super's own home link ("/", accessible
 * name "SUPER XXL — דף הבית"); on the portal (xxl.co.il / www) it keeps linking
 * to https://xxl.co.il. The portal's services are reached from Super's footer
 * ("כל שירותי XXL").
 */
const FOCUS = 'inline-block rounded-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 ' +
  'focus-visible:outline-emerald-700';

export default function HeaderLogo() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language?.startsWith('he') === false ? 'en' : 'he';
  const logo = <XxlLogo variant="header" lang={lang} className="h-10 sm:h-12" />;
  if (isPortalHostname()) {
    return <a href="https://xxl.co.il" className={FOCUS}>{logo}</a>;
  }
  return <Link to="/" aria-label={t('header.home_label')} className={FOCUS}>{logo}</Link>;
}
