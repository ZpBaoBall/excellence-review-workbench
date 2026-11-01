/**
 * 浏览器级 E2E（D3 自检固化，2026-10-25）
 *
 * 从 pwtest2-10 共 9 个临时目录收编的前端核心回归，一次跑完：
 *   E1 表格：列头排序（数值/中文/空值末位/操作列不排）+ >100 阈值分页 + 图表防污染
 *   E2 搜索：字段命中 + 分词 AND + 200ms 防抖（探针实测）+ 重置立即生效
 *   E3 弹窗：ui.toast 显隐 + ui.confirm 三路径 + 批量关联全程零原生 dialog + Ctrl+Enter 三态
 *      （2026-10-27 增：派生伪条目——报告主要优势/建议条款·大条款追加渲染、优势栏回退、
 *        伪条目保存落盘（可改进之处=节全文，2026-10-28 内容落盘）、重开去重 + 现场核实内容往返）
 *   E4 条款回填：Word 提取 → 默认猜测 → 归位 → 写入 → MD 分节/加粗/日志 → 重跑不碰手写节
 *      （2026-10-27 增：H4 概述小节标题、写入目标按阶段锁定变灰、写完两窗齐关、现场日期自动带出）
 *   E5 复盘：灵魂考问四问答题路径 + 复盘 tab 独立补写 + 模式草稿入 40 库
 *      （2026-10-27 增：不勾选做法可开草稿——门禁删除、质量模式段自动补入名称/说明）
 *      （2026-10-28 增：终版写入后 toast 引导复盘三件套、复盘 tab 归档按钮→已归档禁用态）
 *      （2026-10-28 增：复盘门禁换信号源「终版已写」——阶段一 write-onsite 后仍灰、
 *         现场态卡提取 Word 即时开启+切卡重置、终版写入后开启；归位按钮改名）
 *   E6 呈现：只看做法视图分组 + Obsidian URI 构造 + 归位选择记忆
 *   E7 数据卫生：删净测试卡/MD → ledger md5 逐字节还原 → git 仅 test/ 目录
 *
 * 数据态：自包含（备份 ledger → 造 → 删净 → 还原+md5），不依赖外部干净态。
 * 服务：没在跑就自动拉起（uvicorn 子进程），跑完只杀自起的。
 *
 * 运行：
 *   cd .工作台程序
 *   NODE_PATH="C:/Users/10507777/.workbuddy/binaries/node/versions/22.22.2-6/node_modules" \
 *   "C:/Users/10507777/.workbuddy/binaries/node/versions/22.22.2-6/node.exe" test/e2e.js
 */
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { spawn } = require("child_process");
const { chromium } = require("playwright-core");

