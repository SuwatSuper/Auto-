const { chromium } = require('playwright');
const path=require('path'),fs=require('fs'),os=require('os');
const src=fs.readFileSync(path.join(__dirname,'..','TorLifeOS_v10.html'),'utf8');
const noFont=path.join(os.tmpdir(),'nofont.html');
fs.writeFileSync(noFont, src.replace(/<link href="https:\/\/fonts\.googleapis[^>]*>/,''));
(async()=>{
  const b=await chromium.launch();
  for (const [label,f] of [['with Google Fonts link', path.join(__dirname,'..','TorLifeOS_v10.html')],
                           ['without font link', noFont]]){
    const ctx=await b.newContext(); const p=await ctx.newPage();
    await p.addInitScript(()=>{window.__t0=Date.now();});
    const t=Date.now();
    await p.goto('file://'+f);
    await p.waitForFunction(()=>{const h=document.querySelector('#todayHero .hero');
      return h && h.getBoundingClientRect().height>0;},{timeout:60000});
    console.log(label.padEnd(26), Date.now()-t, 'ms to visible content');
    await ctx.close();
  }
  // triple click check
  const ctx=await b.newContext(); const p=await ctx.newPage();
  await p.goto('file://'+noFont); await p.waitForTimeout(800);
  await p.click('aside [data-go="money"]'); await p.waitForTimeout(150);
  await p.fill('#enAmt','77');
  const r = await p.evaluate(()=>{
    const btn=document.getElementById('enSave');
    btn.click(); btn.click(); btn.click();   // three real, synchronous clicks
    return JSON.parse(localStorage.getItem('torlifeos:v8')||'{}');
  });
  await p.waitForTimeout(400);
  console.log('3 synchronous clicks on save -> rows with a=77:',
    await p.evaluate(()=>JSON.parse(localStorage.getItem('torlifeos:v8')).ledger.filter(x=>x.a===77).length));
  await b.close();
})();
