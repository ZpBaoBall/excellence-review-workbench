# -*- coding: utf-8 -*-
"""
政策库模块
- 政策卡片读写（md + frontmatter，落在 vault 的 30-政策库）
- 时效自动计算与体检（失效日期 / 生效日期 / 复核超期）
- 检索任务包生成（写到 exchange/outbox，交给智能体去联网检索）
- inbox 回收（智能体产出放回 exchange/inbox，工作台收编进政策库）
"""
import re
import shutil
import yaml
import frontmatter
import desens  # 出网强制过闸：任务包是要交给外部智能体的，必须脱敏并留痕
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Tuple

BASE = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((BASE / "config.yaml").read_text(encoding="utf-8"))
LIB = CFG["库"]["社会兼职"]
LIB_PATH = Path(LIB["路径"])
# 政策库已移除：独立政策卡不再使用（P4 改为「检索 → 概述+链接 → 内联进企业文件」）。
# 这里指向程序侧空目录，让 load_policies 自然返回空；检索任务包（make_search_pack）不受影响。
POL_DIR = BASE / "data" / "policies"
OUTBOX = Path(CFG["程序"]["交换区"]["outbox"])
INBOX = Path(CFG["程序"]["交换区"]["inbox"])
BACKUP = Path(CFG["程序"]["备份目录"])

# 字段顺序（写回时保持不变）
FIELDS = [
    "id", "标题", "文号", "层级", "发布机构", "区域", "适用行业", "政策类型",
    "发布日期", "生效日期", "失效日期", "人工判定", "时效状态", "来源URL", "来源类型",
    "关键词", "关联项目", "校验日期", "状态",
]
REQUIRED = ["标题", "来源URL"]
# 时效状态 = 机器按日期推算；人工判定 = 人核过的结论，优先级更高
HAND_STATUS = ("已失效", "已修订", "待确认", "现行有效")
AUTO_ONLY = ("即将失效", "未生效")            # 这两个只能机器算，不接受手填
RECHECK_DAYS = 180                            # 超过这个天数未复核就提示


# ── 基础工具 ──────────────────────────────────────────────
def to_date(v) -> date | None:
    """yaml 会把日期解析成 date/datetime，也可能是字符串；统一成 date"""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip().replace("/", "-").replace(".", "-")
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.match(r"(\d{4})-(\d{1,2})$", s)
    if m:
        return date(int(m.group(1)), int(m.group(2)), 1)
    m = re.match(r"^(\d{4})$", s)
    if m:
        return date(int(m.group(1)), 1, 1)
    return None


def dstr(v):
    d = to_date(v)
    return d.isoformat() if d else ""


def arr(v):
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v if x not in (None, "")]
    return [str(v)] if str(v).strip() else []


def ensure_dirs():
    POL_DIR.mkdir(parents=True, exist_ok=True)
    OUTBOX.mkdir(parents=True, exist_ok=True)
    INBOX.mkdir(parents=True, exist_ok=True)


def dump_md(post) -> str:
    text = yaml.dump(post.metadata, allow_unicode=True, sort_keys=False,
                     default_flow_style=False, width=10000)
    return f"---\n{text.strip()}\n---\n\n{post.content}"


# ── 时效计算 ──────────────────────────────────────────────
def compute_status(meta: dict) -> Tuple[str, str]:
    """返回 (时效状态, 提示)。人工判定优先，其余按日期自动推算"""
    hand = str(meta.get("人工判定") or "").strip()
    today = date.today()
    exp = to_date(meta.get("失效日期"))
    eff = to_date(meta.get("生效日期"))

    # 人工核实过的结论优先（机器不再覆盖）
    if hand in HAND_STATUS:
        extra = ""
        if exp and exp < today and hand != "已失效":
            extra = f"（注意：失效日期 {exp.isoformat()} 已过，与人工判定不一致）"
        if exp and exp >= today and hand == "已失效":
            extra = f"（注意：失效日期 {exp.isoformat()} 尚未到，与人工判定不一致）"
        return hand, extra or "（人工判定，未自动推算）"

    if exp and exp < today:
        return "已失效", f"失效日期 {exp.isoformat()} 已过 {(today - exp).days} 天"
    if exp and (exp - today).days <= 90:
        return "即将失效", f"距失效还有 {(exp - today).days} 天（{exp.isoformat()}）"
    if eff and eff > today:
        return "未生效", f"生效日期 {eff.isoformat()}"
    if exp:
        return "现行有效", f"有效期至 {exp.isoformat()}"
    if eff:
        return "现行有效", f"自 {eff.isoformat()} 起施行，未填失效日期"
    return "待确认", "缺生效/失效日期，无法判断时效"


