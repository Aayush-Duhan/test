import type { UIMessage } from '@ai-sdk/react';
import React from 'react';
import { getMessageText } from '~/lib/chat/getMessageText';
import { classNames } from '~/utils/classNames';
import { AssistantMessage } from './AssistantMessage';
import { UserMessage } from './UserMessage';

interface MessagesProps {
  id?: string;
  className?: string;
  isStreaming?: boolean;
  messages?: UIMessage[];
}

export const Messages = React.forwardRef<HTMLDivElement, MessagesProps>((props: MessagesProps, ref) => {
  const { id, isStreaming = false, messages = [] } = props;

  return (
    <div id={id} ref={ref} className={props.className}>
      {messages.length > 0
        ? messages.map((message, index) => {
            const { role } = message;
            const content = getMessageText(message);
            const isUserMessage = role === 'user';
            const isUserMultiline = isUserMessage && content.includes('\n');
            const isFirst = index === 0;
            const isLast = index === messages.length - 1;
            const key = message.id || `${role}-${index}`;

            return (
              <div
                key={key}
                className={classNames('flex w-full', {
                  'justify-end': isUserMessage,
                  'justify-start': !isUserMessage,
                  'mt-4': !isFirst,
                })}
              >
                <div
                  data-multiline={isUserMultiline ? '' : undefined}
                  className={classNames('flex min-w-0 items-start', {
                    'user-message-bubble user-message-bubble-color corner-superellipse/1.1 relative px-4 py-1.5 data-[multiline]:py-3':
                      isUserMessage,
                    'w-full max-w-[min(46rem,92%)] rounded-[calc(0.75rem-1px)] px-4 py-1.5 bg-bolt-elements-messages-background text-bolt-text-primary':
                      !isUserMessage && (!isStreaming || (isStreaming && !isLast)),
                    'w-full max-w-[min(46rem,92%)] rounded-[calc(0.75rem-1px)] px-4 py-1.5 bg-gradient-to-b from-bolt-elements-messages-background from-30% to-transparent text-bolt-text-primary':
                      !isUserMessage && isStreaming && isLast,
                  })}
                >
                  <div
                    className={classNames('grid grid-cols-1 min-w-0', {
                      'w-auto': isUserMessage,
                      'w-full': !isUserMessage,
                    })}
                  >
                    {isUserMessage ? <UserMessage content={content} /> : <AssistantMessage content={content} />}
                  </div>
                </div>
              </div>
            );
          })
        : null}
      {isStreaming && (
        <div className="text-center w-full text-bolt-text-secondary text-4xl mt-4">
          <span className="animate-pulse">...</span>
        </div>
      )}
    </div>
  );
});
