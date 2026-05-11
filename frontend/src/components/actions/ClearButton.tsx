interface ClearButtonProps {
  onClick?: () => void;
}

export const ClearButton = ({ onClick }: ClearButtonProps) => {
  return (
    <button
      onClick={onClick}
      className="px-6 py-2.5 border border-gray-300 rounded-lg text-gray-700 font-medium hover:bg-gray-50 transition-colors"
    >
      Clear
    </button>
  );
};