def check_one(meta: dict) -> List[str]:
    """单条政策的体检问题清单"""
    issues = []
    if not str(meta.get("文号") or "").strip():
        issues.append("缺文号")
    if not str(meta.get("来源URL") or "").strip():
        issues.append("缺来源URL（无法回溯出处）")
    if str(meta.get("来源类型") or "") not in ("政府网站", "政府公报", "标准原文"):
        issues.append("来源非一手（可信度需人工判断）")
    st, msg = compute_status(meta)
    if st in ("已失效", "即将失效", "未生效", "待确认"):
        issues.append(f"{st}：{msg}" if msg else st)
        # 「待确认」的原因就是缺日期，不再重复报「缺生效日期」
        if st == "待确认":
            return issues
    chk = to_date(meta.get("校验日期"))
    if not chk:
        issues.append("从未复核")
    elif (date.today() - chk).days > RECHECK_DAYS:
        issues.append(f"已 {(date.today() - chk).days} 天未复核")
    if not str(meta.get("生效日期") or "").strip():
        issues.append("缺生效日期")
    return issues


# ── 读写 ──────────────────────────────────────────────────
def load_policies() -> List[dict]:
    ensure_dirs()
    out = []
    for f in sorted(POL_DIR.glob("*.md")):
        try:
            post = frontmatter.load(f)
        except Exception:
            continue
        d = dict(post.metadata)
        st, msg = compute_status(d)
        d["_时效"] = st
        d["_提示"] = msg
        d["_问题"] = check_one(d)
        d["_文件"] = f.name
        d["_正文"] = post.content
        out.append(d)
    return out


def find_file(pid: str):
    for f in POL_DIR.glob("*.md"):
        try:
            post = frontmatter.load(f)
        except Exception:
            continue
        if str(post.metadata.get("id", "")) == str(pid):
            return f, post
    return None, None


def next_id(year=None) -> str:
    """生成政策编号：POL-<年>-<三位序号>"""
    year = year or date.today().year
    n = 1
    for f in POL_DIR.glob("*.md"):
        m = re.match(rf"POL-{year}-(\d+)", f.name)
        if m:
            n = max(n, int(m.group(1)) + 1)
    return f"POL-{year}-{n:03d}"


def safe_name(s: str, limit: int = 40) -> str:
    s = re.sub(r'[\\/:*?"<>|\[\]#]', "", str(s or "")).strip()
    return (s[:limit] or "未命名").strip()


def create_policy(fields: Dict[str, Any]) -> dict:
    ensure_dirs()
    title = str(fields.get("标题") or "").strip()
    if not title:
        raise ValueError("标题不能为空")
    pid = str(fields.get("id") or "").strip()
    if not pid:
        y = to_date(fields.get("发布日期")) or date.today()
        pid = next_id(y.year)
    meta: Dict[str, Any] = {"type": "政策", "id": pid, "标题": title}
    for k in FIELDS:
        if k in ("id", "标题", "type"):
            continue
        if k in fields and fields[k] not in (None, "", []):
            meta[k] = fields[k]
    meta.setdefault("状态", "active")
    meta.setdefault("校验日期", date.today().isoformat())
    # 人工判定：只接受人能下的结论；「即将失效 / 未生效」由机器算，不落库
    hand = str(meta.get("人工判定") or "").strip()
    if hand in AUTO_ONLY:
        meta.pop("人工判定", None)
        hand = ""
    # 时效状态 = 机器推算结果，纯展示用，不参与判定
    st, _ = compute_status(meta)
    meta["时效状态"] = st

    fn = f"{pid} {safe_name(title)}.md"
    target = POL_DIR / fn
    i = 2
    while target.exists():
        target = POL_DIR / f"{pid} {safe_name(title)}({i}).md"
        i += 1
    body = str(fields.get("正文") or "## 摘要要点\n\n- \n\n## 与评审的关联\n\n- \n\n## 坑与注意\n\n- \n")
    target.write_text(dump_md(frontmatter.Post(body, **meta)), encoding="utf-8")
    return {"id": pid, "文件": target.name, "标题": title, "时效": st}


