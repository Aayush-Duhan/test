import { useState } from 'react';
import { Plus, Paperclip, FileCode } from 'lucide-react';

interface AttachMenuProps {
  onUploadFile?: () => void;
  onAddImage?: () => void;
  onImportCode?: () => void;
}

export function AttachMenu({ onUploadFile, onAddImage, onImportCode }: AttachMenuProps) {
  const [isOpen, setIsOpen] = useState(false);

  const menuItems = [
    { icon: <Paperclip className="size-4" />, label: 'Upload Folder', onClick: onUploadFile },
    { icon: <FileCode className="size-4" />, label: 'Import file', onClick: onImportCode }
  ];

  const handleItemClick = (onClick?: () => void) => {
    setIsOpen(false);
    onClick?.();
  };

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center justify-center size-8 rounded-full bg-white/[0.08] hover:bg-white/[0.12] text-[#8a8a8f] hover:text-white transition-all duration-200 active:scale-95"
      >
        <Plus className={`size-4 transition-transform duration-200 ${isOpen ? 'rotate-45' : ''}`} />
      </button>

      {isOpen && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} />
          <div className="absolute bottom-full left-0 mb-2 z-50 bg-[#1a1a1e]/95 backdrop-blur-xl border border-white/10 rounded-xl shadow-2xl shadow-black/50 overflow-hidden animate-in fade-in slide-in-from-bottom-2 duration-200">
            <div className="p-1.5 min-w-[180px]">
              {menuItems.map((item, i) => (
                <button
                  key={i}
                  onClick={() => handleItemClick(item.onClick)}
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
