let DATA=[],DICTS={},TREE={},ENUMS={},MODS={},CUR=null,FILT={};
let VIEW=[];                        // B4：当前「筛选+排序」后的全量结果（图表用它，分页只切表格）
const SORT={col:'',dir:1};          // B4：排序列（数据字段名）与方向，1=升序 ▲，-1=降序 ▼
const PAGE_SIZE=100;                // B4：页大小；筛选结果 >100 条才显示分页器
let PAGE=1;                         // B4：当前页码，重新筛选/排序时重置为 1

const $=id=>document.getElementById(id);
const arr=v=>Array.isArray(v)?v:(v?[v]:[]);
const jv=v=>arr(v).join('·')||'—';
const isTodo=v=>!v||arr(v).join('')==='待补'||arr(v).length===0;
const clean=v=>isTodo(v)?'':(arr(v)[0]||'');
const escH=v=>String(v??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

// ── B1 统一提示：toast 替代原生 alert（不阻断、内容可选中复制）；
//    ui.confirm 替代原生 confirm（Promise 化，确定=true/取消=false，点遮罩=取消）──
const ui={
  toast(msg,ms=3600){
    let box=$('toast-box');
    if(!box){ box=document.createElement('div'); box.id='toast-box'; document.body.appendChild(box); }
    const el=document.createElement('div'); el.className='toast';
    el.textContent=msg;                       // textContent：不用 innerHTML，内容可选中复制
    box.appendChild(el);
    requestAnimationFrame(()=>el.classList.add('show'));
    setTimeout(()=>{ el.classList.remove('show'); setTimeout(()=>el.remove(),260); },ms);
    return el;
  },
  confirm(msg){
    return new Promise(res=>{
      const m=document.createElement('div'); m.className='uiconfirm';
      const box=document.createElement('div'); box.className='cbox';
      const txt=document.createElement('div'); txt.className='cmsg'; txt.textContent=msg;
      const btns=document.createElement('div'); btns.className='cbtns';
      const no=document.createElement('button'); no.className='btn'; no.textContent='取消';
      const yes=document.createElement('button'); yes.className='btn'; yes.textContent='确定';
      yes.style.cssText='background:var(--ac);border-color:var(--ac);color:#fff';
      btns.append(no,yes); box.append(txt,btns); m.appendChild(box);
      const done=v=>{ m.remove(); res(v); };   // Promise 只认第一次，重复触发无害
      no.onclick=()=>done(false); yes.onclick=()=>done(true);
      m.onclick=e=>{ if(e.target===m) done(false); };
      m.addEventListener('keydown',e=>{
        if(e.key==='Enter'){ e.preventDefault(); done(true); }
        if(e.key==='Escape'){ e.stopPropagation(); done(false); }   // 不让 B2 的全局 Esc 穿透
      });
      document.body.appendChild(m); yes.focus();
    });
  },
  info(title,msg){                       // 2026-11-02 美化包④：信息弹窗（单钮，无确认语义）
    return new Promise(res=>{
      const m=document.createElement('div'); m.className='uiconfirm';
      const box=document.createElement('div'); box.className='cbox';
      const t=document.createElement('div'); t.className='cmsg';
      t.innerHTML='<b>'+escH(title)+'</b>';
      const txt=document.createElement('div'); txt.className='cmsg'; txt.innerHTML=msg;   // 模板内容，非用户输入
      const btns=document.createElement('div'); btns.className='cbtns';
      const ok=document.createElement('button'); ok.className='btn'; ok.textContent='知道了';
      ok.style.cssText='background:var(--ac);border-color:var(--ac);color:#fff';
      btns.append(ok); box.append(t,txt,btns); m.appendChild(box);
      const done=()=>{ m.remove(); res(); };
      ok.onclick=done; m.onclick=e=>{ if(e.target===m) done(); };
      m.addEventListener('keydown',e=>{ if(e.key==='Escape'||e.key==='Enter'){ e.stopPropagation(); done(); } });
      document.body.appendChild(m); ok.focus();
    });
  }
};

// ── 区域 / 行业 两级下拉（市→区县、门类→大类）────────────
// 数据源是 /api/dicts/tree：改 Obsidian 里的字典表即可，界面自动跟着变
const TC=()=>TREE['区域']||{};
const TM=()=>TREE['行业']||{};
const NONE='__none__';                       // 传这个当 cur → 谁都不选中
const opt=(v,cur,label)=>`<option value="${v}"${v===cur?' selected':''}>${label||v||''}</option>`;
function guessMen(dl){                       // 只选了大类时，反推所属门类
  if(!dl) return '';
  for(const m in TM()) if((TM()[m]||[]).indexOf(dl)>=0) return m;
  return '';
}
function regSel(p,city,dist,blank){          // p = 前缀，如 e / n / q / k
  const cities=Object.keys(TC());
  const ds=city?(TC()[city]||[]):[];
  return `<div class="row">
      <select id="${p}-city">${blank?opt('',city?NONE:'',blank):''}${cities.map(c=>opt(c,city)).join('')}</select>
      <select id="${p}-dist">${opt('',dist?NONE:'','（市级 / 留空）')}${ds.map(d=>opt(d,dist)).join('')}</select>
    </div>`;
}
function indSel(p,men,dl,blank){
  const mens=Object.keys(TM());
  const body=men&&TM()[men]
    ? TM()[men].map(v=>opt(v,dl)).join('')
    : mens.map(m=>`<optgroup label="${m}">${TM()[m].map(v=>opt(v,dl)).join('')}</optgroup>`).join('');
  return `<div class="row">
      <select id="${p}-men">${blank?opt('',men?NONE:'',blank):''}${mens.map(m=>opt(m,men)).join('')}</select>
      <select id="${p}-dl">${opt('',dl?NONE:'','（不限大类）')}${body}</select>
    </div>
    <input id="${p}-kw" class="indkw" placeholder="输入关键词检索行业大类（如：汽车 / 设备 / 金融）">`;
}
function bindSel(p,distBlank,dlBlank){
  const city=$(p+'-city'),men=$(p+'-men'),dl=$(p+'-dl'),kw=$(p+'-kw');
  if(city) city.onchange=()=>{
    $(p+'-dist').innerHTML=opt('','',distBlank||'（市级 / 留空）')
      +(TC()[city.value]||[]).map(d=>opt(d)).join('');
  };
  if(men) men.onchange=()=>{
    const m=men.value;
    const body=m?TM()[m].map(v=>opt(v)).join('')
      :Object.keys(TM()).map(k=>`<optgroup label="${k}">${TM()[k].map(v=>opt(v)).join('')}</optgroup>`).join('');
    $(p+'-dl').innerHTML=opt('','',dlBlank||'（不限大类）')+body;
  };
  if(dl) dl.onchange=()=>{                   // 只选大类也把门类自动带上
    const m=guessMen(dl.value);
    if(dl.value&&m&&men&&!men.value) men.value=m;
  };
  if(kw) kw.oninput=()=>{
    const q=kw.value.trim();
    if(!q){                                  // 清空关键词 → 恢复门类联动
      if(men){ men.disabled=false; }
      if(men&&men.onchange) men.onchange();
      return;
    }
    if(men){ men.value=''; men.disabled=true; }   // 有关键词时跨门类检索
    const hits=[];
    for(const m in TM()) for(const v of (TM()[m]||[])) if(v.includes(q)) hits.push([m,v]);
    const body=hits.length
      ? hits.map(([m,v])=>`<option value="${v}" title="${m}">${m} · ${v}</option>`).join('')
      : `<option value="">无匹配</option>`;
    dl.innerHTML=opt('','','（不限大类）')+body;
  };
}
function pairVal(p){                         // 读回 [一级, 二级]
  const a=$(p+'-city')?$(p+'-city').value:$(p+'-men').value;
  const b=$(p+'-dist')?$(p+'-dist').value:$(p+'-dl').value;
  return [a,b];
}
function indVal(p){                          // 读行业 [门类, 大类]，只选大类时自动补门类
  const men=$(p+'-men')?$(p+'-men').value:'';
  const dl=$(p+'-dl')?$(p+'-dl').value:'';
  return [men||guessMen(dl), dl];
}

// ── 2026-11-02 美化包①：深/浅主题切换（html.light + localStorage 记忆，图表配色跟随）──
const THEME_KEY='zp_theme';
function isLight(){ return document.documentElement.classList.contains('light'); }
function applyTheme(light){
  document.documentElement.classList.toggle('light',light);
  const b=$('b-theme'); if(b) b.textContent=light?'☀️':'🌙';
  try{ localStorage.setItem(THEME_KEY,light?'light':'dark'); }catch(e){}
  if($('view-charts')&&!$('view-charts').hidden) renderCharts(filtered());
}

async function boot(){
  DATA=await (await fetch('/api/projects')).json();
  DICTS=await (await fetch('/api/dicts')).json();
  TREE=await (await fetch('/api/dicts/tree')).json();
  ENUMS=await (await fetch('/api/enums')).json();
  MODS=await (await fetch('/api/modules')).json();
  try{ if(localStorage.getItem(THEME_KEY)==='light') applyTheme(true); }catch(e){}
  $('b-theme').onclick=()=>applyTheme(!isLight());
  renderModbar(); bindActions(); bindDesens();
  buildFilters(); apply();
}

// ── 脱敏 ──────────────────────────────────────────────────
let DS=null;

function bindDesens(){
  $('d-run').onclick=runPreview;
  $('d-refresh').onclick=loadDesens;
  $('d-rotate').onclick=async()=>{
    const r=await fetch('/api/desens/rotate',{method:'POST'});
    const j=await r.json();
    const a=j['自动备份']||{}, c=j['代码备份']||{};
    ui.toast(`备份轮转完成：\n· 自动备份（ledger/MD）：扫描 ${a['扫描到']||0}，保留 ${a['保留']||0}，删除 ${a['删除']||0}\n· 代码备份（改动前快照）：扫描 ${c['扫描到']||0}，保留 ${c['保留']||0}，删除 ${c['删除']||0}\n（整库备份与人工归档目录不动）`);
  };
}

async function loadDesens(){
  DS=await (await fetch('/api/desens/status')).json();
  const on=DS['允许出网场景']||[], off=DS['禁止出网场景']||[];
  $('dsinfo').innerHTML=
    `级别 <b>${DS['级别']}</b> · 允许出网：${on.join(' / ')||'无'} · `+
    `禁止出网：${off.join(' / ')||'无'} · 片段上限 ${DS['片段上限字数']} 字 · `+
    `代号${DS['代号随机']?'每次随机':'固定'}`;
  $('d-scene').innerHTML=[...on,...off].map(s=>`<option>${s}</option>`).join('');
  const rules=DS['规则']||{};
  $('d-rules').innerHTML=Object.entries(rules)
    .map(([k,v])=>`· ${k} → ${v}`).join('<br>')||'（未配置）';
  await loadDesensLog();
}

async function loadDesensLog(){
  const rows=await (await fetch('/api/desens/log')).json();
  $('dtb').innerHTML=rows.length?rows.map(r=>
    `<tr><td>${r['时间']||''}</td><td>${r['场景']||''}</td><td>${r['发给']||''}</td>`+
    `<td>${r['替换']||''}</td><td>${r['字数']||''}</td><td>${r['任务']||''}</td></tr>`
  ).join(''):'<tr><td colspan="6" style="color:var(--tx2)">暂无出网记录</td></tr>';
}

async function runPreview(){
  const src=$('d-src').value;
  if(!src.trim()){ ui.toast('先粘贴一段文字'); return; }
  const r=await fetch('/api/desens/preview',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({文本:src,场景:$('d-scene').value,区域:''})});
  const j=await r.json();
  if(!j.ok){
    $('d-out').textContent='拒绝出网：'+j['原因'];
    $('d-stat').innerHTML='';
    return;
  }
  $('d-out').textContent=j.text;
  $('d-stat').innerHTML='替换 '+j.replaced+' 处 · '+
    (Object.entries(j.stats||{}).map(([k,v])=>`${k}×${v}`).join(' ')||'无命中');
}

function bindActions(){
  $('b-new').onclick=newForm;
  $('b-tpl').onclick=()=>location.href='/api/template';
  $('b-imp').onclick=()=>$('f-file').click();
  // 批量关联报告：按企业名把报告 MD 自动填进「来源文件」为空的卡片（只补空不覆盖，幂等）
  $('b-autolink').onclick=async()=>{
    if(!(await ui.confirm('批量关联报告：按企业名+年份把已有报告自动填进「来源文件」为空的卡片。\\n\\n· 同企业同年份报告精确归位；无同年份报告时挂该企业全部报告（结果里标注）\\n· 只补空，已有关联的卡片不动；可反复点击\\n\\n继续？'))) return;
    const r=await fetch('/api/reports/auto-link',{method:'POST'});
    const j=await r.json().catch(()=>({}));
    if(!r.ok){ ui.toast('批量关联失败：'+(j.detail||r.status)); return; }
    let msg=`关联成功 ${j['关联'].length} 个项目：\n`
      +(j['关联']||[]).map(x=>`· ${x['id']} ${x['企业']} → ${x['报告'].join('、')}（${x['归位']||''}）`).join('\n');
    if((j['无匹配']||[]).length) msg+=`\n\n无匹配报告 ${j['无匹配'].length} 个（企业名下还没有报告，可后补）：\n`+j['无匹配'].join('\n');
    if((j['无法解析企业名的报告']||[]).length) msg+=`\n\n无法解析企业名的报告 ${j['无法解析企业名的报告'].length} 个：\n`+j['无法解析企业名的报告'].join('\n');
    ui.toast(msg);
    await boot();
  };
  $('f-file').onchange=async e=>{
    const f=e.target.files[0]; if(!f) return;
    if(!(await ui.confirm('将按表格内容批量新建卡片（不会覆盖已有卡片）。\n\n· 企业名称+年份+奖项/项目 完全相同的行将跳过（防重复建卡）\n· 同一企业不同年份视为不同项目，正常建卡并互相关联\n\n继续？'))) { e.target.value=''; return; }
    const fd=new FormData(); fd.append('file',f);
    const r=await fetch('/api/import',{method:'POST',body:fd});
    const j=await r.json().catch(()=>({}));
    if(r.ok){
      let msg=`导入完成：读取 ${j['读取行数']} 行，建成 ${j.count} 张卡片`;
      const sk=j['跳过']||[];
      if(sk.length){
        msg+=`\n\n跳过 ${sk.length} 行疑似重复（企业+年份+奖项 与已有卡片相同）：`;
        msg+='\n'+sk.map(s=>`· ${s['企业']}（${s['年份']||'年份空'} · ${s['奖项']||'奖项空'}）——${s['原因']}`).join('\n');
      }
      ui.toast(msg); await boot();
    }
    else ui.toast('导入失败：'+(j.detail||r.status));
    e.target.value='';
  };
}

// ── 政策检索（不再独立存政策卡，只做「生成任务包 → 智能体检索 → 内联回填报告」）──
function packForm(region,industry,pid){
  const rg=arr(region),ind=arr(industry);
  const projs=DATA.map(d=>d['id']+' '+d['企业名称']);
  $('pbody').classList.add('open');
  $('pbody').innerHTML=`
    <h3 class="detail-h" style="margin-bottom:10px">政策检索</h3>
    <p class="detail-sub">粘贴一段你对报告的理解（要查什么政策），连同行业/区域一起打成任务包，
    交给 WorkBuddy 联网检索后，把结果内联回企业报告的「三、政策与指南建议」章节。政策不单独存卡。</p>
    <div class="fld"><label>检索意图（粘贴你对报告的理解 / 要查什么）*</label>
      <textarea id="k-intent" placeholder="例：该企业是传动带/同步带制造，正在评政府质量奖，帮我查浦东新区针对先进制造业、国产替代、专精特新的扶持政策与奖励办法，给出文号与一手出处链接…"></textarea></div>
    <div class="fld"><label>区域</label>${regSel('k',clean(rg[0])||Object.keys(TC())[0]||'',clean(rg[1]),'（不限）')}</div>
    <div class="fld"><label>行业（GB/T 4754）</label>${indSel('k',clean(ind[0]),clean(ind[1]),'（不限）')}</div>
    <div class="fld"><label>关联评审项目 / 回填目标报告</label>
      <select id="k-proj"><option value="">（不关联）</option>${
        projs.map(p=>`<option ${p.startsWith(pid||'')?'selected':''}>${p}</option>`).join('')}</select></div>
    <button class="btn" id="k-go">生成检索任务包到 outbox</button>
    <div class="sec">生成后</div>
    <p style="color:var(--tx2);font-size:12px">到 <code>exchange/outbox</code> 取任务包交给 WorkBuddy 检索；
    或直接把任务包内容贴给 WorkBuddy，检索结果会内联写回报告，<b>不再回收进政策库</b>。</p>
    <div id="k-packs"></div>`;
  bindSel('k','（不限区县）','（不限大类）');
  $('k-go').onclick=async()=>{
    const intent=$('k-intent').value.trim();
    if(!intent){ ui.toast('请先粘贴检索意图'); return; }
    const body={'区域':pairVal('k').filter(Boolean),
      '行业':indVal('k').filter(Boolean),
      '关联项目':$('k-proj').value,'检索意图':intent};
    const r=await fetch('/api/policy/pack',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(body)});
    const j=await r.json().catch(()=>({}));
    if(r.ok){ ui.toast('任务包已生成：\n'+j['路径']); loadPacks(); }
    else ui.toast('生成失败：'+(j.detail||r.status));
  };
  loadPacks();
}

