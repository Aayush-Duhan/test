import { useStore } from '@nanostores/react';
import { type UIMessage, useChat } from '@ai-sdk/react';
import { DefaultChatTransport } from 'ai';
import { useAnimate } from 'framer-motion';
import { memo, useEffect, useRef, useState } from 'react';
import { cssTransition, toast, ToastContainer } from 'react-toastify';
import { X, CheckCircle, AlertCircle } from 'lucide-react';
import { useMessageParser, useShortcuts, useSnapScroll, useSnowflakeConnection, type SnowflakeConnectPayload } from '~/lib/hooks';
import { useChatHistory } from '~/lib/persistence';
import { chatStore } from '~/lib/stores/chat';
import { workbenchStore } from '~/lib/stores/workbench';
import { fileModificationsToHTML } from '~/utils/diff';
import { cubicEasingFn } from '~/utils/easings';
import { createScopedLogger, renderLogger } from '~/utils/logger';
import { BaseChat } from './BaseChat';
import { getMessageText } from '~/lib/chat/getMessageText';

const toastAnimation = cssTransition({
  enter: 'animated fadeInRight',
  exit: 'animated fadeOutRight',
});

const logger = createScopedLogger('Chat');

export function Chat() {
  renderLogger.trace('Chat');

  const { ready, initialMessages, storeMessageHistory } = useChatHistory();

  return (
    <>
      {ready && <ChatImpl initialMessages={initialMessages} storeMessageHistory={storeMessageHistory} />}
      <ToastContainer
        closeButton={({ closeToast }) => {
          return (
            <button className="Toastify__close-button" onClick={closeToast}>
              <X className="text-lg" />
            </button>
          );
        }}
        icon={({ type }) => {
          switch (type) {
            case 'success': {
              return <CheckCircle className="text-bolt-icon-success text-2xl" />;
            }
            case 'error': {
              return <AlertCircle className="text-bolt-icon-error text-2xl" />;
            }
          }

          return undefined;
        }}
        position="bottom-right"
        pauseOnFocusLoss
        transition={toastAnimation}
      />
    </>
  );
}

interface ChatProps {
  initialMessages: UIMessage[];
  storeMessageHistory: (messages: UIMessage[]) => Promise<void>;
}

export const ChatImpl = memo(({ initialMessages, storeMessageHistory }: ChatProps) => {
  useShortcuts();

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [input, setInput] = useState('');
  const [didHydrateInitialMessages, setDidHydrateInitialMessages] = useState(false);
  const [chatStarted, setChatStarted] = useState(initialMessages.length > 0);

  const { showChat } = useStore(chatStore);
  const [animationScope, animate] = useAnimate();

  const {
    messages,
    setMessages,
    sendMessage: sendChatMessage,
    stop,
    status,
  } = useChat({
    transport: new DefaultChatTransport({
      api: '/api/chat?protocol=data',
      credentials: 'include',
    }),
    onError: (error) => {
      logger.error('Request failed\n\n', error);
      toast.error(error.message || 'There was an error processing your request');
    },
  });

  const isLoading = status === 'submitted' || status === 'streaming';

  const {
    connected: snowflakeConnected,
    isBusy: snowflakeBusy,
    error: snowflakeError,
    connect: connectSnowflake,
    disconnect: disconnectSnowflake,
  } = useSnowflakeConnection();

  const { parsedMessages, parseMessages } = useMessageParser();

  const TEXTAREA_MAX_HEIGHT = chatStarted ? 400 : 200;

  useEffect(() => {
    chatStore.setKey('started', initialMessages.length > 0);
  }, [initialMessages.length]);

  useEffect(() => {
    if (didHydrateInitialMessages) {
      return;
    }

    if (initialMessages.length > 0) {
      setMessages(initialMessages);
    }

    setDidHydrateInitialMessages(true);
  }, [didHydrateInitialMessages, initialMessages, setMessages]);

  useEffect(() => {
    parseMessages(messages, isLoading);

    if (messages.length > initialMessages.length) {
      storeMessageHistory(messages).catch((error) => toast.error(error.message));
    }
  }, [messages, isLoading, initialMessages.length, parseMessages, storeMessageHistory]);

  useEffect(() => {
    const textarea = textareaRef.current;

    if (textarea) {
      textarea.style.height = 'auto';

      const scrollHeight = textarea.scrollHeight;

      textarea.style.height = `${Math.min(scrollHeight, TEXTAREA_MAX_HEIGHT)}px`;
      textarea.style.overflowY = scrollHeight > TEXTAREA_MAX_HEIGHT ? 'auto' : 'hidden';
    }
  }, [input, TEXTAREA_MAX_HEIGHT]);

  const runAnimation = async () => {
    if (chatStarted) {
      return;
    }

    await Promise.all([
      animate('#examples', { opacity: 0, display: 'none' }, { duration: 0.1 }),
      animate('#intro', { opacity: 0, flex: 1 }, { duration: 0.2, ease: cubicEasingFn }),
    ]);

    chatStore.setKey('started', true);
    setChatStarted(true);
  };

  const abort = () => {
    stop();
    chatStore.setKey('aborted', true);
    workbenchStore.abortAllActions();
  };

  const sendMessage = async (_event: React.UIEvent, messageInput?: string) => {
    const rawInput = messageInput || input;

    if (rawInput.length === 0 || isLoading) {
      return;
    }

    if (!snowflakeConnected) {
      toast.error('Connect Snowflake before sending a chat message');
      return;
    }

    await workbenchStore.saveAllFiles();

    const fileModifications = workbenchStore.getFileModifcations();

    chatStore.setKey('aborted', false);

    await runAnimation();

    let finalPrompt = rawInput;

    if (fileModifications !== undefined) {
      const diff = fileModificationsToHTML(fileModifications);
      finalPrompt = `${diff}\n\n${rawInput}`;
      workbenchStore.resetAllFileModifications();
    }

    await sendChatMessage({ text: finalPrompt });

    setInput('');
    textareaRef.current?.blur();
  };

  const onConnectSnowflake = async (payload: SnowflakeConnectPayload) => {
    await connectSnowflake(payload);
    toast.success('Snowflake connected');
  };

  const onDisconnectSnowflake = async () => {
    await disconnectSnowflake();
    toast.info('Snowflake disconnected');
  };

  const [messageRef, scrollRef] = useSnapScroll();

  const renderedMessages: UIMessage[] = messages.map((message, index) => {
    const textContent = message.role === 'assistant' ? parsedMessages[index] || getMessageText(message) : getMessageText(message);

    return {
      ...message,
      content: textContent,
    } as UIMessage;
  });

  return (
    <BaseChat
      ref={animationScope}
      textareaRef={textareaRef}
      input={input}
      showChat={showChat}
      chatStarted={chatStarted}
      isStreaming={isLoading}
      sendMessage={sendMessage}
      messageRef={messageRef}
      scrollRef={scrollRef}
      handleInputChange={(event) => setInput(event.target.value)}
      handleStop={abort}
      messages={renderedMessages}
      canSend={snowflakeConnected}
      snowflakeConnected={snowflakeConnected}
      snowflakeBusy={snowflakeBusy}
      snowflakeError={snowflakeError}
      onSnowflakeConnect={onConnectSnowflake}
      onSnowflakeDisconnect={onDisconnectSnowflake}
    />
  );
});
