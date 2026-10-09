/* เทียบข้อมูลจริงระหว่างระบบเดิมกับระบบใหม่ บนข้อมูลชุดเดียวกัน (ไฟล์สำรอง .json ของผู้ใช้)
   วิธีรัน: node tests/compare-backup.cjs <ระบบเดิม.html> <ระบบใหม่.html> <proclean-backup.json> <โฟลเดอร์ผลลัพธ์>
   ผลลัพธ์: ความต่างของข้อมูลทุกฟิลด์ ข้อความบนกระดาษทุกฉบับ ยอดเงิน สต็อก การแบ่งหน้า และชุดตรวจสอบระบบ
   ไฟล์สำรองมีข้อมูลลูกค้า ห้าม commit เข้า repository */
const pw=(function(){ try{ return require('playwright'); }catch(e){ return require('/opt/node22/lib/node_modules/playwright'); } })();
const fs=require('fs'), path=require('path');
const [,,OLD,NEW,BACKUP,OUT]=process.argv;
const raw=fs.readFileSync(BACKUP,'utf8').replace(/^﻿/,'');
const KEY='proclean.office.v1';
(async()=>{
 const b=await pw.chromium.launch({executablePath:'/opt/pw-browsers/chromium-1194/chrome-linux/chrome'});
 const ctx=await b.newContext({timezoneId:'Asia/Bangkok',viewport:{width:1280,height:900}});
 const errs=[];
 // ใส่ข้อมูลลงที่เก็บของเบราว์เซอร์ให้เหมือนเครื่องผู้ใช้
 const seed=await ctx.newPage(); await seed.goto('file://'+OLD);
 await seed.evaluate(([k,v])=>{ localStorage.setItem(k, JSON.stringify(JSON.parse(v))); },[KEY,raw]);
 await seed.close();
 // ---- ระบบเดิม ----
 const o=await ctx.newPage(); o.on('pageerror',e=>errs.push('old:'+e.message));
 await o.goto('file://'+OLD); await o.waitForTimeout(300);
 const oldState=await o.evaluate(k=>JSON.parse(localStorage.getItem(k)),KEY);
 const oldSheets=await o.evaluate(()=>{const P=window.PROCLEAN; const tx=h=>{const e=document.createElement('div');e.innerHTML=h;return e.textContent.replace(/\s+/g,' ').replace(/(พิมพ์เมื่อ|Printed on) [^·]*$/,'').trim();};
   return P.db.docs.map(d=>({id:d.id,no:d.no,type:d.type,text:tx(P.sheetHTML(d,'ต้นฉบับ'))}));});
 const oldStock=await o.evaluate(()=>window.PROCLEAN.db.products.map(p=>({id:p.id,sku:p.sku,stock:p.stock})));
 const oldTotals=await o.evaluate(()=>window.PROCLEAN.db.docs.map(d=>({no:d.no,c:window.PROCLEAN.calcDoc(d)})));
 await o.close();
 // ---- ระบบใหม่ (เปิดทับที่เก็บเดียวกัน) ----
 const n=await ctx.newPage(); n.on('pageerror',e=>errs.push('new:'+e.message));
 await n.goto('file://'+NEW); await n.waitForTimeout(400);
 const newState=await n.evaluate(k=>JSON.parse(localStorage.getItem(k)),KEY);
 const newSheets=await n.evaluate(()=>{const P=window.PROCLEAN; const tx=h=>{const e=document.createElement('div');e.innerHTML=h;return e.textContent.replace(/\s+/g,' ').replace(/(พิมพ์เมื่อ|Printed on) [^·]*$/,'').trim();};
   return P.db.docs.map(d=>({id:d.id,no:d.no,type:d.type,text:tx(P.sheetHTML(d,'ต้นฉบับ'))}));});
 const newStock=await n.evaluate(()=>window.PROCLEAN.db.products.map(p=>({id:p.id,sku:p.sku,stock:p.stock})));
 const newTotals=await n.evaluate(()=>window.PROCLEAN.db.docs.map(d=>({no:d.no,c:window.PROCLEAN.calcDoc(d)})));
 // ---- 1) เทียบข้อมูลที่เก็บทุกฟิลด์ (นอกจากฟิลด์ที่ระบบใหม่เพิ่ม) ----
 const ADDED={'meta.savedAt':1,'meta.taxRule':1,'meta.deleted':1,'meta.userSet':1,'company.branch':1,'company.branchEn':1,'settings.sampleFollowDays':1};
 const diffs=[];
 function walk(a,bb,p){
   if(ADDED[p]) return;
   if(/^docs\.\d+\.taxInv$/.test(p) && a===undefined) return;   // เพิ่มใหม่ (ล็อกหัวเอกสาร)
   if(typeof a!==typeof bb || Array.isArray(a)!==Array.isArray(bb) || (a===null)!==(bb===null)){ diffs.push([p,a,bb]); return; }
   if(a && typeof a==='object'){
     const ks=new Set([...Object.keys(a),...Object.keys(bb)]);
     ks.forEach(k=>walk(a[k],bb[k],p?p+'.'+k:k)); return;
   }
   if(a!==bb) diffs.push([p,a,bb]);
 }
 walk(oldState,newState,'');
 // ---- 2) เทียบข้อความบนกระดาษ ----
 const sheetDiffs=[];
 oldSheets.forEach((x,i)=>{ const y=newSheets[i]; if(!y||x.id!==y.id||x.text!==y.text){
   let k=0; const a=x.text,c=(y||{}).text||''; while(k<a.length&&a[k]===c[k])k++;
   sheetDiffs.push({no:x.no,old:a.slice(Math.max(0,k-50),k+70),new:c.slice(Math.max(0,k-50),k+70)}); }});
 // ---- 3) ยอดเงินและสต็อก ----
 const totalDiffs=oldTotals.filter((x,i)=>JSON.stringify(x)!==JSON.stringify(newTotals[i])).map(x=>x.no);
 const stockDiffs=oldStock.filter((x,i)=>JSON.stringify(x)!==JSON.stringify(newStock[i])).map(x=>x.sku);
 // ---- 4) จัดหน้าพิมพ์จริงของระบบใหม่ ----
 const layout=await n.evaluate(()=>{const P=window.PROCLEAN; const st=document.createElement('div'); st.className='sheet-stage';
   st.style.cssText='position:absolute;left:-12000px;top:0;visibility:hidden'; document.body.appendChild(st);
   const out=P.db.docs.map(d=>{ st.innerHTML=''; const r=P.layoutDocInto(st,d,'ต้นฉบับ',d.lang);
     const sheets=[...st.querySelectorAll('.sheet')];
     return {no:d.no, items:d.items.length, pages:r.pages, rowsOnPaper:st.querySelectorAll('tr.it-row').length,
       overflow:sheets.filter(s=>P.sheetOverflows(s)&&!s.classList.contains('sheet-free')).length, free:sheets.filter(s=>s.classList.contains('sheet-free')).length}; });
   st.remove(); return out;});
 // ---- 5) ชุดตรวจสอบระบบบนข้อมูลจริง ----
 const before=await n.evaluate(k=>localStorage.getItem(k),KEY);
 const self=await n.evaluate(()=>{const r=window.PROCLEAN.runSelfTest(); return {n:r.length, bad:r.filter(x=>!x.pass)};});
 const after=await n.evaluate(k=>localStorage.getItem(k),KEY);
 const strip=s=>{const o=JSON.parse(s); delete o.meta.savedAt; return JSON.stringify(o);};
 // ---- 6) ใบเสนอราคาวันนี้ ----
 const today=await n.evaluate(()=>{const P=window.PROCLEAN; const d=P.db.docs.find(x=>x.no==='QT691009-001'); if(!d) return null;
   const c=P.calcDoc(d); return {no:d.no,date:d.date,due:d.dueDate,status:d.status,party:(d.partySnapshot||{}).name,
     items:d.items.map(it=>({name:it.name,pack:it.pack,qty:it.qty,unit:it.unit,price:it.price,amt:P.lineAmount(it)})),sub:c.sub,grand:c.grand,words:P.bahtText(c.grand)};});
 // ---- 7) PDF ของระบบใหม่ ----
 fs.mkdirSync(OUT,{recursive:true});
 for(const no of ['QT691009-001','QT6909013-01']){
   await n.evaluate(no=>{ const P=window.PROCLEAN; document.querySelectorAll('.print-overlay').forEach(x=>x.remove()); P.openPrint(P.db.docs.find(d=>d.no===no),'one'); },no);
   await n.waitForTimeout(500);
   await n.emulateMedia({media:'print'}); await n.pdf({path:path.join(OUT,'new-'+no+'.pdf'),preferCSSPageSize:true,printBackground:true}); await n.emulateMedia({media:'screen'});
 }
 // PDF ระบบเดิม (ฉบับที่รายการเยอะ) ไว้เทียบปัญหาหน้าซ้อน
 const o2=await ctx.newPage(); await o2.goto('file://'+OLD); await o2.waitForTimeout(300);
 for(const no of ['QT691009-001','QT6909013-01']){
   await o2.evaluate(no=>{ const P=window.PROCLEAN; document.querySelectorAll('.print-overlay').forEach(x=>x.remove()); document.body.classList.remove('printing'); P.openPrint(P.db.docs.find(d=>d.no===no),'one'); },no);
   await o2.waitForTimeout(400);
   await o2.emulateMedia({media:'print'}); await o2.pdf({path:path.join(OUT,'old-'+no+'.pdf'),preferCSSPageSize:true,printBackground:true}); await o2.emulateMedia({media:'screen'});
 }
 console.log(JSON.stringify({diffs,sheetDiffs,totalDiffs,stockDiffs,layout,self,selftestTouchedData:strip(before)!==strip(after),today,errs,
   counts:{old:{docs:oldState.docs.length,cust:oldState.customers.length,sup:oldState.suppliers.length,prod:oldState.products.length,moves:oldState.moves.length,guides:oldState.guides.length},
           new:{docs:newState.docs.length,cust:newState.customers.length,sup:newState.suppliers.length,prod:newState.products.length,moves:newState.moves.length,guides:newState.guides.length}}},null,1));
 await b.close();
})();
