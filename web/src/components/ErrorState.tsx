import { AlertCircle, RefreshCw } from 'lucide-react';

interface Props {
  onRetry?: () => void;
}

export default function ErrorState({ onRetry }: Props) {
  return (
    <div className="flex flex-col items-center py-20 text-center">
      <AlertCircle size={40} className="text-rose-400 mb-4" />
      <p className="text-gray-700 font-medium">Could not reach the backend</p>
      <p className="text-gray-400 text-sm mt-1">
        Make sure <code className="bg-gray-100 px-1 rounded text-xs">uvicorn api.main:app --reload</code> is running
      </p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-4 flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white
                     rounded-lg text-sm font-medium hover:bg-emerald-700 transition-colors"
        >
          <RefreshCw size={14} />
          Retry
        </button>
      )}
    </div>
  );
}
