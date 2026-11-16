---
name: chrome
description: Google Chrome web browser for web browsing, URL navigation, multi-tab workflows, and developer tools.
triggers:
  - chrome
  - google chrome
  - browser
executable_names:
  - chrome.exe
  - chrome
---

# Google Chrome Skill Guide

## Application Overview
Google Chrome is the primary web browser. Navigate using the Omnibox (address bar) and standard tab shortcuts.

## Window Management & Launching
- Launch command: `chrome.exe [url]`
- Standard installation paths:
  - `C:\Program Files\Google\Chrome\Application\chrome.exe`
  - `C:\Program Files (x86)\Google\Chrome\Application\chrome.exe`
- Window class: `Chrome_WidgetWin_1`
- Title format: `[Page Title] - Google Chrome`

## Essential Keyboard Shortcuts
- **Focus Omnibox (Address Bar)**: `Ctrl+L` or `Alt+D`
- **New Tab**: `Ctrl+T`
- **Close Active Tab**: `Ctrl+W`
- **Reopen Closed Tab**: `Ctrl+Shift+T`
- **Next Tab**: `Ctrl+Tab` or `Ctrl+PageDown`
- **Previous Tab**: `Ctrl+Shift+Tab` or `Ctrl+PageUp`
- **Reload Page**: `Ctrl+R` or `F5`
- **Hard Reload**: `Ctrl+Shift+R`
- **Find in Page**: `Ctrl+F`
- **Developer Tools**: `Ctrl+Shift+I` or `F12`
- **Page Zoom In/Out/Reset**: `Ctrl++`, `Ctrl+-`, `Ctrl+0`

## Automation & Ghost Heuristics
1. **Direct Navigation**: Always use `Ctrl+L` -> type URL -> `Enter` to navigate, avoiding mouse clicks on the address bar.
2. **Page Load Wait**: Wait 1.0s to 2.0s after hitting Enter for initial page render before issuing further keyboard/mouse commands.
