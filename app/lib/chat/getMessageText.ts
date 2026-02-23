import type { UIMessage } from '@ai-sdk/react';

function coerceText(value: unknown): string {
  if (typeof value === 'string') {
    return value;
  }

  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (typeof item === 'string') {
          return item;
        }

        if (item && typeof item === 'object' && 'text' in item && typeof (item as { text?: unknown }).text === 'string') {
          return (item as { text: string }).text;
        }

        return '';
      })
      .join('');
  }

  if (value && typeof value === 'object' && 'text' in value && typeof (value as { text?: unknown }).text === 'string') {
    return (value as { text: string }).text;
  }

  return '';
}

export function getMessageText(message: Pick<UIMessage, 'parts'> & { content?: unknown }): string {
  let result = '';

  if (Array.isArray(message.parts) && message.parts.length > 0) {
    result = message.parts
      .map((part) => {
        const p = part as any;

        if (p.type === 'text' && typeof p.text === 'string') {
          return p.text;
        }

        if (p.type === 'reasoning' && (typeof p.reasoning === 'string' || typeof p.text === 'string' || typeof p.details === 'string')) {
          const reasoningContent = p.reasoning || p.text || p.details;
          return `\n\n<details class="reasoning-block bg-bolt-elements-background-depth-1 p-3 rounded-lg my-2"><summary class="cursor-pointer font-semibold select-none text-bolt-elements-textTertiary hover:text-bolt-elements-textPrimary transition-colors flex items-center"><span class="i-ph:brain-duotone text-lg mr-2"></span> Thinking Process</summary>\n\n${reasoningContent}\n\n</details>\n\n`;
        }

        if (p.type === 'tool-invocation' || (typeof p.type === 'string' && p.type.startsWith('tool-'))) {
          const toolName = p.toolInvocation?.toolName || p.toolName || 'unknown-tool';
          return `\n\n> 🛠️ **Tool Call:** \`${toolName}\`\n\n`;
        }

        if (p.type === 'source-url' && p.url) {
          return `\n\n🔗 **Source:** [${p.url}](${p.url})\n\n`;
        }

        if (p.type === 'source-document' && p.sourceId) {
          return `\n\n📄 **Document:** ${p.title || p.sourceId} (${p.mediaType})\n\n`;
        }

        if (p.type === 'file' && p.url) {
          return `\n\n📎 **File:** [Download](${p.url}) (${p.mediaType})\n\n`;
        }

        if (p.type === 'start-step') {
          return `\n\n> ⏳ *Starting Step...*\n\n`;
        }

        if (p.type === 'finish-step') {
          return `\n\n> ✅ *Step Completed.*\n\n`;
        }

        if (typeof p.type === 'string' && p.type.startsWith('data-') && p.data) {
          return `\n\n> 📦 **Data Received** (\`${p.type.replace('data-', '')}\`)\n\n`;
        }

        return '';
      })
      .join('');

    if (result.trim().length > 0) {
      return result;
    }
  }

  return coerceText(message.content);
}
