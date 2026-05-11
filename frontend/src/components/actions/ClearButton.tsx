/**
 * ClearButton — resets the upload / selection state.
 *
 * PURPOSE:
 *   Gives the user a way to clear the current file, provider selection,
 *   and any previously extracted results before starting a new analysis.
 *
 * NOTE:
 *   The `onClick` prop is optional. In UploadPage.tsx it is passed
 *   without a handler, so the component currently does nothing when
 *   clicked unless wired to a store reset action externally.
 */

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
