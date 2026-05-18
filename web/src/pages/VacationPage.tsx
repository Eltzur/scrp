import { Sun } from 'lucide-react';
import ComingSoonPage from './ComingSoonPage';

export default function VacationPage() {
  return (
    <ComingSoonPage
      vertical="vacation"
      icon={<Sun size={64} className="text-orange-600" />}
      headline="חופשות — בקרוב"
      subline="אנחנו בונים את ההשוואה הכי חכמה לטיסות ומלונות בישראל. הירשמו ותהיו הראשונים לדעת כשנעלה."
    />
  );
}
