const { chromium } = require('playwright');
const path = require('path');
const file = path.join(__dirname,'..','TorLifeOS_v10.html');
(async () => {
  const b = await chromium.launch(); const p = await (await b.newContext()).newPage();
  p.on('pageerror', e=>console.log('PAGEERROR:',e.message));
  await p.goto('file://'+file); await p.waitForTimeout(900);
  const out = await p.evaluate(() => {
    const r = {};
    // reproduce the failing selftest manually via UI
    const money = document.querySelector('[data-go="money"]'); money.click();
    const s = document.getElementById('enSearch');
    return { note:'ui ready' };
  });
  // add two ledger rows through the UI
  await p.click('[data-go="money"]');
  await p.fill('#enAmt','50'); await p.fill('#enItem','ข้าวเย็น'); await p.click('#enSave');
  await p.waitForTimeout(200);
  await p.click('[data-go="money"]');
  await p.selectOption('#enCat','อาหารแมว').catch(()=>{});
  await p.fill('#enAmt','300'); await p.fill('#enItem','ซื้อเม็ด'); await p.click('#enSave');
  await p.waitForTimeout(200);
  await p.fill('#enSearch','แมว');
  await p.waitForTimeout(300);
  const html = await p.evaluate(()=>document.getElementById('enTable').innerHTML);
  console.log('--- filtered table (search=แมว) ---');
  console.log(html.slice(0,1200));
  console.log('contains literal อาหารแมว :', html.includes('อาหารแมว'));
  console.log('contains ข้าวเย็น        :', html.includes('ข้าวเย็น'));
  console.log('contains ซื้อเม็ด        :', html.includes('ซื้อเม็ด'));
  await b.close();
})();