async function loadPacks(){
  const j=await (await fetch('/api/policy/packs')).json().catch(()=>[]);
  $('k-packs').innerHTML=(j.length
    ? '<div class="sec">最近任务包（outbox）</div>'+j.map(f=>
        `<div class="pc"><span class="nm">${escH(f['name'])}</span>
         <span class="st">${f['时间']||''}</span>
         <a class="st" href="/api/policy/pack/${encodeURIComponent(f['name'])}" style="color:var(--ac)">下载</a></div>`).join('')
    : '<div class="sec">最近任务包</div><p style="color:var(--tx2);font-size:12px">尚无任务包</p>');
}

function renderModbar(){
  const on=MODS['启用']||[], reg=MODS['登记']||{};
  const off=Object.keys(reg).filter(k=>!on.includes(k));
  $('modinfo').innerHTML=
    '<span><b>当前业务范围：</b>'+on.map(m=>'<span class="on">'+m+'</span>').join(' ')+'</span>'+
    (off.length?'<span>待开发·欢迎共建：'+off.map(m=>'<span class="off" data-mod="'+escH(m)+'" style="cursor:pointer" title="点模块名看规划说明">'+m+'</span>').join(' ')+'</span>':'')+
    '<span style="opacity:.7">点预留模块名看说明；在 config.yaml 的「模块.启用」加一行即可开通新业务线</span>';
  $('modinfo').querySelectorAll('.off[data-mod]').forEach(el=>{
    el.onclick=()=>moduleInfo(el.dataset.mod);
  });
}
/* 美化包④（2026-11-02）：预留模块说明面板——开源后网友共建的入口说明。
   数据全部来自现有 /api/modules 的「登记」段，不新增后端。 */
function moduleInfo(name){
  const reg=(MODS['登记']||{})[name]||{};
  const on=(MODS['启用']||[]).includes(name);
  ui.info('模块 · '+name,
    '<div class="detail-sub" style="margin-bottom:8px">'+escH(reg['说明']||'（暂无说明）')+'</div>'
    +'<div style="font-size:13px;line-height:1.9">'
    +'状态：<span class="pill '+(on?'ok':'unk')+'">'+(on?'已启用':'待开发')+'</span><br>'
    +'奖项范围：'+((reg['奖项枚举']||[]).map(a=>escH(a)).join('、')||'—')+'<br>'
    +'<span style="color:var(--tx2)">该模块暂未开发，数据结构已预留——开源后欢迎共同开发或完善。'
    +'开通方式：config.yaml「模块.启用」列表加一行模块名（界面/台账/图表即自动按模块过滤）。</span></div>');
}

function optSel(el,vals,label){
  const cur=el.value;
  el.innerHTML='<option value="">'+label+'</option>'+
    vals.map(v=>'<option>'+v+'</option>').join('');
  el.value=cur;
}
// 筛选字典 = 字典表全量 ∪ 数据里已出现的值，字典没有的历史值也不会漏
const okVal=v=>!!v&&!isTodo(v);
function dictUnion(tree, field, lv){
  const fromDict=Object.keys(tree);
  const fromData=[...new Set(DATA.map(d=>arr(d[field])[lv]))].filter(okVal);
  return [...new Set([...fromDict,...fromData])];
}
function subUnion(tree, city, field){
  const fromDict=(tree&&tree[city])||[];
  const fromData=[...new Set(DATA.filter(d=>arr(d[field])[0]===city)
    .map(d=>arr(d[field])[1]))].filter(okVal);
  return [...new Set([...fromDict,...fromData])];
}
// 二级下拉：选了一级就只列它的二级，没选就按一级分组全列
function buildSub(el,label,cities,subs){
  const cur=el.value;
  const one=cities.length===1;
  el.innerHTML=`<option value="">${label}</option>`+cities.map(c=>
    one?subs(c).map(v=>`<option>${v}</option>`).join('')
       :`<optgroup label="${c}">${subs(c).map(v=>`<option>${v}</option>`).join('')}</optgroup>`).join('');
  el.value=cur;
}
function buildRegionFilter(){
  const cities=dictUnion(TC(),'区域',0);
  optSel($('f-city'),cities,'全部区域');
  const c=$('f-city').value;
  const list=c?[c]:cities.filter(x=>TC()[x]||DATA.some(d=>arr(d['区域'])[0]===x));
  buildSub($('f-dist'),'全部区县',list,x=>subUnion(TC(),x,'区域'));
}
function buildIndustryFilter(){
  const mens=dictUnion(TM(),'行业',0);
  optSel($('f-men'),mens,'全部行业');
  const m=$('f-men').value;
  const list=m?[m]:mens.filter(x=>TM()[x]||DATA.some(d=>arr(d['行业'])[0]===x));
  buildSub($('f-dl'),'全部大类',list,x=>subUnion(TM(),x,'行业'));
}
function buildFilters(){
  const years=[...new Set(DATA.map(d=>d['年份']))].filter(Boolean).sort();
  const cats=[...new Set(DATA.flatMap(d=>arr(d['类别'])))].filter(Boolean).sort();
  const aws=[...new Set(DATA.map(d=>d['奖项/项目']))].filter(Boolean).sort();
  optSel($('f-year'),years,'全部年份');
  optSel($('f-cat'),cats,'全部类别');
  optSel($('f-award'),aws,'全部奖项');
  buildRegionFilter();
  buildIndustryFilter();
}

// B5：搜索命中字段——企业名称、管理模式名称、id、区域、行业、类别、奖项/项目、结论、阶段、得分
// 列表字段先 join，得分转字符串；每个分词只要在任一字段出现即算该词命中
const KW_FIELDS=[
  d=>d['企业名称'], d=>d['管理模式名称'], d=>d['id'],
  d=>arr(d['区域']).join('·'), d=>arr(d['行业']).join('·'), d=>arr(d['类别']).join('·'),
  d=>d['奖项/项目'], d=>d['结论'], d=>d['阶段'], d=>d['得分']
];
function matchKw(d,kw){
  const words=String(kw||'').toLowerCase().split(/\s+/).filter(Boolean);
  if(!words.length) return true;                        // 空关键词不拦截
  const hay=KW_FIELDS.map(f=>String(f(d)??'').toLowerCase());
  return words.every(w=>hay.some(h=>h.includes(w)));    // 分词 AND：每个词都要命中
}

// B4：对当前筛选结果排序；「年」「得分」按数值，其余按中文 localeCompare('zh-Hans-CN')，
// 列表型字段（区域/行业/类别）用其 join 值比；空值在升/降序下都排在最后
const NUM_COLS=['年份','得分'];
function sortRows(rows){
  if(!SORT.col) return rows;
  const num=NUM_COLS.includes(SORT.col), dir=SORT.dir;
  const val=d=>{
    const v=d[SORT.col];
    return num?v:(Array.isArray(v)?v.join('·'):v);
  };
  return [...rows].sort((a,b)=>{
    if(num){
      const x=val(a), y=val(b);
      const nx=(x==null||x==='')?null:Number(x);
      const ny=(y==null||y==='')?null:Number(y);
      if(nx==null&&ny==null) return 0;
      if(nx==null) return 1;                            // 空值恒排后面
      if(ny==null) return -1;
      return (nx-ny)*dir;
    }
    return String(val(a)??'').localeCompare(String(val(b)??''),'zh-Hans-CN')*dir;
  });
}

function apply(){
  FILT={
    year:$('f-year').value,city:$('f-city').value,dist:$('f-dist').value,
    men:$('f-men').value,dl:$('f-dl').value,
    cat:$('f-cat').value,award:$('f-award').value,
    kw:$('f-kw').value.trim(),todo:$('f-todo').checked
  };
  const rows=DATA.filter(d=>{
    const rg=arr(d['区域']),id=arr(d['行业']);
    if(FILT.year && String(d['年份'])!==FILT.year) return false;
    // 一级：卡片区域数组里含这个值；二级：含该区县，选「市级」时把只填到市一级的也算进来
    if(FILT.city && !rg.includes(FILT.city)) return false;
    if(FILT.dist && !rg.includes(FILT.dist) && !(FILT.dist==='市级'&&rg.length<2)) return false;
    if(FILT.men && !id.includes(FILT.men)) return false;
    if(FILT.dl && !id.includes(FILT.dl)) return false;
    if(FILT.cat && !arr(d['类别']).includes(FILT.cat)) return false;
    if(FILT.award && d['奖项/项目']!==FILT.award) return false;
    if(FILT.todo && !arr(d['待补字段']).length) return false;
    if(FILT.kw && !matchKw(d,FILT.kw)) return false;
    return true;
  });
  PAGE=1;                                        // 重新筛选/排序都回到第 1 页
  const sorted=sortRows(rows);
  $('meta').textContent=`共 ${DATA.length} 个项目，当前筛选 ${rows.length} 个`;
  renderTable(sorted);                           // 表格只渲染当前页
  if(!$('view-charts').hidden) renderCharts(sorted);  // 图表用全量筛选行，不被分页切片污染
}

function renderTable(rows){
  VIEW=rows;                                       // 全量筛选+排序结果：图表与翻页都用它
  const total=rows.length;
  const pages=Math.max(1,Math.ceil(total/PAGE_SIZE));
  if(PAGE>pages) PAGE=pages;
  if(PAGE<1) PAGE=1;
  const start=(PAGE-1)*PAGE_SIZE;
  const page=rows.slice(start,start+PAGE_SIZE);    // 只渲染当前页
  if(!page.length){                                // 美化包⑤：空状态（筛选无结果时给指引，不再是白板）
    $('tb').innerHTML=`<tr class="empty-state"><td colspan="12">${
      DATA.length?'没有符合当前筛选的项目——调一调筛选条件，或点「重置」看全部'
                 :'台账还是空的——点上方「+ 新建项目」或「批量导入」建第一张卡'}</td></tr>`;
    renderPager(total,pages,start,0);
    paintSort();
    return;
  }
  $('tb').innerHTML=page.map(d=>{
    const rg=arr(d['区域']),id=arr(d['行业']);
    return `<tr data-id="${d['id']}">
      <td>${d['id']||'—'}</td>
      <td>${d['企业名称']||'—'}</td>
      <td>${d['管理模式名称']||'—'}</td>
      <td>${d['年份']||'—'}</td>
      <td class="${isTodo(rg)?'todo':''}">${jv(rg)}</td>
      <td class="${isTodo(id)?'todo':''}">${jv(id)}</td>
      <td>${jv(d['类别'])}</td>
      <td>${d['奖项/项目']||'—'}</td>
      <td class="score">${d['得分']??'—'}</td>
      <td>${d['结论']||'—'}</td>
      <td>${progCell(d)}</td>
      <td><button class="tbl-edit" data-id="${d['id']}">编辑</button><button class="tbl-del" data-id="${d['id']}">删除</button></td></tr>`;
  }).join('');
  document.querySelectorAll('#tb tr').forEach(tr=>{
    tr.onclick=e=>{ if(e.target.closest('button')) return; openDetail(tr.dataset.id,tr); };
  });
  document.querySelectorAll('#tb .tbl-edit').forEach(b=>{
    b.onclick=e=>{ e.stopPropagation(); editProject(b.dataset.id); };
  });
  document.querySelectorAll('#tb .tbl-del').forEach(b=>{
    b.onclick=e=>{ e.stopPropagation(); deleteProject(b.dataset.id); };
  });
  renderPager(total,pages,start,page.length);
  paintSort();
}

// B4：阈值分页器——筛选结果 >100 条才显示；≤100 条完全隐去（保持现状）
/* 美化包③（2026-11-02）：表格「进度」列（只读徽标）——信号全部来自现有字段，不新增状态：
   阶段底色（文审/报告已出=fut、现场中=rev、归档=ok）+ 复盘闭环 勾标（终版/①做法确认/
   ②模式草稿/③四问已答），悬停徽标看落定日期。 */
function progCell(d){
  const st={'文审中':'fut','报告已出':'fut','现场中':'rev','归档':'ok'}[d['阶段']]||'unk';
  let h=`<span class="pill ${st}">${escH(d['阶段']||'待定')}</span>`;
  const NAMES={'终版':'终版写入','①':'做法确认','②':'模式草稿','③':'四问已答'};
  for(const m of ['终版','①','②','③']){
    const v=d[{'终版':'终版已写','①':'做法确认','②':'模式草稿','③':'四问已答'}[m]];
    if(v) h+=`<span class="pill ok" title="${NAMES[m]}：${escH(v)}">${m}✓</span>`;
  }
  return `<div class="tbl-prog">${h}</div>`;
}

// B4：阈值分页器——筛选结果 >100 条才显示；≤100 条完全隐去（保持现状）
function renderPager(total,pages,start,shown){
  const pg=$('pager');
  if(total<=PAGE_SIZE){ pg.hidden=true; return; }
  pg.hidden=false;
  $('pg-info').textContent=`第 ${PAGE}/${pages} 页 · 共 ${total} 条（${start+1}-${start+shown}）`;
  $('pg-prev').disabled=PAGE<=1;
  $('pg-next').disabled=PAGE>=pages;
}
// B4：表头 ▲/▼ 指示当前排序列与方向
function paintSort(){
  document.querySelectorAll('#tbl thead th.sortable').forEach(th=>{
    const a=th.querySelector('.arrow');
    if(a) a.textContent=(th.dataset.col===SORT.col)?(SORT.dir>0?'▲':'▼'):'';
  });
}
// B4：点表头在 asc ↔ desc 间切换，再走 apply（重置到第 1 页并重新排序）
document.querySelector('#tbl thead').addEventListener('click',e=>{
  const th=e.target.closest('th.sortable');
  if(!th) return;
  if(SORT.col===th.dataset.col) SORT.dir=-SORT.dir;
  else { SORT.col=th.dataset.col; SORT.dir=1; }
  apply();
});
$('pg-prev').onclick=()=>{ if(PAGE>1){ PAGE--; renderTable(VIEW); } };
$('pg-next').onclick=()=>{ const p=Math.ceil(VIEW.length/PAGE_SIZE); if(PAGE<p){ PAGE++; renderTable(VIEW); } };

function closeDetail(){
  document.querySelectorAll('#tb tr').forEach(x=>x.classList.remove('sel'));
  $('detail').classList.remove('open');
  $('detail').innerHTML='<p class="detail-sub">从左侧选择一个项目查看与编辑</p>';
}

const baseName=p=>String(p||'').split('/').pop().replace(/\.md$/,'');
const normC=s=>String(s||'').replace(/(股份有限公司|有限责任公司|有限公司|合作社|集团公司|集团)$/,'').trim();
const sameCompany=(a,b)=>{const x=normC(a);return !!x&&x===normC(b);};

/* 终版 Word 上传即时信号（2026-10-30 用户最终拍板）：现场态卡完成终版 Word 文字提取后
   置 true——用户的心智模型是「能上传终版报告，本身就说明现场核实的活干完了」，
   所以这个信号只用来**关**「进入现场评审环节」，**不再**用来开「复盘」；
   复盘只认卡片「终版已写」（后端 write-review 目标=现场 时置位、覆盖式）。本标志切卡即重置。 */
let EXTRACT_FLAG=false;

/* 报告窗体 tab 条渲染：openDetail 开卡时画；现场态卡提取 Word 完成后也重绘一次
   （即时关现场核实环节——在提取完成、CUR_EXTRACT 赋值的那条链路里挂钩）。 */
