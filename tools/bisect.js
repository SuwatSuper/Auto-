const { chromium } = require('playwright');
const path=require('path'),fs=require('fs'),os=require('os');
const orig=fs.readFileSync(path.join(__dirname,'..','TorLifeOS_v10.html'),'utf8');
const LINK=/<link href="https:\/\/fonts\.googleapis[^>]*>/;
const variants={
  'as-is (media=print)': orig,
  'no font link at all': orig.replace(LINK,''),
  'no link + no preconnect': orig.replace(LINK,'').replace(/<link rel="preconnect"[^>]*>/g,''),
  'injected from JS after init': orig.replace(LINK,'').replace(
     '<style>', '<style id="__fontslot">/* fonts injected at runtime */\n'),
};
(async()=>{
  const b=await chromium.launch();
  for (const [label,html] of Object.entries(variants)){
    const f=path.join(os.tmpdir(),'v'+Buffer.from(label).toString('hex').slice(0,8)+'.html');
    fs.writeFileSync(f,html);
    const ctx=await b.newContext(); const p=await ctx.newPage();
    const t=Date.now();
    await p.goto('file://'+f);
    await p.waitForFunction(()=>{const h=document.querySelector('#todayHero .hero');
      return h&&h.getBoundingClientRect().height>0;},{timeout:60000}).catch(()=>{});
    console.log(label.padEnd(30), Date.now()-t,'ms');
    await ctx.close();
  }
  await b.close();
})();
