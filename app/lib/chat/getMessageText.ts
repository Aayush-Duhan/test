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
  if (Array.isArray(message.parts) && message.parts.length > 0) {
    const text = message.parts
      .map((part) => {
        if (part.type === 'text' && typeof part.text === 'string') {
          return part.text;
        }

        return '';
      })
      .join('');

    if (text.length > 0) {
      return text;
    }
  }

  return coerceText(message.content);
}
