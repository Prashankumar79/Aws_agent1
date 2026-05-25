/**
 * ClearButton — resets the upload / selection state.
 */
interface ClearButtonProps {
  onClick?: () => void;
}

export const ClearButton = ({ onClick }: ClearButtonProps) => {
  return (
    <button
      onClick={onClick}
      style={{
        padding: '10px 18px',
        border: '0.5px solid rgba(0,0,0,0.2)',
        borderRadius: '8px',
        backgroundColor: 'white',
        color: '#374151',
        fontSize: '13px',
        fontWeight: 500,
        cursor: 'pointer',
        transition: 'background-color 0.15s ease',
        whiteSpace: 'nowrap',
        height: '100%',
      }}
      onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#F9FAFB'}
      onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'white'}
    >
      Clear
    </button>
  );
};
