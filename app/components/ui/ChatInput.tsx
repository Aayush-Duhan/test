import { useEffect, useMemo, useRef, useState } from 'react';
import { SendHorizontal, StopCircle, DatabaseZap, PlugZap, X } from 'lucide-react';
import { AttachMenu, type UploadedFile } from './AttachMenu';
import { LanguageSelector, type Language } from './ModelSelector';
import { Dialog, DialogButton, DialogDescription, DialogRoot, DialogTitle } from './Dialog';
import type { SnowflakeConnectPayload } from '~/lib/hooks';

interface ChatInputProps {
  input: string;
  onInputChange: (event: React.ChangeEvent<HTMLTextAreaElement>) => void;
  onSend: (event: React.UIEvent) => void;
  onStop?: () => void;
  isStreaming?: boolean;
  placeholder?: string;
  canSend?: boolean;
  snowflakeConnected?: boolean;
  snowflakeBusy?: boolean;
  snowflakeError?: string;
  onSnowflakeConnect?: (payload: SnowflakeConnectPayload) => Promise<void>;
  onSnowflakeDisconnect?: () => Promise<void>;
  onLanguageChange?: (language: Language) => void;
  chatId?: string;
  uploadedFiles?: UploadedFile[];
  onFilesUploaded?: (files: UploadedFile[]) => void;
  onFileRemove?: (fileName: string) => void;
}

const defaultConnectionForm: SnowflakeConnectPayload = {
  account: '',
  user: '',
  role: '',
  warehouse: '',
  database: '',
  schema: '',
  authenticator: 'externalbrowser',
};

