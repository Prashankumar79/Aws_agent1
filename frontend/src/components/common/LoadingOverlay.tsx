interface LoadingOverlayProps {
  message?: string;
}

export const LoadingOverlay = ({ message }: LoadingOverlayProps) => {
  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-white/80 backdrop-blur-sm animate-fade-in">
      <div className="relative">
        <div className="w-16 h-16 rounded-full border-4 border-orange-100 border-t-orange-500 animate-spin" />
      </div>
      <p className="mt-6 text-lg font-medium text-gray-700">
        {message || 'Analysing your architecture...'}
      </p>
      <p className="mt-2 text-sm text-gray-400">
        This may take a few minutes for vision analysis and design document generation
      </p>

      {/* Pipeline steps */}
      <div className="mt-8 flex items-center gap-3">
        {['Vision', 'Graph', 'RAG', 'Generate'].map((step, i) => (
          <div key={step} className="flex items-center gap-2">
            <span className="px-3 py-1 rounded-full text-xs font-medium bg-orange-50 text-orange-700">
              {step}
            </span>
            {i < 3 && (
              <div className="w-4 h-px bg-gray-300" />
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
