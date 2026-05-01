import { createClient } from '@supabase/supabase-js';

const url     = import.meta.env.VITE_SUPABASE_URL as string;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string;

if (!url || !anonKey || anonKey === 'PASTE_ANON_KEY_HERE') {
  console.warn('Supabase env vars missing or placeholder — auth will not work');
}

export const supabase = createClient(url ?? '', anonKey ?? '');