export function ChatInput({
  input,
  onInputChange,
  onSend,
  onStop,
  isStreaming = false,
  placeholder = 'What do you want to build?',
  canSend = true,
  snowflakeConnected = false,
  snowflakeBusy = false,
  snowflakeError,
  onSnowflakeConnect,
  onSnowflakeDisconnect,
  onLanguageChange,
  chatId,
  uploadedFiles = [],
  onFilesUploaded,
  onFileRemove,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [connectError, setConnectError] = useState<string | undefined>(undefined);
  const [connectionForm, setConnectionForm] = useState<SnowflakeConnectPayload>(defaultConnectionForm);

  useEffect(() => {
    const textarea = textareaRef.current;

    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
    }
  }, [input]);

  const trimmedInput = useMemo(() => input.trim(), [input]);

  const handleSubmit = () => {
    if (trimmedInput && canSend) {
      onSend?.({} as React.UIEvent);
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSubmit();
    }
  };

  const handleConnectionField = (field: keyof SnowflakeConnectPayload, value: string) => {
    setConnectionForm((previous) => ({
      ...previous,
      [field]: value,
    }));
  };

  const handleConnect = async () => {
    if (!onSnowflakeConnect) {
      return;
    }

    setConnectError(undefined);

    try {
      await onSnowflakeConnect({
        ...connectionForm,
        authenticator: connectionForm.authenticator || 'externalbrowser',
      });

      setIsDialogOpen(false);
    } catch (connectionError) {
      setConnectError(connectionError instanceof Error ? connectionError.message : 'Unable to connect to Snowflake');
    }
  };

  const disableSendButton = !isStreaming && (!trimmedInput || !canSend);

  return (
    <div className="relative w-full max-w-[680px] mx-auto">
      <div className="absolute -inset-[1px] rounded-2xl bg-gradient-to-b from-white/[0.08] to-transparent pointer-events-none" />
      <div className="relative rounded-2xl bg-[#1e1e22] ring-1 ring-white/[0.08] shadow-[0_0_0_1px_rgba(255,255,255,0.05),0_2px_20px_rgba(0,0,0,0.4)]">
        <div className="relative">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={onInputChange}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            className="w-full resize-none bg-transparent text-[15px] text-white placeholder-[#5a5a5f] px-5 pt-5 pb-3 focus:outline-none min-h-[80px] max-h-[200px]"
            style={{ height: '80px' }}
          />
        </div>

        {uploadedFiles.length > 0 && (
          <div className="flex flex-wrap gap-1.5 px-4 pb-2">
            {uploadedFiles.map((file) => (
              <span
                key={file.name}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-blue-500/15 text-blue-300 text-xs border border-blue-500/20"
              >
                <span className="max-w-[120px] truncate">{file.name}</span>
                <button
                  type="button"
                  onClick={() => onFileRemove?.(file.name)}
                  className="hover:text-white transition-colors"
                >
                  <X className="size-3" />
                </button>
              </span>
            ))}
          </div>
        )}

        {(snowflakeError || connectError) && (
          <p className="px-4 pb-1 text-xs text-red-400">{connectError || snowflakeError}</p>
        )}

        {!snowflakeConnected && (
          <p className="px-4 pb-1 text-xs text-amber-300">Connect Snowflake before sending your first message.</p>
        )}

        <div className="flex items-center justify-between px-3 pb-3 pt-1 gap-2">
          <div className="flex items-center gap-1 flex-wrap">
            <AttachMenu chatId={chatId} onFilesSelected={onFilesUploaded} />
            <LanguageSelector onLanguageChange={onLanguageChange} />

            {snowflakeConnected ? (
              <>
                <button
                  type="button"
                  disabled
                  className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
                >
                  <DatabaseZap className="size-3.5" />
                  Snowflake connected
                </button>
                <button
                  type="button"
                  onClick={() => onSnowflakeDisconnect?.()}
                  disabled={snowflakeBusy}
                  className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium bg-neutral-800 text-neutral-300 hover:text-white disabled:opacity-50"
                >
                  <PlugZap className="size-3.5" />
                  Disconnect
                </button>
              </>
            ) : (
              <button
                type="button"
                onClick={() => setIsDialogOpen(true)}
                disabled={snowflakeBusy}
                className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium bg-[#262626] text-neutral-300 hover:text-white disabled:opacity-50"
              >
                <DatabaseZap className="size-3.5" />
                Connect Snowflake
              </button>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={isStreaming ? onStop : handleSubmit}
              disabled={disableSendButton}
              className="flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium bg-[#1488fc] hover:bg-[#1a94ff] text-white transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed active:scale-95 shadow-[0_0_20px_rgba(20,136,252,0.3)]"
            >
              {isStreaming ? (
                <>
                  <span className="hidden sm:inline">Stop</span>
                  <StopCircle className="size-4" />
                </>
              ) : (
                <>
                  <span className="hidden sm:inline">Migrate now</span>
                  <SendHorizontal className="size-4" />
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      <DialogRoot open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <Dialog>
          <DialogTitle>Connect Snowflake</DialogTitle>
          <DialogDescription className="space-y-3">
            <ConnectionField
              label="Account"
              value={connectionForm.account}
              onChange={(value) => handleConnectionField('account', value)}
              placeholder="EYGDS-XXX"
            />
            <ConnectionField
              label="User"
              value={connectionForm.user}
              onChange={(value) => handleConnectionField('user', value)}
              placeholder="name@company.com"
            />
            <ConnectionField
              label="Role"
              value={connectionForm.role}
              onChange={(value) => handleConnectionField('role', value)}
              placeholder="ACCOUNTADMIN"
            />
            <ConnectionField
              label="Warehouse"
              value={connectionForm.warehouse}
              onChange={(value) => handleConnectionField('warehouse', value)}
              placeholder="COMPUTE_WH"
            />
            <ConnectionField
              label="Database"
              value={connectionForm.database}
              onChange={(value) => handleConnectionField('database', value)}
              placeholder="MY_DATABASE"
            />
            <ConnectionField
              label="Schema"
              value={connectionForm.schema}
              onChange={(value) => handleConnectionField('schema', value)}
              placeholder="PUBLIC"
            />
            <ConnectionField
              label="Authenticator"
              value={connectionForm.authenticator || 'externalbrowser'}
              onChange={(value) => handleConnectionField('authenticator', value)}
              placeholder="externalbrowser"
            />
            {(snowflakeError || connectError) && (
              <p className="text-xs text-red-400">{connectError || snowflakeError}</p>
            )}
            <p className="text-xs text-bolt-text-secondary">
              External browser auth opens once and token caching is reused for future LLM calls.
            </p>
          </DialogDescription>
          <div className="flex items-center justify-end gap-2 px-5 pb-4">
            <DialogButton type="secondary" onClick={() => setIsDialogOpen(false)}>
              Cancel
            </DialogButton>
            <DialogButton type="primary" onClick={() => void handleConnect()}>
              {snowflakeBusy ? 'Connecting...' : 'Connect'}
            </DialogButton>
          </div>
        </Dialog>
      </DialogRoot>
    </div>
  );
}

interface ConnectionFieldProps {
  label: string;
  value: string;
  placeholder: string;
  onChange: (value: string) => void;
}

function ConnectionField({ label, value, placeholder, onChange }: ConnectionFieldProps) {
  return (
    <label className="flex flex-col gap-1 text-sm text-bolt-text-primary">
      <span>{label}</span>
      <input
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        className="rounded-md bg-bolt-bg-depth-3 border border-bolt-border px-3 py-2 text-sm text-bolt-text-primary outline-none focus:border-bolt-elements-focus"
      />
    </label>
  );
}
