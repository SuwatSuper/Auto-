const { chromium } = require('playwright');
const path=require('path'); const file=path.join(__dirname,'..','TorLifeOS_v10.html');
(async()=>{
  const b=await chromium.launch(); const ctx=await b.newContext(); const p=await ctx.newPage();
  p.on('pageerror',e=>console.log('PAGEERROR:',e.message));
  await p.goto('file://'+file); await p.waitForTimeout(900);

  // user customises the plan constants
  await p.click('aside [data-go="set"]'); await p.waitForTimeout(200);
  await p.fill('#csLiving','17500'); await p.fill('#csDay','250');
  await p.fill('#csStudy','14');     await p.fill('#csXcap','8000');
  await p.fill('#csGsl','120000');   await p.fill('#csEng','45000');
  await p.click('#csSave'); await p.waitForTimeout(400);
  console.log('saved consts  ->', await p.evaluate(()=>JSON.parse(localStorage.getItem('torlifeos:v8')).consts));

  // reload the app, like the user opening it the next day
  await p.reload({waitUntil:'load'}); await p.waitForTimeout(1500);
  console.log('shown in UI after reload ->', await p.evaluate(()=>{
    document.querySelector('aside [data-go="set"]').click();
    return {LIVING:csLivingV(), };
    function csLivingV(){return document.getElementById('csLiving').value;}
  }));
  const after = await p.evaluate(()=>{
    document.querySelector('aside [data-go="set"]').click();
    return {LIVING:+document.getElementById('csLiving').value, DAY:+document.getElementById('csDay').value,
            STUDY:+document.getElementById('csStudy').value, XCAP:+document.getElementById('csXcap').value,
            GSL:+document.getElementById('csGsl').value, ENG:+document.getElementById('csEng').value};
  });
  console.log('UI values after reload ->', after);
  // trigger any save (visiting statements page writes db.consts)
  await p.click('aside [data-go="stat"]'); await p.waitForTimeout(600);
  console.log('localStorage consts now ->', await p.evaluate(()=>JSON.parse(localStorage.getItem('torlifeos:v8')).consts));
  await b.close();
})();
