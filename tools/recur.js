const { chromium } = require('playwright');
const path=require('path'); const file=path.join(__dirname,'..','TorLifeOS_v10.html');
(async()=>{
  const b=await chromium.launch(); const ctx=await b.newContext();
  const p=await ctx.newPage();
  p.on('pageerror',e=>console.log('PAGEERROR:',e.message));
  await p.goto('file://'+file); await p.waitForTimeout(1000);

  // build a monthly recurring task that is 3 months overdue, using the calendar UI
  await p.click('aside [data-go="cal"]'); await p.waitForTimeout(200);
  for(let i=0;i<3;i++){ await p.click('#calPrev'); await p.waitForTimeout(120); }
  await p.evaluate(()=>{ const c=document.querySelectorAll('#calGrid .cday:not(.out)'); c[9].click(); });
  await p.waitForTimeout(150);
  await p.fill('#tdName','โอน BAM รายเดือน'); await p.check('#tdRep'); await p.click('#tdAdd');
  await p.waitForTimeout(250);

  await p.click('aside [data-go="today"]'); await p.waitForTimeout(250);
  const id = await p.evaluate(()=>{const o=JSON.parse(localStorage.getItem('torlifeos:v8'));
    const t=o.todos.find(x=>x.n==='โอน BAM รายเดือน'); return t? t.id+'|'+t.due : 'NOT FOUND';});
  console.log('created:', id);
  const tid=id.split('|')[0];
  const dues=[id.split('|')[1]];
  for(let i=0;i<3;i++){
    const cb = await p.$(`#todayTodo input[data-tdone="${tid}"]`);
    if(!cb){ console.log('  checkbox gone at click', i); break; }
    await cb.click(); await p.waitForTimeout(300);
    dues.push(await p.evaluate(t=>{const o=JSON.parse(localStorage.getItem('torlifeos:v8'));
      const x=o.todos.find(y=>y.id===t); return x? x.due : 'gone';},tid));
  }
  console.log('due after each tick:', dues.join('  ->  '));
  console.log('today is:', await p.evaluate(()=>{const d=new Date();return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');}));
  console.log('still listed as overdue:', await p.evaluate(()=>document.getElementById('todayTodo').innerText.includes('เลยกำหนด')));
  await b.close();
})();
