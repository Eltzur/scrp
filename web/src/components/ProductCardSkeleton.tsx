export default function ProductCardSkeleton() {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 animate-pulse">
      <div className="h-3 bg-gray-200 rounded w-1/4 mb-3" />
      <div className="h-5 bg-gray-200 rounded w-3/4 mb-1" />
      <div className="h-3 bg-gray-200 rounded w-1/3 mb-4" />
      <div className="space-y-2">
        {[0, 1, 2].map(i => (
          <div key={i} className="flex justify-between">
            <div className="h-3 bg-gray-200 rounded w-2/5" />
            <div className="h-3 bg-gray-200 rounded w-1/5" />
          </div>
        ))}
      </div>
      <div className="h-3 bg-gray-100 rounded w-2/5 mt-4" />
    </div>
  );
}