function paintMTabs(){
  const isOnsite=arr(CUR['类别'])[0]==='现场评审';
  const today=new Date().toISOString().slice(0,10);
  const fsDate=((CUR['现场日期']||'')+'').slice(0,10);
  // 现场环节关门（2026-10-28 用户定；2026-10-30 用户最终拍板修订）：
  // ① 终版已写入=现场评审结束；② 终版 Word 已上传提取完成（EXTRACT_FLAG）=现场核实活儿
  //    已经干完——两者都关「进入现场评审环节」。修正走「重新上传终版 Word → 提取并写入终版」，
  //    write-onsite 重建路径前后端都已封
  const closed=!!CUR['终版已写']||EXTRACT_FLAG;
  const canEnter=isOnsite&&!closed&&(!fsDate||today<=fsDate);
  // 复盘 tab 门禁（2026-10-30 用户最终拍板：只认「终版已写」——必须真正写入终版才开；
  // 文审→现场阶段（write-onsite，阶段一）只做条款核实与信息导出，不复盘；刚提取完未写入
  // 也不开，这是用户明确要的，不要额外放行）
  const hasOnsite=arr(CUR['类别']).includes('现场评审');
  const canReview=hasOnsite&&!!CUR['终版已写'];
  // 关门文案分两种：已写入的报日期；仅上传未写入的（EXTRACT_FLAG）引导去写入终版
  const enterTitle=canEnter?'':(CUR['终版已写']
    ?('终版已写入（'+CUR['终版已写']+'），现场评审环节已关闭——复盘已开启')
    :(EXTRACT_FLAG?'终版 Word 已上传，现场核实环节已关闭——完成条款归位并写入终版后即可复盘'
      :'类别为文件评审，或已过现场日期'));
  $('m-tabs').innerHTML=`
    <button class="on" data-v="report">报告</button>
    <button data-v="onsite" ${canEnter?'':'disabled'} title="${enterTitle}">进入现场评审环节</button>
    <button data-v="review" ${canReview?'':'disabled'} title="${canReview?'':(hasOnsite?'上传现场评审终版 Word 并写入后开启复盘':'未含现场评审类别，不可复盘')}">复盘</button>`;
  $('m-tabs').querySelectorAll('button:not(:disabled)').forEach(b=>b.onclick=()=>{
    saveTabMem();                                   // 美化包⑨：切走前记住滚动/视图
    $('m-tabs').querySelectorAll('button').forEach(x=>x.classList.remove('on'));
    b.classList.add('on');
    const v=b.dataset.v;
    v==='onsite'?renderOnsite():v==='review'?renderReview():renderReport();
  });
}

function openDetail(pid,tr){
  document.querySelectorAll('#tb tr').forEach(x=>x.classList.remove('sel'));
  if(tr) tr.classList.add('sel');
  CUR=DATA.find(d=>String(d['id'])===pid);
  if(!CUR) return;
  // 开卡/切卡即重置「终版 Word 提取完成」的即时门禁信号（只对当前卡的当次提取有效；
  // 终版写入后由卡片「终版已写」字段持久接住——见 paintMTabs 复盘门禁）
  EXTRACT_FLAG=false;
  // 点击企业 → 居中窗体（可全屏/关闭）；右侧面板只留给新建/编辑项目
  $('reportModal').style.display='flex';
  $('reportTitle').textContent=(CUR['企业名称']||'')+' · '+(CUR['id']||'');
  paintMTabs();
  $('reportClose').onclick=closeReport;
  $('reportFull').onclick=()=>{
    const box=$('reportBox');
    const full=box.classList.toggle('full');
    box.style.width=full?'':(OB_W+'px');
    $('reportFull').textContent=full?'还原':'全屏';
  };
  renderReport();
}

// 报告窗体关闭：无编辑态（写入均一次性完成），直接关即可
function closeReport(){
  $('reportModal').style.display='none';
}
// B2 逃离出口①+B3 键盘统一（2026-11-02 美化包⑦）：核实窗体关闭一律走这道闸（按钮/Esc 同源）——
// 有未保存内容先确认，Esc 不绕过
async function closeOpaneGuarded(){
  if(OS_DIRTY){
    const filled=Object.values(OS_NOTES).filter(v=>v&&String(v).trim()).length;
    if(!(await ui.confirm('还有未保存的现场核实内容（已填 '+filled+' 条），关闭后将丢失。确定关闭？'))) return;
  }
  $('onsitePane').style.display='none';
}
/* B2/B3 键盘统一（美化包⑦）：Esc 自上而下关最上层可见弹层（有未保存内容先确认）；
   Ctrl+Enter 触发当前弹层的确认/保存。优先级与 z-index 一致：
   soul(96)≈mode(96) > clause(95) > note(90) > opane(70) > clauseSide(60) > 其余 overlay。 */
const ESC_STACK=[
  {id:'soulModal', dirty:()=>($('soulInput').value||'').trim(), tip:'四问内容未保存，确定关闭？'},
  {id:'modeModal', dirty:()=>(($('mode-name').value||'').trim()||($('mode-desc').value||'').trim()), tip:'模式草稿内容未保存，确定关闭？'},
  {id:'clauseModal'},
  {id:'noteModal', dirty:()=>($('noteModalInput').value||'').trim(), tip:'心得内容未保存，确定关闭？'},
  {id:'opane',     close:closeOpaneGuarded},
  {id:'clauseSide',hide:'clauseSide'},
  {id:'pickModal'},
  {id:'onsiteModal'},
  {id:'placeModal'},
  {id:'reportModal', close:closeReport},
];
function escVisible(x){
  const el=$(x.id); if(!el) return false;
  return (x.id==='opane'||x.id==='reportModal')
    ? el.style.display==='flex'
    : el.style.display!=='none'&&el.style.display!=='';
}
document.addEventListener('keydown',async e=>{
  if(e.ctrlKey&&e.key==='Enter'){
    const op=$('onsitePane'), pm=$('placeModal');
    if(op&&op.style.display==='flex'){ e.preventDefault(); opaneSaveNotes(); return; }
    if(pm&&pm.style.display==='flex'){ e.preventDefault(); $('placeOk').click(); return; }
    // 美化包⑦：小弹窗 Ctrl+Enter = 点它的确认钮
    for(const [m,ok] of [['noteModal','noteModalOk'],['modeModal','modeOk'],['soulModal','soulNext'],
                         ['clauseModal','clauseOk'],['onsiteModal','onsiteOk'],['pickModal','pickOk']]){
      const el=$(m);
      if(el&&el.style.display==='flex'){ e.preventDefault(); const b=$(ok); if(b&&!b.disabled) b.click(); return; }
    }
    return;
  }
  if(e.key!=='Escape') return;
  for(const x of ESC_STACK){
    if(!escVisible(x)) continue;
    e.preventDefault();
    if(x.close){ x.close(); return; }
    if(x.hide){ $(x.hide).style.display='none'; return; }
    if(x.dirty&&x.dirty()){                       // 有未保存内容 → 先走确认闸
      if(!(await ui.confirm(x.tip))) return;
    }
    $(x.id).style.display='none';
    return;
  }
});
// B2 逃离出口②：点遮罩空白处关闭（点在内容框内不关）
function bindReportOverlay(){
  const rm=$('reportModal'); if(!rm) return;
  rm.onclick=e=>{ if(e.target===rm) closeReport(); };
}

/* 现场阶段判定（2026-10-27 用户定）：类别首个元素=现场评审，或阶段已到现场中/归档。
   现场阶段的卡：上传入口写 30 库现场终版（程序节覆盖、手写节保留），不开放组员粘贴入口；
   文审阶段的卡：上传写 20 库文审 MD，粘贴入口（组员）开放。 */
function isOnsiteStageOf(c){
  return arr(c['类别'])[0]==='现场评审'||['现场中','归档'].includes(c['阶段']);
}

async function renderReport(){
  const srcs=arr(CUR['来源文件']);
  const isOnsiteStage=isOnsiteStageOf(CUR);   // 现场阶段：入口/hint/写入目标默认值自适应
  let toolbar='';
  // 上传入口对所有卡开放（2026-10-27 用户定：现场评审的报告也要能上传）；hint 按阶段自适应
  toolbar+=`
    <div style="margin-bottom:10px;display:flex;align-items:center;gap:10px">
      <button class="btn" id="e-extract-btn">提取 Word</button>
      <span class="detail-sub">${isOnsiteStage?'上传现场评审终版 Word，写入 30 库现场 MD（程序节覆盖，手写节保留）':'上传 Word 评审报告，提取后写入文审报告 MD'}</span>
    </div><div id="e-extract-area" style="display:none"></div>`;
  if(srcs.length) toolbar+=`
    <div style="margin-bottom:10px;display:flex;align-items:center;gap:10px">
      <button class="btn pv-btn active" data-v="full">完整</button>
      <button class="btn pv-btn" data-v="practice">只看做法</button>
      <button class="btn" id="e-obs">在 Obsidian 打开</button>
      <span class="detail-sub">复盘修正 / 写判断备注去 Obsidian（MD 是唯一真源）</span>
    </div><div id="pv-practice" style="display:none"></div>`;
  if(!srcs.length){
    $('m-body').innerHTML=toolbar+`<p class="detail-sub">暂无报告。点上方「提取 Word」上传${isOnsiteStage?'现场评审终版':'Word 评审报告'}并写入。</p>`;
    bindExtractBtn();
    return;
  }
  $('m-body').innerHTML=toolbar+`<div class="report-body" id="e-report">加载中…</div>`;
  bindExtractBtn(); bindPracticeSwitch();
  const r=await fetch('/api/file?path='+encodeURIComponent(srcs[0]));
  const j=await r.json().catch(()=>({}));
  $('e-report').innerHTML=r.ok?j.html:`<p class="detail-sub">加载失败：${j.detail||r.status}</p>`;
  if(r.ok){ CUR_REPORT=j; renderPractice(j); restoreTabMem('report'); }   // 美化包⑨：切回恢复滚动/视图
}

let CUR_REPORT=null;   // 当前报告（含做法索引/obsidian_uri）

function bindPracticeSwitch(){
  const btns=[...document.querySelectorAll('.pv-btn')];
  btns.forEach(b=>b.onclick=()=>{
    btns.forEach(x=>x.classList.toggle('active',x===b));
    const v=b.dataset.v;
    $('e-report').style.display=v==='full'?'':'none';
    $('pv-practice').style.display=v==='practice'?'':'none';
  });
  const ob=$('e-obs');
  if(ob) ob.onclick=()=>{
    if(!CUR_REPORT||!CUR_REPORT['obsidian_uri']){ ui.toast('未获取到文件路径'); return; }
    window.open(CUR_REPORT['obsidian_uri'],'_blank');
    ui.toast('已发起 Obsidian 跳转；若未反应请确认 Obsidian 已安装且打开了对应 vault');
  };
}

function renderPractice(j){
  const box=$('pv-practice');
  if(!box) return;
  const list=j['做法']||[];
  if(!list.length){
    box.innerHTML='<p class="detail-sub">该报告暂无结构化做法数据——条款分节 + 加粗标记是 2026-10-24 上线的功能；旧报告可在 Obsidian 里补格式后重新提取。</p>';
    return;
  }
  let h='';
  for(const k of ['优势','建议']){
    const g=list.filter(x=>x['类型']===k);
    if(!g.length) continue;
    h+=`<div class="sec">${k}做法 · ${g.length} 组</div>`;
    g.forEach(x=>{
      h+=`<div class="clause-item"><b>${escH(x['标题']||'未归位')}</b>`;
      const items=x['条目']||[];
      if(!items.length){ h+='<div class="rv" style="color:var(--tx2)">（无条目）</div>'; }
      items.forEach(it=>{
        // 2026-10-30 R2 用户拍板：清单数据源换成「正文全文」——展示概述 + 全文，
        // 方法（全文按「。」切出的句子）列在下面（不再只列加粗片段）
        if(it['概述'])
          h+=`<div class="ci-head" style="margin-top:6px">${escH(it['概述'])}</div>`;
        const full=String(it['全文']||'').trim();
        if(full)
          h+=`<div class="rv">${escH(full).replace(/\n/g,'<br>')}</div>`;
        const ms=(it['方法']||[]);
        if(ms.length)
          h+=`<div class="rv" style="margin-top:4px">${ms.map(f=>'· '+escH(f)).join('<br>')}</div>`;
        else if(!full&&!it['概述'])
          h+='<div class="rv" style="color:var(--tx2)">（无正文内容）</div>';
      });
      h+='</div>';
    });
  }
  box.innerHTML=h;
}

function bindExtractBtn(){
  const b=$('e-extract-btn');
  if(!b) return;
  b.onclick=()=>{
    const area=$('e-extract-area');
    if(!area) return;
    const show=area.style.display==='none';
    area.style.display=show?'block':'none';
    if(show && !area.dataset.init){
      area.dataset.init='1';
      renderExtractInto(area);
    }
  };
  // 2026-10-30 用户最终拍板：全流程（文审/现场核实/复盘）一律走 Word 提取，
  // 平台粘贴入口整体撤除（按钮/绑定/弹窗/函数），后端 /api/paste-extract 保留作死代码
}

/* 组内勾选选项拉平（2026-10-30 R2 用户拍板：整条 / 摘句两种粒度）。
   返回选项数组 [{text, kind}]，kind='whole'（整条=该条正文全文）| 'sentence'（逐句=方法）。
   同一条目内 whole 在前；空值过滤。
   DOM 契约：data-g=组索引、data-f=组内拉平选项下标（顺序必须与本函数一致）。 */
function flatMethods(g){
  const out=[];
  (g['条目']||[]).forEach(it=>{
    const whole=String(it['全文']||'').trim();
    if(whole) out.push({text:whole, kind:'whole'});
    (it['方法']||[]).forEach(f=>{ if(String(f||'').trim()) out.push({text:String(f), kind:'sentence'}); });
  });
  return out;
}

/* 勾选收集（confirmPractices 与 openModeDraftModal 共用，口径唯一）：
   某条目若勾了「整条」→ 只收整条、忽略该条目的句子勾选；否则收被勾的句子。
   同组同文本去重（整条与其他条目的同文句子不会重复落两条）。 */
function collectPicked(){
  const picked=[];
  const checks=[...document.querySelectorAll('.rv-ck:checked')];
  // 第一遍：标出哪些条目勾了整条（键 = 组索引 + 条目索引，取自 data-g/data-i）
  const wholeAt=new Set();
  checks.forEach(ck=>{
    const g=RV_LIST[+ck.dataset.g]; if(!g) return;
    const opt=flatMethods(g)[+ck.dataset.f]; if(!opt) return;
    if(opt.kind==='whole') wholeAt.add(ck.dataset.g+'|'+ck.dataset.i);
  });
  // 第二遍：按规则收
  const bucket=(g)=>{
    const key=String(g['标题']||'未归位');
    let grp=picked.find(p=>p['条款']===key);
    if(!grp){ grp={'条款':key,'做法':[]}; picked.push(grp); }
    return grp;
  };
  checks.forEach(ck=>{
    const g=RV_LIST[+ck.dataset.g]; if(!g) return;
    const opt=flatMethods(g)[+ck.dataset.f]; if(!opt) return;
    if(opt.kind!=='whole' && wholeAt.has(ck.dataset.g+'|'+ck.dataset.i)) return;  // 整条已勾→忽略句子
    const grp=bucket(g);
    if(!grp['做法'].includes(opt.text)) grp['做法'].push(opt.text);
  });
  return picked;
}

/* 复盘四步闭环（2026-10-28 用户定）：① 做法确认（勾选 → 落痕报告 MD「复盘沉淀」节 +
   台账「做法确认」）→ ② 模式草稿（40-质量模式库 + 台账「模式草稿」）→ ③ 四问（灵魂考问 →
   「复盘沉淀」节 + 台账「四问已答」）→ ④ 归档（三步全留痕才亮）。
   状态信号 = 台账字段（值=日期，后端各动作回填、覆盖式）；旧归档卡无字段显示「未完成」
   不强制补（已归档按钮本就是禁用态）。步骤操作以「终版已写」为前提：仅 EXTRACT_FLAG
   即时态（终版未写入）时按钮置灰——确认/留痕必须基于终版内容（tab 仍可进、清单可看）。 */
function rvStep(name,v){
  return v?`<span class="pill ok">${name} ✓ ${escH(v)}</span>`
          :`<span class="pill unk">${name} 未完成</span>`;
}
function rvStatusBar(archived){
  return `<div style="margin-bottom:10px;display:flex;gap:8px;flex-wrap:wrap;align-items:center">
    <span class="detail-sub">复盘闭环：</span>
    ${rvStep('① 做法确认',CUR['做法确认'])}${rvStep('② 模式草稿',CUR['模式草稿'])}${rvStep('③ 四问',CUR['四问已答'])}
    ${archived?'<span class="pill rev">④ 已归档</span>':''}</div>`;
}

async function refreshCurAndReview(){
  /* 各复盘步骤成功后的统一刷新：拉台账 → 更新 CUR → 刷表格/门禁 → 重渲染复盘 tab。
     美化包⑧（2026-11-02）：重渲染前记住滚动位置，渲染后原位恢复——
     勾选确认/写模式草稿/答四问后页面不再跳回顶部。 */
  const keep=$('m-body').scrollTop;
  DATA=await (await fetch('/api/projects')).json();
  if(CUR) CUR=DATA.find(d=>String(d['id'])===CUR['id'])||CUR;
  apply();
  paintMTabs();
  renderReview(keep);
}

