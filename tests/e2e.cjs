/* ทดสอบระบบแบบใช้งานจริงด้วยเบราว์เซอร์ Chromium (Playwright) ในเขตเวลา Asia/Bangkok
   วิธีรัน:  node tests/e2e.cjs [ไฟล์รุ่นเก่า.html]
   - ถ้าระบุไฟล์รุ่นเก่า จะสร้างข้อมูลด้วยรุ่นเก่าก่อน แล้วเปิดรุ่นใหม่ทับ เพื่อยืนยันว่าข้อมูลเดิมไม่หาย */
const path = require('path');
const fs = require('fs');
let pw;
try { pw = require('playwright'); } catch (e) { pw = require('/opt/node22/lib/node_modules/playwright'); }
const NEW = path.resolve(__dirname, '..', 'PROCLEAN-OFFICE.html');
const OLD = process.argv[2] ? path.resolve(process.argv[2]) : null;
const OUT = path.resolve(process.env.E2E_OUT || path.join(__dirname, '..', '.e2e-out'));
fs.mkdirSync(OUT, { recursive: true });

let failed = 0;
function check(name, ok, detail) {
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : '  -> ' + (detail || '')));
  if (!ok) failed++;
}

(async () => {
  const exe = fs.existsSync('/opt/pw-browsers/chromium-1194/chrome-linux/chrome') ? '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' : undefined;
  const browser = await pw.chromium.launch({ executablePath: exe });
  const ctx = await browser.newContext({ timezoneId: 'Asia/Bangkok', viewport: { width: 1280, height: 900 } });
  const errors = [];
  const watch = (pg, tag) => { pg.on('pageerror', e => errors.push(tag + ': ' + e.message)); pg.on('dialog', d => d.dismiss()); };
  const page = await ctx.newPage(); watch(page, 'main');

  /* ---------- 1) ข้อมูลจากรุ่นเก่าต้องอยู่ครบหลังเปิดรุ่นใหม่ ---------- */
  let before = null;
  if (OLD) {
    await page.goto('file://' + OLD);
    before = await page.evaluate(() => {
      const P = window.PROCLEAN, db = P.db;
      db.customers.push({ id: 'cu_old1', name: 'บริษัท ลูกค้าเดิม จำกัด', branch: 'สำนักงานใหญ่', taxId: '0105555555555',
        addr1: '1 ถนนทดสอบ', addr2: 'กรุงเทพฯ', contact: 'คุณเอ', phone: '02-000-0000', email: '', creditDays: 30, note: 'บันทึกภายใน',
        nameEn: '', branchEn: '', addrEn1: '', addrEn2: '', docLang: '' });
      db.products[0].price = 450; db.products[0].cost = 300;
      db.guides[0].tagline = 'ข้อความที่ผู้ใช้แก้เอง';
      const iv = P.newDoc('IV'); iv.partyId = 'cu_old1'; iv.status = 'sent';
      iv.items = [{ id: 'i1', productId: db.products[0].id, name: db.products[0].name, qty: 4, unit: 'แกลลอน', price: 450, disc: 0, discType: 'thb' }];
      P.saveDoc(iv);
      const po = P.newDoc('PO'); po.partyId = 'sp_x'; po.status = 'received';
      po.items = [{ id: 'i2', productId: db.products[0].id, name: db.products[0].name, qty: 20, unit: 'แกลลอน', price: 300, disc: 0, discType: 'thb' }];
      P.saveDoc(po);
      P.save();
      return JSON.parse(localStorage.getItem('proclean.office.v1'));
    });
  }

  await page.goto('file://' + NEW);
  await page.waitForTimeout(400);
  if (before) {
    const after = await page.evaluate(() => JSON.parse(localStorage.getItem('proclean.office.v1')));
    check('ข้อมูลเดิม: จำนวนเอกสารเท่าเดิม', after.docs.length === before.docs.length, after.docs.length + ' vs ' + before.docs.length);
    check('ข้อมูลเดิม: ลูกค้าเดิมอยู่ครบ', after.customers.length === before.customers.length && after.customers.some(c => c.id === 'cu_old1' && c.note === 'บันทึกภายใน'));
    check('ข้อมูลเดิม: ราคาสินค้าที่ตั้งไว้ไม่เปลี่ยน', after.products[0].price === 450 && after.products[0].cost === 300);
    check('ข้อมูลเดิม: คู่มือที่ผู้ใช้แก้ไม่ถูกเขียนทับ', after.guides[0].tagline === 'ข้อความที่ผู้ใช้แก้เอง');
    check('ข้อมูลเดิม: ประวัติสต็อกครบ', after.moves.length === before.moves.length);
    check('ข้อมูลเดิม: เลขที่เอกสารเดิมไม่เปลี่ยน', JSON.stringify(after.docs.map(d => d.no)) === JSON.stringify(before.docs.map(d => d.no)));
    check('ข้อมูลเดิม: เลขรันเอกสารต่อจากเดิม', JSON.stringify(after.counters) === JSON.stringify(before.counters));
    const ar = await page.evaluate(() => window.PROCLEAN.arAging().buckets.total);
    check('ข้อมูลเดิม: ลูกหนี้คงค้างคำนวณได้', ar === 1800, String(ar));
  }

  /* ---------- 2) ชุดตรวจสอบระบบในตัว + ไม่แตะข้อมูลจริง ---------- */
  const snapBefore = await page.evaluate(() => { const d = JSON.parse(localStorage.getItem('proclean.office.v1')); delete d.meta.savedAt; return JSON.stringify(d); });
  const res = await page.evaluate(() => window.PROCLEAN.runSelfTest());
  const bad = res.filter(r => !r.pass);
  check('ชุดตรวจสอบในตัวผ่านทั้งหมด (' + res.length + ' ข้อ)', bad.length === 0, JSON.stringify(bad));
  const snapAfter = await page.evaluate(() => { const d = JSON.parse(localStorage.getItem('proclean.office.v1')); delete d.meta.savedAt; return JSON.stringify(d); });
  check('รันชุดตรวจสอบแล้วข้อมูลจริงไม่เปลี่ยน', snapBefore === snapAfter);

  /* ---------- 3) ใช้งานผ่านหน้าจอจริง ---------- */
  await page.evaluate(() => window.PROCLEAN.go('customers'));
  await page.click('[data-editparty="customer:new"]');
  await page.fill('#pf-name', 'บริษัท ทดสอบหน้าจอ จำกัด');
  await page.fill('#pf-credit', '15');
  await page.selectOption('#pf-lang', 'en');
  await page.click('.modal [data-ok]');
  const custId = await page.evaluate(() => window.PROCLEAN.db.customers.find(c => c.name === 'บริษัท ทดสอบหน้าจอ จำกัด').id);
  // ปุ่ม “เสนอราคา” จากทะเบียนต้องตั้งภาษาตามลูกค้า
  await page.click('[data-quote-for="' + custId + '"]');
  const qLang = await page.evaluate(() => document.querySelector('[data-d="lang"]').value);
  check('ปุ่มเสนอราคาจากทะเบียนลูกค้า ตั้งภาษาเอกสารตามลูกค้า', qLang === 'en', qLang);
  // ค้นหาสินค้าแล้วกด Enter
  await page.click('[data-add-line]');
  const nameInput = page.locator('[data-l="name"]').last();
  await nameInput.fill('ล้างพื้น');
  await page.waitForSelector('.pick-list');
  await nameInput.press('Enter');
  const firstName = await page.locator('[data-l="name"]').first().inputValue();
  check('ค้นหาสินค้าแล้วกด Enter เลือกสินค้าได้', firstName.indexOf('ล้างพื้น') >= 0, firstName);
  // พิมพ์วันที่ด้วยแป้นพิมพ์ต่อเนื่อง ต้องไม่หลุดโฟกัส และวันยืนราคาเลื่อนตาม
  const due0 = await page.inputValue('[data-d="dueDate"]');
  const date0 = await page.inputValue('[data-d="date"]');
  await page.locator('[data-d="date"]').fill('2026-11-02');
  const focusOk = await page.evaluate(() => document.activeElement && document.activeElement.getAttribute('data-d') === 'date');
  check('แก้วันที่แล้วโฟกัสไม่หลุด', focusOk);
  const due1 = await page.inputValue('[data-d="dueDate"]');
  const gap0 = await page.evaluate(([a, b]) => window.PROCLEAN.daysBetween(a, b), [date0, due0]);
  const gap1 = await page.evaluate(([a, b]) => window.PROCLEAN.daysBetween(a, b), ['2026-11-02', due1]);
  check('เปลี่ยนวันที่แล้ววันยืนราคาเลื่อนตามระยะเดิม', gap0 === gap1 && gap1 === 30, gap0 + ' / ' + gap1 + ' / ' + due1);
  const docNo = await page.inputValue('[data-d="no"]');
  check('เปลี่ยนเดือนแล้วเลขที่เอกสารใหม่ย้ายไปชุดเดือนใหม่', /^QT6911/.test(docNo), docNo);
  // บันทึก
  await page.click('[data-save]');
  await page.waitForTimeout(200);
  const savedQ = await page.evaluate(() => window.PROCLEAN.db.docs.find(d => d.type === 'QT' && d.partyId && d.date === '2026-11-02'));
  check('บันทึกใบเสนอราคาผ่านหน้าจอได้', !!savedQ && savedQ.dueDate === '2026-12-02', savedQ && savedQ.dueDate);

  /* ---------- 4) เอกสารรายการมาก: พิมพ์จริงเป็น PDF ---------- */
  await page.evaluate(() => {
    const P = window.PROCLEAN, db = P.db;
    const d = P.newDoc('DN'); d.partyId = db.customers[0].id; d.status = 'draft';
    d.items = [];
    for (let i = 0; i < 64; i++) {
      const p = db.products[i % db.products.length];
      d.items.push({ id: 'z' + i, productId: p.id, sku: p.sku, name: p.name + ' ลำดับ ' + (i + 1), pack: p.pack, unit: p.unit,
        dilution: p.dilution, qty: 1, price: 250, disc: 0, discType: 'thb', note: i % 9 === 0 ? 'หมายเหตุรายการยาว ๆ เพื่อทดสอบความสูงแถวที่ไม่เท่ากัน '.repeat(2) : '' });
    }
    d.note = 'กรุณาตรวจนับสินค้า\nบรรทัดที่สอง\nบรรทัดที่สาม';
    P.saveDoc(d);
    window.__big = d.id;
    P.openPrint(P.db.docs.find(x => x.id === d.id), 'all');
  });
  await page.waitForTimeout(600);
  const pg = await page.evaluate(() => {
    const sh = [...document.querySelectorAll('.print-overlay .sheet')];
    return { n: sh.length, over: sh.filter(s => window.PROCLEAN.sheetOverflows(s)).length,
      rows: document.querySelectorAll('.print-overlay tr.it-row').length, title: document.title };
  });
  check('ใบส่งของ 64 รายการ พร้อมสำเนา: แบ่งหน้าเป็นคู่ (ต้นฉบับ+สำเนา)', pg.n >= 4 && pg.n % 2 === 0, JSON.stringify(pg));
  check('ทุกแผ่นไม่ล้นกระดาษ', pg.over === 0, JSON.stringify(pg));
  check('รายการครบทั้งต้นฉบับและสำเนา', pg.rows === 128, String(pg.rows));
  check('ชื่อไฟล์ PDF ตั้งตามเลขที่เอกสาร', /^DN\d+/.test(pg.title), pg.title);
  await page.emulateMedia({ media: 'print' });
  await page.pdf({ path: path.join(OUT, 'big-dn.pdf'), preferCSSPageSize: true, printBackground: true });
  await page.emulateMedia({ media: 'screen' });
  const pdfPages = require('child_process').execSync('pdfinfo ' + JSON.stringify(path.join(OUT, 'big-dn.pdf'))).toString().match(/Pages:\s+(\d+)/)[1];
  check('PDF ที่พิมพ์ได้จำนวนหน้าเท่ากับหน้าบนจอ (ไม่มีหน้าว่างแทรก/ไม่ล้น)', +pdfPages === pg.n, pdfPages + ' vs ' + pg.n);
  await page.keyboard.press('Escape');
  const closed = await page.evaluate(() => !document.querySelector('.print-overlay') && !document.body.classList.contains('printing') && document.title.indexOf('PROCLEAN') === 0);
  check('กด Esc ปิดหน้าตัวอย่างพิมพ์และคืนชื่อหน้าต่าง', closed);

  /* ---------- 5) จอมือถือ: หน้าตัวอย่างย่อพอดีจอ และการแบ่งหน้าเหมือนจอใหญ่ ---------- */
  const mob = await ctx.newPage(); watch(mob, 'mobile');
  await mob.setViewportSize({ width: 390, height: 800 });
  await mob.goto('file://' + NEW);
  const mres = await mob.evaluate(() => {
    const P = window.PROCLEAN; const d = P.db.docs.find(x => x.id === window.__big) || P.db.docs.find(x => x.type === 'DN' && x.items.length === 64);
    P.openPrint(d, 'one');
    const st = document.querySelector('.print-overlay .sheet-stage');
    return { n: st.querySelectorAll('.sheet').length, zoom: st.style.zoom, w: Math.round(st.getBoundingClientRect().width) };
  });
  check('มือถือ: จำนวนหน้าเท่ากับจอใหญ่ (ต่อชุด)', mres.n === pg.n / 2, JSON.stringify(mres));
  check('มือถือ: ย่อเวทีให้พอดีจอ', +mres.zoom > 0 && +mres.zoom < 1, JSON.stringify(mres));
  await mob.close();

  /* ---------- 6) เปิดสองหน้าต่าง: บันทึกจากหน้าหนึ่ง อีกหน้าต้องเห็นและไม่บันทึกทับ ---------- */
  const tab2 = await ctx.newPage(); watch(tab2, 'tab2');
  await tab2.goto('file://' + NEW);
  await tab2.evaluate(() => { const db = window.PROCLEAN.db; db.customers.push({ id: 'cu_tab2', name: 'ลูกค้าจากหน้าต่างที่สอง' }); window.PROCLEAN.save(); });
  await page.waitForTimeout(300);
  await page.evaluate(() => { const db = window.PROCLEAN.db; db.customers.push({ id: 'cu_tab1', name: 'ลูกค้าจากหน้าต่างแรก' }); window.PROCLEAN.save(); });
  await tab2.waitForTimeout(500);   // localStorage ข้ามหน้าต่างของ Chromium ซิงก์แบบไม่พร้อมกันทันที
  const both = await tab2.evaluate(() => { const c = JSON.parse(localStorage.getItem('proclean.office.v1')).customers; return c.some(x => x.id === 'cu_tab1') && c.some(x => x.id === 'cu_tab2'); });
  const dbg = await page.evaluate(() => ({ route: document.querySelector('.topbar h1') && document.querySelector('.topbar h1').textContent, has2: window.PROCLEAN.db.customers.some(x => x.id === 'cu_tab2'), n: window.PROCLEAN.db.customers.length }));
  check('สองหน้าต่างบันทึกสลับกัน ข้อมูลไม่หาย', both, JSON.stringify(dbg));
  await tab2.close();

  /* ---------- 7) ข้อมูลในเครื่องเสียหาย: ต้องไม่ถูกเขียนทับ ---------- */
  const goodRaw = await page.evaluate(() => localStorage.getItem('proclean.office.v1'));
  const broken = goodRaw.slice(0, Math.floor(goodRaw.length / 2));
  await page.evaluate(r => localStorage.setItem('proclean.office.v1', r), broken);
  const p3 = await ctx.newPage(); watch(p3, 'corrupt');
  await p3.goto('file://' + NEW);
  await p3.waitForTimeout(300);
  const banner = await p3.evaluate(() => !!document.querySelector('[data-dl-raw]'));
  await p3.evaluate(() => { window.PROCLEAN.go('settings'); window.PROCLEAN.save(); });
  const still = await p3.evaluate(() => localStorage.getItem('proclean.office.v1'));
  check('ข้อมูลเสียหาย: แสดงแถบเตือนพร้อมปุ่มดาวน์โหลดข้อมูลเดิม', banner);
  check('ข้อมูลเสียหาย: ระบบไม่บันทึกทับข้อมูลเดิม', still === broken);
  await p3.evaluate(r => localStorage.setItem('proclean.office.v1', r), goodRaw);
  await p3.close();

  /* ---------- 8) ไฟล์ระบบพร้อมข้อมูล: ย้ายเครื่องด้วยไฟล์เดียว ---------- */
  await page.evaluate(() => window.PROCLEAN.go('settings'));
  const [dl] = await Promise.all([page.waitForEvent('download'), page.click('.topbar [data-export-html]')]);
  const embPath = path.join(OUT, 'with-data.html');
  await dl.saveAs(embPath);
  const src = await page.evaluate(() => { const d = window.PROCLEAN.db; return { docs: d.docs.map(x => x.id).sort(), cust: d.customers.length, nos: d.docs.map(x => x.no).sort() }; });
  const ctx2 = await browser.newContext({ timezoneId: 'Asia/Bangkok', viewport: { width: 1280, height: 900 } });   // เครื่องใหม่ (ไม่มีข้อมูล)
  const fresh = await ctx2.newPage(); watch(fresh, 'fresh');
  await fresh.goto('file://' + embPath);
  await fresh.waitForTimeout(300);
  const got = await fresh.evaluate(() => { const d = window.PROCLEAN.db; return { docs: d.docs.map(x => x.id).sort(), cust: d.customers.length, nos: d.docs.map(x => x.no).sort(), st: window.PROCLEAN.embedState,
    stored: !!localStorage.getItem('proclean.office.v1') }; });
  check('เปิดไฟล์พร้อมข้อมูลบนเครื่องใหม่: เอกสารครบทุกฉบับ เลขที่เดิม', JSON.stringify(got.docs) === JSON.stringify(src.docs) && JSON.stringify(got.nos) === JSON.stringify(src.nos), got.docs.length + ' vs ' + src.docs.length);
  check('เปิดไฟล์พร้อมข้อมูลบนเครื่องใหม่: ลูกค้าครบ และบันทึกลงเครื่องแล้ว', got.cust === src.cust && got.stored && got.st === 'loaded', JSON.stringify(got));
  const selfRes = await fresh.evaluate(() => window.PROCLEAN.runSelfTest().filter(r => !r.pass));
  check('ไฟล์พร้อมข้อมูลผ่านชุดตรวจสอบในตัว', selfRes.length === 0, JSON.stringify(selfRes));
  // เครื่องใหม่ทำงานต่อ (เพิ่มเอกสาร) แล้วเปิดไฟล์พร้อมข้อมูลเดิมอีกครั้ง → ต้องไม่ทับงานใหม่
  await fresh.evaluate(() => { const P = window.PROCLEAN; const d = P.newDoc('QT'); d.partyId = P.db.customers[0].id;
    d.items = [{ id: 'n', name: 'งานใหม่บนเครื่องใหม่', qty: 1, unit: 'ชิ้น', price: 10, disc: 0, discType: 'thb' }]; P.saveDoc(d); window.__newId = d.id; });
  const newId = await fresh.evaluate(() => window.__newId);
  const again = await ctx2.newPage(); watch(again, 'again');
  await again.goto('file://' + embPath);
  await again.waitForTimeout(300);
  const kept = await again.evaluate(id => ({ has: window.PROCLEAN.db.docs.some(d => d.id === id), st: window.PROCLEAN.embedState }), newId);
  check('เปิดไฟล์พร้อมข้อมูลซ้ำบนเครื่องที่มีงานใหม่: ไม่ทับงานใหม่', kept.has && kept.st === 'same', JSON.stringify(kept));
  await again.close(); await fresh.close(); await ctx2.close();
  // เครื่องที่สามซึ่งมีข้อมูลชุดอื่นอยู่แล้ว → แสดงแถบให้รวม → กดรวม → ได้ข้อมูลทั้งสองชุด
  const ctx3 = await browser.newContext({ timezoneId: 'Asia/Bangkok', viewport: { width: 1280, height: 900 } });
  const other = await ctx3.newPage(); watch(other, 'other');
  await other.goto('file://' + NEW);
  await other.evaluate(() => { const P = window.PROCLEAN; P.db.customers.push({ id: 'cu_only_here', name: 'ลูกค้าเฉพาะเครื่องนี้' }); P.save(); });
  await other.goto('file://' + embPath);
  await other.waitForTimeout(300);
  const st2 = await other.evaluate(() => ({ st: window.PROCLEAN.embedState, banner: !!document.querySelector('[data-embed-merge]') }));
  if (st2.st === 'differs') {
    await other.click('[data-embed-merge]');
    const [bk] = await Promise.all([other.waitForEvent('download'), other.click('.modal [data-ok]')]);
    const merged = await other.evaluate(() => { const d = window.PROCLEAN.db; return { here: d.customers.some(c => c.id === 'cu_only_here'),
      docs: d.docs.map(x => x.id).sort(), prods: d.products.length }; });
    check('รวมข้อมูลจากไฟล์: ข้อมูลเดิมในเครื่องยังอยู่ และได้เอกสารจากไฟล์ครบทุกฉบับ', merged.here && JSON.stringify(merged.docs) === JSON.stringify(src.docs), JSON.stringify(merged).slice(0, 200));
    check('รวมข้อมูลจากไฟล์: สินค้าไม่ซ้ำ (จับคู่ด้วยรหัสสินค้า)', merged.prods === 16, String(merged.prods));
    check('รวมข้อมูลจากไฟล์: ดาวน์โหลดไฟล์สำรองให้ก่อนรวม', /proclean-backup-/.test(bk.suggestedFilename()), bk.suggestedFilename());
  } else {
    check('เปิดไฟล์พร้อมข้อมูลบนเครื่องที่มีข้อมูลอื่น: แสดงแถบให้เลือกรวมข้อมูล', false, JSON.stringify(st2));
  }
  await other.close(); await ctx3.close();

  /* ---------- 9) เปิดไฟล์รุ่นเก่าค้างไว้อีกหน้าต่าง แล้วรุ่นเก่าบันทึกทับ ---------- */
  if (OLD) {
    const ctx4 = await browser.newContext({ timezoneId: 'Asia/Bangkok' });
    const oldTab = await ctx4.newPage(); watch(oldTab, 'oldTab');
    await oldTab.goto('file://' + OLD);
    const newTab = await ctx4.newPage(); watch(newTab, 'newTab');
    await newTab.goto('file://' + NEW);
    const issued = await newTab.evaluate(() => { const P = window.PROCLEAN; const d = P.newDoc('IV'); d.partyId = 'x'; d.status = 'sent';
      d.items = [{ id: 'a', name: 'ออกให้ลูกค้าแล้ว', qty: 1, unit: 'ชิ้น', price: 100, disc: 0, discType: 'thb' }]; P.saveDoc(d); return d.no; });
    await oldTab.waitForTimeout(300);
    await oldTab.evaluate(() => { window.PROCLEAN.db.company.phone = '000'; window.PROCLEAN.save(); });   // รุ่นเก่าบันทึกข้อมูลเก่าทับ
    await newTab.waitForTimeout(600);
    const st = await newTab.evaluate(no => ({ mem: window.PROCLEAN.db.docs.some(d => d.no === no), next: window.PROCLEAN.newDoc('IV').no,
      stored: JSON.parse(localStorage.getItem('proclean.office.v1')).docs.some(d => d.no === no) }), issued);
    check('ไฟล์รุ่นเก่าที่เปิดค้างบันทึกทับ: เอกสารที่เพิ่งออกไม่หาย', st.mem && st.stored, JSON.stringify(st));
    check('ไฟล์รุ่นเก่าที่เปิดค้างบันทึกทับ: เลขที่เอกสารถัดไปไม่ซ้ำกับที่ออกไปแล้ว', st.next !== issued, st.next + ' vs ' + issued);
    await ctx4.close();

    /* ---------- 10) เอกสาร VAT ที่ออกด้วยรุ่นเก่า พิมพ์ซ้ำต้องได้หัวเอกสารเดิม ---------- */
    const ctx5 = await browser.newContext({ timezoneId: 'Asia/Bangkok' });
    const o5 = await ctx5.newPage(); watch(o5, 'vatOld');
    await o5.goto('file://' + OLD);
    const oldTitles = await o5.evaluate(() => { const P = window.PROCLEAN, db = P.db; db.company.vatRegistered = true; db.company.taxId = '0105555555555';
      const mk = (t, f, st) => { const d = f ? P.convertDoc(f, t) : P.newDoc(t); d.partyId = 'x'; d.vat = true; if (!f) d.items = [{ id: 'a', name: 'x', qty: 1, unit: 'ชิ้น', price: 100, disc: 0, discType: 'thb' }]; d.status = st; return P.saveDoc(d); };
      const q = mk('QT', null, 'won'), dn = mk('DN', q, 'delivered'), iv = mk('IV', dn, 'sent'), rc = mk('RC', iv, 'issued');
      P.save();
      const tx = h => { const e = document.createElement('div'); e.innerHTML = h; return e.querySelector('.sh-title').textContent; };
      return [dn, iv, rc].map(d => ({ id: d.id, t: tx(P.sheetHTML(d, null)) })); });
    const n5 = await ctx5.newPage(); watch(n5, 'vatNew');
    await n5.goto('file://' + NEW);
    const newTitles = await n5.evaluate(ids => ids.map(x => { const P = window.PROCLEAN; const e = document.createElement('div');
      e.innerHTML = P.sheetHTML(P.db.docs.find(d => d.id === x.id), null); return { id: x.id, t: e.querySelector('.sh-title').textContent }; }), oldTitles);
    check('เอกสาร VAT จากรุ่นเก่า พิมพ์ซ้ำได้หัวเอกสาร “ใบกำกับภาษี” เหมือนเดิมทุกใบ', JSON.stringify(oldTitles) === JSON.stringify(newTitles),
      JSON.stringify(oldTitles) + ' => ' + JSON.stringify(newTitles));
    await ctx5.close();
  }

  /* ---------- 10b) เอกสารทุกชนิด (ไทย/อังกฤษ) ที่ออกด้วยรุ่นเก่า พิมพ์ซ้ำต้องได้ข้อความเดิมทุกตัวอักษร ---------- */
  if (OLD) {
    const ctx7 = await browser.newContext({ timezoneId: 'Asia/Bangkok' });
    const o7 = await ctx7.newPage(); watch(o7, 'fidOld');
    await o7.goto('file://' + OLD);
    const TX = `(h=>{const e=document.createElement('div');e.innerHTML=h;return e.textContent.replace(/\\s+/g,' ').replace(/(พิมพ์เมื่อ|Printed on) [^·]*$/,'');})`;
    const oldT = await o7.evaluate(TX => { const tx = eval(TX); const P = window.PROCLEAN, db = P.db;
      db.company.bankName = 'ธนาคารกสิกรไทย'; db.company.bankAcctName = 'สุวัฒน์'; db.company.bankAcctNo = '123-4-56789-0';
      db.customers.push({ id: 'cf', name: 'บริษัท ลูกค้า จำกัด', branch: 'สำนักงานใหญ่', taxId: '0105555555555', addr1: '99/9 ถนนทดสอบ', addr2: 'กรุงเทพมหานคร 10110',
        contact: 'คุณเอ', phone: '02-000-0000', email: 'a@b.c', creditDays: 30, nameEn: 'Customer Co., Ltd.', addrEn1: '99/9 Test Rd', addrEn2: 'Bangkok', branchEn: 'Head Office', docLang: '' });
      const ids = [];
      ['SM', 'QT', 'DN', 'IV', 'BN', 'RC', 'CN', 'PO'].forEach(t => ['th', 'en'].forEach(lang => {
        const d = P.newDoc(t); d.partyId = 'cf'; d.lang = lang; d.poRef = 'PO-77'; d.contactRef = 'คุณเอ';
        d.items = [0, 1, 2].map(i => { const p = db.products[i * 2]; return { id: 'i' + i, productId: p.id, sku: p.sku, name: p.name, nameEn: p.nameEn, pack: p.pack, packEn: p.packEn,
          unit: p.unit, unitEn: p.unitEn, dilution: p.dilution, dilutionEn: p.dilutionEn, qty: i + 2, price: 1234.5 + i, disc: i === 1 ? 10 : 0, discType: i === 1 ? 'pct' : 'thb', note: i === 2 ? 'หมายเหตุ' : '' }; });
        d.disc = 100; d.wht = (t === 'IV'); d.whtRate = 3; d.note = 'เงื่อนไข\nบรรทัดสอง'; d.payMethod = 'โอนเงิน'; d.payRef = 'REF1';
        P.saveDoc(d); ids.push(d.id); }));
      P.save();
      return ids.map(id => ({ id, t: tx(P.sheetHTML(P.db.docs.find(d => d.id === id), 'ต้นฉบับ')) })); }, TX);
    const n7 = await ctx7.newPage(); watch(n7, 'fidNew');
    await n7.goto('file://' + NEW);
    const newT = await n7.evaluate(([ids, TX]) => { const tx = eval(TX); const P = window.PROCLEAN;
      return ids.map(x => ({ id: x.id, t: tx(P.sheetHTML(P.db.docs.find(d => d.id === x.id), 'ต้นฉบับ')) })); }, [oldT, TX]);
    const bad = oldT.filter((x, i) => x.t !== newT[i].t).length;
    check('เอกสาร 8 ชนิด × 2 ภาษา ที่ออกด้วยรุ่นเก่า พิมพ์ซ้ำได้ข้อความเดิมทุกตัวอักษร (' + oldT.length + ' ฉบับ)', bad === 0, bad + ' ฉบับต่างกัน');
    await ctx7.close();
  }

  /* ---------- 11) ส่วนขยายเบราว์เซอร์แทรกสไตล์ → ต้องไม่ติดไปในไฟล์ที่ส่งออก ---------- */
  const ctx6 = await browser.newContext({ timezoneId: 'Asia/Bangkok' });
  await ctx6.addInitScript(() => {
    new MutationObserver(() => { if (document.head && !document.getElementById('ext-injected')) {
      const st = document.createElement('style'); st.id = 'ext-injected'; st.textContent = 'body{background:#000}'; document.head.appendChild(st);
      document.documentElement.setAttribute('data-ext-mode', 'dark'); } }).observe(document, { childList: true, subtree: true });
  });
  const p6 = await ctx6.newPage(); watch(p6, 'ext');
  await p6.goto('file://' + NEW);
  const src6 = await p6.evaluate(() => window.PROCLEAN.buildDataHTML(window.PROCLEAN.db));
  check('ไฟล์พร้อมข้อมูลไม่พาสิ่งที่ส่วนขยายเบราว์เซอร์แทรกติดไปด้วย', src6.length > 1000 && src6.indexOf('ext-injected') < 0 && src6.indexOf('data-ext-mode') < 0);
  await ctx6.close();

  check('ไม่มีข้อผิดพลาด JavaScript ระหว่างทดสอบ', errors.length === 0, errors.join(' | '));
  await browser.close();
  console.log(failed ? '\n' + failed + ' FAILED' : '\nALL PASSED');
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
