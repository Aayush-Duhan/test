# Plan: Limit Editor to SQL and Markdown Only

## Overview
This plan outlines the steps to modify the CodeMirror editor to support only SQL and Markdown languages, removing support for all other languages (JavaScript, TypeScript, HTML, CSS, Python, C++, etc.).

## Current State

### Supported Languages (to be removed)
- TypeScript (`.ts`)
- JavaScript (`.js`, `.mjs`, `.cjs`)
- TSX (`.tsx`)
- JSX (`.jsx`)
- HTML (`.html`)
- CSS (`.css`)
- SASS (`.sass`)
- SCSS (`.scss`)
- JSON (`.json`)
- WebAssembly (`.wat`)
- Python (`.py`)
- C++ (`.cpp`)

### Languages to Keep
- Markdown (`.md`) - Already supported

### Languages to Add
- SQL (`.sql`) - Need to add `@codemirror/lang-sql` package

---

## Implementation Steps

### Step 1: Update Dependencies in package.json

**File:** [`package.json`](package.json)

**Add:**
```json
"@codemirror/lang-sql": "^6.8.0"
```

**Remove:**
```json
"@codemirror/lang-cpp": "^6.0.2",
"@codemirror/lang-css": "^6.2.1",
"@codemirror/lang-html": "^6.4.9",
"@codemirror/lang-javascript": "^6.2.2",
"@codemirror/lang-json": "^6.0.1",
"@codemirror/lang-python": "^6.1.6",
"@codemirror/lang-sass": "^6.0.2",
"@codemirror/lang-wast": "^6.0.2"
```

**Keep:**
```json
"@codemirror/lang-markdown": "^6.2.5"
```

### Step 2: Update Language Support File

**File:** [`app/components/editor/codemirror/languages.ts`](app/components/editor/codemirror/languages.ts)

**Replace entire file content with:**
```typescript
import { LanguageDescription } from '@codemirror/language';

export const supportedLanguages = [
  LanguageDescription.of({
    name: 'SQL',
    extensions: ['sql'],
    async load() {
      return import('@codemirror/lang-sql').then((module) => module.standardSQL);
    },
  }),
  LanguageDescription.of({
    name: 'Markdown',
    extensions: ['md'],
    async load() {
      return import('@codemirror/lang-markdown').then((module) => module.markdown());
    },
  }),
];

export async function getLanguage(fileName: string) {
  const languageDescription = LanguageDescription.matchFilename(supportedLanguages, fileName);

  if (languageDescription) {
    return await languageDescription.load();
  }

  return undefined;
}
```

---

## Files to Modify

| File | Action | Description |
|------|--------|-------------|
| [`package.json`](package.json) | Modify | Add SQL lang, remove unused language packages |
| [`app/components/editor/codemirror/languages.ts`](app/components/editor/codemirror/languages.ts) | Rewrite | Keep only SQL and Markdown language definitions |

---

## Commands to Run After Changes

```bash
# Install new dependency and remove unused ones
pnpm install

# Or manually remove and reinstall
pnpm remove @codemirror/lang-cpp @codemirror/lang-css @codemirror/lang-html @codemirror/lang-javascript @codemirror/lang-json @codemirror/lang-python @codemirror/lang-sass @codemirror/lang-wast
pnpm add @codemirror/lang-sql
```

---

## Notes

1. **SQL Dialect**: The plan uses `standardSQL` from `@codemirror/lang-sql`. Other dialects available:
   - `standardSQL` - Standard SQL
   - `MySQL` - MySQL dialect
   - `PostgreSQL` - PostgreSQL dialect
   - `MSSQL` - Microsoft SQL Server
   - `SQLite` - SQLite dialect

2. **Markdown**: The existing Markdown support will be preserved as-is.

3. **Fallback**: Files without `.sql` or `.md` extensions will load without syntax highlighting.

4. **Bundle Size**: Removing unused language packages will reduce the bundle size significantly.
