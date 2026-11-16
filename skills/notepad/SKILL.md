---
name: notepad
description: Standard Windows Notepad text editor for quick notes, logs, and scratch editing.
triggers:
  - notepad
  - text editor
executable_names:
  - notepad.exe
  - notepad
---

# Windows Notepad Skill Guide

## Application Overview
Classic and modern Windows Notepad text editor. Simple buffer suitable for scratch notes and configuration viewing.

## Window Management & Launching
- Launch command: `notepad.exe [filepath]`
- Standard installation paths:
  - `C:\Windows\System32\notepad.exe`
  - `C:\Windows\notepad.exe`
- Window class: `Notepad`
- Title format: `[filename] - Notepad` or `*Untitled - Notepad`

## Essential Keyboard Shortcuts
- **New File**: `Ctrl+N`
- **Open File**: `Ctrl+O`
- **Save File**: `Ctrl+S`
- **Save As**: `Ctrl+Shift+S`
- **Find**: `Ctrl+F`
- **Replace**: `Ctrl+H`
- **Time/Date Stamp**: `F5`

## Automation & Ghost Heuristics
1. **Modal Dialog Handling**: Notepad shows native `#32770` dialogs for unsaved files. Always handle with `Enter` (Save), `Alt+N` (Don't Save), or `Esc` (Cancel).
2. **Word Wrap**: Toggle word wrap with `Alt+Z` (modern) or `Alt+O` then `W` (classic) if text spans beyond viewport.
