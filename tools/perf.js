const { chromium } = require('playwright');
const path=require('path'); const file=path.join(__dirname,'..','TorLifeOS_v10.html');
(async()=>{
  const b=await chromium.launch(); const ctx=await b.newContext(); const p=await ctx.newPage();
  await p.goto('file://'+file); await p.waitForTimeout(1200);
  for (const N of [0, 700, 1900]) {
    await p.evaluate((n)=>{
      const o=JSON.parse(localStorage.getItem('torlifeos:v8'));
      o.ledger=o.ledger.filter(r=>!/^big/.test(r.id)); o.health=o.health.filter(r=>!/^bh/.test(r.id));
      const base=new Date();
      for(let i=0;i<n;i++){const d=new Date(base);d.setDate(d.getDate()-(i%400));
        o.ledger.push({id:'big'+i,d:d.toISOString().slice(0,10),k:'expense',c:'ค่ากิน',a:99,n:'x'+i,note:''});}
      for(let i=0;i<Math.round(n/4);i++){const d=new Date(base);d.setDate(d.getDate()-i);
        o.health.push({id:'bh'+i,d:d.toISOString().slice(0,10),w:58,s:7,wt:8,cig:0,head:0,n:''});}
      localStorage.setItem('torlifeos:v8',JSON.stringify(o));
    }, N);
    const pg = await ctx.newPage();
    await pg.addInitScript(()=>{ window.__marks={}; window.__t0=Date.now(); });
    await pg.goto('file://'+file);
    await pg.waitForFunction(()=>document.querySelector('#todayHero .hero'),{timeout:60000});
    const paint = await pg.evaluate(()=>Date.now()-window.__t0);
    const testMs = await pg.evaluate(()=>{const s=Date.now();
      document.querySelector('aside [data-go="set"]').click();
      document.getElementById('selfTestBtn').click(); return Date.now()-s;});
    const recs = await pg.evaluate(()=>{const o=JSON.parse(localStorage.getItem('torlifeos:v8'));return o.ledger.length+o.health.length;});
    console.log(`records=${String(recs).padStart(5)}  time-to-interactive=${String(paint).padStart(6)}ms   selfTest=${String(testMs).padStart(6)}ms`);
    await pg.close();
  }
  await b.close();
})();
