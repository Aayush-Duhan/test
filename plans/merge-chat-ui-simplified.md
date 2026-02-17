# Plan: Simplified Chat UI Merge

## Overview
This plan outlines a simplified approach to merge the BoltStyleChat UI with BaseChat functionality, removing unnecessary features based on requirements.

---

## Features to Include

### UI Elements (from BoltStyleChat)
1. **RayBackground** - Beautiful gradient ray effect background
2. **Title Section** - "What will you build today?" with gradient text
3. **ChatInput** - Modern rounded input with:
   - Plus button with attach menu (simplified)
   - Model selector dropdown
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
4. ❌ **Example prompts display** - Not needed (remove EXAMPLE_PROMPTS display)
5. ❌ **Figma import** - Only GitHub import needed
6. ❌ **Attach menu file/image options** - Simplify or remove

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
- Extract the RayBackground function from BoltStyleChat
- Standalone reusable component

#### 2.2 ModelSelector Component
**File:** `app/components/ui/ModelSelector.tsx`
- Model dropdown (UI only for now)
- Can be connected to backend later

#### 2.3 ChatInput Component (Simplified)
**File:** `app/components/ui/ChatInput.tsx`
- Modern chat input with:
  - Auto-resize textarea
  - Enter to send, Shift+Enter for newline
  - Model selector
  - Send/Stop button
- **Remove:** Plan button, Enhance prompt button

#### 2.4 GitHubImportButton Component
**File:** `app/components/ui/GitHubImportButton.tsx`
- Simple button to import from GitHub
- Can be expanded with actual functionality later

### Step 3: Modify BaseChat Component

**File:** [`app/components/chat/BaseChat.tsx`](app/components/chat/BaseChat.tsx)

**Changes:**
1. Import new UI components
2. Add RayBackground
3. Replace intro section with simplified title
4. Replace textarea with new ChatInput component
5. Add GitHub import button below input
6. Remove EXAMPLE_PROMPTS display
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
| `app/components/ui/ModelSelector.tsx` | Model dropdown |
| `app/components/ui/ChatInput.tsx` | Simplified chat input |
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

## Simplified Component Design

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

### GitHubImportButton Props

```typescript
interface GitHubImportButtonProps {
  onImport?: (source: string) => void;
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
│                                                             │
│                    ┌─────────────────────┐                  │
│                    │  [+] [Model ▼] [Send] │                 │
│                    │  Chat input area...   │                 │
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

## Notes

1. **Model Selector**: UI-only initially, can connect to actual model switching later.

2. **GitHub Import**: UI-only initially, actual import functionality can be added later.

3. **Clean Removal**: The enhance prompt and example prompts code should be completely removed, not just hidden.

4. **Theme**: Uses dark theme colors (#0f0f0f, #1e1e22, etc.) matching BoltStyleChat.
