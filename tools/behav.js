const { chromium } = require('playwright');
const path=require('path'); const file=path.join(__dirname,'..','TorLifeOS_v10.html');
(async()=>{
  const b=await chromium.launch(); const ctx=await b.newContext({acceptDownloads:true});
  const p=await ctx.newPage();
  const csp=[]; p.on('console',m=>{ if(/Refused|Content Security/i.test(m.text())) csp.push(m.text()); });
  p.on('pageerror',e=>console.log('PAGEERROR:',e.message));
  await p.goto('file://'+file); await p.waitForTimeout(900);

  // 1) download / backup under CSP
  await p.click('aside [data-go="set"]'); await p.waitForTimeout(150);
  let dl=null;
  try { const [d]=await Promise.all([p.waitForEvent('download',{timeout:4000}), p.click('#expJson')]); dl=d.suggestedFilename(); }
  catch(e){ dl='FAILED: '+e.message.split('\n')[0]; }
  console.log('backup JSON download ->', dl);
  let dl2=null;
  try { const [d]=await Promise.all([p.waitForEvent('download',{timeout:4000}), p.click('#expCsv')]); dl2=d.suggestedFilename(); }
  catch(e){ dl2='FAILED: '+e.message.split('\n')[0]; }
  console.log('CSV download ->', dl2);

  // 2) nightNote wiped when clicking a SAVERS / q3 button
  await p.click('aside [data-go="today"]'); await p.waitForTimeout(200);
  await p.fill('#nightNote','ข้อความที่พิมพ์ไว้ยังไม่ได้กดปิดวัน');
  await p.click('#saversBox button[data-sav="S"]'); await p.waitForTimeout(250);
  console.log('nightNote after SAVERS click ->', JSON.stringify(await p.inputValue('#nightNote')));
  await p.fill('#nightNote','พิมพ์อีกรอบ');
  await p.click('#nightBox button[data-q3="q1"]'); await p.waitForTimeout(250);
  console.log('nightNote after Q3 click   ->', JSON.stringify(await p.inputValue('#nightNote')));

  // 3) search caret position
  await p.click('aside [data-go="money"]'); await p.waitForTimeout(150);
  await p.fill('#enSearch','abcdef');
  await p.evaluate(()=>{const e=document.getElementById('enSearch'); e.focus(); e.setSelectionRange(3,3);});
  await p.keyboard.type('X'); await p.waitForTimeout(200);
  console.log('search value after typing X at pos3 ->', JSON.stringify(await p.inputValue('#enSearch')),
    'caret:', await p.evaluate(()=>document.getElementById('enSearch').selectionStart));

  // 4) health record for a FUTURE date counted in "30 days"
  const fut = await p.evaluate(()=>{
    const d=new Date(); d.setDate(d.getDate()+200);
    const iso=d.toISOString().slice(0,10);
    return iso;
  });
  console.log('future date used:', fut);

  console.log('CSP violations:', csp.length ? csp : 'none');
  await b.close();
})();
