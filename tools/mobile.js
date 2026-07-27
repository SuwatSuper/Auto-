const { chromium, devices } = require('playwright');
const path=require('path'); const file=path.join(__dirname,'..','TorLifeOS_v10.html');
(async()=>{
  const b=await chromium.launch();
  const ctx=await b.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true,deviceScaleFactor:3});
  const p=await ctx.newPage();
  p.on('pageerror',e=>console.log('PAGEERROR:',e.message));
  await p.goto('file://'+file); await p.waitForTimeout(1200);
  // horizontal overflow check on every view
  const views=['today','dash','sys','lala','farm','exam','mach','money','funds','biz','stat','cal','health','fam','docs','risk','plan','set'];
  for (const v of views){
    await p.evaluate(k=>{document.querySelector('#mobileBar [data-go="'+k+'"]')?.click();
      document.querySelector('#drawerNav [data-go="'+k+'"]')?.click();}, v);
    await p.waitForTimeout(120);
    const o = await p.evaluate(()=>({sw:document.documentElement.scrollWidth, cw:document.documentElement.clientWidth,
      offenders: Array.from(document.querySelectorAll('#app *')).filter(e=>e.getBoundingClientRect().right > window.innerWidth+2)
        .slice(0,3).map(e=>e.tagName+'.'+(e.className&&e.className.baseVal===undefined?String(e.className).slice(0,30):''))}));
    if (o.sw > o.cw+1) console.log('OVERFLOW on', v, o.sw, '>', o.cw, o.offenders);
  }
  console.log('mobile drawer reachable pages:', await p.evaluate(()=>document.querySelectorAll('#drawerNav [data-go]').length));
  console.log('done');
  await b.close();
})();