def update_policy(pid: str, fields: Dict[str, Any]) -> dict:
    f, post = find_file(pid)
    if not f:
        raise FileNotFoundError(f"未找到政策 {pid}")
    if CFG.get("安全", {}).get("写入前备份", True):
        BACKUP.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, BACKUP / f"{datetime.now():%Y%m%d-%H%M%S}-{f.name}")
    for k, v in fields.items():
        if k == "正文":
            post.content = v
        elif k in ("时效状态",) or (k == "人工判定" and str(v) in AUTO_ONLY):
            continue
        else:
            post.metadata[k] = v
    st, _ = compute_status(post.metadata)
    post.metadata["时效状态"] = st
    f.write_text(dump_md(post), encoding="utf-8")
    return {"ok": True, "文件": f.name, "时效": st}


def delete_policy(pid: str) -> dict:
    f, _ = find_file(pid)
    if not f:
        raise FileNotFoundError(f"未找到政策 {pid}")
    Bak = BACKUP / "deleted-policies"
    Bak.mkdir(parents=True, exist_ok=True)
    shutil.move(str(f), str(Bak / f"{datetime.now():%Y%m%d-%H%M%S}-{f.name}"))
    return {"ok": True, "已移到": str(Bak / f.name)}


def health_report() -> dict:
    ps = load_policies()
    buckets = {"已失效": [], "即将失效": [], "未生效": [], "待确认": [], "现行有效": []}
    for p in ps:
        buckets.setdefault(p["_时效"], []).append(p)
    need = [p for p in ps if p["_问题"]]
    return {
        "总数": len(ps),
        "按时效": {k: len(v) for k, v in buckets.items()},
        "需处理": [
            {"id": p.get("id"), "标题": p.get("标题"), "时效": p["_时效"], "问题": p["_问题"]}
            for p in need
        ],
        "检查日期": date.today().isoformat(),
    }


# ── 检索任务包 ────────────────────────────────────────────
def industry_keywords(industry: List[str]) -> List[str]:
    """行业 → 检索关键词（脱敏：只带行业口径，不带企业名）"""
    kw = []
    for x in industry:
        x = str(x).strip()
        if not x:
            continue
        m = re.match(r"^([A-Z])\d{2}\s*(.*)$", x)
        if m:
            if m.group(2):
                kw.append(m.group(2))
        else:
            kw.append(x)
    return kw or ["（未指定行业）"]