/* 美化包⑨（2026-11-02）：报告/复盘 tab 的滚动位置与「只看做法」视图记忆
   （键=项目id+tab；同卡重开/切 tab 回来都在原位、原视图）。 */
let TAB_MEM={};
function tabMemKey(v){ return (CUR?CUR['id']:'')+'|'+v; }
function saveTabMem(){
  const cur=document.querySelector('#m-tabs button.on');
  if(!cur) return;
  const v=cur.dataset.v;
  if(v!=='report'&&v!=='review') return;
  const pvBtn=document.querySelector('.pv-btn.active');
  TAB_MEM[tabMemKey(v)]={scroll:$('m-body').scrollTop, pv:(pvBtn&&pvBtn.dataset.v)||'full'};
}
function restoreTabMem(v){
  const m=TAB_MEM[tabMemKey(v)];
  if(!m) return;
  $('m-body').scrollTop=m.scroll;
  if(v==='report'&&m.pv==='practice'){
    const pb=document.querySelector('.pv-btn[data-v="practice"]');
    if(pb) pb.click();
  }
}

function renderReview(keepScroll){
  /* 复盘 tab（R5 2026-10-25；2026-10-28 四步闭环重构，见 rvStep 注释）。
     keepScroll=美化包⑧：复盘步骤刷新后原位恢复滚动。 */
  const srcs=arr(CUR['来源文件']);
  if(!srcs.length){ $('m-body').innerHTML='<p class="detail-sub">暂无关联报告，无法复盘。</p>'; return; }
  $('m-body').innerHTML='<p class="detail-sub">加载做法清单…</p>';
  fetch('/api/file?path='+encodeURIComponent(srcs[0])).then(r=>r.json()).then(j=>{
    // 2026-10-27 新结构：条目=[{概述,方法:[...]}]；按拉平后的有效方法过滤（空片段已滤）
    const list=(j['做法']||[]).filter(x=>flatMethods(x).length);
    RV_LIST=list;
    const archived=CUR['阶段']==='归档';
    const finalWritten=!!CUR['终版已写'];
    const st1=!!CUR['做法确认'], st2=!!CUR['模式草稿'], st3=!!CUR['四问已答'];
    const lack=[];
    if(!st1) lack.push('做法确认');
    if(!st2) lack.push('模式草稿');
    if(!st3) lack.push('四问');
    const lockTip=finalWritten?'':'终版写入后开放（当前仅为终版 Word 提取即时预览）';
    const dis=finalWritten?'':'disabled';
    // ④ 归档门禁（2026-10-28 用户定）：三步全留痕才亮；已归档显示禁用态
    const archTip=!finalWritten?'终版写入后开放':(lack.length?'闭环未完成，还差：'+lack.join('、'):'三步已留痕，可归档');
    const archBtn=archived
      ?'<button class="btn" id="rv-archived" disabled title="该项目已归档">④ 已归档</button>'
      :`<button class="btn" id="rv-archive" ${(!finalWritten||lack.length)?'disabled':''} title="${archTip}">④ 归档</button>`;
    let html=rvStatusBar(archived);
    if(!list.length){
      // 旧格式报告无结构化做法：确认按钮走「0 条」通道，闭环照样可达
      html+=`<div class="clause-item"><b>① 做法确认</b>
        <div class="detail-sub" style="margin:6px 0">该报告暂无结构化做法数据——条款分节+正文内容是 2026-10-24 上线功能；旧报告可在 Obsidian 里补格式后重新提取。</div>
        <button class="btn" id="rv-confirm" ${dis} title="${lockTip}">确认（本报告无结构化做法）</button></div>`;
    }else{
      html+='<div class="clause-item"><b>① 做法确认（勾选值得沉淀的做法）</b>';
      list.forEach((x,gi)=>{
        html+=`<div style="margin-top:8px"><b>${escH(x['标题']||'未归位')}</b> <span class="detail-sub">${escH(x['类型'])}</span>`;
        let fi=0;   // 组内跨条目连续编号（拉平后的选项下标 = data-f 契约，与模式草稿共用）
        // 遍历顺序必须与 flatMethods 一致：先「整条」再「逐句」
        (x['条目']||[]).forEach((it,ii)=>{
          // 每条 = 概述（小节标题，旧格式无概述则不显示）+ 整条/逐句两组复选框
          if(it['概述'])
            html+=`<div class="ci-head" style="margin-top:6px">${escH(it['概述'])}</div>`;
          const whole=String(it['全文']||'').trim();
          if(whole){   // 整条：值 = 该条正文全文
            html+=`<label style="display:block;margin:6px 0;cursor:pointer" title="${escH(whole)}"><input type="checkbox" class="rv-ck" data-g="${gi}" data-f="${fi}" data-i="${ii}" style="margin-right:6px"><b>【整条】</b>${escH(whole.length>90?whole.slice(0,90)+'…':whole)}</label>`;
            fi++;
          }
          (it['方法']||[]).forEach(f=>{
            if(!String(f||'').trim()) return;   // 过滤 docx 加粗 run 产生的空片段
            html+=`<label style="display:block;margin:6px 0 6px 22px;cursor:pointer"><input type="checkbox" class="rv-ck" data-g="${gi}" data-f="${fi}" data-i="${ii}" style="margin-right:6px">${escH(f)}</label>`;
            fi++;
          });
        });
        html+='</div>';
      });
      html+=`<div style="margin-top:8px"><button class="btn" id="rv-confirm" ${dis} title="${lockTip}">确认勾选的做法</button>
        <span class="detail-sub">落痕到报告 MD「复盘沉淀」节（Obsidian 可见），台账记完成日期</span></div></div>`;
    }
    html+=`<div class="fld" style="margin-top:12px;display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      <button class="btn" id="rv-draft" ${dis} title="${lockTip}">${st2?('② 更新模式草稿（'+escH(CUR['模式草稿'])+'）'):'② 生成模式草稿'}</button>
      <button class="btn" id="rv-soul" ${dis} title="${lockTip}">${st3?('③ 四问 ✓ '+escH(CUR['四问已答'])+'（可补写）'):'③ 灵魂考问（四问）'}</button>
      ${archBtn}
      <span class="detail-sub">模式写入 40-质量模式库，之后去 Obsidian 精修；三步全留痕才能归档</span></div>`;
    $('m-body').innerHTML=html;
    if(keepScroll) $('m-body').scrollTop=keepScroll; else restoreTabMem('review');   // 美化包⑧⑨
    $('rv-confirm').onclick=confirmPractices;
    $('rv-draft').onclick=openModeDraftModal;
    $('rv-soul').onclick=openSoulModal;
    if(!archived&&finalWritten&&!lack.length) $('rv-archive').onclick=archiveProject;
  }).catch(()=>{ $('m-body').innerHTML='<p class="detail-sub">报告加载失败</p>'; });
}

async function confirmPractices(){
  /* ① 做法确认（2026-10-28 用户定；2026-10-30 R2 勾选项结构变更）：勾选做法 →
     /api/practice-confirm（MD 落痕 + 台账置位）。勾选收集口径见 collectPicked。
     有清单但零勾选时弹确认——零条只置位台账、不落空 callout（R4），防手滑。 */
  const picked=collectPicked();
  const n=picked.reduce((s,p)=>s+p['做法'].length,0);
  if(RV_LIST.length&&!n&&!(await ui.confirm('未勾选任何做法。\n\n确认留痕吗？（本报告无需沉淀的做法；也可取消后勾选）'))) return;
  const r=await fetch('/api/practice-confirm',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({project_id:CUR['id'],做法:picked})});
  const j=await r.json().catch(()=>({}));
  if(!r.ok){ ui.toast('做法确认失败：'+(j.detail||r.status)); return; }
  ui.toast('做法确认已留痕（'+n+' 条）→ 报告「复盘沉淀」节，状态①已点亮');
  refreshCurAndReview();
}

/* 复盘 tab 归档（2026-10-28 用户定；门禁=三步全留痕）：ui.confirm 二次确认 → PUT 阶段=归档 →
   统一刷新（状态条变「④ 已归档」）。 */
async function archiveProject(){
  if(!CUR||!CUR['id']){ ui.toast('未获取到项目'); return; }
  if(!(await ui.confirm('确认归档该项目？\n\n· 阶段将改为「归档」，复盘闭环完成\n· 归档后仍可在复盘 tab 补写四问、更新模式草稿'))) return;
  const r=await fetch('/api/projects/'+encodeURIComponent(CUR['id']),{method:'PUT',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({fields:{阶段:'归档'}})});
  const j=await r.json().catch(()=>({}));
  if(!r.ok){ ui.toast('归档失败：'+(j.detail||r.status)); return; }
  ui.toast('已归档：'+(CUR['企业名称']||CUR['id'])+'\n复盘闭环完成——做法确认/模式草稿/四问已留痕，产物在报告 MD 与 40-质量模式库');
  await refreshCurAndReview();
}

let RV_LIST=[];          // 复盘 tab 的做法清单（勾选用）

async function openModeDraftModal(){
  const picked=collectPicked();
  // 2026-10-30 用户最终拍板（R3-a）：模式名/说明**从 40 库模式卡读回**预填——
  // 终版写入时后端已把质量模式段自动写进模式卡，这里 GET /api/mode-card 取回，
  // 不依赖内存变量 CUR_EXTRACT（刷新/切卡即丢）。接口无数据时才回退用内存提取结果。
  let autoName='', autoDesc='';
  try{
    const r=await fetch('/api/mode-card?project_id='+encodeURIComponent(CUR['id']));
    const j=await r.json().catch(()=>({}));
    if(r.ok&&j['存在']){ autoName=String(j['模式名称']||''); autoDesc=String(j['说明']||''); }
    else throw 0;
  }catch(e){
    const modes=(CUR_EXTRACT&&CUR_EXTRACT['模式'])||[];   // 兜底：内存提取结果
    if(modes.length){
      const raw=String(modes[0]['文本']||'').replace(/\*\*/g,'').trim();
      const mi=raw.indexOf('质量模式：');
      const body=(mi>=0?raw.slice(mi+'质量模式：'.length):raw).trim();
      const nl=body.indexOf('\n');
      if(nl>=0){ autoName=body.slice(0,nl).trim(); autoDesc=body.slice(nl+1).trim(); }
      else autoName=body;
    }
  }
  // 2026-10-27 用户定 / 2026-10-30 重申：允许不勾选做法直接生成模式草稿（不卡），
  // 只给提示（toast，不阻塞），用户可在模式卡里补批注
  if(!picked.length)
    ui.toast('未勾选过程方法——没有过程方法支撑的模式不是好模式；可继续编写并在模式卡中补充批注');
  $('mode-preview').innerHTML=picked.length
    ?picked.map(p=>`<b>${escH(p['条款'])}</b><br>`+p['做法'].map(f=>'· '+escH(f)).join('<br>')).join('<br><br>')
    :'<span class="detail-sub">（未勾选做法——可直接生成模式草稿，入选做法留空）</span>';
  $('mode-name').value=autoName; $('mode-desc').value=autoDesc;
  $('modeModal').style.display='flex';
  setTimeout(()=>$('mode-name').focus(),50);           // 美化包⑩：自动聚焦
  $('modeClose').onclick=()=>$('modeModal').style.display='none';
  $('modeCancel').onclick=()=>$('modeModal').style.display='none';
  $('modeOk').onclick=async()=>{
    const name=($('mode-name').value||'').trim();
    if(!name){ ui.toast('填模式名称'); return; }
    const r=await fetch('/api/mode-draft',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({project_id:CUR['id'],模式名称:name,说明:$('mode-desc').value.trim(),做法:picked})});
    const j=await r.json().catch(()=>({}));
    if(!r.ok){ ui.toast('写入失败：'+(j.detail||r.status)); return; }
    $('modeModal').style.display='none';
    ui.toast('模式草稿已写入 40-质量模式库/'+j['文件']+'\n去 Obsidian 精修即为正式模式卡');
    refreshCurAndReview();   // 状态②点亮（台账「模式草稿」=今天，后端已回填）
  };
}

// ── 提取 Word（B1 文审提取，内嵌在报告 tab 的展开区）───────
async function renderExtractInto(container){
  container.innerHTML=`
    <div class="fld"><label>选择 Word 评审报告（.docx，临时解析不留存）</label>
      <input type="file" id="extract-file" accept=".docx"></div>
    <div id="extract-result"><p class="detail-sub">选文件后自动解析，这里显示提取的结构化数据</p></div>`;
  $('extract-file').onchange=async e=>{
    const f=e.target.files[0];
    if(!f) return;
    $('extract-result').innerHTML='<p class="detail-sub">解析中…</p>';
    const fd=new FormData();
    fd.append('file', f);
    const r=await fetch('/api/extract-docx', {method:'POST', body:fd});
    const j=await r.json().catch(()=>({}));
    if(!r.ok){ $('extract-result').innerHTML='<p class="detail-sub">解析失败：'+escH(j.detail||r.status)+'</p>'; return; }
    CUR_EXTRACT=j;
    CUR_EXTRACT['_来源文件名']=f.name;   // Word 不留存，只记名（提取日志/自检用）
    // 2026-10-30 用户最终拍板：你能上传「终版评审报告」本身就说明现场核实的活干完了
    // —— 这是动作事实。故现场态卡提取终版 Word 完成即视为现场核实环节结束：
    // 「进入现场评审环节」就地置灰（EXTRACT_FLAG），避免回头再点干扰复盘；
    // 「复盘」仍只认「终版已写」，必须真正写入终版后才开（tab 条是开卡时画的静态
    // HTML，此处就地重绘）
    if(isOnsiteStageOf(CUR)){ EXTRACT_FLAG=true; paintMTabs(); }
    $('extract-result').innerHTML=extractHtml(j)+
      `<div class="fld" style="margin-top:12px"><button class="btn" id="extract-write">条款归位并写入报告</button></div>`;
    $('extract-write').onclick=openClauseModal;
  };
}

let CUR_EXTRACT=null;   // 最近一次提取结果（含评分表/澄清/意见结论/子条款/归位条款）

function normEntries(v){
  /* 兼容两种格式：条目 dict（新，带标题/加粗）或纯字符串（旧） */
  if(!Array.isArray(v)) return [];
  return v.map(x=>typeof x==='string'?{标题:'',文本:x,加粗片段:[],段落数:1}:x).filter(Boolean);
}

function extractHtml(j){
  const clar=j['澄清']||[];
  const rows=[];
  rows.push(`<div class="sec">企业名称</div><div class="rv">${escH(j['企业名称']||'（未识别）')}</div>`);
  const scoreN=(j['评分表']||[]).length;
  if(scoreN||clar.length){
    rows.push(`<div class="sec">评分表与澄清（现场评审阶段使用）</div>`);
    rows.push(`<div class="rv">评分表 ${scoreN} 项 · 澄清 ${clar.length} 条 · 得分 ${escH(j['总计']?j['总计']['得分']:'—')} 分 · ${escH(j['推荐']||'')} —— 文审不写入，进入现场评审时提取、勾选条款后使用</div>`);
  }
  if(j['自检']&&j['自检']['提示'])
    rows.push(`<div class="rv" style="border-color:var(--warn);color:var(--warn)">⚠ ${escH(j['自检']['提示'])}</div>`);
  const op=j['意见结论']||{};
  const advs=normEntries(op['主要优势']), sugs=normEntries(op['主要改进建议']);
  if(op['基本情况']||advs.length||sugs.length||op['评审结论']){
    rows.push(`<div class="sec">资料评审意见和结论</div>`);
    if(op['基本情况']) rows.push(`<div class="clause-item"><b>一、基本情况</b><div class="rv">${escH(op['基本情况'])}</div></div>`);
    if(advs.length) rows.push(`<div class="clause-item"><b>二、主要优势（${advs.length} 条，加粗=方法）</b>${entryListHtml(advs)}</div>`);
    if(sugs.length) rows.push(`<div class="clause-item"><b>三、主要改进建议（${sugs.length} 条，加粗=方法）</b>${entryListHtml(sugs)}</div>`);
    if(op['评审结论']) rows.push(`<div class="clause-item"><b>四、资料评审结论</b><div class="rv">${escH(op['评审结论'])}</div></div>`);
  }
  if((j['模式']||[]).length)
    rows.push(`<div class="sec">识别到质量模式 ${j['模式'].length} 段</div>`+
      j['模式'].map(m=>`<div class="rv">${escH(String(m['文本']||'').slice(0,120))}</div>`).join(''));
  return rows.join('');
}

