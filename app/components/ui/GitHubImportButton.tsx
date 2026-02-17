import { Github } from 'lucide-react';

interface GitHubImportButtonProps {
  onImport?: () => void;
}

export function GitHubImportButton({ onImport }: GitHubImportButtonProps) {
  return (
    <div className="flex items-center gap-4 justify-center">
      <span className="text-sm text-[#6a6a6f]">or import from</span>
      <button
        onClick={onImport}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border border-white/10 bg-[#0f0f0f] hover:bg-[#1a1a1e] text-[#8a8a8f] hover:text-white transition-all duration-200 active:scale-95"
      >
        <Github className="size-4" />
        <span>GitHub</span>
      </button>
    </div>
  );
}
