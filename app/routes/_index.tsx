import { ClientOnly } from '~/components/ClientOnly';
import { BaseChat } from '~/components/chat/BaseChat';
import { Chat } from '~/components/chat/Chat.client';

export default function Index() {
  return (
    <div className="h-full w-full">
      <ClientOnly fallback={<BaseChat />}>{() => <Chat />}</ClientOnly>
    </div>
  );
}