function entryListHtml(entries){
  return entries.map((e,i)=>{
    const bold=(e['加粗片段']||[]);
    const num=(e['序号']||'')?escH(e['序号'])+' ':'';
    return `<div class="ci-item">
      <div class="ci-head">#${i+1} ${num}${e['标题']?'概述：'+escH(e['标题']):''}${bold.length?` · 方法 ${bold.length} 处`:''}</div>
      <div class="rv" style="color:var(--tx2)">展开：${escH(String(e['文本']||'').replace(/\*\*/g,'').slice(0,100))}</div>
      ${bold.length?`<div class="ci-bold">方法：${bold.map(b=>escH(b)).join('；')}</div>`:''}
    </div>`;
  }).join('');
}

// ── 灵魂考问（复盘四问，一题一屏；2026-10-27 起收敛为复盘 tab 专属，上传/写入流程不再考问）──
const SOUL_Q=[
  {k:'长见识', q:'这个企业/项目，让我认知到了什么以前不知道、想不到的？', g:'行业暗知识、没想到的模式手法、原来可以这样干…'},
  {k:'校准',   q:'我（文审时）的判断，现场被证实了哪些、推翻了哪些？为什么？', g:'评审直觉的对账——被推翻的比被证实的更值钱'},
  {k:'提炼',   q:'哪几个做法/句式/提问技巧，下个项目可以直接搬过去用？', g:'可复用的才是你的资产'},
  {k:'避雷',   q:'我踩过/差点踩的坑是什么？重来一次会在哪个条款多问一句？', g:'防火墙——写下来就不会再犯第二次'},
];
let SOUL_I=0, SOUL_A={};

function openSoulModal(){
  SOUL_I=0; SOUL_A={};
  $('soulModal').style.display='flex';
  paintSoul();
}
function paintSoul(){
  const q=SOUL_Q[SOUL_I];
  $('soulTitle').textContent=`灵魂考问 · 第 ${SOUL_I+1}/${SOUL_Q.length} 题`;
  $('soulGuide').innerHTML=`<b>${q.k}</b>——${escH(q.q)}<br><span style="color:var(--tx2)">${escH(q.g)}</span>`;
  $('soulInput').value=SOUL_A[SOUL_I]||'';
  $('soulHint').textContent=`第 ${SOUL_I+1} 题 / 共 ${SOUL_Q.length} 题 · 答完保存进复盘沉淀`;
  $('soulNext').textContent=SOUL_I===SOUL_Q.length-1?'保存':'下一题';
  $('soulSkip').style.display=SOUL_I===SOUL_Q.length-1?'none':'';
  setTimeout(()=>$('soulInput').focus(),50);           // 美化包⑩：自动聚焦
  $('soulClose').onclick=()=>{ $('soulModal').style.display='none'; };
  $('soulSkip').onclick=()=>{ SOUL_A[SOUL_I]=''; SOUL_I++; SOUL_I<SOUL_Q.length?paintSoul():finishSoul(); };
  $('soulNext').onclick=()=>{ SOUL_A[SOUL_I]=$('soulInput').value.trim(); SOUL_I++; SOUL_I<SOUL_Q.length?paintSoul():finishSoul(); };
}
function finishSoul(){
  // B3 guard（2026-10-27 用户定）：四问全空不写——防止再产生全「（未答）」的空模板
  if(!SOUL_Q.some((q,i)=>(SOUL_A[i]||'').trim())){ ui.toast('至少答一问再保存'); return; }
  const note=SOUL_Q.map((q,i)=>`**Q${i+1} ${q.k}**：${q.q}\nA：${(SOUL_A[i]||'').trim()||'（未答）'}`).join('\n\n');
  $('soulModal').style.display='none';
  // 2026-10-27 起唯一入口 = 复盘 tab：保存即写入「复盘沉淀」节（手写节，程序永不覆盖）
  fetch('/api/review-note',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({project_id:CUR['id'],note})})
    .then(r=>r.json()).then(j=>{
      ui.toast(j.ok?('灵魂考问已写入 '+j['文件']+' 的「复盘沉淀」节，状态③已点亮'):('写入失败：'+(j.detail||'')));
      if(j.ok) refreshCurAndReview();   // 状态③点亮（台账「四问已答」=今天，后端已回填）
    });
}

// ── B2 归位写入 ───────────────────────────────────────────
let CLAUSE_DATA=null;    // 归位弹窗暂存 {优势:[entry...], 建议:[entry...]}
let CLAUSE_LIST=[];      // config 条款归位清单（12 项）
let PLACE_TARGET='';     // 写入目标：''=文审 20 库 / '现场'=组长终版 30 库

/* ③ 归位历史记忆（localStorage）：同类小标题上次选过 → 这次自动带出 */
const CLAUSE_MEM_KEY='zp_clause_memory';
function memGet(k){ try{ return (JSON.parse(localStorage.getItem(CLAUSE_MEM_KEY)||'{}'))[k]||''; }catch(e){ return ''; } }
function memSet(k,v){ try{
  const m=JSON.parse(localStorage.getItem(CLAUSE_MEM_KEY)||'{}');
  if(v) m[k]=v; else delete m[k];
  localStorage.setItem(CLAUSE_MEM_KEY,JSON.stringify(m));
}catch(e){} }
function memKey(e){ return (e['标题']||String(e['文本']||'').replace(/\*\*/g,'').slice(0,16)).trim(); }
/* 序号前缀剥离：选了条款 → 「（一）/1.」让位给条款号（用户 2026-10-25 定）；
   未归位的条目保留原文序号。 */
function stripNum(t){ return String(t||'').replace(/^[（(][一二三四五六七八九十]+[）)]\s*|^\d+[、．.]\s*/, ''); }

function guessClause(entry, clauses){
  /* 按小标题+正文关键词猜条款：标题命中权重 5、正文命中权重 1，
     每个关键词只计一次（防正文重复词压过标题）。猜中用户确认、猜空手工选。*/
  const title=String(entry['标题']||'');
  const text=String(entry['文本']||'').replace(/\*\*/g,'');
  let best='', bestScore=0;
  for(const c of (clauses||[])){
    let s=0;
    for(const kw of (c['关键词']||[])){
      if(title.includes(kw)) s+=5;
      else if(text.includes(kw)) s+=1;
    }
    if(s>bestScore){ bestScore=s; best=String(c['号']); }
  }
  return best;
}

function openClauseModal(){
  const j=CUR_EXTRACT;
  if(!j){ ui.toast('请先选择 Word 文件完成提取'); return; }
  const clauses=j['归位条款']||[];
  CLAUSE_LIST=clauses;
  const op=j['意见结论']||{};
  const groups=[['优势',normEntries(op['主要优势'])],['建议',normEntries(op['主要改进建议'])]];
  if(!groups[0][1].length && !groups[1][1].length){ openPlaceModal(); return; }  // 无条目：走原路
  CLAUSE_DATA={优势:groups[0][1], 建议:groups[1][1]};
  let html='';
  for(const [label,entries] of groups){
    if(!entries.length) continue;
    html+=`<div class="sec">主要${label}（${entries.length} 条）</div>`;
    entries.forEach((e,i)=>{
      const guess=memGet(memKey(e))||guessClause(e,clauses);   // 记忆优先，其次关键词猜
      const bold=(e['加粗片段']||[]);
      html+=`<div class="clause-item">
        <div class="ci-head">${label} #${i+1}${e['标题']?' · 概述：'+escH(e['标题']):''}${bold.length?` · 方法 ${bold.length} 处`:''}</div>
        <div class="rv" style="color:var(--tx2)">展开：${escH(String(e['文本']||'').replace(/\*\*/g,'').slice(0,80))}…</div>
        ${bold.length?`<div class="ci-bold">方法：${bold.map(b=>escH(b.slice(0,30))).join('；')}</div>`:''}
        <select class="ci-sel" data-g="${label}" data-i="${i}">
          <option value=""${guess?'':' selected'}>未归位（条款标识挂「概述」）</option>
          ${clauses.map(c=>`<option value="${c['号']}"${guess===String(c['号'])?' selected':''}>${c['号']} ${c['名']}</option>`).join('')}
        </select></div>`;
    });
  }
  $('clauseBody').innerHTML=html;
  $('clauseModal').style.display='flex';
  updateClauseHint();
  { const s0=$('clauseBody').querySelector('.ci-sel'); if(s0) setTimeout(()=>s0.focus(),50); }   // 美化包⑩
  $('clauseModalClose').onclick=()=>$('clauseModal').style.display='none';
  $('clauseCancel').onclick=()=>$('clauseModal').style.display='none';
  $('clauseOk').onclick=confirmClauses;
  $('clauseMemClear').onclick=()=>{
    try{ localStorage.removeItem(CLAUSE_MEM_KEY); }catch(e){}
    ui.toast('已清除条款选择记忆');
    $('clauseBody').querySelectorAll('select').forEach(s=>{
      const arr=s.dataset.g==='优势'?CLAUSE_DATA.优势:CLAUSE_DATA.建议;
      const e=arr[+s.dataset.i];
      s.value=e?guessClause(e,CLAUSE_LIST):'';
    });
    updateClauseHint();
  };
  $('clauseBody').querySelectorAll('select').forEach(s=>s.onchange=updateClauseHint);
}

function updateClauseHint(){
  const sels=[...$('clauseBody').querySelectorAll('select')];
  const un=sels.filter(s=>!s.value).length;
  $('clauseHint').textContent=un?`${un} 条未归位 → 将进「未归位」节，复盘时补`:'全部已归位';
}

function confirmClauses(){
  $('clauseBody').querySelectorAll('select').forEach(s=>{
    const arr=s.dataset.g==='优势'?CLAUSE_DATA.优势:CLAUSE_DATA.建议;
    const e=arr[+s.dataset.i];
    if(e){
      e['条款']=s.value||'';
      memSet(memKey(e), s.value||'');       // 选择进记忆，下次同标题自动带出
      // 选了条款 → 剥离标题序号前缀（条款号进 MD 节标题）；未归位保留原文序号
      if(s.value && e['标题']) e['标题']=stripNum(e['标题']);
      if(s.value) e['序号']='';
    }
  });
  const j=CUR_EXTRACT;
  if(j&&j['意见结论']){ j['意见结论']['主要优势']=CLAUSE_DATA.优势; j['意见结论']['主要改进建议']=CLAUSE_DATA.建议; }
  $('clauseModal').style.display='none';
  openPlaceModal();                         // 归位确认后直接进写入弹窗（2026-10-27 用户定：上传/写入流程不再灵魂考问）
}

async function openPlaceModal(){
  const j=CUR_EXTRACT;
  if(!j){ ui.toast('请先提取 Word 或粘贴复盘内容'); return; }
  const op=j['意见结论']||{};
  const advN=normEntries(op['主要优势']).length;
  const sugN=normEntries(op['主要改进建议']).length;
  const modes=(j['模式']||[]).length;
  // 写入目标按阶段锁定（2026-10-27 用户定：报告归口唯一化——一个企业的报告要么文审
  // 要么现场，不允许双存）：现场态锁「现场报告终版（30 库）」、文审态锁「文审报告
  // （20 库）」，另一个按钮 disabled 变灰不可选
  PLACE_TARGET=isOnsiteStageOf(CUR)?'现场':'';
  // 现场态：通配发现 30 库已有现场报告（容忍「-现场评审」后缀）——日期自动带出 +
  // 明示「更新而不是新建」（后端 /api/onsite-report-path 与写入端同一发现逻辑）
  let onsireName='';
  if(PLACE_TARGET){
    try{
      const rp=await (await fetch('/api/onsite-report-path?project_id='+encodeURIComponent(CUR['id']))).json();
      onsireName=rp['文件名']||'';
    }catch(e){ onsireName=''; }
  }
  $('placeTitle').textContent=PLACE_TARGET?'写入现场报告终版':'写入文审报告';
  $('place-intro').textContent=PLACE_TARGET
    ?(onsireName?('将更新已有现场报告：'+onsireName+'（程序节按本次提取覆盖，旧「现场核实信息」的普通条款块自动折叠归档到文尾（伪条目/开场白保留）；写入成功后文审报告删除）')
                 :'将提取的基本情况、主要优势、主要改进建议写入现场报告终版（30 库）：程序节按本次提取覆盖，旧「现场核实信息」的普通条款块自动折叠归档到文尾（伪条目/开场白保留）；写入成功后文审报告删除。')
    :'将提取的基本情况、主要优势、主要改进建议写入文审报告（优势/建议已按条款分节，重跑只覆盖程序节、手写节保留）。评审结论只回台账，评分表与澄清留待现场评审阶段使用。';
  const rows=[`<div class="rv">将写入：基本情况 + 主要优势 ${advN} 条 + 主要改进建议 ${sugN} 条（已按条款分节）${modes?` + 质量模式 ${modes} 段`:''}</div>`];
  rows.push(`<div class="fld"><label>写入目标（按阶段锁定）</label>
    <div style="display:flex;gap:8px">
      <button class="btn pv-btn${PLACE_TARGET?'':' active'}" data-t="" ${PLACE_TARGET?'disabled':''}>文审报告（20 库）</button>
      <button class="btn pv-btn${PLACE_TARGET?' active':''}" data-t="现场" ${PLACE_TARGET?'':'disabled'}>现场报告终版（30 库）</button>
    </div>
    <div class="detail-sub" style="margin-top:4px">${PLACE_TARGET?'现场阶段：终版写入 30 库（程序节全覆盖、旧现场核实信息折叠归档），写入后文审报告自动删除':'文审阶段：写入 20 库；进入现场评审、组长复盘后再写终版'}</div></div>`);
  // 现场日期自动带出：① 30 库已有现场报告的文件名日期（^(\d{8})-）② 卡片「现场日期」；都空则留空
  let defDate=(PLACE_TARGET?(CUR['现场日期']||''):(CUR['报告日期']||''))||'';
  if(PLACE_TARGET&&onsireName){
    const dm=onsireName.match(/^(\d{4})(\d{2})(\d{2})-/);
    if(dm) defDate=`${dm[1]}-${dm[2]}-${dm[3]}`;
  }
  rows.push(`<div class="fld"><label id="place-date-label">${PLACE_TARGET?'现场日期':'报告日期'}</label><input type="date" id="place-date" value="${escH(defDate)}"></div>`);
  $('placeForm').innerHTML=rows.join('');
  // 2026-11-02 老张定：勾选条款、确认日期后直接写入，不再弹窗确认报告内容
  $('place-date').value=defDate;
  doWriteReview();
  $('placeModalClose').onclick=()=>$('placeModal').style.display='none';
  $('placeCancel').onclick=()=>$('placeModal').style.display='none';
  $('placeOk').onclick=doWriteReview;
}

