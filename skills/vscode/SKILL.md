---
name: vscode
description: Visual Studio Code IDE with integrated terminal, multi-tab editing, command palette, and workspace search.
triggers:
  - vscode
  - code
  - visual studio code
executable_names:
  - code.exe
  - code.cmd
  - code
---

# Visual Studio Code Skill Guide

## Application Overview
Visual Studio Code is an Electron-based development environment. Rely on the Command Palette and built-in shortcuts for zero-latency deterministic control.

## Window Management & Launching
- Launch command: `code.exe [directory_or_file]`
- Standard installation path: `%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe`
- Window class: `Chrome_WidgetWin_1`
- Title format: contains `Visual Studio Code`

## Essential Keyboard Shortcuts
- **Command Palette**: `Ctrl+Shift+P` (access any internal command or setting)
- **Quick Open File**: `Ctrl+P` (type filename, press Enter)
- **Toggle Integrated Terminal**: `Ctrl+` ` (backtick)
- **Toggle Primary Side Bar**: `Ctrl+B`
- **Global Search across Workspace**: `Ctrl+Shift+F`
- **Save File**: `Ctrl+S`
- **Save All**: `Ctrl+K, S`
- **Close Active Editor**: `Ctrl+W`
- **Next Editor Tab**: `Ctrl+PageDown`
- **Previous Editor Tab**: `Ctrl+PageUp`
- **Jump to Line Number**: `Ctrl+G`

## Automation & Ghost Heuristics
1. **Direct Workspace Opening**: When opening a project directory, launch with the path directly: `open_app("code.exe C:\\path\\to\\project")`.
2. **Deterministic Actions**: Prefer `Ctrl+Shift+P` + typing the command name over clicking toolbar icons or status bar buttons.
3. **Terminal Execution**: Use `Ctrl+` ` to toggle terminal, or delegate execution tasks to Sub-Agent B rather than typing commands into the GUI terminal.
