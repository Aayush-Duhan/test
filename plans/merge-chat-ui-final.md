# Plan: Final Chat UI Merge

## Overview
This plan outlines the final approach to merge the BoltStyleChat UI with BaseChat functionality, incorporating all requested features.

---

## Features to Include

### UI Elements (from BoltStyleChat)
1. **RayBackground** - Beautiful gradient ray effect background
2. **Title Section** - "What will you build today?" with gradient text
3. **ChatInput** - Modern rounded input with:
   - **Plus button with attach menu** (Upload file, Add image, Import code)
   - **Model selector dropdown**
   - Send button
4. **GitHub Import Button** - Only GitHub import option

### Functionality (from BaseChat)
1. **Message handling** - sendMessage, handleInputChange
2. **Streaming support** - isStreaming, handleStop
3. **Messages display** - Messages component integration
4. **Workbench integration** - Workbench component
5. **Menu sidebar** - Menu component

---

## Features to Remove

1. ❌ **AnnouncementBadge** - Not needed
2. ❌ **Plan button** - Not needed
3. ❌ **Enhance prompt functionality** - Not needed
4. ❌ **Example prompts display** - Not needed
5. ❌ **Figma import** - Only GitHub import needed

---

## Implementation Steps

### Step 1: Add lucide-react Dependency

**File:** [`package.json`](package.json)

**Add:**
```json
"lucide-react": "^0.454.0"
```

### Step 2: Create New UI Components

#### 2.1 RayBackground Component
**File:** `app/components/ui/RayBackground.tsx`
- Gradient ray background effect
- Standalone reusable component

#### 2.2 ModelSelector Component
**File:** `app/components/ui/ModelSelector.tsx`
- Model dropdown with options:
  - Sonnet 4.5 (Default)
  - Opus 4.5 (Pro)
  - Haiku 4.5
  - GPT-4o
  - Gemini 2.0
- UI only for now, can connect to backend later

#### 2.3 AttachMenu Component
**File:** `app/components/ui/AttachMenu.tsx`
- Plus button with dropdown menu:
  - Upload file
  - Add image
  - Import code
- UI only for now, functionality can be added later

#### 2.4 ChatInput Component
**File:** `app/components/ui/ChatInput.tsx`
- Modern chat input with:
  - Auto-resize textarea
  - Enter to send, Shift+Enter for newline
  - AttachMenu (plus button)
  - ModelSelector
  - Send/Stop button
- **No Plan button, No Enhance prompt button**

#### 2.5 GitHubImportButton Component
**File:** `app/components/ui/GitHubImportButton.tsx`
- Simple button to import from GitHub
- Can be expanded with actual functionality later

### Step 3: Modify BaseChat Component

**File:** [`app/components/chat/BaseChat.tsx`](app/components/chat/BaseChat.tsx)

**Changes:**
1. Import new UI components (RayBackground, ChatInput, GitHubImportButton)
2. Add RayBackground as background
3. Replace intro section with title: "What will you build today?"
4. Replace textarea with new ChatInput component
5. Add GitHub import button below input
6. Remove EXAMPLE_PROMPTS display section
7. Remove enhance prompt button and related props
8. Keep Messages component for chat history
9. Keep Workbench integration
10. Keep Menu sidebar

### Step 4: Update Props Interface

Remove from BaseChatProps:
- `enhancingPrompt`
- `promptEnhanced`
- `enhancePrompt`

---

## Files to Create

| File | Description |
|------|-------------|
| `app/components/ui/RayBackground.tsx` | Gradient ray background |
| `app/components/ui/ModelSelector.tsx` | Model dropdown with 5 options |
| `app/components/ui/AttachMenu.tsx` | Plus button with attach options |
| `app/components/ui/ChatInput.tsx` | Main chat input component |
| `app/components/ui/GitHubImportButton.tsx` | GitHub import button |

## Files to Modify

| File | Changes |
|------|---------|
| [`package.json`](package.json) | Add lucide-react dependency |
| [`app/components/chat/BaseChat.tsx`](app/components/chat/BaseChat.tsx) | Integrate new UI, remove unused features |
| [`app/components/chat/BaseChat.module.scss`](app/components/chat/BaseChat.module.scss) | Update styles |

## Files to Potentially Delete

| File | Reason |
|------|--------|
| `app/components/chat/SendButton.client.tsx` | Replaced by ChatInput component |

---

## Component Props Design

### ChatInput Props

```typescript
interface ChatInputProps {
  input: string;
  onInputChange: (event: React.ChangeEvent<HTMLTextAreaElement>) => void;
  onSend: (event: React.UIEvent) => void;
  onStop?: () => void;
  isStreaming?: boolean;
  placeholder?: string;
}
```

### ModelSelector Props

```typescript
interface ModelSelectorProps {
  selectedModel?: string;
  onModelChange?: (model: Model) => void;
}

interface Model {
  id: string;
  name: string;
  description: string;
  icon: React.ReactNode;
  badge?: string;
}
```

### AttachMenu Props

```typescript
interface AttachMenuProps {
  onUploadFile?: () => void;
  onAddImage?: () => void;
  onImportCode?: () => void;
}
```

### GitHubImportButton Props

```typescript
interface GitHubImportButtonProps {
  onImport?: () => void;
}
```

---

## Commands to Run

```bash
# Add lucide-react dependency
pnpm add lucide-react
```

---

## Visual Layout

```
┌─────────────────────────────────────────────────────────────┐
│ [Menu Sidebar]                                              │
│                                                             │
│                    ┌─────────────────┐                      │
│                    │  Ray Background  │                     │
│                    └─────────────────┘                      │
│                                                             │
│              What will you build today?                     │
│           Create stunning apps & websites                   │
│                                                             │
│                    ┌─────────────────────┐                  │
│                    │ [+] [Model ▼] [Send]│                  │
│                    │ Chat input area...  │                  │
│                    └─────────────────────┘                  │
│                                                             │
│                    or import from [GitHub]                  │
│                                                             │
│                    [Messages Area]                          │
│                                                             │
│                    [Workbench Panel]                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## AttachMenu Options

When clicking the plus button, show:
1. 📎 Upload file
2. 🖼️ Add image
3. 💻 Import code

---

## ModelSelector Options

| Model | Description | Badge |
|-------|-------------|-------|
| Sonnet 4.5 | Fast & intelligent | Default |
| Opus 4.5 | Most capable | Pro |
| Haiku 4.5 | Lightning fast | - |
| GPT-4o | OpenAI flagship | - |
| Gemini 2.0 | Google AI | - |

---

## Notes

1. **Model Selector**: UI-only initially, can connect to actual model switching later.

2. **Attach Menu**: UI-only initially, file upload functionality can be added later.

3. **GitHub Import**: UI-only initially, actual import functionality can be added later.

4. **Clean Removal**: The enhance prompt and example prompts code should be completely removed.

5. **Theme**: Uses dark theme colors (#0f0f0f, #1e1e22, etc.) matching BoltStyleChat.

6. **Icons**: Uses lucide-react icons (Plus, ChevronDown, Check, Sparkles, Zap, Brain, Github, SendHorizontal, Paperclip, Image, FileCode).