async function doWriteReview(){
  const j=CUR_EXTRACT;
  if(!j) return;
  const dateEl=$('place-date');
  const date=dateEl?dateEl.value:'';
  const body={
    id:CUR['id'],
    企业名称:j['企业名称']||'',
    意见结论:j['意见结论'],
    总计:j['总计']||{},
    报告日期:date,
    评分表:j['评分表']||[],
    澄清:j['澄清']||[],
    汇总:j['汇总']||[],
    推荐:j['推荐']||'',
    来源文件名:j['_来源文件名']||'',
    目标:PLACE_TARGET,
    模式:j['模式']||[]
  };
  $('placeOk').disabled=true; $('placeOk').textContent='写入中…';
  const r=await fetch('/api/write-review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const res=await r.json().catch(()=>({}));
  $('placeOk').disabled=false; $('placeOk').textContent='确认写入';
  if(!r.ok){ ui.toast('写入失败：'+(res.detail||r.status)); return; }
  $('placeModal').style.display='none';
  DATA=await (await fetch('/api/projects')).json();
  if(CUR) CUR=DATA.find(d=>String(d['id'])===CUR['id'])||CUR;
  apply();
  if(PLACE_TARGET==='现场'){
    // 2026-11-02 老张定:确认写入后直接关闭报告窗体(归位结果已写入 MD,复盘可随时从台账重开)
    closeReport();
    ui.toast('终版报告已生成——已进入复盘：① 确认做法 → ② 模式草稿 → ③ 四问 → ④ 归档'
      +'\n已写入：'+res['路径']+'（得分 '+res['得分']+' 分）'
      +((res['已删除文审']||[]).length?'\n归口唯一化：已删除 '+(res['已删除文审']||[]).length+' 份文审报告 md':''));
  }else{
    closeReport();
    ui.toast('已写入：'+res['路径']+'\n得分 '+res['得分']+' 分 · 阶段已按评审结论推进');
  }
}

// ── 现场评审：进入现场环节（核实窗体）+ 编辑弹窗勾选条款 ─────────
let ONSITE_DATA=null;      // 核实窗体数据（/api/onsite-report-terms，解析自现场报告 MD）
let OS_SELECTED=null;      // 核实窗体当前查看的条款号（null=未选）
let OS_NOTES={};           // 条款号 → 现场核实文本
let OS_NOTES_INIT={};      // 打开核实窗体时的快照（用于判断是否存在未保存改动）
let OS_DIRTY=false;        // 是否存在未保存的现场核实改动
let OS_SAVING=false;       // 切换条款触发保存时的进行中锁（防连点）
let OS_LEFT_W=250;         // 核实窗体左栏宽度（拖拽可调）
let OS_SIDE_W=380;         // 核实窗体右栏「条款心得/原文」宽度（拖拽可调，默认同 CSS 380px）
let OB_W=920;              // 报告预览窗体宽度（左右拖拽可调）
/* 美化包⑥（2026-11-02）：三个宽度 localStorage 记忆 + 双击把手复位，读写集中在 WIDTHS_* */
const WIDTHS_KEY='zp_widths';
const WIDTHS_DEF={OS_LEFT_W:250,OS_SIDE_W:380,OB_W:920};
function loadWidths(){
  let s={}; try{ s=JSON.parse(localStorage.getItem(WIDTHS_KEY)||'{}'); }catch(e){}
  OS_LEFT_W=Math.min(520,Math.max(140,Number(s.OS_LEFT_W)||WIDTHS_DEF.OS_LEFT_W));
  OS_SIDE_W=Math.min(900,Math.max(280,Number(s.OS_SIDE_W)||WIDTHS_DEF.OS_SIDE_W));
  OB_W=Math.min(1500,Math.max(460,Number(s.OB_W)||WIDTHS_DEF.OB_W));
}
function saveWidths(){
  try{ localStorage.setItem(WIDTHS_KEY,JSON.stringify({OS_LEFT_W,OS_SIDE_W,OB_W})); }catch(e){}
}
function resetWidths(){
  try{ localStorage.removeItem(WIDTHS_KEY); }catch(e){}
  OS_LEFT_W=WIDTHS_DEF.OS_LEFT_W; OS_SIDE_W=WIDTHS_DEF.OS_SIDE_W; OB_W=WIDTHS_DEF.OB_W;
  const box=$('reportBox'); if(box&&!box.classList.contains('full')) box.style.width=OB_W+'px';
  const lft=$('opaneLeft'); if(lft&&!lft.classList.contains('collapsed')) lft.style.flexBasis=OS_LEFT_W+'px';
  const side=$('opaneSide'); if(side&&side.style.display!=='none') side.style.flexBasis=OS_SIDE_W+'px';
  ui.toast('窗体宽度已恢复默认（250 / 380 / 920）');
}
loadWidths();              // 启动即读记忆宽度
let OS_SIDE_PATH=null;     // 心得窗格当前条款路径
let PICK_DATA=null;        // 勾选弹窗数据（/api/onsite-score 评分表缓存）
let PICK_ITEMS=[];         // 勾选弹窗条目
let ED_PICKS=[];           // 编辑弹窗暂存的勾选条款（picks）
let UPDATE_PENDING=false;  // 勾选确认后是否自动接「写入现场报告」

async function renderOnsite(){
  $('m-body').innerHTML='<p class="detail-sub">加载现场评审报告…</p>';
  const r=await fetch('/api/onsite-report-terms?project_id='+encodeURIComponent(CUR['id']));
  const j=await r.json().catch(()=>({}));
  if(!j['ok']){
    $('m-body').innerHTML='<p class="detail-sub">'+escH(j['提示']||('加载失败：'+(j.detail||r.status)))+'</p>';
    return;
  }
  ONSITE_DATA=j;
  openOnsitePane();
}

// 核实窗体：左栏条款 = 解析现场报告 MD 的「### 条款标题」（MD 为唯一真源）
// 优势栏用条款块内自己的「文审优势」行（2026-10-27 回退：不再按条款号前两段匹配
// 「## 主要优势」节全文预填）；派生伪条目（报告主要优势条款·X / 报告主要建议条款·X）
// 的优势/可改进之处由后端读取时从对应节现派生带回，前端照常三栏渲染——
// 全链路按条款号字符串处理（无排序/无格式假设），伪条目条款号唯一不碰撞
function opaneTerms(){
  const arr=(ONSITE_DATA['条款']||[]).map(t=>({
    条款号:t['条款号'],条款名:t['条款名'],文件:t['目标文件'],路径:t['路径']||'',
    条目:[{优势:t['优势']||'',可改进之处:t['可改进之处']||'',现场核实:t['现场核实']||''}]
  }));
  // 组长：开场白视为「我负责的条款」之一（内容取自现场报告 MD「## 开场白」节，写回同一节）
  if(ONSITE_DATA['组长']) arr.unshift({条款号:'开场白',条款名:'',文件:'',路径:'',条目:[{优势:'',可改进之处:''}]});
  return arr;
}

function opanePath(no){
  const t=(ONSITE_DATA['条款']||[]).find(x=>String(x['条款号'])===String(no));
  return (t&&t['路径'])||'';
}

function openOnsitePane(){
  const terms=opaneTerms();
  if(!terms.length){ ui.toast('现场评审报告中没有条款核实内容。'); return; }
  $('opaneTitle').textContent='现场评审 · '+(CUR['企业名称']||'');
  $('onsitePane').style.display='flex';
  $('opaneClose').onclick=closeOpaneGuarded;
  $('opaneExpand').onclick=()=>{ $('opaneLeft').classList.remove('collapsed'); $('opaneLeft').style.flexBasis=OS_LEFT_W+'px'; };
  $('opaneSideClose').onclick=()=>{ $('opaneSide').style.display='none'; $('opaneSideRz').style.display='none'; };
  $('opaneSideNote').onclick=opaneAddNote;
  $('opaneSave').onclick=opaneSaveNotes;
  $('opaneExport').onclick=()=>{
    if(!CUR||!CUR['id']){ ui.toast('未获取到项目'); return; }
    location.href='/api/export-onsite-docx?project_id='+encodeURIComponent(CUR['id']);
    ui.toast('正在生成 Word（按条款三栏：文审优势/可改进之处/现场核实）…');
  };
  bindOpaneResize();
  bindOpaneSideResize();
  OS_NOTES={};
  terms.forEach(t=>{ OS_NOTES[t['条款号']]=(t['条目'][0]||{})['现场核实']||''; });
  OS_NOTES_INIT=JSON.parse(JSON.stringify(OS_NOTES));
  // 组长：开场白伪条目的内容从后端「## 开场白」节提取，纳入保存集合
  if(ONSITE_DATA['组长']) OS_NOTES['开场白']=ONSITE_DATA['开场白']||'';
  OS_DIRTY=false;
  OS_SELECTED=null; OS_SIDE_PATH=null;
  $('opaneSide').style.display='none';
  $('opaneSideRz').style.display='none';
  $('opaneLeft').classList.remove('collapsed');
  $('opaneLeft').style.flexBasis=OS_LEFT_W+'px';
  renderOpaneList();
  renderOpaneMain(null);
}

function renderOpaneList(){
  const rows=opaneTerms().map(t=>{
    const sel=OS_SELECTED===t['条款号']?' sel':'';
    return `<div class="opane-term${sel}" data-no="${escH(t['条款号'])}">
      <span class="no">${escH(t['条款号'])}</span><span class="nm">${escH(t['条款名']||'')}</span></div>`;
  }).join('');
  $('opaneList').innerHTML=rows;
  $('opaneList').querySelectorAll('.opane-term').forEach(el=>{
    el.onclick=()=>selectOpaneTerm(el.dataset.no);
  });
}

// 切换条款：当前条款有未保存核实内容时，先提示保存（确定=保存后切换；取消=留在当前条款）
async function selectOpaneTerm(no){
  if(no===OS_SELECTED) return;      // 点的就是当前条款，无需切换
  if(OS_SAVING) return;             // 正在保存，防连点
  if(OS_DIRTY){
    const filled=Object.values(OS_NOTES).filter(v=>v&&String(v).trim()).length;
    if(!(await ui.confirm('当前有未保存的核实内容（已填 '+filled+' 条）。\n确定＝先保存再切换；取消＝留在当前条款继续编辑。'))) return;
    const res=await saveOsNotes();
    if(!res.ok){ ui.toast('保存失败：'+res.提示+'\n将留在当前条款，未保存内容不会丢失。'); return; }
  }
  OS_SELECTED=no;
  $('opaneLeft').classList.add('collapsed');
  $('opaneLeft').style.flexBasis='34px';
  renderOpaneList();
  renderOpaneMain(no);
}

function renderOpaneMain(no){
  if(!no){
    $('opaneMain').innerHTML='<div class="opane-empty">点左侧条款编号开始核实</div>';
    return;
  }
  const t=opaneTerms().find(x=>x['条款号']===no);
  if(!t){ $('opaneMain').innerHTML=''; return; }
  const isOpening=(no==='开场白');
  const title=isOpening?'开场白':((t['条款号']||'')+' '+(t['条款名']||''));
  const items=(t['条目']||[]).map(it=>{
    let h='';
    if(it['优势']) h+=`<div class="opane-kv"><span class="k">优势</span><span class="v">${escH(it['优势'])}</span></div>`;
    if(it['可改进之处']) h+=`<div class="opane-kv"><span class="k">可改进之处</span><span class="v">${escH(it['可改进之处'])}</span></div>`;
    return h;
  }).join('');
  const noteK=isOpening?'内容':'现场核实';
  const notePh=isOpening?'填写开场白内容（组长进场宣读）…':'现场填写核实内容…';
  $('opaneMain').innerHTML=`
    <div class="opane-title" data-path="${escH(t['路径']||'')}" data-title="${escH(title)}">${escH(title)}</div>
    ${items}
    <div class="opane-kv"><span class="k">${noteK}</span><textarea class="opane-note" placeholder="${notePh}">${escH(OS_NOTES[no]||'')}</textarea></div>
    ${isOpening?'<div class="opane-kv"><button class="btn" id="opaneOpeningLoad">载入标准话术</button></div>':''}`;
  const ti=$('opaneMain').querySelector('.opane-title');
  ti.onclick=()=>{ const p=ti.dataset.path; if(p) openOpaneSide(p, ti.dataset.title||title); };
  const note=$('opaneMain').querySelector('.opane-note');
  if(note) note.oninput=()=>{ OS_NOTES[no]=note.value; OS_DIRTY=true; };
  const ol=$('opaneOpeningLoad');
  if(ol) ol.onclick=loadOpeningScript;
}

// 载入固定标准话术（本地读取不脱敏）→ 填入开场白编辑框（可再改，保存即写回 MD）
async function loadOpeningScript(){
  const ta=$('opaneMain').querySelector('.opane-note');
  if(!ta) return;
  if(ta.value.trim()&&!(await ui.confirm('开场白已有内容，载入标准话术将覆盖当前内容。确定覆盖？'))) return;
  const r=await fetch('/api/opening');
  const j=await r.json().catch(()=>({}));
  if(j['ok']){ ta.value=j['文本']||''; OS_NOTES['开场白']=ta.value; OS_DIRTY=true; }
  else ui.toast(j['提示']||('加载失败：'+(j.detail||r.status)));
}

async function openOpaneSide(path,title){
  OS_SIDE_PATH=path;
  $('opaneSideTitle').textContent=title||'条款';
  $('opaneSide').style.display='flex';
  $('opaneSideRz').style.display='';
  $('opaneSideBody').innerHTML='加载中…';
  const r=await fetch('/api/clause?path='+encodeURIComponent(path));
  const j=await r.json().catch(()=>({}));
  $('opaneSideBody').innerHTML=r.ok?j.html:'<p class="detail-sub">加载失败：'+(j.detail||r.status)+'</p>';
}

async function opaneAddNote(){
  if(!OS_SIDE_PATH) return;
  const note=await askNote();
  if(!note||!note.trim()) return;
  const r=await fetch('/api/clause-note',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:OS_SIDE_PATH,note:note})});
  if(r.ok){ openOpaneSide(OS_SIDE_PATH,$('opaneSideTitle').textContent); }
  else{ const j=await r.json().catch(()=>({})); ui.toast('追加失败：'+(j.detail||r.status)); }
}

// 保存核实内容 → 写回现场报告 MD；返回 {ok,更新} 或 {ok:false,提示}（保存按钮与切换条款共用）
// A1② 增量语义：只发相对开屏快照（OS_NOTES_INIT）变化过的键。后端按键逐条写 MD、缺键不清空——
// 若发全字典，未加载出来或被并发会话改过的键会带着旧值/空值把 MD 已存内容冲掉（A1 数据事故根因）。
async function saveOsNotes(){
  const diff={};
  new Set([...Object.keys(OS_NOTES),...Object.keys(OS_NOTES_INIT)]).forEach(k=>{
    if((OS_NOTES[k]||'')!==(OS_NOTES_INIT[k]||'')) diff[k]=OS_NOTES[k]||'';
  });
  const r=await fetch('/api/onsite-note',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:CUR['id'],核实:diff})});
  const j=await r.json().catch(()=>({}));
  if(r.ok){
    OS_DIRTY=false;
    OS_NOTES_INIT=JSON.parse(JSON.stringify(OS_NOTES));
    return {ok:true,更新:j['更新']};
  }
  return {ok:false,提示:j['detail']||r.status};
}

async function opaneSaveNotes(){
  const res=await saveOsNotes();
  if(res.ok) ui.toast('已写回现场报告 '+res.更新+' 条内容');
  else ui.toast('保存失败：'+res.提示);
}

function bindOboxResize(){
  const box=$('reportBox');
  if(!box||!$('oboxRzL')||!$('oboxRzR')) return;   // 报告弹窗 DOM 未就绪（脚本在弹窗 HTML 之前）则跳过
  let state=null;   // {dir, sx, sw, rz}
  const down=dir=>e=>{
    if(box.classList.contains('full')) return;
    state={dir, sx:e.clientX, sw:box.getBoundingClientRect().width, rz:e.currentTarget};
    state.rz.classList.add('on');
    document.body.style.cursor='col-resize'; document.body.style.userSelect='none';
    e.preventDefault();
  };
  $('oboxRzL').onmousedown=down(-1);
  $('oboxRzR').onmousedown=down(1);
  document.addEventListener('mousemove',e=>{
    if(!state) return;
    const dw=state.dir*(e.clientX-state.sx);
    OB_W=Math.min(1500,Math.max(460,state.sw+dw));
    box.style.width=OB_W+'px';
  });
  document.addEventListener('mouseup',()=>{
    if(!state) return;
    state.rz.classList.remove('on');
    state=null;
    document.body.style.cursor=''; document.body.style.userSelect='';
    saveWidths();                                   // 美化包⑥：宽度落记忆
  });
  [$('oboxRzL'),$('oboxRzR')].forEach(h=>{ h.ondblclick=resetWidths; });   // 美化包⑥：双击复位
}

function bindOpaneResize(){
  const rz=$('opaneRz'), left=$('opaneLeft');
  let sx=0, sw=0, on=false;
  rz.onmousedown=e=>{ on=true; sx=e.clientX; sw=OS_LEFT_W; rz.classList.add('on'); document.body.style.cursor='col-resize'; e.preventDefault(); };
  document.addEventListener('mousemove',e=>{
    if(!on) return;
    OS_LEFT_W=Math.min(520,Math.max(140,sw+e.clientX-sx));
    if(!$('opaneLeft').classList.contains('collapsed')) left.style.flexBasis=OS_LEFT_W+'px';
  });
  document.addEventListener('mouseup',()=>{ if(!on) return; on=false; rz.classList.remove('on'); document.body.style.cursor=''; saveWidths(); });
  rz.ondblclick=resetWidths;                        // 美化包⑥：双击复位
}

// 右栏「条款心得/原文」宽拖拽（手柄在主区与侧栏之间；侧栏关闭时手柄一并隐藏）
function bindOpaneSideResize(){
  const rz=$('opaneSideRz'), side=$('opaneSide');
  if(!rz||!side) return;
  side.style.flexBasis=OS_SIDE_W+'px';
  let sx=0, sw=0, on=false;
  rz.onmousedown=e=>{ on=true; sx=e.clientX; sw=OS_SIDE_W; rz.classList.add('on'); document.body.style.cursor='col-resize'; e.preventDefault(); };
  document.addEventListener('mousemove',e=>{
    if(!on) return;
    OS_SIDE_W=Math.min(900,Math.max(280,sw-(e.clientX-sx)));
    side.style.flexBasis=OS_SIDE_W+'px';
  });
  document.addEventListener('mouseup',()=>{ if(!on) return; on=false; rz.classList.remove('on'); document.body.style.cursor=''; saveWidths(); });
  rz.ondblclick=resetWidths;                        // 美化包⑥：双击复位
}

