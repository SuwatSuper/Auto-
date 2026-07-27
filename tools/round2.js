const { chromium } = require('playwright');
const path=require('path'); const file=path.join(__dirname,'..','TorLifeOS_v10.html');
(async()=>{
  const b=await chromium.launch(); const ctx=await b.newContext({acceptDownloads:true});
  const p=await ctx.newPage();
  const errs=[]; p.on('pageerror',e=>errs.push(e.message+' :: '+String(e.stack).split('\n')[1]));
  await p.goto('file://'+file); await p.waitForTimeout(1000);
  const go=async v=>{await p.click(`aside [data-go="${v}"]`);await p.waitForTimeout(100);};

  // seed one row per module
  await go('lala'); await p.fill('#llInc','1200');await p.fill('#llFuel','200');await p.fill('#llFood','100');
  await p.click('#llEve button[data-v="6"]');await p.click('#llSave');await p.waitForTimeout(200);
  await go('farm'); await p.fill('#fmAmt','6000');await p.fill('#fmItem','ค่าพันธุ์');await p.click('#fmSave');await p.waitForTimeout(150);
  await go('exam'); await p.fill('#stHrs','2.5');await p.click('#stSave');await p.waitForTimeout(150);
  await go('health');await p.fill('#hS','7');await p.fill('#hW','58');await p.click('#hSave');await p.waitForTimeout(150);
  await go('funds');await p.fill('#bamAmt','4000');await p.click('#bamPay');await p.waitForTimeout(150);
  await go('money');await p.fill('#enAmt','250');await p.fill('#enItem','ข้าวเย็น');await p.click('#enSave');await p.waitForTimeout(150);
  await go('mach');await p.fill('#xpName','เทมเพลต');await p.fill('#xpCost','500');await p.click('#xpSave');await p.waitForTimeout(150);

  // ---- exercise EVERY edit (✎) dialog: open, change a value, save
  const edits=[['money','#enTable','[data-enedit]'],['lala','#llTable','[data-lledit]'],
    ['farm','#fmTable','[data-fmedit]'],['exam','#stTable','[data-stedit]'],
    ['health','#hTable','[data-hedit]'],['funds','#bamTable','[data-bamedit]'],
    ['risk','#riskList','[data-rkedit]'],['docs','#docList','[data-dcedit]'],
    ['mach','#xpList','[data-xpedit]']];
  for (const [v,box,sel] of edits){
    await go(v);
    if (v==='mach') await p.evaluate(()=>document.querySelectorAll('#xpList details').forEach(d=>d.open=true));
    const n = await p.evaluate(([bx,s])=>document.querySelectorAll(bx+' '+s).length,[box,sel]);
    if(!n){ console.log('  (no rows for', v, sel, ')'); continue; }
    await p.evaluate(([bx,s])=>document.querySelector(bx+' '+s).click(),[box,sel]);
    await p.waitForTimeout(150);
    const open = await p.evaluate(()=>document.getElementById('edBox').style.display==='block');
    if(!open){ console.log('  EDIT DIALOG DID NOT OPEN for', v, sel); continue; }
    const fields = await p.evaluate(()=>Array.from(document.querySelectorAll('#edFields [data-ef]')).map(e=>e.dataset.ef+':'+e.tagName));
    await p.click('#edOk'); await p.waitForTimeout(200);
    const err = await p.evaluate(()=>document.getElementById('edErr').textContent);
    const stillOpen = await p.evaluate(()=>document.getElementById('edBox').style.display==='block');
    console.log(`  edit ${v.padEnd(7)} fields=${fields.length} saved=${!stillOpen}${err?' err="'+err+'"':''}`);
    if(stillOpen) await p.click('#edCancel');
  }

  // (recurring-todo coverage lives in tools/recur.js — injecting localStorage here is
  //  overwritten by the app's own beforeunload save, so it must be driven through the UI)

  // ---- theme + palette + drawer
  await go('set');
  for(const th of ['dark','auto','light']){ await p.click(`#thSeg button[data-th="${th}"]`); await p.waitForTimeout(120); }
  await p.keyboard.press('Control+k'); await p.waitForTimeout(200);
  await p.fill('#cmdInput','สวน'); await p.waitForTimeout(150);
  await p.keyboard.press('Enter'); await p.waitForTimeout(250);
  console.log('palette navigated to:', await p.evaluate(()=>document.getElementById('vTitle').textContent));

  console.log('ERRORS:', errs.length? errs : 'none');
  await b.close();
})();
