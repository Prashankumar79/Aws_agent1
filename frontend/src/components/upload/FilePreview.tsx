/**
 * FilePreview — displays the uploaded file name, size, and status badge.
 *
 * PURPOSE:
 *   After a user drops or selects a file in UploadDropzone, this component
 *   shows confirmation that the file was accepted and is ready for analysis.
 *
 * WHY IT EXISTS:
 *   Separated from UploadDropzone so the dropzone stays focused on
 *   file-input handling, while FilePreview handles the "already-uploaded"
 *   state rendering.
 *
 * CONNECTIONS:
 *   • UploadPage.tsx     → conditionally renders FilePreview after upload
 *   • UploadDropzone.tsx → sets the uploadedFile state that feeds this
 */

import { UploadedFile } from '../../types/schema';

interface FilePreviewProps {
  file: UploadedFile;
}

export const FilePreview = ({ file }: FilePreviewProps) => {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
          <svg className="w-6 h-6 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
            />
          </svg>
        </div>
        <div>
          <p className="font-medium text-gray-900">{file.name}</p>
          <p className="text-sm text-gray-500">{file.size} uploaded</p>
        </div>
      </div>
      <span className="px-3 py-1 bg-green-100 text-green-700 rounded-full text-sm font-medium">
        {file.status}
      </span>
    </div>
  );
};
