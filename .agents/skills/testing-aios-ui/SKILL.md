---
name: testing-aios-ui
description: Test AIOS dashboard and website HTML interfaces. Use when verifying CSS redesigns, design system changes, typography, WebGL shaders, or layout modifications.
---

# Testing AIOS UI (Dashboard & Website)

## Overview
AIOS uses standalone HTML files (`AIOS-DASHBOARD.html`, `AIOS-WEBSITE.html`) that can be opened directly in Chrome via `file://` protocol. No build step or server required.

## How to Open
1. Navigate Chrome to `file:///home/ubuntu/AIOS/AIOS-DASHBOARD.html` or `file:///home/ubuntu/AIOS/AIOS-WEBSITE.html`
2. The website has a cinematic entry animation (~4.5s) — wait or click to dismiss before testing

## Design System Verification
The bespoke design system uses these custom properties — verify via `getComputedStyle`:

### Typography
- **Display**: `"Space Grotesk"` — used on `h1`, `h2`, `.brand-name`, `.module h3`
- **Body**: `"Inter"` — used on body, `.lead`, `.btn`, `.nav-links`
- **Mono**: `"JetBrains Mono"` — used on `.kicker`, `.module-label`, `.command-title`, `.status`, `.footer`

### Colors
- `--void: #04050A` (html background) → `rgb(4, 5, 10)`
- `--gold: #C4A35A` → `rgb(196, 163, 90)` (border accents)
- `--green: #00E88F` → `rgb(0, 232, 143)` (status indicators)

### Anti-Template Checks
- `border-radius` should be `3px` on cards/modules/buttons (NOT 8px which indicates Material/Bootstrap)
- `border-radius` should be `6px` on floating nav (--radius-lg)
- Transitions should include `cubic-bezier(0.34, 1.56, 0.64, 1)` (spring) — NOT linear or ease

### WebGL Shader Verification
- Check `document.getElementById('siteEyeWebGLCanvas')?.dataset.running === 'true'`
- Check `document.getElementById('siteEyeCanvas')?.dataset.running === 'true'`
- Look for shader compile errors in console

### Nav Glassmorphism
- `backdrop-filter` should contain `blur(48px)` and `saturate(1.8)`
- Nav should be `position: fixed` with gold-tinted border

## Key Verification Console Script
```javascript
// Run in browser console to verify design system
JSON.stringify({
  h1Font: getComputedStyle(document.querySelector('h1')).fontFamily,
  bodyBg: getComputedStyle(document.documentElement).backgroundColor,
  moduleRadius: getComputedStyle(document.querySelector('.module')).borderRadius,
  navBlur: getComputedStyle(document.querySelector('.nav')).backdropFilter,
  webglRunning: document.getElementById('siteEyeWebGLCanvas')?.dataset.running
})
```

## Common Issues
- The cinematic entry might make the page appear blank for ~4.5s — click or wait
- Fonts load from Google Fonts CDN — may not render if offline; fallback to system fonts
- WebGL shader might not compile on some GPU drivers — check console for warnings
- The nav is `position: fixed` and floats over content — scroll down to see it over sections

## Devin Secrets Needed
None — testing is fully local with no authentication required.
