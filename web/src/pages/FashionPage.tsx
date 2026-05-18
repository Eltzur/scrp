import { Shirt } from 'lucide-react';
import ComingSoonPage from './ComingSoonPage';

export default function FashionPage() {
  return (
    <ComingSoonPage
      vertical="fashion"
      icon={<Shirt size={64} className="text-purple-600" />}
      headline="אופנה — בקרוב"
      subline="אנחנו בונים את ההשוואה הכי חכמה לבגדים ונעליים בישראל. הירשמו ותהיו הראשונים לדעת כשנעלה."
    />
  );
}
