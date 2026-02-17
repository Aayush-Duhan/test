import { useStore } from '@nanostores/react';
import { MessageSquare, Code2 } from 'lucide-react';
import { chatStore } from '~/lib/stores/chat';
import { workbenchStore } from '~/lib/stores/workbench';
import { classNames } from '~/utils/classNames';

interface HeaderActionButtonsProps { }

export function HeaderActionButtons({ }: HeaderActionButtonsProps) {
  const showWorkbench = useStore(workbenchStore.showWorkbench);
  const { showChat } = useStore(chatStore);

  const canHideChat = showWorkbench || !showChat;

  return (
    <div className="flex">
      <div className="flex border border-gray-300 dark:border-gray-600 rounded-md overflow-hidden">
        <Button
          active={showChat}
          disabled={!canHideChat}
          onClick={() => {
            if (canHideChat) {
              chatStore.setKey('showChat', !showChat);
            }
          }}
        >
          <MessageSquare size={16} />
        </Button>
        <div className="w-[1px] bg-bolt-border" />
        <Button
          active={showWorkbench}
          onClick={() => {
            if (showWorkbench && !showChat) {
              chatStore.setKey('showChat', true);
            }

            workbenchStore.showWorkbench.set(!showWorkbench);
          }}
        >
          <Code2 size={16} />
        </Button>
      </div>
    </div>
  );
}

interface ButtonProps {
  active?: boolean;
  disabled?: boolean;
  children?: any;
  onClick?: VoidFunction;
}

function Button({ active = false, disabled = false, children, onClick }: ButtonProps) {
  return (
    <button
      className={classNames('flex items-center p-1.5', {
        'bg-bolt-item-bg-default hover:bg-bolt-item-bg-active text-bolt-text-tertiary hover:text-bolt-text-primary':
          !active,
        'bg-bolt-item-bg-accent text-bolt-item-content-accent': active && !disabled,
        'bg-bolt-item-bg-default text-alpha-gray-20 dark:text-alpha-white-20 cursor-not-allowed':
          disabled,
      })}
      onClick={onClick}
    >
      {children}
    </button>
  );
}
