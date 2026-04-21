import { Search } from 'lucide-react';

const SUGGESTIONS = ['במבה', 'חלב תנובה', 'cottage', 'ביצים', 'לחם'];

interface Props {
  query?: string;
}

export default function EmptyState({ query }: Props) {
  const hasQuery = query && query.trim().length >= 2;

  return (
    <div className="flex flex-col items-center py-20 text-center">
      <Search size={40} className="text-gray-300 mb-4" />
      {hasQuery ? (
        <>
          <p className="text-gray-600 font-medium">No products found for "{query}"</p>
          <p className="text-gray-400 text-sm mt-1">Try a shorter term or check the spelling</p>
        </>
      ) : (
        <>
          <p className="text-gray-600 font-medium">Start typing to compare prices</p>
          <p className="text-gray-400 text-sm mt-1">Try:</p>
          <div className="flex flex-wrap gap-2 justify-center mt-3">
            {SUGGESTIONS.map(s => (
              <span
                key={s}
                className="px-3 py-1 bg-gray-100 rounded-full text-sm text-gray-600 font-medium"
              >
                {s}
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
