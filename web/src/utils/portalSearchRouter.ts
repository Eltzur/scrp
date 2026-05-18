export type VerticalIntent = 'groceries' | 'vacation' | 'fashion' | 'unknown';

export interface RouteResult {
  intent: VerticalIntent;
  destination: string; // URL to navigate to
  query: string;       // the original query
}

/**
 * Mock intent classifier. Replace this function body with a Claude Haiku API call later.
 * Keep the function signature identical so the swap is one function.
 */
export function classifyAndRoute(query: string): RouteResult {
  const q = query.trim().toLowerCase();
  if (!q) return { intent: 'unknown', destination: '', query };

  // Hebrew + English keyword rules for the 3 verticals
  const groceriesKeywords = ['חלב', 'לחם', 'גבינה', 'ביצים', 'יוגורט', 'תנובה', 'שטראוס', 'אסם', 'עוף', 'בשר', 'ירקות', 'פירות', 'מצרכים', 'סופר', 'קוטג', 'במבה', 'ביסלי', 'milk', 'bread', 'cheese', 'eggs'];
  const vacationKeywords  = ['טיסה', 'טיסות', 'מלון', 'מלונות', 'חופשה', 'חופשות', 'חופש', 'נופש', 'נסיעה', 'נסיעות', 'בית מלון', 'אילת', 'יוון', 'פראג', 'איסטנבול', 'דובאי', 'flight', 'hotel', 'vacation'];
  const fashionKeywords   = ['נעלי', 'נעליים', 'חולצה', 'חולצות', 'מכנסי', 'מכנסיים', 'שמלה', 'שמלות', 'בגד', 'בגדים', 'אופנה', 'ניו באלאנס', 'נייקי', 'אדידס', 'זארה', 'אייץ אנד אם', 'shoes', 'shirt', 'dress', 'clothes', 'nike', 'adidas', 'zara'];

  const matches = (keywords: string[]) => keywords.some(kw => q.includes(kw));

  if (matches(groceriesKeywords)) {
    return { intent: 'groceries', destination: `https://super.xxl.co.il/?q=${encodeURIComponent(query)}`, query };
  }
  if (matches(vacationKeywords)) {
    return { intent: 'vacation', destination: '/vacation', query };
  }
  if (matches(fashionKeywords)) {
    return { intent: 'fashion', destination: '/fashion', query };
  }
  return { intent: 'unknown', destination: '', query };
}
