# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Thai-language B2B catalog site for **โปรคลีน ซัพพลาย ไทยแลนด์ (PROCLEAN SUPPLY THAILAND)**, a distributor (not a manufacturer) of cleaning concentrates from the BIOMATE, SAFECO, and RIVERRA brands. There is no backend and no checkout. Every call to action goes to LINE (`@672xlnwi`) or phone (`tel:+66811764104`).

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
- **Motion:** `[data-words]` headings (split into word spans with `Intl.Segmenter`, starting at opacity 0), `[data-count]` numbers, and `.sweep` product images reveal on scroll through a rAF-throttled `getBoundingClientRect` check. Don't switch this back to IntersectionObserver alone, because it never fires for elements the user jumps past (End key, scrollbar drag), which leaves headings invisible. Motion is skipped under `prefers-reduced-motion`.
- **After in-app navigation**, focus moves to the page `<h1>` (`tabindex="-1"`) for screen readers. Focus is not moved on initial load, so the skip link stays the first Tab stop.
- **LINE CTAs** use `https://line.me/R/oaMessage/%40672xlnwi/?<url-encoded prefilled message>`. Product pages prefill the product name and sizes.

## Content constraints visible in the site

- Wording consistently presents the business as a distributor ("แบรนด์ X · จัดจำหน่ายโดย โปรคลีน ซัพพลาย ไทยแลนด์"), never as the manufacturer.
- The privacy page (`/privacy/`) states that the site uses no cookies and lists Cloudflare, LINE, and Web3Forms as third parties. Update it if you add analytics, cookies, or a form (`/thanks/` exists for a future form but nothing links to it yet).