// ── 勾选弹窗（编辑项目类别=现场评审时勾选「我负责的条款」）────────
async function openPickModal(){
  const r=await fetch('/api/onsite-score?project_id='+encodeURIComponent(CUR['id']));
  const j=await r.json().catch(()=>({}));
  if(!j['ok']){ ui.toast(j['提示']||('加载评分表缓存失败：'+(j.detail||r.status))); return; }
  PICK_DATA=j; PICK_ITEMS=[];
  const savedNos=new Set((j['勾选条款']||[]).map(p=>String(p['条款号']||'').trim()));
  const rows=[];
  const tag=it=>escH(it['类目']||'')+(it['分值']?' · '+escH(it['分值'])+'分':'');

  (j['直接对应']||[]).forEach(it=>{
    const id=PICK_ITEMS.length;
    const label=(it['目标条款号']||'')+' '+(it['目标条款名']||'');
    PICK_ITEMS.push({kind:'direct',条款号:it['目标条款号'],条款名:it['目标条款名'],目标文件:it['目标文件'],优势:it['优势'],可改进之处:it['可改进之处']});
    rows.push(`<div class="os-item" data-idx="${id}"><div class="os-head">
      <input type="checkbox" class="os-chk" data-idx="${id}" ${savedNos.has(String(it['目标条款号']||'').trim())?'checked':''}>
      <span class="os-title">${escH(label)}</span>
      <span class="os-tag">${tag(it)}</span></div></div>`);
  });

  (j['自动归']||[]).forEach(it=>{
    const id=PICK_ITEMS.length;
    const to=(it['目标']||[]).map(t=>t['条款号']).join(' / ');
    const allIn=(it['目标']||[]).every(t=>savedNos.has(String(t['条款号']||'').trim()));
    PICK_ITEMS.push({kind:'auto',目标:it['目标']||[],优势:it['优势'],可改进之处:it['可改进之处']});
    rows.push(`<div class="os-item" data-idx="${id}"><div class="os-head">
      <input type="checkbox" class="os-chk" data-idx="${id}" ${allIn?'checked':''}>
      <span class="os-title">${escH(it['评分项']||'')} ${escH(it['条款名']||'')}</span>
      <span class="os-tag">${tag(it)} · 归到 ${escH(to)}</span></div></div>`);
  });

  if((j['弹窗判断']||[]).length){
    const opts=j['条款库'].map(c=>`<option value="${escH(c['文件']||'')}" data-no="${escH(c['条款号']||'')}" data-name="${escH(c['条款名']||'')}">${escH(c['条款号']||'')} ${escH(c['条款名']||'')}</option>`).join('');
    j['弹窗判断'].forEach(it=>{
      const id=PICK_ITEMS.length;
      PICK_ITEMS.push({kind:'popup',优势:it['优势'],可改进之处:it['可改进之处']});
      rows.push(`<div class="os-item" data-idx="${id}"><div class="os-head">
        <input type="checkbox" class="os-chk" data-idx="${id}">
        <span class="os-title">${escH(it['评分项']||'')} ${escH(it['条款名']||'')}</span>
        <span class="os-tag">${tag(it)} · 横切项</span></div>
        <div class="os-pop" style="display:none">
          <select class="os-select"><option value="">— 选归属条款 —</option>${opts}</select>
        </div></div>`);
    });
  }

  $('pickForm').innerHTML=rows.join('');
  $('pickSub').textContent='适用标准 '+(j['标准']||'')+' · 从缓存的评分表勾选要核实的条款（横切项需选归属）';
  $('pickModal').style.display='flex';
  setTimeout(()=>{ const el=$('pickForm').querySelector('.os-chk'); if(el) el.focus(); },50);   // 美化包⑩
  $('pickModalClose').onclick=()=>{ $('pickModal').style.display='none'; UPDATE_PENDING=false; };
  $('pickCancel').onclick=()=>{ $('pickModal').style.display='none'; UPDATE_PENDING=false; };
  $('pickForm').querySelectorAll('.os-chk').forEach(chk=>{
    chk.onchange=()=>{
      const pop=chk.closest('.os-item').querySelector('.os-pop');
      if(pop) pop.style.display=chk.checked?'block':'none';
    };
  });
  $('pickOk').onclick=pickConfirm;
}

function pickConfirm(){
  const picks=[];
  $('pickForm').querySelectorAll('.os-item').forEach(item=>{
    const chk=item.querySelector('.os-chk');
    if(!chk || !chk.checked) return;
    const rec=PICK_ITEMS[Number(item.dataset.idx)];
    if(!rec) return;
    if(rec.kind==='direct'){
      picks.push({条款号:rec.条款号,条款名:rec.条款名,目标文件:rec.目标文件,优势:rec.优势,可改进之处:rec.可改进之处,现场核实:''});
    }else if(rec.kind==='auto'){
      (rec.目标||[]).forEach(t=>{
        picks.push({条款号:t['条款号'],条款名:t['条款名'],目标文件:t['文件'],优势:rec.优势,可改进之处:rec.可改进之处,现场核实:''});
      });
    }else{ // popup 横切项
      const sel=item.querySelector('.os-select');
      if(!sel || !sel.value) return;
      const opt=sel.selectedOptions[0];
      picks.push({条款号:opt.dataset.no,条款名:opt.dataset.name,目标文件:sel.value,优势:rec.优势,可改进之处:rec.可改进之处,现场核实:''});
    }
  });
  const merged=mergePicks(picks);
  if(!merged.length){ ui.toast('请至少勾选一条（横切项还需选归属条款）'); return; }
  ED_PICKS=merged;
  $('pickModal').style.display='none';
  const hint=$('ed-pick-hint');
  if(hint) hint.textContent=`已勾选 ${ED_PICKS.length} 条条款（点「更新」可重新勾选）`;
  if(UPDATE_PENDING){
    UPDATE_PENDING=false;
    askOnsiteWrite(ED_PICKS);
  }
}

// 同条款多评分项合并为一条（优势/可改进多行，现场核实取一条）
function mergePicks(picks){
  const map={}, order=[];
  (picks||[]).forEach(p=>{
    const no=String(p['条款号']||'').trim();
    if(!no) return;
    if(!map[no]){ map[no]={条款号:no,条款名:p['条款名'],目标文件:p['目标文件'],优势:[],可改进:[],现场核实:p['现场核实']||''}; order.push(no); }
    if(p['优势']) map[no].优势.push(p['优势']);
    if(p['可改进之处']) map[no].可改进.push(p['可改进之处']);
    if(!map[no].现场核实 && p['现场核实']) map[no].现场核实=p['现场核实'];
  });
  return order.map(no=>{ const m=map[no];
    return {条款号:m.条款号,条款名:m.条款名,目标文件:m.目标文件,优势:m.优势.join('\n'),可改进之处:m.可改进.join('\n'),现场核实:m.现场核实}; });
}

function askOnsiteWrite(picks){
  if(!picks || !picks.length){ ui.toast('请至少勾选一条要核实的条款（横切项还需选归属条款）'); return; }
  // 现场日期默认自动关联原现场报告文件名（YYYYMMDD-企业名-现场评审.md）；改日期→文件名跟随+删旧文件，库内唯一
  const onsiteSrc=arr(CUR['来源文件']).find(p=>String(p).includes('30-现场评审库'))||'';
  const dm=baseName(onsiteSrc).match(/^(\d{4})(\d{2})(\d{2})-/);
  const defDate=dm?`${dm[1]}-${dm[2]}-${dm[3]}`:(((CUR['现场日期']||'')+'').slice(0,10));
  const rows=[`<div class="rv">将生成现场评审报告：文审全文 + 现场核实信息 ${picks.length} 条（原文审报告将删除迁移）</div>`];
  rows.push(`<div class="fld"><label>现场评审结论（回台账，可留空）</label><input type="text" id="os-concl" placeholder="如：同意进入现场评审 / 拟推荐获奖…"></div>`);
  rows.push(`<div class="fld"><label>现场日期（默认关联原报告；改动后文件名跟随，现场评审库只保留唯一一份）</label><input type="date" id="onsite-date" value="${escH(defDate)}"></div>`);
  $('onsiteForm').innerHTML=rows.join('');
  $('onsiteModal').style.display='flex';
  setTimeout(()=>{ const el=$('os-concl'); if(el) el.focus(); },50);   // 美化包⑩
  $('onsiteModalClose').onclick=()=>$('onsiteModal').style.display='none';
  $('onsiteCancel').onclick=()=>$('onsiteModal').style.display='none';
  $('onsiteOk').onclick=()=>doWriteOnsite(picks);
}

async function doWriteOnsite(picks){
  const dateEl=$('onsite-date');
  const date=dateEl?dateEl.value:'';
  const concl=$('os-concl');
  const body={
    id:CUR['id'],
    企业名称:CUR['企业名称'],
    现场日期:date,
    结论:concl?concl.value:'',
    勾选条款:picks
  };
  $('onsiteOk').disabled=true; $('onsiteOk').textContent='写入中…';
  const r=await fetch('/api/write-onsite',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const res=await r.json().catch(()=>({}));
  $('onsiteOk').disabled=false; $('onsiteOk').textContent='确认写入';
  if(!r.ok){ ui.toast('写入失败：'+(res.detail||r.status)); return; }
  $('onsiteModal').style.display='none';
  DATA=await (await fetch('/api/projects')).json();
  if(CUR) CUR=DATA.find(d=>String(d['id'])===CUR['id'])||CUR;
  apply();
  editProject(CUR['id']);
  ui.toast('已生成现场评审报告：'+res['路径']+'\n原文审报告已删除迁移（现场报告含全文）'+((res['已删除文审']||[]).length?'（已删 '+res['已删除文审'].length+' 份文审 md）':'')+'；阶段仍为「现场中」，复盘后请手动改「归档」。');
}

// ── 条款查阅侧栏（现场评审里点条款名/「查看」打开，含追加心得）─────
let CUR_CLAUSE=null;
async function openClauseSide(path, title){
  CUR_CLAUSE=path;
  $('clauseSideTitle').textContent=title;
  $('clauseSide').style.display='flex';
  $('clauseSideBody').innerHTML='加载中…';
  $('clauseSideClose').onclick=()=>{ $('clauseSide').style.display='none'; };
  $('clauseNoteBtn').onclick=addClauseNote;
  const r=await fetch('/api/clause?path='+encodeURIComponent(path));
  const j=await r.json().catch(()=>({}));
  $('clauseSideBody').innerHTML=r.ok?j.html:'<p class="detail-sub">加载失败：'+(j.detail||r.status)+'</p>';
}

function askNote(){
  return new Promise(resolve=>{
    $('noteModalInput').value='';
    $('noteModal').style.display='flex';
    setTimeout(()=>$('noteModalInput').focus(),50);   // 美化包⑩：自动聚焦首输入框
    const done=v=>{ $('noteModal').style.display='none'; resolve(v); };
    $('noteModalOk').onclick=()=>done($('noteModalInput').value);
    $('noteModalCancel').onclick=()=>done(null);
    $('noteModalClose').onclick=()=>done(null);
  });
}

async function addClauseNote(){
  if(!CUR_CLAUSE) return;
  const note=await askNote();
  if(!note||!note.trim()) return;
  const r=await fetch('/api/clause-note',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({path:CUR_CLAUSE,note:note})});
  const j=await r.json().catch(()=>({}));
  if(r.ok){ openClauseSide(CUR_CLAUSE, $('clauseSideTitle').textContent); }
  else { ui.toast('追加失败：'+(j.detail||r.status)); }
}

async function deleteProject(pid){
  const d=DATA.find(x=>String(x['id'])===pid);
  const nm=(d&&d['企业名称'])?d['企业名称']:pid;
  if(!(await ui.confirm(`确认删除项目「${nm}」（${pid}）？\n\n· 仅删除台账记录，不删除关联的报告文件\n· 会同步清理其他项目「历史项目」里对它的引用\n· 删除前已自动备份，误删可从 backup 找回`))) return;
  const r=await fetch('/api/projects/'+encodeURIComponent(pid),{method:'DELETE'});
  const j=await r.json().catch(()=>({}));
  if(r.ok){ await boot(); closeDetail(); }
  else ui.toast('删除失败：'+(j.detail||r.status));
}

async function editProject(pid){
  const d=DATA.find(x=>String(x['id'])===pid);
  if(!d) return;
  CUR=d; ED_PICKS=[]; UPDATE_PENDING=false;
  document.querySelectorAll('#tb tr').forEach(x=>x.classList.remove('sel'));
  const tr=document.querySelector(`#tb tr[data-id="${pid}"]`);
  if(tr) tr.classList.add('sel');
  $('detail').classList.add('open');
  const curHist=arr(d['历史项目']);
  const peers=DATA.filter(x=>String(x['id'])!==pid && sameCompany(x['企业名称'],d['企业名称']));
  const cat=arr(d['类别'])[0]||'';
  const cats=[...new Set((DICTS['类别']||[]).map(r=>r[0]))];
  $('detail').innerHTML=`
    <h3 class="detail-h"><span>编辑项目</span><span class="x" id="ed-close">×</span></h3>
    <p class="detail-sub">${d['id']} · 改企业名称会同步重命名关联文件</p>
    <div class="fld"><label>企业名称 *</label><input id="ed-name" value="${escH(d['企业名称']||'')}"></div>
    <div class="fld"><label>类别 *</label><select id="ed-cat">
      ${cats.map(c=>`<option ${c===cat?'selected':''}>${c}</option>`).join('')}</select>
      <div class="detail-sub" id="ed-pick-hint" style="margin-top:4px">${cat==='现场评审'?'现场评审：点「更新」可勾选/调整条款并重建现场报告':''}</div></div>
    <div class="fld"><label>阶段</label><select id="ed-stage">
      ${(ENUMS['阶段']||[]).map(c=>`<option ${c===d['阶段']?'selected':''}>${c}</option>`).join('')}</select></div>
    <div class="fld"><label>结论</label><select id="ed-conc">
      <option value="">（待定）</option>${(ENUMS['结论']||[]).map(c=>`<option ${c===d['结论']?'selected':''}>${c}</option>`).join('')}</select></div>
    <div class="fld"><label>得分</label><input id="ed-score" type="number" value="${d['得分']??''}"></div>
    <div class="fld"><label>评审角色</label><select id="ed-role">
      <option value="">（留空）</option>${(ENUMS['评审角色']||[]).map(c=>`<option ${c===d['评审角色']?'selected':''}>${c}</option>`).join('')}</select></div>
    <div class="fld"><label>适用标准</label><select id="ed-std">
      <option value="">（未指定）</option>${(ENUMS['适用标准']||[]).map(c=>`<option ${c===d['适用标准']?'selected':''}>${c}</option>`).join('')}</select></div>
    <div class="fld"><label>报告日期（文件评审项目，用于文件名）</label><input id="ed-rdate" type="date" value="${d['报告日期']||''}"></div>
    <div class="fld"><label>现场日期（现场评审项目，用于文件名）</label><input id="ed-fdate" type="date" value="${d['现场日期']||''}"></div>
    <div class="fld"><label>历史项目（勾选同企业历史评价）</label>
      <div class="chk-list" id="ed-hist">${peers.length?peers.map(h=>`
        <label><input type="checkbox" value="${h['id']}" ${curHist.includes(String(h['id']))?'checked':''}>
          <span>${escH(h['企业名称']||'')}<br>
          <span class="sub">${h['年份']||'—'} · ${jv(h['类别'])} · ${h['奖项/项目']||'—'} · ${h['得分']??'—'}分 · ${h['结论']||'—'}</span></span></label>`).join('')
        :'<span style="color:var(--tx2);font-size:12px">无同企业其他项目</span>'}</div></div>
    <button class="btn" id="ed-save">保存</button>
    <button class="btn" id="ed-update" style="margin-left:8px;display:none">更新（重建现场报告）</button>
    <button class="btn ghost" id="ed-cancel" style="margin-left:8px">取消</button>`;
  setTimeout(()=>{ const el=$('ed-name'); if(el) el.focus(); },50);   // 美化包⑩
  $('ed-close').onclick=closeDetail;
  $('ed-cancel').onclick=()=>openDetail(pid);
  const syncUpdateBtn=()=>{
    // 现场环节关门（2026-10-28 用户定）：终版已写后「更新（重建现场报告）」隐藏——
    // 重建会截掉终版的提取日志/折叠归档块（后端 write-onsite 400 兜底）；
    // 修正统一走「重新上传终版 Word → 提取并写入终版」
    const isOnsiteCat=$('ed-cat').value==='现场评审';
    const off=isOnsiteCat&&!!d['终版已写'];
    $('ed-update').style.display=isOnsiteCat&&!off?'inline-block':'none';
    $('ed-pick-hint').textContent=off
      ?'终版已写入（'+d['终版已写']+'），现场评审环节已关闭——修正请重新上传终版 Word 走「提取并写入终版」'
      :(isOnsiteCat?'现场评审：点「更新」可勾选/调整条款并重建现场报告':'');
  };
  syncUpdateBtn();
  $('ed-cat').onchange=()=>{
    syncUpdateBtn();
    if($('ed-cat').value==='现场评审' && !ED_PICKS.length && !d['终版已写']){
      UPDATE_PENDING=true;
      openPickModal();
    }
  };
  const saveFields=async()=>{
    const fields={
      '企业名称':$('ed-name').value.trim(),
      '类别':[$('ed-cat').value],
      '阶段':$('ed-stage').value,
      '结论':$('ed-conc').value,
      '得分':$('ed-score').value,
      '评审角色':$('ed-role').value,
      '适用标准':$('ed-std').value,
      '报告日期':$('ed-rdate').value,
      '现场日期':$('ed-fdate').value,
      '历史项目':[...document.querySelectorAll('#ed-hist input:checked')].map(i=>i.value)
    };
    if(!fields['企业名称']){ ui.toast('企业名称不能为空'); return false; }
    const r=await fetch('/api/projects/'+encodeURIComponent(pid),{method:'PUT',
      headers:{'Content-Type':'application/json'},body:JSON.stringify({fields})});
    const j=await r.json().catch(()=>({}));
    if(!r.ok){ ui.toast('保存失败：'+(j.detail||r.status)); return null; }
    return j;
  };
  $('ed-save').onclick=async()=>{
    const j=await saveFields();
    if(!j) return;
    if(j['更名文件'] && j['更名文件'].length){ ui.toast('企业名称已更新，同步重命名了 '+j['更名文件'].length+' 份关联文件'); }
    await boot(); closeDetail();
  };
  $('ed-update').onclick=async()=>{
    if(!await saveFields()) return;
    closeDetail();
    DATA=await (await fetch('/api/projects')).json();
    CUR=DATA.find(x=>String(x['id'])===pid)||CUR;
    if(!ED_PICKS.length){ UPDATE_PENDING=true; openPickModal(); return; }
    askOnsiteWrite(ED_PICKS);
  };
}

