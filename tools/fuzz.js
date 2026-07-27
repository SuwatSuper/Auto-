const { chromium } = require('playwright');
const path = require('path');
const file = process.argv[2] || path.join(__dirname,'..','TorLifeOS_v10.html');
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({viewport:{width:1400,height:900}});
  const p = await ctx.newPage();
  const errs=[];
  p.on('pageerror', e=>errs.push('PAGEERROR: '+e.message+'\n'+String(e.stack).split('\n').slice(0,4).join('\n')));
  p.on('dialog', d=>d.dismiss());
  await p.goto('file://'+file); await p.waitForTimeout(800);

  // seed data through the real UI paths
  await p.evaluate(()=>{ window.__toasts=[]; });
  const views=['today','dash','sys','lala','farm','exam','mach','money','funds','biz','stat','cal','health','fam','docs','risk','plan','set'];

  // fill forms
  async function go(v){ await p.click(`aside [data-go="${v}"]`); await p.waitForTimeout(80); }

  await go('lala');
  await p.fill('#llInc','1200'); await p.fill('#llFuel','200'); await p.fill('#llFood','100');
  await p.fill('#llHrs','9'); await p.fill('#llKm','120'); await p.fill('#llJobs','14');
  await p.click('#llEve button[data-v="6"]'); await p.click('#llMor button[data-v="4"]');
  await p.click('#llSave'); await p.waitForTimeout(200);

  await go('farm'); await p.fill('#fmAmt','6000'); await p.fill('#fmItem','ค่าพันธุ์'); await p.click('#fmSave'); await p.waitForTimeout(150);
  await go('exam'); await p.fill('#stHrs','2.5'); await p.click('#stSave'); await p.waitForTimeout(150);
  await go('mach'); await p.fill('#xpName','เทมเพลตภาษี'); await p.fill('#xpCost','500'); await p.fill('#xpChan','Shopee'); await p.click('#xpSave'); await p.waitForTimeout(150);
  await go('money'); await p.fill('#enAmt','1200'); await p.fill('#enItem','ทดสอบ'); await p.click('#enSave'); await p.waitForTimeout(150);
  await go('health'); await p.fill('#hW','58.5'); await p.fill('#hS','6'); await p.fill('#hWt','8'); await p.click('#hSave'); await p.waitForTimeout(150);
  await go('funds'); await p.fill('#bamAmt','4000'); await p.click('#bamPay'); await p.waitForTimeout(150);
  await go('biz'); await p.fill('#acName','ค่าโฆษณา'); await p.fill('#acVal','0'); await p.fill('#acBud','1000'); await p.click('#acAdd'); await p.waitForTimeout(150);
  await p.fill('#bzAmt','800'); await p.fill('#bzItem','ยิงแอด'); await p.click('#bzSave'); await p.waitForTimeout(150);
  await go('docs'); await p.fill('#dcName','พินัยกรรม'); await p.click('#dcAdd'); await p.waitForTimeout(150);
  await go('cal'); await p.fill('#tdName','งานทดสอบ'); await p.click('#tdAdd'); await p.waitForTimeout(150);

  console.log('--- seeded. errors so far:', errs.length);

  // click EVERY actionable element on every view (non-destructive first pass: skip delete/reset)
  const skip = /resetAll|rsBak|rsBak2|impJson|fileIn|avFile|dcFile|printBtn/;
  for (const v of views) {
    await go(v);
    const sels = await p.evaluate((vv)=>{
      const root=document.getElementById('v-'+vv);
      const out=[];
      root.querySelectorAll('button').forEach((el,i)=>{ if(!el.id||!/resetAll|rsBak|impJson|printBtn/.test(el.id)) out.push(i); });
      return out;
    }, v);
    for (const i of sels) {
      try {
        await p.evaluate(({vv,ii})=>{
          const root=document.getElementById('v-'+vv);
          const el=root.querySelectorAll('button')[ii];
          if(!el) return;
          if(el.id && /resetAll|rsBak|rsBak2|impJson|printBtn|expJson|expCsv/.test(el.id)) return;
          el.click();
        }, {vv:v, ii:i});
        await p.waitForTimeout(25);
        // close any modal that opened
        await p.evaluate(()=>{
          ['#dlgBox','#edBox','#docModal','#txtBox'].forEach(s=>{const e=document.querySelector(s); if(e&&e.style.display==='block') e.style.display='none';});
        });
      } catch(e){ }
    }
    await p.waitForTimeout(60);
  }
  console.log('--- clicked all buttons. errors:', errs.length);

  // keyboard shortcuts
  for (const k of ['g','t','g','d','g','m','g','c','g','s','n','Escape','h','Escape','?','Escape','Control+k','Escape']) {
    await p.keyboard.press(k); await p.waitForTimeout(60);
  }
  await p.evaluate(()=>{['#dlgBox','#edBox','#docModal','#txtBox'].forEach(s=>{const e=document.querySelector(s); if(e) e.style.display='none';});});

  // reload -> persistence
  await p.reload({waitUntil:'load'}); await p.waitForTimeout(1200);
  const st = await p.evaluate(()=>{
    const raw = localStorage.getItem('torlifeos:v8');
    const o = JSON.parse(raw);
    return {ledger:o.ledger.length, lala:o.lala.length, farm:o.farm.length, study:o.study.length,
            exps:o.exps.length, bam:o.bam.length, health:o.health.length, docs:o.docs.length,
            ledgerAmts:o.ledger.map(r=>r.a), size:raw.length};
  });
  console.log('--- after reload:', JSON.stringify(st));

  console.log('=== ERRORS ('+errs.length+') ===');
  [...new Set(errs)].forEach(e=>console.log(e));
  await b.close();
})();