def make_search_pack(region: List[str] = None, industry: List[str] = None,
                     note: str = "", pid: str = "", intent: str = "") -> Path:
    """生成政策检索任务包，写到 exchange/outbox。

    政策是公开信息、不存独立卡：检索结果由智能体「内联回填」进企业报告的
    「三、政策与指南建议」章节，不再回收入库。检索意图（委托方粘贴的对报告的
    理解）允许保留企业名（用于查企业是否在公开公示中，委托方已确认不涉密）。
    """
    ensure_dirs()
    region = arr(region) or ["上海市"]
    industry = arr(industry)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    ind_kw = industry_keywords(industry)
    region_kw = [r for r in region if r]
    sites = CFG.get("检索", {}).get("政府站点白名单", [])

    lines = [
        f"# 政策检索任务包 · {stamp}",
        "",
        "> 本文件由「评审工作台」生成，请智能体（WorkBuddy / Claude / 其他）读取后执行：",
        "> ① 按「检索意图」联网查公开政策；② 把结果内联写回目标企业报告的「三、政策与指南建议」章节。",
        "",
        "## 一、检索意图（委托方粘贴的对报告的理解，据此提炼检索式）",
        "",
    ]
    if intent:
        lines.append(intent)
    else:
        lines.append("（未填写，仅按下方区域 + 行业 + 建议检索式检索）")
    lines += [
        "",
        "## 二、检索范围",
        "",
        f"- 区域：{' · '.join(region_kw)}",
        f"- 行业：{' · '.join(industry) or '（未指定）'}",
    ]
    if pid:
        lines.append(f"- 关联评审项目：{pid}")
    if note:
        lines.append(f"- 补充要求：{note}")
    lines += [
        "",
        "## 三、建议检索式（只含行业与区域；企业名仅用于查公开公示，不写入检索式）",
        "",
    ]
    for r in region_kw:
        for k in ind_kw:
            lines.append(f"- `{r} {k} 政策 支持 措施`")
    for k in ind_kw:
        lines.append(f"- `{k} 高质量发展 专项 扶持办法`")
        lines.append(f"- `{k} 质量强区 卓越绩效 政府质量奖 奖励`")
    lines += [
        "",
        "## 四、采信来源（白名单优先）",
        "",
    ] + [f"- `{s}`" for s in sites] + [
        "",
        "二手来源（新闻、公众号、行业媒体）也可以收，但必须在结果里标注来源类型，",
        "并在「坑与注意」里写明未找到一手出处的风险。",
        "",
        "## 五、回填方式（内联进报告，不单独存政策卡）",
        "",
        "检索完成后，把每条政策以「概述 + 链接」内联写回目标企业报告的",
        "`## 三、政策与指南建议` 章节，追加为一条表格行：",
        "",
        "| 政策/规划 | 契合点 | 加分标签 / 建议 |",
        "|---|---|---|",
        "| 《政策全称》（文号） | 与企业的契合点（一句话） | 建议 + [来源](一手链接) |",
        "",
        "规则：",
        "- 政策本身**不单独存卡**（政策有时效性，用完不留冗余文件）。",
        "- 文号找不到就留空，**禁止编造文号和链接**；判断不出写「待确认」。",
        "- 若报告没有该章节，在报告末尾新建该章节。",
        "",
        "## 六、落点",
        "",
        f"- 本任务包在：`{OUTBOX}`",
        "- 目标报告 = 关联评审项目对应的 `10-政府质量奖/20-资料评审库/*.md`（按企业名定位）。",
        "",
    ]
    # ── 出网强制过闸 ──
    # 政策检索查的是公开信息，委托方已确认「企业名出网查公开公示」不涉密，
    # 故 keep_companies=True 跳过企业名代名；人名/地址/电话/金额等仍脱敏并留痕。
    content = "\n".join(lines)
    task_name = f"政策检索 {'/'.join(region_kw)} · {'/'.join(ind_kw)}（指令类·豁免字数·保留企业名）"
    try:
        r = desens.mask(content, scene="政策检索", vendor="智能体（任务包）",
                        task=task_name, region=region_kw[-1] if region_kw else "",
                        check_len=False, keep_companies=True)
        content = r.text
    except desens.DesensError as e:
        raise RuntimeError(f"任务包未通过脱敏检查，已拒绝生成：{e}")

    path = OUTBOX / f"政策检索任务包-{stamp}.md"
    path.write_text(content, encoding="utf-8")
    return path


def collect_inbox() -> dict:
    """把 exchange/inbox 里 type: 政策 的 md 收编进政策库"""
    ensure_dirs()
    got, skip = [], []
    for f in sorted(INBOX.glob("*.md")):
        try:
            post = frontmatter.load(f)
        except Exception:
            skip.append(f.name)
            continue
        meta = dict(post.metadata)
        if str(meta.get("type", "")).strip() != "政策":
            skip.append(f.name)
            continue
        title = str(meta.get("标题") or f.stem).strip()
        if not meta.get("id"):
            y = to_date(meta.get("发布日期")) or date.today()
            meta["id"] = next_id(y.year)
        meta.setdefault("状态", "active")
        # 兼容：智能体若直接填了「时效状态」，转成「人工判定」再让机器复核
        # 注意：必须在下面写入机器推算值「之前」读取，否则会把推算值误当人工判定
        old = str(meta.pop("时效状态", "") or "").strip()
        if old in HAND_STATUS and not str(meta.get("人工判定") or "").strip():
            meta["人工判定"] = old
        st, _ = compute_status(meta)
        meta["时效状态"] = st
        target = POL_DIR / f"{meta['id']} {safe_name(title)}.md"
        i = 2
        while target.exists():
            target = POL_DIR / f"{meta['id']} {safe_name(title)}({i}).md"
            i += 1
        target.write_text(dump_md(frontmatter.Post(post.content, **meta)), encoding="utf-8")
        got.append({"id": meta["id"], "标题": title, "文件": target.name, "时效": st})
        shutil.move(str(f), str(BACKUP / f"inbox-done-{datetime.now():%Y%m%d-%H%M%S}-{f.name}"))
    return {"ok": True, "回收": got, "跳过": skip}


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "health"
    if cmd == "health":
        r = health_report()
        print(f"政策总数 {r['总数']} | 按时效 {r['按时效']}")
        for x in r["需处理"]:
            print(f"  ⚠ {x['id']} {x['标题']} → {'；'.join(x['问题'])}")
    elif cmd == "pack":
        print(make_search_pack(sys.argv[2:3], sys.argv[3:4]))
    elif cmd == "collect":
        print(collect_inbox())
