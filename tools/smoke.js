// Browser smoke test for index.html (needs the `playwright` package + Chromium).
// Usage: node tools/smoke.js [path/to/index.html]
const { chromium } = require("playwright");
const fs = require("fs");
const http = require("http");

const file = process.argv[2] || "index.html";
const url = "http://127.0.0.1:8787/";
const fails = [];
const expect = (ok, msg) => { if (!ok) fails.push(msg); };
// Run one scenario; a thrown error (e.g. missing element) is reported as a failure, not a crash
const step = async (name, fn) => { try { await fn(); } catch (e) { fails.push(`${name}: ${e.message.split("\n")[0]}`); } };

(async () => {
  // Serve over HTTP like a real host (file:// blocks new-tab navigation in Chromium)
  const server = http.createServer((req, res) => {
    if (req.url !== "/") { res.writeHead(404); return res.end(); }
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    res.end(fs.readFileSync(file));
  });
  await new Promise((ok) => server.listen(8787, "127.0.0.1", ok));
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 375, height: 740 } });
  const page = await ctx.newPage();
  page.setDefaultTimeout(3000);
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const hash = () => page.evaluate(() => decodeURIComponent(location.hash));
  const go = async (h) => { await page.goto("about:blank"); await page.goto(url + h); await page.waitForTimeout(120); };

  // Every route renders: one h1, all images hydrated, no horizontal scroll on a phone
  let routes = [];
  await step("routes", async () => {
    await go("");
    routes = await page.evaluate(() => [...document.querySelectorAll("template[data-route]")].map((t) => t.dataset.route));
    for (const r of routes) {
      await page.evaluate((r) => { location.hash = "#" + r; }, r);
      await page.waitForTimeout(60);
      const s = await page.evaluate(() => ({
        h1: document.querySelectorAll("main h1").length,
        noSrc: [...document.querySelectorAll("img")].filter((i) => !i.getAttribute("src")).length,
        overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      }));
      expect(s.h1 === 1 && !s.noSrc && !s.overflow, `${r}: ${JSON.stringify(s)}`);
    }
  });

  // Internal links are rewritten to #/ so new-tab / copy-link work on single-file hosting
  await step("links", async () => {
    await go("");
    expect(await page.evaluate(() => !document.querySelector('a[href^="/"]:not([href^="//"])')), "internal links not rewritten to #/");
    const [tab] = await Promise.all([
      ctx.waitForEvent("page", { timeout: 2000 }).catch(() => null),
      page.click('.cat[href$="/categories/bathroom/"]', { modifiers: ["Control"] }),
    ]);
    if (tab) await tab.waitForURL(/#\/categories\/bathroom\/$/).catch(() => {});
    expect(tab && tab.url().endsWith("#/categories/bathroom/"), "ctrl-click did not open the route in a new tab: " + (tab && tab.url()));
    expect((await hash()) === "", "ctrl-click navigated the current tab");
    if (tab) await tab.close();
  });

  // Filters: deep link, live search, Enter keeps scroll position and a clean URL
  await step("filters", async () => {
    await go("#/products/?brand=riverra");
    expect((await page.textContent("#count")) === "พบ 4 รายการ", "deep-link brand filter");
    await page.fill("input[name=q]", "ถู พื้น");
    expect((await page.textContent("#count")) === "พบ 1 รายการ", "live search");
    await page.evaluate(() => window.scrollTo(0, 300));
    await page.press("input[name=q]", "Enter");
    await page.waitForTimeout(150);
    expect((await page.evaluate(() => scrollY)) === 300, "Enter in search re-rendered the page");
    expect((await hash()) === "#/products/?q=ถู พื้น&brand=riverra".replace(" ", "+"), "filter URL: " + (await hash()));
    await page.fill("input[name=q]", "zzzz");
    expect(await page.isVisible("#empty"), "empty state not shown");
  });

  // 404 search form navigates to the catalog without empty params
  await step("404 search", async () => {
    await go("#/no-such-page/");
    await page.fill("main input[name=q]", "กระจก");
    await page.click("main button[type=submit]");
    await page.waitForTimeout(120);
    expect((await hash()) === "#/products/?q=กระจก", "404 search URL: " + (await hash()));
  });

  // Scroll-reveal headings must not stay invisible when the user jumps past them
  await step("reveal", async () => {
    await go("#/services/");
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(800);
    expect(await page.evaluate(() => document.getElementById("band-h").classList.contains("in")), "band heading never revealed after jump");
  });

  // Scroll-reveal blocks (.rv) must all end up visible and cleaned up, even after a jump
  await step("block reveal", async () => {
    await go("");
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(2300);
    expect(await page.evaluate(() => document.querySelectorAll("main .rv").length === 0), "some .rv blocks never revealed");
    expect(await page.evaluate(() => [...document.querySelectorAll("main .grid > *, main .tl > li")].every((e) => getComputedStyle(e).opacity === "1")), "revealed blocks not fully opaque");
  });

  // Reduced motion: movement removed (no rise/float/sweep/transform), gentle opacity fades kept, nothing left hidden
  await step("reduced motion", async () => {
    const rctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, reducedMotion: "reduce" });
    const rp = await rctx.newPage();
    await rp.goto(url);
    expect(await rp.evaluate(() => getComputedStyle(document.querySelector(".lineup > img")).animationName === "none"), "hero float runs under reduced motion");
    expect(await rp.evaluate(() => !document.querySelector(".card .shinebox")), "light sweep injected under reduced motion");
    expect(await rp.evaluate(() => [...document.querySelectorAll(".rv, .w")].every((e) => getComputedStyle(e).transform === "none")), "reveal moves elements under reduced motion");
    await rp.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await rp.waitForTimeout(1500);
    expect(await rp.evaluate(() => !document.querySelector("main .rv:not(.in)")), "content left hidden under reduced motion");
    await rctx.close();
  });

  // Filtering moves cards into view without a scroll: they must be revealed, not left at opacity 0
  await step("filter reveal", async () => {
    for (const reducedMotion of ["no-preference", "reduce"]) {
      const fctx = await browser.newContext({ viewport: { width: 1366, height: 800 }, reducedMotion });
      const fp = await fctx.newPage();
      await fp.goto(url + "#/products/");
      await fp.waitForTimeout(800);
      await fp.selectOption("select[name=brand]", "riverra");
      await fp.waitForTimeout(1500);
      const stuck = await fp.evaluate(() => [...document.querySelectorAll("[data-pid]:not([hidden])")]
        .filter((c) => c.getBoundingClientRect().top < innerHeight && getComputedStyle(c).opacity === "0").length);
      expect(stuck === 0, `filter (${reducedMotion}): ${stuck} matching cards left invisible`);
      await fctx.close();
    }
  });

  // Print / Save as PDF must not drop anything the reveal state hides
  await step("print", async () => {
    await go("");
    await page.emulateMedia({ media: "print" });
    const hidden = await page.evaluate(() => [...document.querySelectorAll("main .rv, main .rv img, main .w")]
      .filter((e) => getComputedStyle(e).opacity === "0").length);
    expect(hidden === 0, `print: ${hidden} elements invisible`);
    await page.emulateMedia({ media: "screen" });
  });

  // First load of the home page is painted before the script runs: blocks already on screen must not be hidden again
  await step("no first-paint flicker", async () => {
    const tctx = await browser.newContext({ viewport: { width: 1280, height: 1500 } });
    const tp = await tctx.newPage();
    await tp.goto(url);
    expect(await tp.evaluate(() => !document.querySelector(".cat").classList.contains("rv")), "on-screen category tile re-hidden after first paint");
    expect(await tp.evaluate(() => !document.querySelector(".facts-row [data-count]").matches(".counting") && document.querySelector(".facts-row [data-count]").textContent === "17"), "on-screen count reset after first paint");
    await tctx.close();
  });

  // Focus moves to the new page heading after navigation
  await step("focus", async () => {
    await go("");
    // wait for the scroll-reveal to finish so the link is stable before clicking
    await page.locator('.rows a[href$="/industries/hotel/"]').scrollIntoViewIfNeeded();
    await page.waitForFunction(() => !document.querySelector('.rows a[href$="/industries/hotel/"]').closest("li").classList.contains("rv"), null, { timeout: 5000 });
    await page.click('.rows a[href$="/industries/hotel/"]');
    await page.waitForTimeout(120);
    expect(await page.evaluate(() => document.activeElement.tagName === "H1"), "focus not moved to h1");
  });

  // Skip link focuses <main> without dropping the current route
  await step("skip link", async () => {
    await go("#/about/");
    await page.keyboard.press("Tab");
    await page.keyboard.press("Enter");
    expect((await hash()) === "#/about/", "skip link changed the route");
    expect(await page.evaluate(() => document.activeElement.id === "main"), "skip link did not focus main");
  });

  // Mobile menu closes on link, outside click and Escape
  await step("menu", async () => {
    await go("");
    await page.click(".menu summary");
    await page.mouse.click(20, 650);
    expect(await page.evaluate(() => !document.querySelector("details.menu[open]")), "menu stayed open after outside click");
    await page.click(".menu summary");
    await page.keyboard.press("Escape");
    expect(await page.evaluate(() => !document.querySelector("details.menu[open]")), "menu stayed open after Escape");
    await page.click(".menu summary");
    await page.click('.menu a[href$="/about/"]');
    await page.waitForTimeout(120);
    expect((await page.title()).startsWith("เกี่ยวกับเรา") && (await page.evaluate(() => !document.querySelector("details.menu[open]"))), "menu link");
  });

  // LINE links only work in the LINE phone app; on a desktop they must open the QR dialog
  // instead of navigating to LINE's "download the app" page
  await step("line desktop", async () => {
    const dctx = await browser.newContext({ viewport: { width: 1366, height: 768 } });
    const dp = await dctx.newPage();
    dp.setDefaultTimeout(3000);
    dp.on("pageerror", (e) => errors.push(e.message));
    let lineHits = 0;
    await dp.route("https://line.me/**", (r) => { lineHits++; r.fulfill({ body: "line" }); });
    await dp.goto(url + "#/products/biomate-floor-buff/");
    const href = await dp.getAttribute(".quote .btn--pri", "href");
    await dp.click(".quote .btn--pri");
    expect(await dp.evaluate(() => document.getElementById("line-dlg").open), "desktop LINE click did not open the dialog");
    expect(lineHits === 0, "desktop LINE click navigated to line.me");
    expect(await dp.isVisible("#dlg-qr svg"), "dialog QR not rendered");
    expect((await dp.textContent("#dlg-msg")) === "ขอใบเสนอราคา: BIOMATE ผลิตภัณฑ์ปั่นเงาพื้น", "dialog message: " + (await dp.textContent("#dlg-msg")));
    expect((await dp.getAttribute("#dlg-open", "href")) === href, "open-in-app link differs from the button link");
    const mail = decodeURIComponent(await dp.getAttribute("#dlg-mail", "href"));
    expect(mail === "mailto:suwat10928@gmail.com?subject=ขอใบเสนอราคา: BIOMATE ผลิตภัณฑ์ปั่นเงาพื้น", "dialog email link: " + mail);
    await dp.keyboard.press("Escape");
    expect(!(await dp.evaluate(() => document.getElementById("line-dlg").open)), "Escape did not close the dialog");
    await dctx.close();
  });

  // On phones the same link goes straight to LINE (the app opens via universal/app link)
  await step("line mobile", async () => {
    const mctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
    const mp = await mctx.newPage();
    mp.setDefaultTimeout(3000);
    await mp.route("https://line.me/**", (r) => r.fulfill({ body: "line" }));
    await mp.goto(url + "#/products/biomate-floor-buff/");
    await mp.tap(".quote .btn--pri");
    await mp.waitForURL(/^https:\/\/line\.me\/R\/oaMessage\//);
    await mctx.close();
  });

  expect(!errors.length, "page errors: " + errors.join("; "));
  await browser.close();
  server.close();
  console.log(`${routes.length} routes checked`);
  fails.forEach((f) => console.log("FAIL", f));
  process.exit(fails.length ? 1 : 0);
})();