function newForm(){
  document.querySelectorAll('#tb tr').forEach(x=>x.classList.remove('sel'));
  $('detail').classList.add('open');
  const city=Object.keys(TC())[0]||'';       // 默认落在字典第一项（上海市）
  const cats=[...new Set((DICTS['类别']||[]).map(r=>r[0]))];
  const aws=ENUMS['奖项/项目']||[];
  $('detail').innerHTML=`
    <h3 class="detail-h"><span>新建项目</span><span class="x" id="n-close">×</span></h3>
    <p class="detail-sub">id 自动生成（年份-SH-类别码-序号）· 输企业名自动检索历史，勾选要关联的历史评价</p>
    <div class="fld"><label>企业名称 *</label><input id="n-name" placeholder="填全称（自动检索该企业历史）"></div>
    <div id="n-hist"></div>
    <div class="fld"><label>年份 *</label><input id="n-year" type="number" value="${new Date().getFullYear()}">
      <div class="detail-sub" style="margin-top:4px">填<b>评审年份</b>（决定编号前缀，如 2024-SH-文审-001）；随下方报告/现场日期<b>自动带出</b>，可手改——编号生成后不变</div></div>
    <div class="fld"><label>区域</label>${regSel('n',city,'')}</div>
    <div class="fld"><label>行业（GB/T 4754）</label>${indSel('n','','','（先选门类，或直接在右边挑大类）')}</div>
    <div class="fld"><label>类别 *</label><div class="chk" id="n-cat">
      ${cats.map(c=>`<span class="${c==='文件评审'?'on':''}">${c}</span>`).join('')}</div></div>
    <div class="fld"><label>奖项 / 项目</label>
      <input id="n-award" list="n-awards" placeholder="如 区政府质量奖">
      <datalist id="n-awards">${aws.map(a=>`<option value="${a}">`).join('')}</datalist></div>
    <div class="fld"><label>适用标准</label><select id="n-std">
      <option value="">（未指定）</option>${(ENUMS['适用标准']||[]).map(c=>`<option>${c}</option>`).join('')}</select></div>
    <div class="fld"><label>阶段</label><select id="n-stage">
      ${(ENUMS['阶段']||[]).map(c=>`<option ${c==='文审中'?'selected':''}>${c}</option>`).join('')}</select></div>
    <div class="fld"><label>结论</label><select id="n-conc">
      <option value="">（待定）</option>${(ENUMS['结论']||[]).map(c=>`<option>${c}</option>`).join('')}</select></div>
    <div class="fld"><label>得分</label><input id="n-score" type="number" placeholder="只填数字，不要带「分」"></div>
    <div class="fld"><label>评审角色</label><select id="n-role">
      <option value="">（留空）</option>${(ENUMS['评审角色']||[]).map(c=>`<option>${c}</option>`).join('')}</select></div>
    <div class="fld"><label>报告日期（文件评审项目，用于文件名）</label><input id="n-rdate" type="date"></div>
    <div class="fld"><label>现场日期（现场评审项目，用于文件名）</label><input id="n-fdate" type="date"></div>
    <div class="fld"><label>备注</label><input id="n-note" placeholder="写进卡片正文"></div>
    <button class="btn" id="n-create">创建卡片</button>
    <button class="btn ghost" id="n-cancel" style="margin-left:8px">取消</button>`;
  $('n-cat').querySelectorAll('span').forEach(s=>s.onclick=()=>{
    $('n-cat').querySelectorAll('span').forEach(x=>x.classList.remove('on'));
    s.classList.add('on');
  });
  bindSel('n','（市级 / 留空）','（留空）');
  // 2026-11-02 用户反馈修复：只填报告/现场日期（如 2024-xx）不手改年份 → 卡片归错年（编号 2026-…）。
  // 日期变化即把年份同步成日期所在年；年份仍可手改（下一次改日期会再带出）
  const syncYear=()=>{
    const d=($('n-rdate').value||$('n-fdate').value||'').slice(0,4);
    if(/^\d{4}$/.test(d)) $('n-year').value=d;
  };
  ['n-rdate','n-fdate'].forEach(id=>{ $(id).onchange=syncYear; $(id).oninput=syncYear; });
  $('n-create').onclick=create;
  $('n-cancel').onclick=closeDetail;
  $('n-close').onclick=closeDetail;
  let histTimer=null;
  $('n-name').oninput=()=>{
    clearTimeout(histTimer);
    const q=$('n-name').value.trim();
    histTimer=setTimeout(async()=>{
      const hb=$('n-hist');
      if(q.length<2){ hb.innerHTML=''; return; }
      const hist=await (await fetch('/api/projects/search?q='+encodeURIComponent(q))).json();
      if(!hist.length){
        hb.innerHTML='<div class="tip" style="border-color:#2c5c47;color:#7ee2b8;margin-top:6px">未检索到该企业的历史评价</div>';
        return;
      }
      hb.innerHTML='<div class="sec" style="margin-top:4px">历史评价（勾选要关联的；不影响上方企业名称输入）</div><div class="chk-list">'+
        hist.map(h=>`<label><input type="checkbox" value="${h['id']}" data-name="${escH(h['企业名称']||'')}">
          <span>${escH(h['企业名称']||'')}<br>
          <span class="sub">${h['年份']||'—'} · ${jv(h['类别'])} · ${h['奖项/项目']||'—'} · ${h['得分']??'—'}分 · ${h['结论']||'—'}</span></span></label>`).join('')+'</div>';
      const fillCompanyFromChecked=()=>{
        const names=[...document.querySelectorAll('#n-hist input:checked')].map(cb=>cb.dataset.name).filter(Boolean);
        if(!names.length) return;
        const cur=$('n-name').value.trim();
        if(!cur && names.length){ $('n-name').value=names.slice().sort((a,b)=>b.length-a.length)[0]; }   // 仅空时补全,绝不覆盖手工输入
      };
      hb.querySelectorAll('input[type=checkbox]').forEach(cb=>{ cb.onchange=fillCompanyFromChecked; });
    },300);
  };
  $('n-name').focus();
}

async function create(){
  const name=($('n-name').value||'').trim();
  if(!name){ ui.toast('企业名称不能为空'); return; }
  const catEl=$('n-cat').querySelector('span.on');
  if(!catEl){ ui.toast('请选择类别'); return; }
  const cats=[catEl.textContent];
  const [rcity,rdist]=pairVal('n');
  const [indMen,indDl]=indVal('n');
  const histChecked=[...document.querySelectorAll('#n-hist input:checked')].map(i=>i.value);
  const fields={
    '企业名称':name,
    '年份':Number($('n-year').value)||null,
    '区域市级':rcity,
    '区域区县':rdist,
    '行业门类':indMen,
    '行业大类':indDl,
    '类别':cats,
    '奖项/项目':$('n-award').value,
    '适用标准':$('n-std').value,
    '阶段':$('n-stage').value,
    '结论':$('n-conc').value,
    '得分':$('n-score').value,
    '评审角色':$('n-role').value,
    '报告日期':$('n-rdate').value,
    '现场日期':$('n-fdate').value,
    '备注':$('n-note').value,
    '历史项目':histChecked
  };
  const r=await fetch('/api/projects',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({fields})});
  const j=await r.json().catch(()=>({}));
  if(!r.ok){ ui.toast('创建失败：'+(j.detail||r.status)); return; }
  const pid=j['id'];
  await boot();
  closeDetail();
  ui.toast('已创建：'+pid+'  '+j['企业']);
}

function ax(){                       // 坐标轴配色随深/浅主题（2026-11-02 美化包①）
  return isLight()
    ?{axisLabel:{color:'#5b6673'},axisLine:{lineStyle:{color:'#c3ccd7'}},splitLine:{lineStyle:{color:'#e2e7ee'}}}
    :{axisLabel:{color:'#9aa3b2'},axisLine:{lineStyle:{color:'#333a45'}},splitLine:{lineStyle:{color:'#262b34'}}};
}
function tone(){                     // 图表文字/底色/主色随主题
  return isLight()
    ?{text:'#3a424d',panel:'#ffffff',panel2:'#eef1f6',border:'#d4dbe4',label:'#5b6673',ac:'#1c66c4'}
    :{text:'#c7cdd8',panel:'#1e2229',panel2:'#242932',border:'#333a45',label:'#9aa3b2',ac:'#4a9eff'};
}
const PAL=['#4a9eff','#38c5a0','#ef9f27','#a78bfa','#e24b4a','#5dcaa5','#f0997b','#85b7eb'];
function chart(id,opt){
  const el=$(id); if(!el) return;
  const t=tone();
  const c=echarts.getInstanceByDom(el)||echarts.init(el,null,{renderer:'canvas'});
  c.setOption(Object.assign({backgroundColor:'transparent',
    textStyle:{color:t.text},
    tooltip:{trigger:'axis',backgroundColor:t.panel2,borderColor:t.border,
      textStyle:{color:isLight()?'#242a31':'#e6e9ef'}}},opt),true);
  c.resize();
}
function countBy(rows,fn){
  const m={};
  rows.forEach(d=>{const k=fn(d)||'待补';m[k]=(m[k]||0)+1});
  return Object.entries(m).sort((a,b)=>b[1]-a[1]);
}
function bar(id,data,name,horiz){
  const axp=ax(), t=tone();
  chart(id,{grid:horiz?{left:90,right:30,top:24,bottom:24}:{left:40,right:20,top:24,bottom:40},
    xAxis:horiz?Object.assign({type:'value'},axp):Object.assign({type:'category',data:data.map(d=>d[0])},axp),
    yAxis:horiz?Object.assign({type:'category',data:data.map(d=>d[0])},axp):Object.assign({type:'value'},axp),
    series:[{type:'bar',data:data.map(d=>d[1]),name:name,
      itemStyle:{color:t.ac,borderRadius:[3,3,0,0]},barMaxWidth:26}]});
}
function pie(id,data){
  const t=tone();
  chart(id,{tooltip:{trigger:'item',backgroundColor:t.panel2,borderColor:t.border,
      textStyle:{color:isLight()?'#242a31':'#e6e9ef'}},
    legend:{bottom:0,textStyle:{color:t.label},itemWidth:10,itemHeight:10},
    series:[{type:'pie',radius:['38%','62%'],center:['50%','45%'],data:data.map(d=>({name:d[0],value:d[1]})),
      itemStyle:{borderColor:t.panel,borderWidth:2},
      label:{color:t.label,formatter:'{b} {c}'}}],
    color:PAL});
}
function renderCharts(rows){
  bar('c-year',countBy(rows,d=>d['年份']),'项目数');
  pie('c-cat',countBy(rows,d=>arr(d['类别'])[0]));
  // 区域口径跟着筛选走：选了市就看各区县分布，没选就看各市
  bar('c-region',countBy(rows,d=>{
    const rg=arr(d['区域']);
    return FILT.city?(rg[1]||'市级 / 未分区县'):(rg[0]||'待补');
  }),FILT.city?'各区县项目数':'各市项目数',true);
  pie('c-industry',countBy(rows,d=>FILT.men?(arr(d['行业'])[1]||arr(d['行业'])[0]):arr(d['行业'])[0]));
  pie('c-award',countBy(rows,d=>d['奖项/项目']));
  const bins={'50分以下':0,'50-59':0,'60-69':0,'70-79':0,'80-89':0,'90+':0,'无分':0};
  rows.forEach(d=>{
    const s=d['得分'];
    if(s==null){bins['无分']++;return}
    if(s<50)bins['50分以下']++;else if(s<60)bins['50-59']++;
    else if(s<70)bins['60-69']++;else if(s<80)bins['70-79']++;
    else if(s<90)bins['80-89']++;else bins['90+']++;
  });
  bar('c-score',Object.entries(bins).filter(x=>x[1]),'项目数');
  const years=[...new Set(rows.map(d=>d['年份']))].filter(Boolean).sort();
  const cats=[...new Set(rows.flatMap(d=>arr(d['类别'])))].sort();
  const axp=ax(), t=tone();
  chart('c-cross',{grid:{left:50,right:20,top:40,bottom:40},
    legend:{top:0,textStyle:{color:t.label}},
    xAxis:Object.assign({type:'category',data:years},axp),
    yAxis:Object.assign({type:'value'},axp),
    series:cats.map((c,i)=>({name:c,type:'bar',stack:'t',barMaxWidth:40,
      itemStyle:{color:PAL[i%PAL.length]},
      data:years.map(y=>rows.filter(d=>d['年份']===y&&arr(d['类别']).includes(c)).length)})),
    color:PAL});
}

function switchTab(t){
  document.querySelectorAll('.tabs button').forEach(x=>x.classList.remove('active'));
  document.querySelector(`.tabs button[data-tab="${t}"]`).classList.add('active');
  $('view-list').hidden=t!=='list';
  $('view-charts').hidden=t!=='charts';
  $('view-policy').hidden=t!=='policy';
  $('view-desens').hidden=t!=='desens';
  if(t==='charts') setTimeout(()=>renderCharts(filtered()),30);
  if(t==='desens') loadDesens();
  if(t==='policy'){ packForm(); }
}
document.querySelectorAll('.tabs button').forEach(b=>{
  b.onclick=()=>switchTab(b.dataset.tab);
});
function filtered(){
  return VIEW;   // B4：全量「筛选+排序」结果；分页后表格只是其中一页，图表与 resize 仍用全量
}
['f-year','f-dist','f-dl','f-cat','f-award','f-todo'].forEach(id=>$(id).onchange=apply);
$('f-city').onchange=()=>{buildRegionFilter();apply();};    // 换市 → 区县跟着换
$('f-men').onchange=()=>{buildIndustryFilter();apply();};   // 换门类 → 大类跟着换
let kwTimer=0;                                   // B5：搜索防抖计时器（200ms）
$('f-kw').oninput=()=>{ clearTimeout(kwTimer); kwTimer=setTimeout(apply,200); };
$('f-reset').onclick=()=>{
  ['f-year','f-city','f-dist','f-men','f-dl','f-cat','f-award'].forEach(id=>$(id).value='');
  $('f-kw').value='';$('f-todo').checked=false;
  SORT.col='';SORT.dir=1;PAGE=1;                 // 同时重置排序与分页状态
  buildRegionFilter();buildIndustryFilter();apply();   // 重置立即生效，不走防抖
};
window.onresize=()=>{if(!$('view-charts').hidden) renderCharts(filtered())};
// 报告弹窗 HTML 在本脚本之后，等 DOM 解析完再绑拖拽手柄，避免 null 报错断掉 boot()
if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',()=>{bindOboxResize();bindReportOverlay();});
else {bindOboxResize();bindReportOverlay();}
boot();
