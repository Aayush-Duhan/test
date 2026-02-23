import { useState, useRef } from 'react';
import { Plus, Paperclip, FileCode, FolderOpen } from 'lucide-react';

export interface UploadedFile {
  name: string;
  path: string;
  content: string;
}

interface AttachMenuProps {
  onFilesSelected?: (files: UploadedFile[]) => void;
  chatId?: string;
  disabled?: boolean;
}

export function AttachMenu({ onFilesSelected, chatId, disabled }: AttachMenuProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  const handleUpload = async (selectedFiles: FileList | null) => {
    if (!selectedFiles || selectedFiles.length === 0 || !chatId) {
      return;
    }

    setIsUploading(true);

    try {
      const formData = new FormData();

      for (let i = 0; i < selectedFiles.length; i++) {
        formData.append('files', selectedFiles[i]);
      }

      const response = await fetch(`/api/upload/${encodeURIComponent(chatId)}`, {
        method: 'POST',
        body: formData,
        credentials: 'include',
      });

      if (!response.ok) {
        throw new Error(`Upload failed: ${response.statusText}`);
      }

      const data: { files: UploadedFile[] } = await response.json();
      onFilesSelected?.(data.files as UploadedFile[]);
    } catch (error) {
      console.error('File upload failed:', error);
    } finally {
      setIsUploading(false);
    }
  };

  const handleFileClick = () => {
    setIsOpen(false);
    fileInputRef.current?.click();
  };

  const handleFolderClick = () => {
    setIsOpen(false);
    folderInputRef.current?.click();
  };

  const menuItems = [
    { icon: <FolderOpen className="size-4" />, label: 'Upload Folder', onClick: handleFolderClick },
    { icon: <FileCode className="size-4" />, label: 'Import Files', onClick: handleFileClick },
  ];

  return (
    <div className="relative">
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".sql,.ddl,.prc,.pkb,.pks,.trg,.vw,.fnc,.pls,.plb"
        className="hidden"
        onChange={(e) => void handleUpload(e.target.files)}
      />
      <input
        ref={folderInputRef}
        type="file"
        multiple
        // @ts-expect-error - webkitdirectory is not in the type defs
        webkitdirectory=""
        className="hidden"
        onChange={(e) => void handleUpload(e.target.files)}
      />

      <button
        onClick={() => setIsOpen(!isOpen)}
        disabled={disabled || isUploading}
        className="flex items-center justify-center size-8 rounded-full bg-white/[0.08] hover:bg-white/[0.12] text-[#8a8a8f] hover:text-white transition-all duration-200 active:scale-95 disabled:opacity-40"
      >
        {isUploading ? (
          <div className="size-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
        ) : (
          <Plus className={`size-4 transition-transform duration-200 ${isOpen ? 'rotate-45' : ''}`} />
        )}
      </button>

      {isOpen && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} />
          <div className="absolute bottom-full left-0 mb-2 z-50 bg-[#1a1a1e]/95 backdrop-blur-xl border border-white/10 rounded-xl shadow-2xl shadow-black/50 overflow-hidden animate-in fade-in slide-in-from-bottom-2 duration-200">
            <div className="p-1.5 min-w-[180px]">
              {menuItems.map((item, i) => (
                <button
                  key={i}
                  onClick={item.onClick}
                  className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-[#a0a0a5] hover:bg-white/5 hover:text-white transition-all duration-150"
                >
                  {item.icon}
                  <span className="text-sm">{item.label}</span>
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
