# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Thai-language B2B catalog site for **โปรคลีน ซัพพลาย ไทยแลนด์ (PROCLEAN SUPPLY THAILAND)**, a distributor (not a manufacturer) of cleaning concentrates from the BIOMATE, SAFECO, and RIVERRA brands. There is no backend and no checkout. Every call to action goes to LINE (`@672xlnwi`), phone (`tel:+66811764104`), or email (`mailto:suwat10928@gmail.com`). `check.py` fails if links use more than one of each.

The entire site is **one self-contained file, `index.html`** (~2 MB). It has no build step and no dependencies. Fonts and images are inlined as base64.

## Commands

```bash
python3 tools/check.py            # static consistency checks (routes, links, images, ids, product counts, noindex)
node tools/smoke.js               # Playwright browser smoke test; needs the `playwright` package + Chromium
NODE_PATH=$(npm root -g) node tools/smoke.js   # in the Claude Code cloud container (playwright is installed globally)
python3 -m http.server            # preview at http://localhost:8000/ (opening index.html directly also works)
```

Both scripts take an optional path argument, so you can compare a modified copy against `HEAD`: `python3 tools/check.py <(git show HEAD:index.html)`. Run both before committing changes to `index.html`.

## Working with index.html

- The file contains lines hundreds of KB long (base64 `@font-face`, images, and the `window.__IMG` map). Don't `Read` the whole file. Use `grep -n -o`, `cut -c1-400`, or a Python script that replaces `data:...;base64,...` with placeholders before viewing.
- Make edits as exact-string replacements (for example in Python, after asserting the snippet occurs exactly once). Line-based tools struggle with the giant lines.

## Architecture (single-file, hash-routed)

- **Pages are `<template data-route="/path/">` elements.** Each one carries `data-title` (the document title) and `data-mbar` (the LINE link for the fixed mobile bottom bar). The router in the final `<script>` reads `location.hash` (`#/products/?brand=riverra`), clones the matching template into `<main>`, and falls back to `/404.html` when no route matches.
- **The home page exists twice.** It appears as static markup in `<main>` (shown on first load and without JS) and as `<template data-route="/">`. The two must stay identical, and `check.py` enforces this.
- **Internal links are authored as real paths** (`href="/products/x/"`). At runtime, `links()` rewrites them to `#/products/x/` so that new tabs and copied links work on single-file hosting. Keep authoring real paths so the markup can later be split into a real multi-page site.
- **Images are referenced by key** (`<img data-img="biomate-dishwash-gallon">`). The base64 data lives either on the first inline `<img src="data:...">` in the static home page or in the `window.__IMG` map just before the main script. `hydrate()` fills in `src` after each render. Images inside templates never have `src`. A new image needs a new `__IMG` entry.
- **Product data is denormalized.** Each product's card (`<article class="card" data-pid data-brand data-cat data-size data-ind data-search>`) is repeated on `/products/`, its category, industry, and brand pages, and in "related" sections. Count labels such as "N รายการ" (home tiles, industry rows, brand blurbs, about page) and the total of 17 products are hard-coded text. Adding or changing a product means updating every copy. `check.py` verifies that the cards and counts on each listing page match the `/products/` catalog.
- **The `/products/` filter** (`form#filters`) filters cards live using `data-*` attributes and keeps state in the hash via `history.replaceState`. `norm()` makes search ignore whitespace and zero-width characters and maps Thai digits to Arabic digits. Other forms with an `action` (the 404 search) navigate to `#<action>?<non-empty params>`.
- **Motion:** `[data-words]` headings (split into word spans with `Intl.Segmenter`, starting at opacity 0), `[data-count]` numbers, and `.sweep` product images reveal on scroll through a rAF-throttled `getBoundingClientRect` check. Don't switch this back to IntersectionObserver alone, because it never fires for elements the user jumps past (End key, scrollbar drag), which leaves headings invisible. The same check reveals content blocks: `motion()` adds `.rv` to `.grid > *`, `.feats > *`, `.tl > li`, `.rows > li`, and `.contact-grid > *`. Blocks revealed in the same frame get a staggered `--d` delay. After the transition, `.rv`/`.in` and `--d` are removed again, so the elements' own hover transitions work normally. `motion()` also injects a `.shinebox` into card images for the shine sweep. Load-time entrances (hero, `.ph-head`, the `.pd` column, the hero and product image float loops, the primary-button shine) are pure CSS keyframes. The hero image and `h1` animate `transform` only and are never hidden, which protects LCP. Route changes fade `<main>` in via `main.animate()`. Under `prefers-reduced-motion`, nothing moves: a CSS rule kills every keyframe animation and limits transitions to opacity and colour, and forces `transform`/`filter` to `none` on reveal targets. Reveals still fade in, though, and the card shine is skipped. Blocks are first hidden with `.rv-init`, which has no transition, so they don't visibly fade out. On the first load of the static home page (already painted before the script runs), `motion(main, true)` doesn't hide headings or blocks that are already on screen. `check()` reveals everything still pending once the page can't scroll any further (page end, or auto-height preview iframes), and it also runs on `load` and `document.fonts.ready`. `tools/motion-check.html` is a standalone page that tells a site owner whether their device or viewer runs JS and whether reduced motion is on.
- **After in-app navigation**, focus moves to the page `<h1>` (`tabindex="-1"`) for screen readers. Focus is not moved on initial load, so the skip link stays the first Tab stop.
- **LINE CTAs** use `https://line.me/R/oaMessage/%40672xlnwi/?<url-encoded prefilled message>`. Product pages prefill the product name and sizes. These links only open the LINE *phone* app. LINE for PC/Mac doesn't support them, and desktop browsers land on LINE's "download the app" page. So on mouse/desktop devices (`(hover: hover) and (pointer: fine)`), the click handler intercepts every `line.me/R/` link and opens `<dialog id="line-dlg">` instead. That dialog shows a QR of the same chat link, with a shortened message (greeting, sizes, and the "— จากหน้าเว็บ" suffix stripped so the QR stays scannable at an integer 3–4px per module), plus copy, open-in-app (`data-direct`, never intercepted), and phone options. On phones and tablets the link is followed directly. The QR encoder is the vendored, minified `qrcode-generator` 2.0.4 (MIT) in its own `<script>` before the image map. The static `<img data-img="qr">` is the "add friend" code (`line.me/R/ti/p/%40672xlnwi`) and serves as the fallback.

## Content constraints visible in the site

- Wording consistently presents the business as a distributor ("แบรนด์ X · จัดจำหน่ายโดย โปรคลีน ซัพพลาย ไทยแลนด์"), never as the manufacturer.
- The privacy page (`/privacy/`) states that the site uses no cookies and lists Cloudflare, LINE, and Web3Forms as third parties. Update it if you add analytics, cookies, or a form (`/thanks/` exists for a future form but nothing links to it yet).
