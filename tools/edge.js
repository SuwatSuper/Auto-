const { chromium } = require('playwright');
const path=require('path'); const file=path.join(__dirname,'..','TorLifeOS_v10.html');
const iso=d=>d.toISOString().slice(0,10);
(async()=>{
  const b=await chromium.launch(); const p=await (await b.newContext()).newPage();
  p.on('pageerror',e=>console.log('PAGEERROR:',e.message));
  await p.goto('file://'+file); await p.waitForTimeout(900);

  const r = await p.evaluate(()=>{
    const out={};
    const S=s=>document.querySelector(s);
    // reach into the closure via a rendered artefact instead: use UI + localStorage
    return out;
  });

  // A) future-dated health record pollutes rolling windows
  await p.click('aside [data-go="health"]'); await p.waitForTimeout(150);
  const future = await p.evaluate(()=>{const d=new Date();d.setDate(d.getDate()+120);return d.toISOString().slice(0,10);});
  await p.fill('#hDate', future); await p.fill('#hS','1'); await p.fill('#hW','99'); await p.click('#hSave');
  await p.waitForTimeout(300);
  const hstat = await p.evaluate(()=>document.getElementById('hStat').innerText.replace(/\n+/g,' | '));
  console.log('A) health 30-day panel with a record dated +120 days:');
  console.log('   ', hstat.slice(0,220));

  // B) delete a fund that a saving-ledger row points at
  await p.click('aside [data-go="money"]'); await p.waitForTimeout(150);
  await p.click('#enSeg button[data-k="saving"]'); await p.waitForTimeout(120);
  await p.fill('#enAmt','5000');
  await p.selectOption('#enFund', {index:1});
  await p.click('#enSave'); await p.waitForTimeout(250);
  const fundsAfter = await p.evaluate(()=>JSON.parse(localStorage.getItem('torlifeos:v8')).funds.map(f=>f.id+'='+f.v).join(','));
  console.log('B) funds after logging 5000 saving ->', fundsAfter);

  // C) repeated todo checkbox on a FUTURE month occurrence
  const c = await p.evaluate(()=>{
    const raw=JSON.parse(localStorage.getItem('torlifeos:v8'));
    return raw.todos.filter(t=>t.rep).map(t=>t.id+':'+t.due).join(' , ');
  });
  console.log('C) repeating todos ->', c);

  // D) import round trip: export then re-import
  await p.click('aside [data-go="set"]'); await p.waitForTimeout(150);
  const before = await p.evaluate(()=>{const o=JSON.parse(localStorage.getItem('torlifeos:v8'));
    return {ledger:o.ledger.length,health:o.health.length,funds:o.funds.map(f=>f.v).join('/')}; });
  console.log('D) before export ->', JSON.stringify(before));

  // E) thDate with a broken month
  console.log('E) rendering with malformed dates...');
  await p.evaluate(()=>{
    const o=JSON.parse(localStorage.getItem('torlifeos:v8'));
    o.ledger.push({id:'bad1',d:'2026-13-45',k:'expense',c:'ค่ากิน',a:10,n:'วันที่พัง',note:''});
    o.ledger.push({id:'bad2',d:'',k:'expense',c:'ค่ากิน',a:10,n:'ไม่มีวันที่',note:''});
    o.health.push({id:'bad3',d:'ไม่ใช่วันที่',w:1,s:1,wt:1,cig:0,head:0,n:''});
    localStorage.setItem('torlifeos:v8',JSON.stringify(o));
  });
  await p.reload({waitUntil:'load'}); await p.waitForTimeout(1400);
  for (const v of ['today','dash','money','health','stat','cal','sys']) {
    await p.click(`aside [data-go="${v}"]`); await p.waitForTimeout(150);
  }
  const undef = await p.evaluate(()=>{
    const t=document.body.innerText;
    return {undefinedCount:(t.match(/undefined/g)||[]).length, nanCount:(t.match(/NaN/g)||[]).length};
  });
  console.log('E) after malformed dates ->', JSON.stringify(undef));
  const st = await p.evaluate(()=>{
    document.getElementById('selfTestBtn')&&null;
    document.querySelector('aside [data-go="set"]').click();
    document.getElementById('selfTestBtn').click();
    return document.querySelector('#selfTestBox .al div').textContent;
  });
  console.log('E) self-test ->', st);
  await b.close();
})();
