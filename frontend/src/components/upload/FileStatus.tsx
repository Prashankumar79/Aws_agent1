interface FileStatusProps {
  status: string;
}

export const FileStatus = ({ status }: FileStatusProps) => {
  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'ready':
        return 'bg-green-100 text-green-700';
      case 'uploading':
        return 'bg-blue-100 text-blue-700';
      case 'error':
        return 'bg-red-100 text-red-700';
      default:
        return 'bg-gray-100 text-gray-700';
    }
  };

  return (
    <span className={`px-3 py-1 rounded-full text-sm font-medium ${getStatusColor(status)}`}>
      {status}
    </span>
  );
};
