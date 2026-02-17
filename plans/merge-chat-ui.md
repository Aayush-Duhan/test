# Plan: Merge BoltStyleChat UI with BaseChat Functionality

## Overview
This plan outlines how to merge the visually appealing BoltStyleChat UI with the existing BaseChat functionality. The goal is to keep the beautiful ray background, announcement badge, and modern chat input design while preserving all the existing functionality like message handling, streaming, and workbench integration.

---

## Analysis

### BoltStyleChat UI Features (to adopt)
1. **RayBackground** - Beautiful gradient ray effect background
2. **AnnouncementBadge** - Glassmorphism badge at top
3. **Title Section** - "What will you build today?" with gradient text
4. **ChatInput** - Modern rounded input with:
   - Plus button with attach menu
   - Model selector dropdown
   - Plan button
   - "Build now" send button
5. **ImportButtons** - Figma/GitHub import options
6. **Uses lucide-react icons**

### BaseChat Functionality (to preserve)
1. **Message handling** - sendMessage, handleInputChange
2. **Streaming support** - isStreaming, handleStop
3. **Prompt enhancement** - enhancePrompt, enhancingPrompt, promptEnhanced
4. **Messages display** - Messages component integration
5. **Workbench integration** - Workbench component
6. **Menu sidebar** - Menu component
7. **Example prompts** - EXAMPLE_PROMPTS array
8. **Keyboard shortcuts** - Enter to send, Shift+Enter for newline

---

## Implementation Steps

### Step 1: Add lucide-react Dependency

**File:** [`package.json`](package.json)

**Add:**
```json
"lucide-react": "^0.454.0"
```

### Step 2: Create New UI Components

Create the following new components:

#### 2.1 RayBackground Component
**File:** `app/components/ui/RayBackground.tsx`
- Extract the RayBackground function from BoltStyleChat
- Make it a standalone reusable component

#### 2.2 AnnouncementBadge Component
**File:** `app/components/ui/AnnouncementBadge.tsx`
- Extract the AnnouncementBadge function
- Make it configurable with text and href props

#### 2.3 ModelSelector Component
**File:** `app/components/ui/ModelSelector.tsx`
- Extract the ModelSelector function
- For now, keep it UI-only (no actual model switching)
- Can be connected to backend later

#### 2.4 ChatInput Component (Enhanced)
**File:** `app/components/ui/ChatInput.tsx`
- Create a new enhanced chat input component
- Integrate with BaseChat's functionality:
  - `input` value and `handleInputChange`
  - `sendMessage` function
  - `isStreaming` state
  - `handleStop` function
  - `enhancePrompt` function

### Step 3: Modify BaseChat Component

**File:** [`app/components/chat/BaseChat.tsx`](app/components/chat/BaseChat.tsx)

**Changes:**
1. Import new UI components
2. Replace the intro section with BoltStyleChat's title section
3. Replace the textarea with the new ChatInput component
4. Add RayBackground
5. Add AnnouncementBadge
6. Keep Messages component for chat history
7. Keep Workbench integration
8. Keep Menu sidebar

### Step 4: Update Styles

**File:** [`app/components/chat/BaseChat.module.scss`](app/components/chat/BaseChat.module.scss)

- Add new styles for the merged layout
- Ensure dark theme compatibility

---

## Component Mapping

| BoltStyleChat Element | BaseChat Equivalent | Action |
|----------------------|---------------------|--------|
| RayBackground | None | Add new |
| AnnouncementBadge | None | Add new |
| Title "What will you build" | "Where ideas begin" | Replace |
| ChatInput | textarea + SendButton | Replace with enhanced version |
| ModelSelector | None | Add new (UI only) |
| ImportButtons | None | Add new |
| Plus/Attach menu | None | Add new (UI only) |
| Plan button | Enhance prompt button | Merge functionality |
| Send button | SendButton | Replace with new style |
| Messages | Messages component | Keep existing |
| Workbench | Workbench component | Keep existing |
| Menu | Menu component | Keep existing |

---

## Files to Create

1. `app/components/ui/RayBackground.tsx`
2. `app/components/ui/AnnouncementBadge.tsx`
3. `app/components/ui/ModelSelector.tsx`
4. `app/components/ui/ChatInput.tsx`

## Files to Modify

1. [`package.json`](package.json) - Add lucide-react dependency
2. [`app/components/chat/BaseChat.tsx`](app/components/chat/BaseChat.tsx) - Integrate new UI
3. [`app/components/chat/BaseChat.module.scss`](app/components/chat/BaseChat.module.scss) - Update styles

## Files to Keep Unchanged

1. `app/components/chat/Messages.client.tsx` - Message display
2. `app/components/chat/SendButton.client.tsx` - May be replaced by ChatInput
3. `app/components/workbench/Workbench.client.tsx` - Workbench
4. `app/components/sidebar/Menu.client.tsx` - Sidebar menu

---

## Detailed Component Design

### New ChatInput Component

```typescript
interface ChatInputProps {
  input: string;
  onInputChange: (event: React.ChangeEvent<HTMLTextAreaElement>) => void;
  onSend: (event: React.UIEvent) => void;
  onStop?: () => void;
  isStreaming?: boolean;
  enhancingPrompt?: boolean;
  promptEnhanced?: boolean;
  onEnhancePrompt?: () => void;
  placeholder?: string;
}
```

Features:
- Auto-resize textarea
- Enter to send, Shift+Enter for newline
- Plus button with attach menu (UI only for now)
- Model selector (UI only for now)
- Plan/Enhance prompt button
- Send/Stop button based on streaming state

---

## Commands to Run

```bash
# Add lucide-react dependency
pnpm add lucide-react
```

---

## Notes

1. **Model Selector**: Initially UI-only. Can be connected to actual model switching logic later.

2. **Attach Menu**: Initially UI-only. File upload functionality can be added later.

3. **Import Buttons**: Initially UI-only. Figma/GitHub import can be implemented later.

4. **Theme**: The new UI uses a dark theme with specific colors (#0f0f0f, #1e1e22, etc.). Ensure compatibility with existing theme variables.

5. **Icons**: Replace existing iconify icons with lucide-react icons where the new UI is used.
