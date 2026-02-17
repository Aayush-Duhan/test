import { useStore } from '@nanostores/react';
import { motion, type Variants } from 'framer-motion';
import { memo, useCallback, useEffect } from 'react';
import { toast } from 'react-toastify';
import { Terminal, XCircle } from 'lucide-react';
import {
  type OnChangeCallback as OnEditorChange,
  type OnScrollCallback as OnEditorScroll,
} from '~/components/editor/codemirror/CodeMirrorEditor';
import { IconButton } from '~/components/ui/IconButton';
import { PanelHeaderButton } from '~/components/ui/PanelHeaderButton';
import { workbenchStore } from '~/lib/stores/workbench';
import { cubicEasingFn } from '~/utils/easings';
import { renderLogger } from '~/utils/logger';
import { EditorPanel } from './EditorPanel';

interface WorkspaceProps {
  chatStarted?: boolean;
  isStreaming?: boolean;
}

const workbenchVariants = {
  closed: {
    width: 0,
    transition: {
      duration: 0.2,
      ease: cubicEasingFn,
    },
  },
  open: {
    width: 'var(--workbench-width)',
    transition: {
      duration: 0.2,
      ease: cubicEasingFn,
    },
  },
} satisfies Variants;

export const Workbench = memo(({ chatStarted, isStreaming }: WorkspaceProps) => {
  renderLogger.trace('Workbench');

  const showWorkbench = useStore(workbenchStore.showWorkbench);
  const selectedFile = useStore(workbenchStore.selectedFile);
  const currentDocument = useStore(workbenchStore.currentDocument);
  const unsavedFiles = useStore(workbenchStore.unsavedFiles);
  const files = useStore(workbenchStore.files);

  useEffect(() => {
    workbenchStore.setDocuments(files);
  }, [files]);

  const onEditorChange = useCallback<OnEditorChange>((update) => {
    workbenchStore.setCurrentDocumentContent(update.content);
  }, []);

  const onEditorScroll = useCallback<OnEditorScroll>((position) => {
    workbenchStore.setCurrentDocumentScrollPosition(position);
  }, []);

  const onFileSelect = useCallback((filePath: string | undefined) => {
    workbenchStore.setSelectedFile(filePath);
  }, []);

  const onFileSave = useCallback(() => {
    workbenchStore.saveCurrentDocument().catch(() => {
      toast.error('Failed to update file content');
    });
  }, []);

  const onFileReset = useCallback(() => {
    workbenchStore.resetCurrentDocument();
  }, []);

  return (
    chatStarted && (
      <motion.div
        initial="closed"
        animate={showWorkbench ? 'open' : 'closed'}
        variants={workbenchVariants}
        className="z-workbench sticky top-0 self-start h-full shrink-0 overflow-hidden"
      >
        <div className="h-full box-border py-4 pr-4 pl-3">
          <div className="h-full w-[var(--workbench-inner-width)] max-w-full ml-auto">
            <div className="h-full flex flex-col bg-bolt-bg-depth-2 border border-bolt-border shadow-sm rounded-lg overflow-hidden">
              <div className="flex items-center px-3 py-2 border-b border-bolt-border">
                <div className="ml-auto" />
                <PanelHeaderButton
                  className="mr-1 text-sm"
                  onClick={() => {
                    workbenchStore.toggleTerminal(!workbenchStore.showTerminal.get());
                  }}
                >
                  <Terminal />
                  Toggle Terminal
                </PanelHeaderButton>
                <IconButton
                  icon={<XCircle />}
                  className="-mr-1"
                  size="xl"
                  onClick={() => {
                    workbenchStore.showWorkbench.set(false);
                  }}
                />
              </div>
              <div className="relative flex-1 overflow-hidden">
                <EditorPanel
                  editorDocument={currentDocument}
                  isStreaming={isStreaming}
                  selectedFile={selectedFile}
                  files={files}
                  unsavedFiles={unsavedFiles}
                  onFileSelect={onFileSelect}
                  onEditorScroll={onEditorScroll}
                  onEditorChange={onEditorChange}
                  onFileSave={onFileSave}
                  onFileReset={onFileReset}
                />
              </div>
            </div>
          </div>
        </div>
      </motion.div>
    )
  );
});
