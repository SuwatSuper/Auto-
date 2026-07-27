const { chromium } = require('playwright');
const path = require('path');
const file = process.argv[2] || path.join(__dirname,'..','TorLifeOS_v10.html');

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport:{width:1400,height:900} });
  const page = await ctx.newPage();
  const errors = [], console_msgs = [], csp = [];
  page.on('pageerror', e => errors.push('PAGEERROR: '+e.message));
  page.on('console', m => {
    const t = m.text();
    if (m.type()==='error') { console_msgs.push('CONSOLE.'+m.type()+': '+t); }
    if (/Content Security Policy|Refused to/i.test(t)) csp.push(t);
  });
  await page.goto('file://'+file, { waitUntil:'load' });
  await page.waitForTimeout(1500);

  // run self-test explicitly and scrape results
  const res = await page.evaluate(() => {
    document.getElementById('selfTestBtn').click();
    const box = document.getElementById('selfTestBox');
    const rows = Array.from(box.querySelectorAll('tr')).map(tr => {
      const tds = tr.querySelectorAll('td');
      return { pass: tds[0].textContent.trim()==='ผ่าน', name: tds[1].textContent.trim(), note: tds[2].textContent.trim() };
    });
    return { head: box.querySelector('.al div') ? box.querySelector('.al div').textContent : '', rows };
  });
  console.log('=== SELF-TEST ===');
  console.log(res.head);
  res.rows.filter(r=>!r.pass).forEach(r=>console.log('  FAIL:', r.name, '|', r.note));
  console.log('total checks:', res.rows.length, 'failed:', res.rows.filter(r=>!r.pass).length);

  // visit every view
  const views = await page.evaluate(()=>Array.from(document.querySelectorAll('.view')).map(v=>v.id.replace('v-','')));
  for (const v of views) {
    await page.evaluate(k => { document.querySelector('[data-go="'+k+'"]').click(); }, v);
    await page.waitForTimeout(120);
  }
  console.log('=== visited views:', views.join(','));

  await page.waitForTimeout(600);
  console.log('=== PAGE ERRORS ==='); errors.forEach(e=>console.log(' ', e));
  console.log('=== CONSOLE ERRORS ==='); [...new Set(console_msgs)].forEach(e=>console.log(' ', e));
  await browser.close();
})();
