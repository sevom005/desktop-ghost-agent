---
name: notepad_plus_plus
description: Advanced multi-tab source code and text editor with syntax highlighting, search/replace, and line navigation.
triggers:
  - notepad++
  - notepad plus plus
  - npp
executable_names:
  - notepad++.exe
  - notepad++
---

# Notepad++ Skill Guide

## Application Overview
Notepad++ is a fast, lightweight, tabbed code and text editor for Windows. Always interact using direct keyboard shortcuts and CLI arguments rather than visual pixel hunting.

## Window Management & Launching
- Launch command: `notepad++.exe [filepath]`
- Standard installation paths:
  - `C:\Program Files (x86)\Notepad++\notepad++.exe`
  - `C:\Program Files\Notepad++\notepad++.exe`
- Window class: `Notepad++`
- Title format: `[filepath] - Notepad++`

## Essential Keyboard Shortcuts
- **New Tab**: `Ctrl+N`
- **Open File**: `Ctrl+O`
- **Save File**: `Ctrl+S`
- **Save All**: `Ctrl+Shift+S`
- **Close Active Tab**: `Ctrl+W`
- **Next Tab**: `Ctrl+PageDown` or `Ctrl+Tab`
- **Previous Tab**: `Ctrl+PageUp` or `Ctrl+Shift+Tab`
- **Jump to Line Number**: `Ctrl+G` (enter line number, press Enter)
- **Find**: `Ctrl+F`
- **Find & Replace**: `Ctrl+H`
- **Duplicate Current Line**: `Ctrl+D`
- **Toggle Comment**: `Ctrl+Q` or `Ctrl+K`

## Automation & Ghost Heuristics
1. **Direct File Opening**: Always pass the file path as an argument to `open_app("notepad++.exe C:\\path\\to\\file.py")` to open it immediately without GUI dialog navigation.
2. **Editing & Appending**: Focus the main editor pane (`Scintilla1`), jump to line (`Ctrl+G`) or EOF (`Ctrl+End`), then send text input.
3. **Unsaved Dialog**: If closing an unsaved buffer triggers a save prompt dialog (`#32770`), press `Enter` to save, `Alt+N` or `Esc` to discard/cancel.
