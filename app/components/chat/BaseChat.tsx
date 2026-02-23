import type { UIMessage } from '@ai-sdk/react';
import React, { type RefCallback } from 'react';
import { ClientOnly } from '~/components/ClientOnly';
import { Workbench } from '~/components/workbench/Workbench.client';
import { classNames } from '~/utils/classNames';
import { Messages } from './Messages.client';
import { ChatInput } from '~/components/ui/ChatInput';
import { RayBackground } from '~/components/ui/RayBackground';
import { SetupWizard, type WizardConfig } from '~/components/wizard/SetupWizard';
import type { Language } from '~/components/ui/ModelSelector';
import type { UploadedFile } from '~/components/ui/AttachMenu';
import type { SnowflakeConnectPayload } from '~/lib/hooks';

import styles from './BaseChat.module.scss';

interface BaseChatProps {
  textareaRef?: React.RefObject<HTMLTextAreaElement> | undefined;
  messageRef?: RefCallback<HTMLDivElement> | undefined;
  scrollRef?: RefCallback<HTMLDivElement> | undefined;
  showChat?: boolean;
  chatStarted?: boolean;
  isStreaming?: boolean;
  messages?: UIMessage[];
  input?: string;
  canSend?: boolean;
  snowflakeConnected?: boolean;
  snowflakeBusy?: boolean;
  snowflakeError?: string;
  onSnowflakeConnect?: (payload: SnowflakeConnectPayload) => Promise<void>;
  onSnowflakeDisconnect?: () => Promise<void>;
  handleStop?: () => void;
  sendMessage?: (event: React.UIEvent, messageInput?: string) => void;
  handleInputChange?: (event: React.ChangeEvent<HTMLTextAreaElement>) => void;
  onLanguageChange?: (language: Language) => void;
  onWizardComplete?: (config: WizardConfig) => void;
  chatId?: string;
  uploadedFiles?: UploadedFile[];
  onFilesUploaded?: (files: UploadedFile[]) => void;
  onFileRemove?: (fileName: string) => void;
}

export const BaseChat = React.forwardRef<HTMLDivElement, BaseChatProps>(
  (
    {
      textareaRef: _textareaRef,
      messageRef,
      scrollRef,
      showChat = true,
      chatStarted = false,
      isStreaming = false,
      messages,
      input = '',
      canSend = true,
      snowflakeConnected = false,
      snowflakeBusy = false,
      snowflakeError,
      onSnowflakeConnect,
      onSnowflakeDisconnect,
      sendMessage,
      handleInputChange,
      handleStop,
      onLanguageChange,
      onWizardComplete,
      chatId,
      uploadedFiles,
      onFilesUploaded,
      onFileRemove,
    },
    ref,
  ) => {
    return (
      <div
        ref={ref}
        className={classNames(styles.BaseChat, 'relative flex h-full w-full overflow-hidden', {
          'bg-bolt-chat-active-bg': chatStarted,
          'bg-bolt-bg-depth-1': !chatStarted,
        })}
        data-chat-visible={showChat}
      >
        {!chatStarted && <RayBackground />}
        <div ref={scrollRef} className="relative z-10 flex h-full w-full box-border overflow-y-auto">
          <div className="flex h-full min-w-0 flex-1">
            <div className={classNames(styles.Chat, 'relative flex min-w-0 flex-1 flex-col h-full')}>
              {chatStarted ? (
                <div className="pt-6 px-6 pb-4 min-h-full flex flex-col">
                  <ClientOnly>
                    {() => (
                      <Messages
                        ref={messageRef}
                        className="flex flex-col w-full max-w-chat px-4 pb-6 mx-auto z-1"
                        messages={messages}
                        isStreaming={isStreaming}
                      />
                    )}
                  </ClientOnly>
                  <div className="relative w-full max-w-chat mx-auto mt-auto z-prompt sticky bottom-0 pb-2 sm:pb-4">
                    <div className="w-full max-w-[700px] mx-auto mt-2">
                      <ChatInput
                        input={input}
                        onInputChange={(event) => handleInputChange?.(event)}
                        onSend={(event) => sendMessage?.(event)}
                        onStop={handleStop}
                        isStreaming={isStreaming}
                        canSend={canSend}
                        snowflakeConnected={snowflakeConnected}
                        snowflakeBusy={snowflakeBusy}
                        snowflakeError={snowflakeError}
                        onSnowflakeConnect={onSnowflakeConnect}
                        onSnowflakeDisconnect={onSnowflakeDisconnect}
                        onLanguageChange={onLanguageChange}
                        chatId={chatId}
                        uploadedFiles={uploadedFiles}
                        onFilesUploaded={onFilesUploaded}
                        onFileRemove={onFileRemove}
                        placeholder="What do you want to build?"
                      />
                    </div>
                  </div>
                </div>
              ) : (
                <div className="relative z-10 flex h-full w-full items-center justify-center px-4 py-8 overflow-y-auto">
                  <SetupWizard
                    snowflakeConnected={snowflakeConnected}
                    snowflakeBusy={snowflakeBusy}
                    snowflakeError={snowflakeError}
                    onSnowflakeConnect={onSnowflakeConnect!}
                    onSnowflakeDisconnect={onSnowflakeDisconnect!}
                    onComplete={(config) => onWizardComplete?.(config)}
                  />
                </div>
              )}
            </div>
          </div>
          <ClientOnly>{() => <Workbench chatStarted={chatStarted} isStreaming={isStreaming} />}</ClientOnly>
        </div>
      </div>
    );
  },
);
