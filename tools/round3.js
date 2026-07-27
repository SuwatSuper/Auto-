const { chromium } = require('playwright');
const path=require('path'),fs=require('fs'),os=require('os');
const file=path.join(__dirname,'..','TorLifeOS_v10.html');
(async()=>{
  const b=await chromium.launch(); const ctx=await b.newContext({acceptDownloads:true});
  const p=await ctx.newPage();
  const errs=[]; p.on('pageerror',e=>errs.push(e.message));
  await p.goto('file://'+file); await p.waitForTimeout(1000);
  const go=async v=>{await p.click(`aside [data-go="${v}"]`);await p.waitForTimeout(100);};

  // A) build a rich dataset, export, wipe, re-import, compare
  await go('lala'); await p.fill('#llInc','1250');await p.fill('#llFuel','210');await p.click('#llSave');await p.waitForTimeout(150);
  await go('money');await p.fill('#enAmt','250');await p.fill('#enItem','ข้าว "เย็น" & น้ำ <ผัก>');await p.click('#enSave');await p.waitForTimeout(150);
  await go('set'); await p.fill('#setName','ระบบของตอ');await p.click('#setNameSave');await p.waitForTimeout(150);
  await p.fill('#csLiving','15500');await p.fill('#csDay','195');await p.click('#csSave');await p.waitForTimeout(300);
  const snapA = await p.evaluate(()=>{const o=JSON.parse(localStorage.getItem('torlifeos:v8'));
    return {ledger:o.ledger.length,lala:o.lala.length,name:o.prof.name,consts:o.consts,item:o.ledger[o.ledger.length-1].n};});
  const [dl]=await Promise.all([p.waitForEvent('download'),p.click('#expJson')]);
  const tmp=path.join(os.tmpdir(),'roundtrip.json'); await dl.saveAs(tmp);
  const exported=JSON.parse(fs.readFileSync(tmp,'utf8'));
  console.log('A) exported keys:',Object.keys(exported).length,'ledger:',exported.ledger.length,'consts:',JSON.stringify(exported.consts));

  await p.evaluate(()=>{localStorage.clear();});
  await p.reload({waitUntil:'load'}); await p.waitForTimeout(1200);
  await go('set');
  await p.setInputFiles('#fileIn',tmp); await p.waitForTimeout(900);
  const snapB = await p.evaluate(()=>{const o=JSON.parse(localStorage.getItem('torlifeos:v8'));
    return {ledger:o.ledger.length,lala:o.lala.length,name:o.prof.name,consts:o.consts,item:o.ledger[o.ledger.length-1].n};});
  console.log('A) before import:',JSON.stringify(snapA));
  console.log('A) after  import:',JSON.stringify(snapB));
  console.log('A) round-trip identical:', JSON.stringify(snapA)===JSON.stringify(snapB));

  // B) 1500 ledger rows -> perf + render sanity
  const t0=Date.now();
  await p.evaluate(()=>{
    const o=JSON.parse(localStorage.getItem('torlifeos:v8'));
    const base=new Date();
    for(let i=0;i<1500;i++){const d=new Date(base);d.setDate(d.getDate()-(i%400));
      o.ledger.push({id:'big'+i,d:d.toISOString().slice(0,10),k:i%3===0?'income':i%3===1?'saving':'expense',
        c:'ค่ากิน',a:(i*7)%900+10,n:'รายการ '+i,note:''});}
    for(let i=0;i<400;i++){const d=new Date(base);d.setDate(d.getDate()-i);
      o.health.push({id:'bh'+i,d:d.toISOString().slice(0,10),w:57+(i%9)*0.3,s:5+(i%5),wt:6+(i%5),cig:i%13,head:i%9===0?1:0,n:''});}
    localStorage.setItem('torlifeos:v8',JSON.stringify(o));
  });
  const page2 = await ctx.newPage(); const e2=[]; page2.on('pageerror',e=>e2.push(e.message));
  const t1=Date.now();
  await page2.goto('file://'+file); await page2.waitForTimeout(200);
  await page2.waitForFunction(()=>document.querySelector('#todayHero .hero'),{timeout:15000});
  console.log('B) first paint with 1900 records:', Date.now()-t1,'ms');
  for(const v of ['today','dash','money','health','stat','sys','cal']){
    const s=Date.now(); await page2.click(`aside [data-go="${v}"]`); await page2.waitForTimeout(50);
    process.stdout.write(`   ${v}=${Date.now()-s}ms`);
  }
  console.log('');
  console.log('B) errors on big dataset:', e2.length? e2 : 'none');
  const st2 = await page2.evaluate(()=>{document.querySelector('aside [data-go="set"]').click();
    document.getElementById('selfTestBtn').click();
    return document.querySelector('#selfTestBox .al div').textContent;});
  console.log('B) self-test on big dataset:', st2);

  // C) rapid clicking (double-submit / race)
  const page3 = await ctx.newPage(); const e3=[]; page3.on('pageerror',e=>e3.push(e.message));
  await page3.goto('file://'+file); await page3.waitForTimeout(1000);
  await page3.click('aside [data-go="money"]');
  const MARK=123457;   // unique amount so pre-seeded bulk rows can't be miscounted
  const c0=await page3.evaluate(m=>JSON.parse(localStorage.getItem('torlifeos:v8')).ledger.filter(r=>r.a===m).length,MARK);
  await page3.fill('#enAmt',String(MARK));
  await page3.evaluate(()=>{const btn=document.getElementById('enSave');btn.click();btn.click();btn.click();});
  await page3.waitForTimeout(500);
  const c1=await page3.evaluate(m=>JSON.parse(localStorage.getItem('torlifeos:v8')).ledger.filter(r=>r.a===m).length,MARK);
  console.log('C) rows created by 3 rapid clicks (1 expected):', c1-c0);
  // rapid view switching
  for(let i=0;i<40;i++) await page3.evaluate(i=>{const v=['today','dash','sys','money','stat','cal'][i%6];
    document.querySelector('aside [data-go="'+v+'"]').click();},i);
  await page3.waitForTimeout(400);
  console.log('C) errors after 40 rapid view switches:', e3.length? e3 : 'none');

  console.log('MAIN PAGE ERRORS:', errs.length? errs : 'none');
  await b.close();
})();
