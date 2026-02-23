import type { UIMessage } from '@ai-sdk/react';
import React, { useMemo } from 'react';
import { getMessageText } from '~/lib/chat/getMessageText';
import { classNames } from '~/utils/classNames';
import { AssistantMessage } from './AssistantMessage';
import { UserMessage } from './UserMessage';
import { WorkflowProgress } from './WorkflowProgress';

interface MessagesProps {
  id?: string;
  className?: string;
  isStreaming?: boolean;
  messages?: UIMessage[];
}

/**
 * Extract the latest workflow-status data from a UIMessage's parts.
 * The data stream sends `data-workflow-status` custom data parts.
 */
function extractWorkflowData(message: UIMessage): any | null {
  if (!message.parts) return null;

  let latest: any = null;
  for (const part of message.parts) {
    // AI SDK surfaces custom data parts with type 'data'
    if ((part as any).type === 'data' && (part as any).data) {
      const items = Array.isArray((part as any).data) ? (part as any).data : [(part as any).data];
      for (const item of items) {
        if (item && typeof item === 'object' && 'runId' in item && 'steps' in item) {
          latest = item;
        }
      }
    }
  }
  return latest;
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

          // Check for workflow progress data in assistant messages
          const workflowData = !isUserMessage ? extractWorkflowData(message) : null;

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
                className={classNames('flex flex-col min-w-0', {
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

                {/* Render workflow progress if present */}
                {workflowData && (
                  <div className="w-full mt-2">
                    <WorkflowProgress data={workflowData} />
                  </div>
                )}
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