const ROOT = path.resolve(__dirname, "..");
// 路径口径（2026-11-02 迁移落定，与 _helper.py 同源）：vault/落点/台账读 config.yaml。
// node 侧不引 yaml 依赖，按行首缩进做最小行解析（只取所需键；键位变动时这里同步改）。
const _cfg = fs.readFileSync(path.join(ROOT, "config.yaml"), "utf8");
const _pick = (re) => ((_cfg.match(re) || [])[1] || "").trim().replace(/^["']|["']$/g, "");
const _luo = (k) => _pick(new RegExp(`^ {6}${k}: (.+)$`, "m"));
const VAULT = _pick(/^ {2}根: (.+)$/m);
const LEDGER = path.join(_pick(/^ {2}数据目录: (.+)$/m) || path.join(ROOT, "data"), "ledger.json");
const MD20 = path.join(VAULT, _luo("资料评审库"));
const MD30 = path.join(VAULT, _luo("现场评审库"));
const MD40 = path.join(VAULT, _luo("质量模式库"));
const FIX = path.join(__dirname, "fixtures");
const BAK = path.join(ROOT, "data", "tmp-e2e-ledger.json");
const PY = "C:/Users/10507777/.workbuddy/binaries/python/envs/zp-workbench/Scripts/python.exe";
const EDGE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8765";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const md5 = (p) => crypto.createHash("md5").update(fs.readFileSync(p)).digest("hex");

/* 收掉所有遮罩层：2026-10-30 拍板「终版写入后报告弹窗保留（自动切复盘）」，
   所以任何「写完再点表格行」的步骤前必须先收干净，否则 overlay 拦截点击 → 30s 超时。 */
async function closeOverlays(page) {
  await page.evaluate(() => {
    document.querySelectorAll(".overlay").forEach((o) => { o.style.display = "none"; });
  });
  await sleep(250);
}

// 测试企业名统一带标记，清理按标记删，绝不误伤真实数据
const ST = "上海ST二e测试有限公司";
const PAGE_N = 105;                        // 分页阈值 100，造 105 条
// 测试卡通用字段（模块级共享：e1Table/e2Search 等多处造卡复用，避免跨函数引用局部变量）
const BASE_ROW = { "市级": "上海市", "区/县": "浦东新区", "行业门类": "制造业",
  "行业大类": "C34 通用设备制造业", "类别": "文件评审", "奖项/项目": "区政府质量奖" };

const results = [];
function t(name, cond, detail = "") {
  results.push({ name, ok: !!cond, detail });
  console.log(`  ${cond ? "PASS" : "FAIL"} | ${name}${detail ? " | " + detail : ""}`);
  return !!cond;
}

/* ── 服务管理（同 selftest._helper：复用/自起/只杀自起的） ── */
async function probe() {
  try {
    const r = await fetch(BASE + "/", { signal: AbortSignal.timeout(2000) });
    return r.status === 200;
  } catch { return false; }
}
let spawned = null;
async function ensureService() {
  if (await probe()) { console.log("[服务] 已在运行，复用现有实例"); return; }
  console.log("[服务] 未运行，拉起子进程（E2E 专用，跑完自动关闭）…");
  spawned = spawn(PY, [path.join(ROOT, "app", "main.py")], { cwd: ROOT, stdio: "ignore" });
  for (let i = 0; i < 40; i++) { if (await probe()) return; await sleep(500); }
  throw new Error("服务 20 秒内未就绪");
}
async function stopService() {
  if (spawned) { spawned.kill(); console.log("[服务] E2E 拉起的子进程已关闭"); }
}

/* ── API 助手（Node fetch，UTF-8 原生；瞬断/5xx 重试，服务倒了自愈重拉） ── */
async function api(method, p, body, retry = 3) {
  for (let i = 0; i <= retry; i++) {
    try {
      const r = await fetch(BASE + p, {
        method,
        headers: { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: AbortSignal.timeout(60000),
      });
      const j = await r.json().catch(() => ({}));
      if (r.status >= 500 && i < retry) { await sleep(600 * (i + 1)); continue; }
      return { status: r.status, j };
    } catch (e) {
      if (i === retry) throw e;
      if (!(await probe())) { console.log("  [服务] 连接中断且服务已停，重新拉起…"); await ensureService(); }
      await sleep(600 * (i + 1));
    }
  }
}
const mkCard = (fields) => api("POST", "/api/projects", { fields });
const rmCard = (id) => api("DELETE", "/api/projects/" + encodeURIComponent(id));
/* ── 批量造卡：一律走 CSV 一次 import ──
   并发调 POST /api/projects 会丢卡：api_create → import_rows 是 read-modify-write
   （load_ledger→append→save_ledger）无锁，并发请求互相覆盖（2026-10-25 实测丢 90+/103）。
   单人使用无此路径；测试侧用「一次 import 单次 save」根治。 */
const CSV_HEAD = ["企业名称", "年份", "市级", "区/县", "行业门类", "行业大类", "类别",
  "奖项/项目", "适用标准", "阶段", "结论", "得分", "评审角色", "报告日期", "现场日期", "备注"];
const csvCell = (v) => {
  const s = String(v ?? "");
  return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
};
async function importCsv(rows) {
  const lines = [CSV_HEAD.join(",")];
  for (const r of rows) lines.push(CSV_HEAD.map((h) => csvCell(r[h] ?? "")).join(","));
  const payload = Buffer.from("\uFEFF" + lines.join("\r\n"), "utf-8");   // BOM：utf-8-sig 友好
  const boundary = "----e2e" + Date.now();
  const buf = Buffer.concat([
    Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="e2e.csv"\r\nContent-Type: text/csv\r\n\r\n`),
    payload,
    Buffer.from(`\r\n--${boundary}--\r\n`),
  ]);
  const r = await fetch(BASE + "/api/import", {
    method: "POST",
    headers: { "Content-Type": `multipart/form-data; boundary=${boundary}` },
    body: buf,
    signal: AbortSignal.timeout(120000),
  });
  return r.json();
}
async function allCards() { return (await api("GET", "/api/projects?all=1")).j; }
async function cleanTestCards(mark) {
  const cards = await allCards();
  let n = 0;
  for (const c of cards) {
    if (String(c["企业名称"] || "").includes(mark)) { await rmCard(c.id); n++; }
  }
  return n;
}

/* ── 数据态守卫 ── */
let origMd5 = "";
let ORIG_IDS = [];               // 开跑时的台账卡集合快照（E7b 还原断言用，2026-11-02 动态化）
async function guardEnter() {
  origMd5 = md5(LEDGER);
  fs.copyFileSync(LEDGER, BAK);
}
function guardExit() {
  fs.copyFileSync(BAK, LEDGER);
  const now = md5(LEDGER);
  if (now !== origMd5) throw new Error(`ledger 还原后 md5 不一致（测试污染！）`);
  fs.unlinkSync(BAK);
}

/* ── 浏览器 ── */
async function newPage() {
  const browser = await chromium.launch({
    executablePath: EDGE,
    args: ["--no-proxy-server"],
  });
  const page = await browser.newPage();
  const jsErrors = [];
  page.on("pageerror", (e) => jsErrors.push(String(e)));
  return { browser, page, jsErrors };
}

/* ═══ E1 排序 + 阈值分页 + 图表防污染 ═══ */
async function e1Table(page) {
  console.log("\n── E1 表格：排序 + 阈值分页 + 图表防污染 ──");
  // 造 6 张混合卡（年份/得分/结论不同，供排序断言）——CSV 一次导入
  const mix = [
    { y: 2023, s: 92.5, c: "推荐" }, { y: 2025, s: 60, c: "暂缓" },
    { y: 2026, s: "", c: "不推荐" }, { y: 2024, s: 85, c: "推荐" },
    { y: 2025, s: "", c: "获奖" }, { y: 2026, s: 407.5, c: "推荐" },
  ];
  const t0 = Date.now();
  const irMix = await importCsv(mix.map((m, i) => ({
    ...BASE_ROW, "企业名称": `${ST}排序${i}`, "年份": m.y, "得分": m.s, "结论": m.c })));
  t("E1' 混合卡一次导入 6 张", (irMix.items || []).length === 6, JSON.stringify(irMix).slice(0, 80));
  console.log(`  (导入 6 张，${Date.now() - t0}ms)`);
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForSelector("#tb tr", { timeout: 10000 });
  await sleep(400);

  // ① 年份 asc/desc + 箭头
  await page.click('th.sortable[data-col="年份"]');
  await sleep(300);
  const asc = await page.$$eval("#tb tr td:nth-child(4)", (tds) => tds.map((x) => x.textContent.trim()));
  t("E1a 年份升序", JSON.stringify(asc) === JSON.stringify([...asc].sort()), asc.join(","));
  const arrowAsc = await page.$eval('th.sortable[data-col="年份"] .arrow', (a) => a.textContent);
  t("E1b 当前列箭头▲", arrowAsc === "▲", arrowAsc);
  await page.click('th.sortable[data-col="年份"]');
  await sleep(300);
  const desc = await page.$$eval("#tb tr td:nth-child(4)", (tds) => tds.map((x) => x.textContent.trim()));
  t("E1c 年份降序", JSON.stringify(desc) === JSON.stringify([...desc].sort().reverse()), desc.join(","));
  const arrowDesc = await page.$eval('th.sortable[data-col="年份"] .arrow', (a) => a.textContent);
  t("E1d 当前列箭头▼", arrowDesc === "▼", arrowDesc);

  // ② 得分数值序（非字符串序）+ 空值末位
  await page.click('th.sortable[data-col="得分"]');   // 换列 → asc
  await sleep(300);
  const scores = await page.$$eval("#tb tr td:nth-child(9)", (tds) => tds.map((x) => x.textContent.trim()));
  const nums = scores.map((s) => (s === "" || s === "—" ? Infinity : parseFloat(s)));
  const sorted = [...nums].sort((a, b) => a - b);
  t("E1e 得分数值序升", JSON.stringify(nums) === JSON.stringify(sorted), scores.join(","));
  t("E1f 空得分排最后", nums[nums.length - 1] === Infinity, scores[scores.length - 1]);

  // ③ 点「操作」列无反应
  const before = await page.$eval("#tb tr td:nth-child(2)", (x) => x.textContent);
  await page.click("th:not(.sortable)");
  await sleep(250);
  const after = await page.$eval("#tb tr td:nth-child(2)", (x) => x.textContent);
  t("E1g 操作列不可排（无变化）", before === after);

  // ④ 造到 105 条（CSV 一次导入 97 张——禁并发建卡，见 importCsv 注释）
  // 2026-11-02 美化包：基数动态取——用户真实卡不再干扰分页/图表断言（此前硬编码 105）
  const baseTotal = await page.evaluate(async () =>
    (await (await fetch("/api/projects")).json()).length);
  const totalExp = baseTotal + (PAGE_N - 8);
  const t1 = Date.now();
  const irPg = await importCsv(Array.from({ length: PAGE_N - 8 }, (_, i) => ({
    ...BASE_ROW, "企业名称": `${ST}分页${String(i).padStart(3, "0")}有限公司`, "年份": 2024 })));
  t("E1'2 分页卡一次导入 97 张", (irPg.items || []).length === PAGE_N - 8,
    `made=${(irPg.items || []).length}`);
  console.log(`  (导入 ${PAGE_N - 8} 张，${Date.now() - t1}ms)`);
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForSelector("#tb tr", { timeout: 10000 });
  await sleep(500);
  const rowsShown = await page.$$eval("#tb tr", (trs) => trs.length);
  t("E1h 105 条时首页渲染 100 行", rowsShown === 100, String(rowsShown));
  const info = await page.$eval("#pg-info", (x) => x.textContent);
  t("E1i 分页信息文案", new RegExp(`第 1/2 页 · 共 ${totalExp} 条`).test(info), info);
  const prevDisabled = await page.$eval("#pg-prev", (b) => b.disabled);
  t("E1j 首页 prev 禁用", prevDisabled === true);

  // ⑤ 翻页 + 边界
  await page.click("#pg-next");
  await sleep(400);
  const rows2 = await page.$$eval("#tb tr", (trs) => trs.length);
  t("E1k 第 2 页渲染剩余行", rows2 === totalExp - 100, String(rows2));
  const nextDisabled = await page.$eval("#pg-next", (b) => b.disabled);
  t("E1l 末页 next 禁用", nextDisabled === true);
  const prevUsable = await page.$eval("#pg-prev", (b) => b.disabled);
  t("E1m 第 2 页 prev 可用", prevUsable === false);

  // ⑥ 图表防污染（第 2 页 → 图表数据仍全量）
  await page.click('.tabs button[data-tab="charts"]');
  await sleep(900);
  const chartSum = await page.evaluate(() => {
    try {
      const inst = window.echarts && window.echarts.getInstanceByDom(document.getElementById("c-year"));
      const d = inst && inst.getOption().series[0].data;
      return d ? d.reduce((a, b) => a + (Number(b) || 0), 0) : null;
    } catch { return null; }
  });
  if (chartSum !== null) {
    t("E1n 图表数据全量（全量，非当前页切片）", chartSum === totalExp, String(chartSum));
  } else {
    const meta = await page.$eval("#meta, .meta", (x) => x.textContent).catch(() => "");
    t("E1n 图表数据全量（meta 降级验法）", new RegExp(`当前筛选 ${totalExp}`).test(meta), meta);
  }

  // ⑦ 翻页后改筛选 → 回第 1 页（先切回台账 tab——图表 tab 下表格视图隐藏）
  await page.click('.tabs button[data-tab="list"]');
  await sleep(500);
  await page.waitForSelector("#pg-prev", { state: "visible", timeout: 5000 });
  await page.click("#pg-prev");
  await sleep(300);
  await page.selectOption("#f-year", "2024");
  await sleep(500);
  const backFirst = await page.$eval("#pg-info", (x) => x.textContent);
  t("E1o 重筛回第 1 页", /第 1\//.test(backFirst), backFirst);

  // ⑧ 删到 ≤100 → 分页器隐藏
  const cards = (await allCards()).filter((c) => String(c["企业名称"]).includes(`${ST}分页`));
  for (const c of cards.slice(0, 8)) await rmCard(c.id);
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForSelector("#tb tr", { timeout: 10000 });
  await sleep(400);
  const pagerHidden = await page.$eval("#pager", (p) => p.hasAttribute("hidden"));
  t("E1p ≤100 条分页器隐藏", pagerHidden === true);
}

/* ═══ E2 搜索 + 防抖 ═══ */
async function e2Search(page) {
  console.log("\n── E2 搜索：字段命中 + 分词 AND + 防抖 ──");
  await page.fill("#f-kw", "");
  await sleep(300);
  // ① 单字段命中（阶段字段）——自适应读锦持真实阶段，不写死它的状态
  //    （2026-10-26 教训：写死「现场中」曾在台账被陈旧备份污染后误报 FAIL）
  const jinchiStage = (await allCards()).find((c) => c["id"] === "2026-SH-文审-001")?.["阶段"] || "报告已出";
  // 命中数按台账实算（不写死 1）：锦持阶段改过之后可能与另一张卡同阶段（如「归档」），
  // 写死会让这条断言变成数据态探针——2026-10-30 实测：锦持阶段改为「归档」后与五同撞车
  const stageN = (await allCards()).filter((c) => c["阶段"] === jinchiStage).length;
  await page.fill("#f-kw", jinchiStage);
  await sleep(600);
  let rows = await page.$$eval("#tb tr", (trs) => trs.length);
  t(`E2a 阶段字段命中（搜「${jinchiStage}」命中 ${stageN} 张）`,
    rows === stageN && rows >= 1, `${rows} / 期望 ${stageN}`);

  // ② 分词 AND（造甲/乙/甲乙三卡——企业名含关键词，命中「企业名称」字段）
  const irS = await importCsv([
    { ...BASE_ROW, "企业名称": `${ST}搜索甲独有`, "年份": 2024 },
    { ...BASE_ROW, "企业名称": `${ST}搜索乙独有`, "年份": 2024 },
    { ...BASE_ROW, "企业名称": `${ST}搜索甲乙都有`, "年份": 2024 },
  ]);
  t("E2' 搜索卡一次导入 3 张", (irS.items || []).length === 3);
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForSelector("#tb tr", { timeout: 10000 });
  await sleep(300);
  await page.fill("#f-kw", "甲乙");
  await sleep(600);
  rows = await page.$$eval("#tb tr", (trs) => trs.length);
  t("E2b 分词 AND（仅两词都命中）", rows === 1, String(rows));

  // ③ 防抖探针
  await page.fill("#f-kw", "");
  await sleep(400);
  await page.evaluate(() => {
    window.__n = 0;
    const o = window.apply;
    window.apply = function () { window.__n++; return o.apply(this, arguments); };
  });
  await page.fill("#f-kw", "甲");
  await page.fill("#f-kw", "甲乙");
  await page.fill("#f-kw", "甲乙都");
  const n0 = await page.evaluate(() => window.__n);
  await sleep(500);
  const n1 = await page.evaluate(() => window.__n);
  t("E2c 200ms 防抖（5 字符 delta=1）", n0 === 0 && n1 === 1, `n0=${n0} n1=${n1}`);

  // ④ 重置立即生效
  await page.click("#f-reset");
  await sleep(400);
  const kw = await page.$eval("#f-kw", (x) => x.value);
  const all = await page.$$eval("#tb tr", (trs) => trs.length);
  t("E2d 重置清空且立即生效", kw === "" && all > 10, `kw="${kw}" rows=${all}`);
}

/* ═══ E3 弹窗统一 + 键盘 ═══ */
async function e3Dialogs(page) {
  console.log("\n── E3 弹窗：toast/confirm/零原生 dialog/Ctrl+Enter ──");
  let nativeDialogs = 0;
  page.on("dialog", async (d) => { nativeDialogs++; await d.dismiss().catch(() => {}); });

  // ① toast 显隐
  await page.evaluate(() => ui.toast("E2E 测试 toast 内容"));
  await sleep(300);
  const toastShown = await page.$(".toast") !== null || await page.$("#toast") !== null
    || (await page.evaluate(() => document.body.innerText.includes("E2E 测试 toast 内容")));
  t("E3a toast 显示", toastShown);
  await sleep(4200);
  const toastGone = await page.evaluate(() => !document.body.innerText.includes("E2E 测试 toast 内容"));
  t("E3b toast 自动消失（3.6s）", toastGone);

  // ② confirm 三路径（Promise 化）——按钮查找必须限定在 .uiconfirm 遮罩内：
  //    页面存在静态「确定」(#noteModalOk)/「取消」(#clauseCancel/#placeCancel) 按钮，文档序在
  //    动态 confirm 之前，全局 find 会点错按钮导致 promise 永不 resolve（2026-10-26 修复挂死）
  const conf = await page.evaluate(async () => {
    const p = ui.confirm("确定吗");
    const m = [...document.querySelectorAll(".uiconfirm")].pop();
    [...m.querySelectorAll("button")].find((b) => b.textContent === "确定").click();
    return await p;
  });
  t("E3c confirm 确定=true", conf === true, String(conf));
  const conf2 = await page.evaluate(async () => {
    const p = ui.confirm("取消吗");
    const m = [...document.querySelectorAll(".uiconfirm")].pop();
    [...m.querySelectorAll("button")].find((b) => b.textContent === "取消").click();
    return await p;
  });
  t("E3d confirm 取消=false", conf2 === false, String(conf2));
  const conf3 = await page.evaluate(async () => {
    const p = ui.confirm("遮罩吗");
    const m = [...document.querySelectorAll(".uiconfirm")].pop();
    m.click();                       // 产品遮罩即 .uiconfirm 本体（e.target===遮罩 → 取消）
    return await p;
  });
  t("E3e confirm 遮罩=false（可取消）", conf3 === false, String(conf3));

  // ③ 批量关联真实链路 + 零原生 dialog
  const linkBtn = await page.$("#auto-link, [id*=auto][id*=link], #batch-link");
  if (linkBtn) {
    await page.evaluate(() => {
      window.__dialogs = 0;
      const origAlert = window.alert, origConfirm = window.confirm;
      window.alert = () => { window.__dialogs++; };
      window.confirm = () => { window.__dialogs++; return true; };
    });
    await linkBtn.click();
    // 产品确认弹窗是 .uiconfirm（无 id、无 .cf-foot），旧选择器 "[id*=confirm] button" 永远匹配不到，
    // confirm 会残留遮罩挡住后续所有点击（2026-10-26 修复）：等遮罩出现 → 点遮罩内「确定」→ 等结果 toast 消散
    await page.waitForSelector(".uiconfirm", { timeout: 5000 });
    await page.evaluate(() => {
      const m = [...document.querySelectorAll(".uiconfirm")].pop();
      [...m.querySelectorAll("button")].find((b) => b.textContent === "确定")?.click();
    });
    await page.waitForSelector(".toast", { timeout: 10000 }).catch(() => { });
    await sleep(4200);
    const dlg = await page.evaluate(() => window.__dialogs || 0);
    t("E3f 批量关联全程零原生 dialog", dlg === 0, String(dlg));
  } else {
    t("E3f 批量关联入口不在当前视图（跳过，不改结论）", true, "未找到按钮");
  }
  t("E3g 全程无原生 dialog 事件", nativeDialogs === 0, String(nativeDialogs));

  // ④ Ctrl+Enter 三态路由（打开核实窗体 → Ctrl+Enter 走保存）
  //    自建「现场评审」测试卡 + 最小现场 MD（2026-10-26）：不再点首行依赖真实卡状态——
  //    锦持回到文件评审后「进入现场评审」禁用是正确产品行为；且 opane 需要
  //    来源文件指向 30 库现场 MD 才打开（端点 _find_onsite_report 规则）
  const e3md = path.join(MD30, "20260825-" + ST + ".md");
  fs.writeFileSync(e3md, [
    "---", "标准: GBT19580 卓越", `企业名称: ${ST}`, "现场日期: 2024-10-25", "---", "",
    `# ${ST} · 现场评审`, "", "## 现场核实信息", "", "### 4.2 战略", "",
    "- 优势：", "- 可改进之处：", "- 现场核实：", "",
  ].join("\n"), "utf-8");
  const e3card = await api("POST", "/api/projects", { fields: {
    ...BASE_ROW, "类别": ["现场评审"], "企业名称": `${ST}键盘路由`, "年份": 2024,
    "来源文件": ["政府质量奖-现场评审库/20260825-" + ST + ".md"] } });
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForSelector("#tb tr", { timeout: 10000 });
  // 总量 >100 时翻页器会把排末尾的新卡挤到第 2 页（DOM 无此行）——
  // 用搜索过滤（自动回第 1 页）把新卡带出来（2026-10-26）
  await page.fill("#f-kw", `${ST}键盘路由`);
  await sleep(500);
  await page.click(`#tb tr[data-id="${e3card.j.id}"]`);
  await sleep(800);
  await page.evaluate(() => {
    const btns = [...document.querySelectorAll("#m-tabs button, .tabs button")];
    const o = btns.find((b) => /现场/.test(b.textContent || ""));
    if (o && !o.disabled) o.click();
  });
  await sleep(600);
  const saved = await page.evaluate(() => {
    window.__saved = 0;
    if (typeof opaneSaveNotes === "function") {
      const o = opaneSaveNotes;
      window.opaneSaveNotes = function () { window.__saved++; return o.apply(this, arguments); };
      return typeof o === "function";
    }
    return false;
  });
  if (saved) {
    await page.keyboard.press("Control+Enter");
    await sleep(600);
    const n = await page.evaluate(() => window.__saved || 0);
    t("E3h Ctrl+Enter 触发保存（核实窗体可见）", n >= 1, String(n));
  } else {
    t("E3h Ctrl+Enter 路由（当前项目无现场窗体，跳过）", true, "opane 未初始化");
  }

  // ⑤ 派生伪条目（2026-10-27 用户定）：细条款按前两段命中「## 主要优势」/「## 主要改进建议」
  //    的 H3 大条款 → 「我负责的条款」末尾追加「报告主要优势条款·4.3 / 报告主要建议条款·4.5」；
  //    伪优势条目优势栏显示节全文、细条款优势栏回退用块内「文审优势」行；首次保存伪条目核实
  //    内容 → MD 建标准三行块；重开 → 往返（条款号/核实内容重读正确）+ 去重（不重复追加）
  await cleanTestCards(`${ST}派生`);
  const dvMd = path.join(MD30, "20260827-" + ST + "派生.md");
  fs.writeFileSync(dvMd, [
    "---", "标准: GBT19580 卓越", `企业名称: ${ST}派生`, "现场日期: 2026-08-27", "---", "",
    `# ${ST}派生 · 现场评审`, "",
    "## 主要优势", "", "### 4.3 顾客与市场", "", "#### 深耕顾客细分市场", "",
    "公司**实施**顾客细分方法，建立顾客信息库。", "",
    "## 主要改进建议", "", "### 4.5 过程管理", "", "**建议完善过程管理制度引用。**", "",
    "## 现场核实信息", "", "### 4.3.2 顾客和市场的了解", "",
    "相关条款：[[GBT19580-卓越-4.3.2顾客和市场的了解]]", "",
    "- 文审优势：块内自有优势：按区域细分四大市场。", "- 可改进之处：建议展开需求了解方法。", "- 现场核实：", "",
    "### 4.5.1 过程管理的实施", "", "- 可改进之处：建议补充过程绩效指标。", "- 现场核实：", "",
  ].join("\n"), "utf-8");
  const dvCard = await api("POST", "/api/projects", { fields: {
    ...BASE_ROW, "类别": ["现场评审"], "企业名称": `${ST}派生`, "年份": 2024,
    "来源文件": ["政府质量奖-现场评审库/20260827-" + ST + "派生.md"] } });
  const openDvPane = async () => {
    await page.reload({ waitUntil: "networkidle" });
    await page.waitForSelector("#tb tr", { timeout: 10000 });
    await page.fill("#f-kw", `${ST}派生`);
    await sleep(500);
    await page.click(`#tb tr[data-id="${dvCard.j.id}"]`);
    await sleep(800);
    await page.evaluate(() => {
      const btns = [...document.querySelectorAll("#m-tabs button, .tabs button")];
      const o = btns.find((b) => /现场/.test(b.textContent || ""));
      if (o && !o.disabled) o.click();
    });
    await sleep(1200);
  };
  // 选中条款后左栏自动折叠（产品行为：.opane-left.collapsed .opane-list{display:none}）——
  // 点下一条前先点「条款 ›」展开（走真实用户路径，不用 evaluate 硬点隐藏元素）
  const opanePickTerm = async (no) => {
    await page.evaluate(() => { $("opaneExpand")?.click(); });
    await sleep(200);
    await page.click(`#opaneList .opane-term[data-no="${no}"]`);
    await sleep(300);
  };
  await openDvPane();
  const leftText = await page.$eval("#opaneList", (x) => x.innerText);
  t("E3i1 左栏追加伪优势条目「报告主要优势条款·4.3 顾客与市场」",
    leftText.includes("报告主要优势条款·4.3") && leftText.includes("顾客与市场"),
    leftText.slice(0, 120).replace(/\n/g, " "));
  t("E3i2 左栏追加伪建议条目「报告主要建议条款·4.5 过程管理」",
    leftText.includes("报告主要建议条款·4.5") && leftText.includes("过程管理"));
  const leftCount = await page.$$eval("#opaneList .opane-term", (els) =>
    els.filter((e) => (e.dataset.no || "") === "报告主要优势条款·4.3").length);
  t("E3i3 伪优势条目只出现一次（不重复）", leftCount === 1, String(leftCount));
  // 伪优势条目：优势栏 = 主要优势节全文
  await opanePickTerm("报告主要优势条款·4.3");
  const advMain = await page.$eval("#opaneMain", (x) => x.innerText);
  t("E3i4 伪优势条目优势栏显示节全文（深耕顾客细分市场）",
    advMain.includes("深耕顾客细分市场") && advMain.includes("顾客信息库"),
    advMain.slice(0, 80).replace(/\n/g, " "));
  // 细条款：优势栏回退用块内自己的「文审优势」行（非节全文）
  await opanePickTerm("4.3.2");
  const realMain = await page.$eval("#opaneMain", (x) => x.innerText);
  t("E3i5 细条款优势栏回退用块内文审优势行（非节全文）",
    realMain.includes("块内自有优势") && !realMain.includes("深耕顾客细分市场"),
    realMain.slice(0, 80).replace(/\n/g, " "));
  // 伪建议条目：内容进「可改进之处」栏
  await opanePickTerm("报告主要建议条款·4.5");
  const sugMain = await page.$eval("#opaneMain", (x) => x.innerText);
  t("E3i6 伪建议条目内容进可改进之处栏",
    sugMain.includes("建议完善过程管理制度引用"), sugMain.slice(0, 80).replace(/\n/g, " "));
  // 首次保存伪条目核实内容 → MD 落盘完整三行（2026-10-28 用户定内容落盘：
  // 可改进之处行=主要改进建议节全文，优势行留空；现场核实行=填写内容）
  await page.fill("#opaneMain .opane-note", "E2E伪条目核实内容");
  await page.click("#opaneSave");
  await sleep(1500);
  const dvTxt = fs.readFileSync(dvMd, "utf-8");
  t("E3i7 保存落盘：### 报告主要建议条款·4.5 + 可改进之处=节全文 + 现场核实行",
    dvTxt.includes("### 报告主要建议条款·4.5 过程管理")
    && dvTxt.includes("- 可改进之处：建议完善过程管理制度引用。")
    && dvTxt.includes("- 现场核实：E2E伪条目核实内容"),
    dvTxt.slice(dvTxt.indexOf("### 报告主要建议"), 140).replace(/\n/g, "⏎"));
  // 重开核实窗体 → 去重（伪条目仍只一条）+ 往返（现场核实内容重读正确）
  await openDvPane();
  const rt = await page.evaluate(() => {
    const els = [...document.querySelectorAll("#opaneList .opane-term")];
    return { sug: els.filter((e) => e.dataset.no === "报告主要建议条款·4.5").length,
             adv: els.filter((e) => e.dataset.no === "报告主要优势条款·4.3").length,
             total: els.length };
  });
  t("E3i8 重开后伪条目各只一条（去重）", rt.sug === 1 && rt.adv === 1, JSON.stringify(rt));
  await opanePickTerm("报告主要建议条款·4.5");
  const noteVal = await page.$eval("#opaneMain .opane-note", (x) => x.value);
  t("E3i9 伪条目现场核实内容往返（重读=保存值）",
    noteVal === "E2E伪条目核实内容", noteVal);
  await rmCard(dvCard.j.id);
  fs.unlinkSync(dvMd);
  // 关核实窗体 + 报告弹窗（开着会遮住台账工具栏，#f-reset 点不到——2026-10-27 修复）
  await page.evaluate(() => { $("opaneClose")?.click(); closeReport(); });
  await sleep(300);
  await page.click("#f-reset");
  await sleep(400);
}

/* ═══ E4 条款回填全链 ═══ */
async function e4ClauseBackfill(page, jsErrors) {
  console.log("\n── E4 条款回填：提取→猜测→归位→写入→分节 ──");
  if (!fs.existsSync(path.join(FIX, "B45条款样本.docx"))) {
    console.log("  fixtures 缺失，请先跑 test/make_docx.py");
    return;
  }
  await cleanTestCards(ST);
  // 「现场评审」只为启用报告窗体的复盘 tab（E5 依赖）；现场阶段判定取类别首个元素，本卡仍是文件评审
  //   → 文审态（工具栏带粘贴入口、写入目标默认文审 20 库），提取/写入链路不受影响
  const mk = await mkCard({ "企业名称": ST, "年份": 2024, "类别": ["文件评审", "现场评审"],
    "市级": "上海市", "区/县": "浦东新区", "行业门类": "制造业", "行业大类": "C34 通用设备制造业",
    "奖项/项目": "区政府质量奖", "适用标准": "GBT19580 卓越", "报告日期": "2024-10-25" });
  const pid = mk.j.id;
  t("E4a 建测试卡", !!pid, String(pid));

  await page.reload({ waitUntil: "networkidle" });
  await page.waitForSelector(`#tb tr[data-id="${pid}"]`, { timeout: 10000 });
  await page.click(`#tb tr[data-id="${pid}"]`);
  await sleep(900);

  // 提取（须先点「提取 Word」按钮：#extract-file 由 renderExtractInto 动态渲染，
  //    直接 evaluate 强制 display:block 不会初始化，setInputFiles 会超时——2026-10-26 修复）
  await page.click("#e-extract-btn");
  await sleep(200);
  await page.setInputFiles("#extract-file", path.join(FIX, "B45条款样本.docx"));
  await page.waitForSelector("#extract-write", { timeout: 20000 });
  await sleep(400);
  t("E4b 提取完成（按钮出现）", true);
  // 归位按钮改名（2026-10-28 用户定）：归口在后续写入弹窗里选，名字不预设文审
  const wbtnText = await page.$eval("#extract-write", (b) => b.textContent.trim());
  t("E4b2 归位按钮改名「条款归位并写入报告」", wbtnText === "条款归位并写入报告", wbtnText);

  // 写入 → 归位弹窗 → 默认猜测
  await page.click("#extract-write");
  await sleep(600);
  const clauseVisible = await page.$eval("#clauseModal", (m) => m.style.display === "flex");
  t("E4c 归位弹窗打开", clauseVisible);
  const guesses = await page.$$eval("#clauseBody select", (sels) => sels.map((s) => s.value));
  t("E4d 默认猜测（战略→4.2、顾客→4.3）",
    guesses[0] === "4.2" && guesses[1] === "4.3", guesses.join(","));

  // 确认归位 → 直接进写入弹窗（2026-10-27 用户定：上传/写入流程不再灵魂考问，考问收敛为复盘 tab 专属）
  await page.click("#clauseOk");
  await sleep(500);
  const soulGone = await page.$eval("#soulModal", (m) => m.style.display !== "flex");
  t("E4e 归位确认后不进灵魂考问", soulGone);
  const placeVisible = await page.$eval("#placeModal", (m) => m.style.display === "flex");
  // 2026-11-02 老张定：归位确认后直接写入，不再弹写入确认窗
  t("E4f 归位确认后直接写入（不弹写入确认窗）", !placeVisible);
  // 写入目标按阶段锁定（2026-10-27 用户定：报告归口唯一化，不允许双存）——
  // 本卡文审态（类别首元素=文件评审、阶段未到现场）：锁「文审报告（20 库）」，现场按钮变灰不可选
  const lockW = await page.evaluate(() => {
    const btns = [...document.querySelectorAll("#placeForm .pv-btn")];
    const wen = btns.find((b) => b.dataset.t === ""), xian = btns.find((b) => b.dataset.t === "现场");
    return { wenDisabled: wen.disabled, wenActive: wen.classList.contains("active"),
             xianDisabled: xian.disabled, xianActive: xian.classList.contains("active") };
  });
  t("E4f2 文审态锁定：现场按钮 disabled 变灰不可选",
    lockW.wenDisabled === false && lockW.wenActive === true
    && lockW.xianDisabled === true && lockW.xianActive === false, JSON.stringify(lockW));
  // 2026-11-02 老张定：写入自动进行——等「已写入：」toast 即完成信号（替代旧 placeOk 点击）
  await page.waitForFunction(
    () => [...document.querySelectorAll(".toast")].some((x) => (x.textContent || "").includes("已写入")),
    { timeout: 20000 });
  await sleep(400);

  // 写入成功：写入弹窗 + 报告窗体都关（2026-10-27 用户定：确认写入后后面的窗口也自动关闭）
  const modalsClosed = await page.evaluate(() =>
    $("placeModal").style.display === "none" && $("reportModal").style.display === "none");
  t("E4f3 写入成功后 placeModal+reportModal 都关闭", modalsClosed);

  // MD 断言
  const mdPath = path.join(MD20, "20241025-" + ST + ".md");
  const md = fs.existsSync(mdPath) ? fs.readFileSync(mdPath, "utf-8") : "";
  t("E4g 写入文审 MD", md.length > 0, mdPath);
  t("E4h 条款分节 4.2/4.3", md.includes("### 4.2") && md.includes("### 4.3"));
  t("E4i 加粗片段保留", md.includes("**技术创新驱动") || md.includes("**“技术创新驱动"));
  t("E4j 提取日志行", /\d{4}-\d{2}-\d{2}.{0,40}提取自/.test(md));
  t("E4k 概述进 H4 小节标题（2026-10-27 新格式，bullet 行已不在）",
    /#### 战略引领发展/.test(md) || /#### （一）战略/.test(md));

  // 重跑保护：手写节不被覆盖（写入后报告窗体已关——重开项目再走提取链）
  fs.appendFileSync(mdPath, "\n## 复盘沉淀\n\n手写防覆盖标记-xyz123\n");
  await page.click(`#tb tr[data-id="${pid}"]`);
  await sleep(900);
  await page.click("#e-extract-btn");
  await sleep(200);
  await page.setInputFiles("#extract-file", path.join(FIX, "B45条款样本.docx"));
  await page.waitForSelector("#extract-write", { timeout: 20000 });
  await page.click("#extract-write");
  await sleep(500);
  await page.click("#clauseOk");
  await sleep(400);
  // 2026-11-02 老张定：归位确认后直接写入（不再弹写入确认窗）——等完成 toast
  await page.waitForFunction(
    () => [...document.querySelectorAll(".toast")].some((x) => (x.textContent || "").includes("已写入")),
    { timeout: 20000 });
  await sleep(2500);
  const md2 = fs.readFileSync(mdPath, "utf-8");
  t("E4l 重跑不碰手写节（复盘沉淀保留）", md2.includes("手写防覆盖标记-xyz123"));
  t("E4m 重跑再留一条提取日志", (md2.match(/提取自/g) || []).length >= 2,
    String((md2.match(/提取自/g) || []).length));

  // 现场态：目标锁「现场报告终版」+ 现场日期从 30 库文件名自动带出（2026-10-27 用户定）。
  // 卡片「现场日期」故意填成不同日期，验证优先级 ①30 库文件名日期 ② 卡片字段
  const osMd = path.join(MD30, "20260930-" + ST + ".md");
  fs.writeFileSync(osMd, [
    "---", "标准: GBT19580 卓越", `企业名称: ${ST}`, "现场日期: 2026-09-30", "---", "",
    `# ${ST} · 现场评审`, "", "## 现场核实信息", "", "### 4.2 战略", "", "- 现场核实：", "",
  ].join("\n"), "utf-8");
  const osCard = await mkCard({ ...BASE_ROW, "类别": ["现场评审"], "企业名称": `${ST}现场锁定`,
    "年份": 2024, "现场日期": "2026-01-01", "阶段": "现场中",
    "来源文件": ["政府质量奖-现场评审库/20260930-" + ST + ".md"] });
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForSelector("#tb tr", { timeout: 10000 });
  await page.fill("#f-kw", `${ST}现场锁定`);
  await sleep(500);
  await page.click(`#tb tr[data-id="${osCard.j.id}"]`);
  await sleep(800);
  const lockO = await page.evaluate(async () => {
    CUR_EXTRACT = { "意见结论": { "主要优势": [], "主要改进建议": [] }, "模式": [] };
    await openPlaceModal();
    const btns = [...document.querySelectorAll("#placeForm .pv-btn")];
    const wen = btns.find((b) => b.dataset.t === ""), xian = btns.find((b) => b.dataset.t === "现场");
    return { wenDisabled: wen.disabled, wenActive: wen.classList.contains("active"),
             xianDisabled: xian.disabled, xianActive: xian.classList.contains("active"),
             date: $("place-date").value, intro: $("place-intro").textContent };
  });
  t("E4n 现场态锁定：文审按钮 disabled 变灰、现场按钮可选",
    lockO.wenDisabled === true && lockO.wenActive === false
    && lockO.xianDisabled === false && lockO.xianActive === true, JSON.stringify(lockO));
  t("E4n2 现场日期自动带出取 30 库文件名日期（优先于卡片字段）",
    lockO.date === "2026-09-30", lockO.date);
  t("E4n3 写入引导明示「更新已有现场报告」", /20260930-/.test(lockO.intro), lockO.intro.slice(0, 50));
  await page.evaluate(() => { $("placeCancel").click(); closeReport(); });
  await rmCard(osCard.j.id);
  fs.unlinkSync(osMd);
  await page.click("#f-reset");   // 清掉搜索过滤，别把后续 E5/E6 的项目行滤没
  await sleep(500);

  t("E4o E4 段无 JS 错", jsErrors.length === 0, jsErrors[0] || "");
  return { pid, mdPath };
}

/* ═══ E5 灵魂考问 + 复盘 tab + 模式草稿 ═══ */
async function e5SoulAndMode(page, ctx) {
  console.log("\n── E5 复盘：门禁三态 + 灵魂考问答题 + 独立补写 + 模式草稿 ──");
  const { pid } = ctx;
  // ⓪ 阶段一写入后复盘 tab 仍禁用（2026-10-28 用户定）：阶段一（勾选条款→/api/write-onsite）
  //    只做条款核实与信息导出，产物虽含 30 库现场报告，门禁信号源「终版已写」不置位。
  //    E4 卡的来源还只有文审 MD → 先真实走一次阶段一写入，复盘 tab 必须保持灰。
  const w1 = await api("POST", "/api/write-onsite",
    { id: pid, "企业名称": ST, "现场日期": "2026-08-25", "结论": "", "勾选条款": [] });
  t("E5a0a 阶段一 write-onsite ok", w1.j.ok === true, JSON.stringify(w1.j).slice(0, 100));
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForSelector("#tb tr", { timeout: 10000 });
  await page.click(`#tb tr[data-id="${pid}"]`);
  await sleep(900);
  const gateStage1 = await page.$eval('#m-tabs button[data-v="review"]', (b) => b.disabled);
  t("E5a0 阶段一写入后复盘 tab 仍禁用（write-onsite 产物不放开）",
    gateStage1 === true, String(gateStage1));
  const cStage1 = (await allCards()).find((c) => c.id === pid);
  t("E5a0b 阶段一不置终版已写（API 复核）", !cStage1["终版已写"], String(cStage1["终版已写"]));
  await page.evaluate(() => { closeReport(); });
  await sleep(300);
  // ⓵ 即时开启 + 切卡重置（终版写入前；2026-10-28 用户定「上传终版 Word 当时就开启」）：
  //    现场态卡完成 Word 文字提取 → 复盘 tab 即开；切到另一卡即时信号重置、回灰；
  //    终版写入后才由卡片「终版已写」字段持久接住。
  await api("PUT", "/api/projects/" + encodeURIComponent(pid), { fields: { "类别": ["现场评审"] } });
  // 前端 DATA 是内存副本：PUT 后必须 reload 让 CUR 反映新类别（否则 openPlaceModal
  // 按旧类别判文审态、写入目标锁错——2026-10-28 实测抓过这个坑）
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForSelector("#tb tr", { timeout: 10000 });
  await sleep(400);
  await page.click(`#tb tr[data-id="${pid}"]`);
  await sleep(900);
  await page.click("#e-extract-btn");
  await sleep(200);
  await page.setInputFiles("#extract-file", path.join(FIX, "B45条款样本.docx"));
  await page.waitForSelector("#extract-write", { timeout: 20000 });
  await sleep(400);
  // 2026-10-30 用户最终拍板【旧约定改掉】：提取终版 Word 完成 = 现场核实活干完了
  // ——只用来**关**「进入现场评审环节」，**不再**用来开「复盘」；复盘只认「终版已写」
  const gateLive = await page.evaluate(() => {
    const rv = document.querySelector('#m-tabs button[data-v="review"]');
    const os = document.querySelector('#m-tabs button[data-v="onsite"]');
    return { review: rv.disabled, onsite: os.disabled, osTitle: os.title };
  });
  t("E5g0 提取终版 Word 后：现场核实环节变灰（上传即视为活干完）",
    gateLive.onsite === true, JSON.stringify(gateLive));
  t("E5g0a 提取后未写入：复盘 tab 仍禁用（只认「终版已写」，不再即时开启）",
    gateLive.review === true, String(gateLive.review));
  t("E5g0a2 变灰文案引导去写入终版（不出现「终版已写入（）」空括号）",
    /终版 Word 已上传/.test(gateLive.osTitle) && !/（）/.test(gateLive.osTitle),
    gateLive.osTitle);
  // 切到另一张现场态卡（无终版已写）：即时信号重置 → 复盘 tab 回灰
  const cut = await mkCard({ ...BASE_ROW, "类别": ["现场评审"], "企业名称": `${ST}切卡重置`,
    "年份": 2024, "现场日期": "2026-08-25" });
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForSelector("#tb tr", { timeout: 10000 });
  await page.click(`#tb tr[data-id="${cut.j.id}"]`);
  await sleep(900);
  const gateCut = await page.$eval('#m-tabs button[data-v="review"]', (b) => b.disabled);
  t("E5g0b 切到另一卡：即时信号重置，复盘 tab 禁用", gateCut === true, String(gateCut));
  await page.evaluate(() => { closeReport(); });   // 先关报告窗体，否则遮罩挡住表格行点击
  await sleep(300);
  // 切回原卡：未写终版 → 仍灰（即时信号不跨卡、不持久）
  await page.click(`#tb tr[data-id="${pid}"]`);
  await sleep(900);
  const gateBack = await page.$eval('#m-tabs button[data-v="review"]', (b) => b.disabled);
  t("E5g0c 切回原卡未写入：复盘 tab 仍禁用", gateBack === true, String(gateBack));
  await rmCard(cut.j.id);
  await sleep(200);
  // 重开原卡再提取一次 → 即时开启复现
  await page.click("#e-extract-btn");
  await sleep(200);
  await page.setInputFiles("#extract-file", path.join(FIX, "B45条款样本.docx"));
  await page.waitForSelector("#extract-write", { timeout: 20000 });
  await sleep(400);
  const gateLive2 = await page.evaluate(() => {
    const rv = document.querySelector('#m-tabs button[data-v="review"]');
    const os = document.querySelector('#m-tabs button[data-v="onsite"]');
    return { review: rv.disabled, onsite: os.disabled };
  });
  t("E5g0d 再提取：现场核实环节仍灰 + 复盘 tab 仍禁用（未写入）",
    gateLive2.onsite === true && gateLive2.review === true, JSON.stringify(gateLive2));

  // ⓶ 终版写入（2026-10-30 用户最终拍板）：现场态卡走「写入现场报告终版（30 库）」——
  //    placeModal 关、**报告窗体不关**（自动切到复盘页，复盘零跳转），toast 引导复盘四步；
  //    写入后复盘门禁由「终版已写」接住
  await page.click("#extract-write");
  await sleep(500);
  // 钩住 ui.toast 捕获引导文案——必须先于 clauseOk（2026-11-02 老张定：归位确认后即自动写入）
  await page.evaluate(() => {
    window.__toasts = [];
    const orig = ui.toast;
    ui.toast = function (m) { window.__toasts.push(String(m)); return orig.apply(this, arguments); };
  });
  await page.click("#clauseOk");
  await sleep(400);
  const lockFinal = await page.evaluate(() => {
    const btns = [...document.querySelectorAll("#placeForm .pv-btn")];
    const xian = btns.find((b) => b.dataset.t === "现场");
    return { xianDisabled: xian.disabled, xianActive: xian.classList.contains("active") };
  });
  t("E5h 现场态锁定：写入目标=现场报告终版（30 库）",
    lockFinal.xianDisabled === false && lockFinal.xianActive === true, JSON.stringify(lockFinal));
  // 2026-11-02 老张定：归位确认后直接写入；终版写入后直接关闭报告窗体（复盘可随时从台账重开）
  await page.waitForFunction(
    () => [...document.querySelectorAll(".toast")].some((x) => (x.textContent || "").includes("已写入")),
    { timeout: 20000 });
  await sleep(600);
  const finalWrite = await page.evaluate(() => {
    return {
      placeClosed: $("placeModal").style.display === "none",
      reportClosed: $("reportModal").style.display === "none",
      toasts: window.__toasts || [],
    };
  });
  t("E5h2 终版写入：placeModal 关 / 报告窗体直接关闭（2026-11-02 老张定）",
    finalWrite.placeClosed === true && finalWrite.reportClosed === true, JSON.stringify(finalWrite));
  t("E5h3 终版 toast 引导复盘四步（做法/模式/四问/归档）",
    finalWrite.toasts.some((x) => x.includes("终版报告已生成") && x.includes("已进入复盘")
      && x.includes("归档")),
    JSON.stringify(finalWrite.toasts).slice(0, 120));
  // 终版写入后：复盘 tab 开启（信号源=卡片「终版已写」，写入日期由后端回填）
  // （窗体已关——从台账重开卡拿新门禁，下一步流程自己点复盘 tab）
  await page.click(`#tb tr[data-id="${pid}"]`);
  await sleep(1200);
  const gateFinal = await page.$eval('#m-tabs button[data-v="review"]', (b) => b.disabled);
  t("E5a1 终版写入后复盘 tab 开启（信号源=终版已写）", gateFinal === false, String(gateFinal));
  const cFinal = (await allCards()).find((c) => c.id === pid);
  t("E5a1b 终版已写=写入日期（API 复核）", cFinal["终版已写"] === "2026-08-25",
    String(cFinal["终版已写"]));
  // ② 复盘 tab 独立灵魂考问（四问都答）——写 srcs[0]=终版写入后的现场 MD
  const osRel = (cFinal["来源文件"] || [])[0] || "";
  const mdPath = path.join(VAULT, osRel);
  await page.evaluate(() => {
    document.querySelector('#m-tabs button[data-v="review"]').click();
  });
  await sleep(1000);
  const rvSoul = await page.$("#rv-soul");
  if (!rvSoul) {
    t("E5a 复盘 tab 入口未渲染", false, "现场 MD 来源已配，入口应渲染");
  } else {
    await rvSoul.click();
    await sleep(500);
    const soulOpen = await page.$eval("#soulModal", (m) => m.style.display === "flex");
    t("E5a 复盘 tab 独立考问打开", soulOpen);
    const answers = ["E2E长见识：再制造旧件溯源比想象中粗。", "E2E校准：4.4.3 是展示问题实质不弱。",
      "E2E提炼：战略解码机制可直接搬用。", "E2E避雷：差点把展示不足误判为管理弱项。"];
    for (let i = 0; i < 4; i++) {
      await page.fill("#soulInput", answers[i]);
      await page.click("#soulNext");
      await sleep(350);
    }
    await sleep(600);
    const md = fs.existsSync(mdPath) ? fs.readFileSync(mdPath, "utf-8") : "";
    t("E5b 四问答案进复盘沉淀", md.includes("E2E长见识") && md.includes("E2E避雷"));
    // 2026-10-27 起考问收敛为复盘 tab 专属：经 review-note 落「复盘沉淀」节 callout
    // （写入流程不再产「复盘 · 灵魂考问」callout——那正是全「（未答）」空模板的来源）
    t("E5c 灵魂考问 callout 格式（复盘沉淀节）",
      /\[!note\]-\s*\d{4}-\d{2}-\d{2}\s+复盘沉淀/.test(md) && md.includes("> **Q1 长见识**"));
  }

  // ① 做法确认（2026-10-30：归档门禁要求三步留痕——此前 e2e 只做了四问与模式草稿，
  //    缺这一步归档按钮是 disabled 的；同时覆盖 R2 整条/摘句与 R4 同日去重）
  await page.evaluate(() => { document.querySelector('#m-tabs button[data-v="review"]').click(); });
  await sleep(1200);
  const confirmBtn = await page.$("#rv-confirm");
  // 用**本地**日期（后端写入的是本地日期；toISOString 取的是 UTC，跨日边界会差一天）
  const _d = new Date();
  const today2 = `${_d.getFullYear()}-${String(_d.getMonth() + 1).padStart(2, "0")}-${String(_d.getDate()).padStart(2, "0")}`;
  if (!confirmBtn) {
    t("E5p 做法确认按钮未渲染", false, "复盘 tab 应渲染做法确认按钮");
  } else {
    const cks = await page.$$(".rv-ck");
    t("E5p1 R2 终版正文（无加粗）也能出可勾选项", cks.length > 0, String(cks.length));
    const kinds = await page.$$eval(".rv-ck",
      (els) => els.slice(0, 3).map((e) => e.parentElement.textContent.slice(0, 10)));
    t("E5p2 R2 清单提供「整条」粒度（首个选项带【整条】）",
      kinds.length > 0 && kinds[0].includes("【整条】"), JSON.stringify(kinds));
    if (cks.length) await cks[0].check();
    await confirmBtn.click();
    await sleep(1500);
    const mdP = fs.existsSync(mdPath) ? fs.readFileSync(mdPath, "utf-8") : "";
    t("E5p3 做法确认落痕（callout 进「复盘沉淀」节）",
      /做法确认（\d+ 条）/.test(mdP), mdP.slice(-120));
    t("E5p4 台账「做法确认」=今天",
      ((await allCards()).find((c) => c.id === pid) || {})["做法确认"] === today2,
      String(((await allCards()).find((c) => c.id === pid) || {})["做法确认"]));
    // R4 同日再确认一次 → 就地改写，不追加第二条
    await page.evaluate(() => { document.querySelector('#m-tabs button[data-v="review"]').click(); });
    await sleep(1200);
    const cks2 = await page.$$(".rv-ck");
    if (cks2.length) await cks2[0].check();
    const cb2 = await page.$("#rv-confirm");
    if (cb2) { await cb2.click(); await sleep(1500); }
    const mdP2 = fs.existsSync(mdPath) ? fs.readFileSync(mdPath, "utf-8") : "";
    const nCo = (mdP2.match(/做法确认（\d+ 条）/g) || []).length;
    t("E5p5 R4 同日重复确认只留一条 callout（连点两次不产生两条）", nCo === 1, String(nCo));
  }

  // ② 模式草稿（勾做法 → 生成 → 40 库断言）
  await page.evaluate(() => { document.querySelector('#m-tabs button[data-v="review"]').click(); });
  await sleep(1200);
  const draftBtn = await page.$("#rv-draft");
  if (!draftBtn) {
    t("E5d 模式草稿按钮未渲染", false, "现场 MD 做法清单应渲染出按钮");
  } else {
    const cks = await page.$$(".rv-ck");
    if (!cks.length) {
      t("E5d 做法清单为空", false, "现场 MD 含加粗方法，应有复选框");
    } else {
      await cks[0].check();
      await draftBtn.click();
      await sleep(500);
      await page.fill("#mode-name", "ST二e测试模式");
      await page.fill("#mode-desc", "E2E 模式草稿测试");
      await page.click("#modeOk");
      await sleep(1500);
      const modeFile = path.join(MD40, ST + "-模式.md");
      const ok = fs.existsSync(modeFile);
      t("E5d 模式草稿写入 40 库", ok, modeFile);
      if (ok) {
        const mt = fs.readFileSync(modeFile, "utf-8");
        t("E5e 模式卡 frontmatter+做法", mt.includes("ST二e测试模式") && mt.includes("企业名称"));
        fs.unlinkSync(modeFile);
      }
    }
    // ②b 门禁已删（2026-10-27 用户定）：不勾选做法也能直接开模式草稿弹窗
    // （写入成功后 refreshCurAndReview 会重渲染 m-body，按钮句柄已失效——必须重查）
    await page.evaluate(() =>
      document.querySelectorAll(".rv-ck:checked").forEach((c) => { c.checked = false; }));
    const draftBtn2 = await page.$("#rv-draft");
    await draftBtn2.click();
    await sleep(400);
    const noPickOpen = await page.$eval("#modeModal", (m) => m.style.display === "flex");
    t("E5f 不勾选做法可直接开模式草稿（门禁删除）", noPickOpen);
    await page.evaluate(() => { $("modeCancel").click(); });
    await sleep(200);
    // ②c 模式名/说明**从 40 库模式卡读回**预填（2026-10-30 R3-a 用户最终拍板：
    //     不再以内存变量 CUR_EXTRACT 为唯一来源——刷新/切卡即丢；接口无数据时才兜底用它）
    const mcRel = "政府质量奖-质量模式库/" + ST + "-模式.md";
    const mcPath = path.join(VAULT, mcRel);
    fs.writeFileSync(mcPath, ["---", "类型: 模式", `企业名称: ${ST}`, "---", "",
      `# ${ST} · 管理模式`, "", "## 模式卡读回测试模式", "", "这是模式卡里读回的说明。", "",
      "<!-- 用户区开始 -->", "## 复盘优化区", "", "E2E用户批注：这个模式要配案例佐证。",
      "<!-- 用户区结束 -->", ""].join("\n"), "utf-8");
    const autoFill = await page.evaluate(async () => {
      await openModeDraftModal();
      return { name: $("mode-name").value, desc: $("mode-desc").value,
               open: $("modeModal").style.display === "flex" };
    });
    t("E5g 模式名/说明从 40 库模式卡读回预填（不依赖内存变量）",
      autoFill.open === true && autoFill.name === "模式卡读回测试模式"
      && autoFill.desc === "这是模式卡里读回的说明。", JSON.stringify(autoFill));
    // R3-c：更新模式卡（零勾选也能写）→ 用户区批注保留、程序区被替换
    await page.fill("#mode-name", "模式卡读回测试模式（更新）");
    await page.fill("#mode-desc", "更新后的说明。");
    await page.click("#modeOk");
    await sleep(1800);
    const mt2 = fs.existsSync(mcPath) ? fs.readFileSync(mcPath, "utf-8") : "";
    t("E5g2 R3-c 零勾选也能写模式草稿 + 用户区批注原样保留",
      mt2.includes("E2E用户批注：这个模式要配案例佐证。")
      && mt2.includes("模式卡读回测试模式（更新）") && mt2.includes("更新后的说明。"),
      mt2.slice(0, 140));
    t("E5g3 R3-c 用户区标记成对存在",
      (mt2.match(/<!-- 用户区开始 -->/g) || []).length === 1
      && (mt2.match(/<!-- 用户区结束 -->/g) || []).length === 1, "");
    fs.unlinkSync(mcPath);
    await page.evaluate(() => { $("modeCancel").click(); });
    await sleep(200);

    // ③ 终版写入已前移至 ⓶（即时开启验完再写；写入后 E5a1/E5a1b 验字段接住）

    // ④ 复盘 tab 归档按钮（2026-10-28 用户定）：确认 → PUT 阶段=归档 → 按钮变「已归档」禁用态
    // （②c 只关了 modeModal，报告窗体还开着——先关再点行，否则遮罩挡点击）
    await page.evaluate(() => { closeReport(); });
    await sleep(300);
    await page.click(`#tb tr[data-id="${pid}"]`);
    await sleep(900);
    await page.evaluate(() => { document.querySelector('#m-tabs button[data-v="review"]').click(); });
    await sleep(1000);
    const archBtn = await page.$("#rv-archive");
    if (!archBtn) {
      t("E5i 复盘 tab 归档按钮未渲染", false, "现场态+30 库来源应渲染归档按钮");
    } else {
      await archBtn.click();
      await sleep(400);
      // ui.confirm 遮罩内点「确定」（必须限定 .uiconfirm 内，防点错静态按钮——2026-10-26 修复）
      await page.evaluate(() => {
        const m = [...document.querySelectorAll(".uiconfirm")].pop();
        [...m.querySelectorAll("button")].find((b) => b.textContent === "确定").click();
      });
      await sleep(1500);
      const archState = await page.evaluate(() => ({
        archivedBtn: !!$("rv-archived"),
        archivedDisabled: $("rv-archived") ? $("rv-archived").disabled : null,
        liveBtn: !!$("rv-archive"),
      }));
      t("E5i 归档按钮：确认后变「已归档」禁用态",
        archState.archivedBtn === true && archState.archivedDisabled === true
        && archState.liveBtn === false, JSON.stringify(archState));
      const cards = await allCards();
      const cur = cards.find((c) => c.id === pid);
      t("E5i2 归档后卡片阶段=归档（API 复核）", !!cur && cur.阶段 === "归档",
        String(cur && cur.阶段));
    }
    // 恢复文审态（类别+阶段都还原，E6 的提取/写入链路按文审态跑，与既有行为一致）
    await api("PUT", "/api/projects/" + encodeURIComponent(pid), { fields: {
      "类别": ["文件评审", "现场评审"], "阶段": "文审中" } });
    await page.evaluate(() => { if ($("reportModal")?.style.display === "flex") closeReport(); });
    await sleep(300);
}
}

/* ═══ E6 只看做法 + Obsidian + 归位记忆 ═══ */
async function e6PracticeView(page, ctx) {
  console.log("\n── E6 呈现：只看做法 + Obsidian URI + 归位记忆 ──");
  const { pid } = ctx;
  // ① 只看做法视图
  await page.evaluate(() => { if ($("reportModal")?.style.display === "flex") closeReport(); });
  await sleep(400);
  await page.click(`#tb tr[data-id="${pid}"]`);
  await sleep(1000);
  await page.click('.pv-btn[data-v="practice"]');
  await sleep(600);
  const pv = await page.$eval("#pv-practice", (x) => x.innerText);
  t("E6a 只看做法视图有分组", /4\.\d/.test(pv), pv.slice(0, 60).replace(/\n/g, " "));
  t("E6b 做法视图含加粗片段", pv.includes("技术创新驱动") || pv.includes("核心壁垒"));
  await page.click('.pv-btn[data-v="full"]');
  await sleep(400);
  const fullVisible = await page.$eval("#e-report", (x) => x.style.display !== "none");
  t("E6c 切回完整视图", fullVisible);

  // ② Obsidian URI（拦 window.open 不断真跳）
  const uri = await page.evaluate(() => {
    window.__opened = null;
    const o = window.open;
    window.open = (u) => { window.__opened = u; return null; };
    $("e-obs")?.click();
    return window.__opened;
  });
  t("E6d Obsidian URI 构造", typeof uri === "string" && uri.startsWith("obsidian://open"), uri || "null");

  // ③ 归位选择记忆（清记忆 → 默认 4.2 → 改选 4.6 → 再提取默认 4.6 → 清除回 4.2）
  await page.evaluate(() => localStorage.removeItem("zp_clause_memory"));
  // 新渲染的 m-body 需重新点「提取 Word」初始化提取区（renderExtractInto）；同 m-body 内的
  // 二次提取才可用 evaluate 强制显示（再点按钮会把已展开的区域收起）
  await page.click("#e-extract-btn");
  await sleep(200);
  await page.setInputFiles("#extract-file", path.join(FIX, "B45条款样本.docx"));
  await page.waitForSelector("#extract-write", { timeout: 20000 });
  await page.click("#extract-write");
  await sleep(500);
  const g1 = await page.$$eval("#clauseBody select", (s) => s.map((x) => x.value));
  t("E6e 清记忆后默认=关键词猜测（4.2）", g1[0] === "4.2", g1.join(","));
  await page.selectOption('#clauseBody select >> nth=0', "4.6");
  await page.click("#clauseOk");
  await sleep(300);
  // 2026-11-02 老张定：归位确认后直接写入（不再弹写入确认窗）——等完成 toast
  await page.waitForFunction(
    () => [...document.querySelectorAll(".toast")].some((x) => (x.textContent || "").includes("已写入")),
    { timeout: 20000 });
  await sleep(2000);
  // 再提取：记忆应带出 4.6（终版写入后报告弹窗按设计保留，先收遮罩再重开项目走提取链）
  await closeOverlays(page);
  await page.click(`#tb tr[data-id="${pid}"]`);
  await sleep(900);
  await page.click("#e-extract-btn");
  await sleep(200);
  await page.setInputFiles("#extract-file", path.join(FIX, "B45条款样本.docx"));
  await page.waitForSelector("#extract-write", { timeout: 20000 });
  await page.click("#extract-write");
  await sleep(500);
  const g2 = await page.$$eval("#clauseBody select", (s) => s.map((x) => x.value));
  t("E6f 记忆命中（同标题默认 4.6）", g2[0] === "4.6", g2.join(","));
  // 清除记忆 → 回 4.2
  const clr = await page.$("#clauseMemClear");
  if (clr) {
    await clr.click();
    await sleep(400);
    const g3 = await page.$$eval("#clauseBody select", (s) => s.map((x) => x.value));
    t("E6g 清除记忆回退关键词默认（4.2）", g3[0] === "4.2", g3.join(","));
  }
  await page.click("#clauseCancel");
  await sleep(300);
}

/* ═══ E7 数据卫生 ═══ */
async function e7Hygiene() {
  console.log("\n── E7 数据卫生 ──");
  const n1 = await cleanTestCards(ST);
  const n2 = await cleanTestCards("上海B45");
  for (const f of [path.join(MD20, "20241025-" + ST + ".md"),
                   path.join(MD30, "20260930-" + ST + ".md"),
                   // 两个 20260825 都要清：E3 键盘路由卡的 e3md 遗留 + E5 终版写入产物
                   path.join(MD30, "20260825-" + ST + ".md"),
                   path.join(MD30, "20260825-" + ST + "-现场评审.md"),
                   path.join(MD30, "20260827-" + ST + "派生.md"),
                   path.join(MD40, ST + "-模式.md")]) {
    if (fs.existsSync(f)) fs.unlinkSync(f);
  }
  t("E7a 测试卡删净", (await allCards()).every((c) => !String(c["企业名称"]).includes("ST二e")),
    `删卡 ${n1 + n2} 张`);
  const cards = await allCards();
  const ids = cards.map((c) => c.id);
  // 2026-11-02 美化包：还原断言改动态——与开跑时快照逐一比对（用户真实卡数量不再影响）
  t("E7b 台账还原=初始卡集合（不多不少）",
    JSON.stringify([...ids].sort()) === JSON.stringify([...ORIG_IDS].sort()), ids.join(","));
  const now = md5(LEDGER);
  t("E7c ledger 还原后 md5 一致", now === origMd5, `${origMd5.slice(0, 8)} vs ${now.slice(0, 8)}`);
}

/* ═══ 主流程 ═══ */
(async () => {
  console.log("=".repeat(56));
  console.log("评审工作台浏览器 E2E（D3）");
  await ensureService();
  await guardEnter();
  let ctx = null;
  let exitCode = 0;
  try {
    const { browser, page, jsErrors } = await newPage();
    await page.goto(BASE, { waitUntil: "networkidle" });
    await page.waitForSelector("#tb tr", { timeout: 15000 });
    await sleep(400);
    ORIG_IDS = await page.evaluate(async () =>
      (await (await fetch("/api/projects")).json()).map((c) => c.id));

    await e1Table(page);
    await e2Search(page);
    await e3Dialogs(page);
    ctx = await e4ClauseBackfill(page, jsErrors);
    if (ctx) await e5SoulAndMode(page, ctx);
    if (ctx) await e6PracticeView(page, ctx);
    await e7Hygiene();

    const bad = jsErrors.length;
    t("E7d 全程 pageerror=0", bad === 0, jsErrors[0] || "");
    await browser.close();
  } catch (e) {
    console.error("E2E 执行异常:", e);
    results.push({ name: "E2E 未崩溃完成", ok: false, detail: String(e).slice(0, 200) });
  }
  try { guardExit(); } catch (e) { console.error("数据态还原失败:", e.message); exitCode = 1; }

  const n = results.length;
  const fails = results.filter((r) => !r.ok);
  console.log(`\n${"=".repeat(56)}\nE2E: ${n - fails.length}/${n} 通过`);
  for (const f of fails) console.log(`  FAIL | ${f.name} | ${f.detail}`);
  await stopService();
  process.exit(fails.length || exitCode ? 1 : 0);
})();
