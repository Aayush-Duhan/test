import { useStore } from '@nanostores/react';
import { ClientOnly } from '~/components/ClientOnly';
import { chatStore } from '~/lib/stores/chat';
import { HeaderActionButtons } from './HeaderActionButtons.client';
import { ChatDescription } from '~/lib/persistence/ChatDescription.client';

export function Header() {
  const chat = useStore(chatStore);

  return (
    <header className="flex h-[48px] shrink-0 w-full items-center bg-[#0b0c10] text-white px-4 border-b border-white/10">
      <div className="flex items-center gap-2 z-logo text-white cursor-pointer">
        <a href="/" className="flex items-center gap-4 text-white">
          <img src="/EY.svg" alt="EY" className="h-7 w-auto" />
          <span className="text-[24px] leading-none font-semibold tracking-wide">ETHAN</span>
        </a>
      </div>
      <span className="flex-1 px-4 truncate text-center text-white/80">
        <ClientOnly>{() => <ChatDescription />}</ClientOnly>
      </span>
      {chat.started && (
        <ClientOnly>
          {() => (
            <div className="mr-1">
              <HeaderActionButtons />
            </div>
          )}
        </ClientOnly>
      )}
    </header>
  );
}
