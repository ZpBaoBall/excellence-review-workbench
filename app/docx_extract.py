"""Word 资料评审报告解析器（B1 文审提取）

解析政府质量奖资料评审报告 Word 的四段结构，提取评分表 23 项并按映射归位 15 子条款。
纯解析 + 归位，不写文件、不联网。映射表由调用方（main.py）从 config 读入传入。
"""
import zipfile
import re
from pathlib import Path


def _txt(s: str) -> str:
    """提取一段 XML 里所有 <w:t> 文本，压缩空白"""
    return re.sub(r"\s+", " ", "".join(re.findall(r"<w:t(?: [^>]*)?>(.*?)</w:t>", s, re.S))).strip()


def _blocks(body: str):
    """按文档顺序切出表格块 / 段落块"""
    return re.findall(r"<w:tbl>.*?</w:tbl>|<w:p(?: [^>]*)?>.*?</w:p>", body, re.S)


def _table_rows(tbl_xml: str):
    tr_pat = re.compile(r"<w:tr(?: [^>]*)?>.*?</w:tr>", re.S)
    tc_pat = re.compile(r"<w:tc(?=[ >]).*?</w:tc>", re.S)
    rows = []
    for tr in tr_pat.finditer(tbl_xml):
        cells = [_txt(tc.group(0)) for tc in tc_pat.finditer(tr.group(0))]
        rows.append(cells)
    return rows


def _parse_score_table(rows):
    """解析条款评分表（7 列 + 澄清行）。

    返回 (评分项列表, 澄清列表)。
    评分项 = {'类目','类目号','评分项','条款名','分值','优势','可改进之处'}
    澄清   = {'类目号','类目','内容'}
    类目列是合并单元格，需继承上一个非空类目。
    """
    items = []
    clarifies = []
    cur_cat = ""
    cur_cat_no = ""
    for r in rows[1:]:
        if not any(r):
            continue
        first = r[0] if len(r) > 0 else ""
        # 澄清行：跨列合并，标题在首列
        if "现场需重点澄清" in first:
            content = r[1] if len(r) > 1 else ""
            if content:
                clarifies.append({"类目号": cur_cat_no, "类目": cur_cat, "内容": content})
            continue
        # 表头/其他行：评分项行（第二列是条款号）
        clause_no = r[1].strip() if len(r) > 1 else ""
        if not re.match(r"^\d+(\.\d+)+$", clause_no):
            continue
        if first:
            cur_cat = first
            m = re.match(r"^(\d+(?:\.\d+)?)", first)
            cur_cat_no = m.group(1) if m else first
        # 内容及分值列拆条款名 + 分值
        cp = r[2].strip() if len(r) > 2 else ""
        name, score = cp, ""
        m = re.match(r"^(.*?)[（(](\d+)\s*分?[）)]\s*$", cp)
        if m:
            name, score = m.group(1).strip(), m.group(2)
        items.append({
            "类目": cur_cat, "类目号": cur_cat_no, "评分项": clause_no,
            "条款名": name, "分值": score,
            "优势": (r[3] if len(r) > 3 else "").strip(),
            "可改进之处": (r[4] if len(r) > 4 else "").strip(),
        })
    return items, clarifies


def _parse_summary(rows):
    """解析评分汇总表（7 列），返回 (汇总项, 总计, 推荐意见)"""
    items = []
    total = {}
    recommend = ""
    cur_cat = ""
    for r in rows[1:]:
        if not any(r):
            continue
        first = r[0].strip() if len(r) > 0 else ""
        if "总计得分" in first:
            total = {"分值": r[1] if len(r) > 1 else "", "得分": r[2] if len(r) > 2 else ""}
            continue
        if "是否推荐" in first or "推荐" in first:
            recommend = first
            continue
        clause_no = r[1].strip() if len(r) > 1 else ""
        if not re.match(r"^\d+(\.\d+)+$", clause_no):
            continue
        if first:
            cur_cat = first
        items.append({
            "类目": cur_cat, "评分项": clause_no,
            "内容": (r[2] if len(r) > 2 else "").strip(),
            "分值": (r[3] if len(r) > 3 else "").strip(),
            "系数": (r[4] if len(r) > 4 else "").strip(),
            "得分": (r[5] if len(r) > 5 else "").strip(),
        })
    return items, total, recommend


_OPINION_SECTIONS = [
    (("组织基本情况", "企业基本情况", "基本情况", "组织概况"), "基本情况"),
    (("主要优势和创新点", "主要优势与创新点", "优势和创新点", "主要的优势", "主要优势", "优势"), "主要优势"),
    (("主要的改进建议", "主要改进建议", "改进建议", "改进意见", "建议"), "主要改进建议"),
    (("资料评审结论", "评审结论", "结论"), "评审结论"),
]
# 节标题行前缀：一、/ 一. / （一） / (一) / 1. 等
_SEC_PREFIX = re.compile(r"^\s*(?:[（(][一二三四五六七八九十]+[）)]|[一二三四五六七八九十]+[、．.]|\d+[、．.])\s*")
# 条目内序号标题句：中文（一）（二）…或阿拉伯 1. 2. …（半角括号兼容——五同样本实测混用）
_CN_NUM = re.compile(r"^(?:[（(][一二三四五六七八九十]+[）)]|\d+[、．.])\s*")


def _cell_paragraphs(tc_xml):
    """提取一个单元格内所有非空段落的文本（保留段落边界，供意见结论按段拆分）"""
    ps = re.findall(r"<w:p(?: [^>]*)?>.*?</w:p>", tc_xml, re.S)
    out = []
    for p in ps:
        t = _txt(p)
        if t:
            out.append(t)
    return out


# ── 条款回填（2026-10-24，想法 2 地基）──────────────────────
# Word 约定见《00-政府质量奖-标注约定》：方法只加粗一种标记；不写条款号，
# 提取时输入回填。方法为句子级（2026-10-27 用户定）：加粗文字按「。」断句，
# 一句一方法（见 _bold_frags）。这里负责：run 级加粗解析、小标题+正文段合并成条目、提取自检。

def _runs(p_xml):
    """段落 XML → runs [{text, bold}]。<w:b/> 或 <w:b w:val="1"/> 为加粗；
    w:val="0"/false 为显式关闭（继承被关）。"""
    runs = []
    for rm in re.finditer(r"<w:r(?: [^>]*)?>.*?</w:r>", p_xml, re.S):
        r = rm.group(0)
        txt = "".join(re.findall(r"<w:t(?: [^>]*)?>(.*?)</w:t>", r, re.S))
        if not txt:
            continue
        bm = re.search(r"<w:b(?: [^>]*)?/>", r)
        bold = bool(bm) and not re.search(r'w:val="(?:0|false|off)"', bm.group(0))
        runs.append({"text": txt, "bold": bold})
    return runs


def _para_size(p_xml):
    """段落最大字号（pt）：w:sz 为半磅，除 2；取不到返回 0"""
    sizes = [int(m.group(1)) / 2 for m in re.finditer(r'<w:sz w:val="(\d+)"', p_xml)]
    return max(sizes) if sizes else 0


def _md_bold(runs):
    """runs → 带 **加粗** 标记的文本（MD 原生，写入即呈现）

    2026-10-27 根因修复：加粗 run 的文本 strip 后为空时（用户 Word 里单独加粗的
    空格/空段，产出 `** **` 会让 markdown 解析失败、报告视图裸露 `**`），按普通
    文本输出不加 `**`——空加粗本就没有呈现意义。
    """
    return "".join(f"**{r['text']}**" if r.get("bold") and str(r.get("text") or "").strip()
                   else str(r.get("text") or "")
                   for r in runs if r.get("text"))


def _bold_frags(runs):
    """加粗片段列表（「只看方法」视图的数据源）——句子级（2026-10-27 用户约定）。

    方法 = 加粗文字按「。」断句，一句一方法：该条目所有加粗 run 的文本按顺序
    拼接（只拼加粗文本，不加非加粗的粘连文本）→ 按「。」切分；每个非空（去空白）
    片段为一个方法，保留各自的句尾「。」（阅读时是完整句子）；未终止的尾巴
    （最后一段无「。」）也保留，不丢用户标的内容；空/纯空白/纯标点片段丢弃
    （用户约定提取「加粗的文字」，光秃秃的标点如孤立的半角「.」不是文字，
    2026-10-27 遗留①：真文件段尾一个孤立加粗句点曾缝出一个叫「.」的方法）。
    历史半句加粗的文件效果为「半句们缝成一句」，比原来的碎片强，可接受。
    """
    text = "".join(r["text"] for r in runs if r.get("bold") and r.get("text"))
    if not text.strip():
        return []
    parts = re.split(r"。", text)
    out = []
    for i, seg in enumerate(parts):
        seg = seg.strip()
        # 纯标点（无任何中日韩文字/字母/数字）不是方法；带文字的片段即使以标点
        # 开头/结尾（如引号片段「"xxx"」）也保留
        if not seg or not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", seg):
            continue
        # 句尾「。」被 split 吃掉要补回（末段除外：它本来就没有「。」）
        out.append(seg + "。" if i < len(parts) - 1 else seg)
    return out


def _is_title_like(text, size, body_size):
    """小标题判定：短 + 无句末标点；字号明显大于正文时放宽到 30 字。
    「质量模式」标记段永不判小标题——它要走 _extract_modes 拆出（2026-10-25 回归教训）。
    允许例外（各企业 Word 习惯不一），兜底靠复盘时手工修正。"""
    t = (text or "").strip()
    if not t or "质量模式" in t:
        return False
    if re.search(r"[。！？；…]$", t):
        return False
    if size and body_size and size > body_size * 1.1:
        return len(t) <= 30
    return len(t) <= 20


def _cell_entries(tc_xml):
    """结论表单元格 → 条目列表（_entries_from_paras 的便捷包装）"""
    return _entries_from_paras(_cell_paras(tc_xml))


def as_entries(v):
    """兼容旧格式：[str] → [entry]；已是 entry 原样返回"""
    out = []
    for x in (v if isinstance(v, list) else []):
        if isinstance(x, dict) and "文本" in x:
            out.append(x)
        elif isinstance(x, str) and x.strip():
            out.append({"标题": "", "文本": x.strip(), "加粗片段": [], "段落数": 1})
    return out


def entry_text(e):
    """条目 → 纯文本（去 ** 标记，供计数/旧展示）"""
    return str((e or {}).get("文本", "") or "").replace("**", "")



def _split_opinion(paras):
    """拆「资料评审意见和结论」为四段（输入为段落文本列表，保留段落边界）。

    结构：一、基本情况 / 二、主要优势 / 三、主要改进建议 / 四、资料评审结论
    返回 {'基本情况': str, '主要优势': [段...], '主要改进建议': [段...], '评审结论': str}
    —— 旧版纯文本接口，保留供兼容；新提取走 _split_opinion_xml（优势/建议为条目结构）。
    """
    out = {"基本情况": "", "主要优势": [], "主要改进建议": [], "评审结论": ""}
    buf = {"基本情况": [], "主要优势": [], "主要改进建议": [], "评审结论": []}
    cur = None
    for p in paras:
        t = p.strip()
        if not t:
            continue
        hit = None
        for title, key in _OPINION_SECTIONS:
            if re.match(r"^[一二三四五六七八九十]+、\s*" + re.escape(title), t):
                hit = key
                break
        if hit:
            cur = hit
            continue
        if cur:
            buf[cur].append(t)
    out["基本情况"] = "\n".join(buf["基本情况"]).strip()
    out["评审结论"] = "\n".join(buf["评审结论"]).strip()
    out["主要优势"] = buf["主要优势"]
    out["主要改进建议"] = buf["主要改进建议"]
    return out


def _cell_paras(tc_xml):
    """单元格 → 段落列表 [{runs, text, size}]（非空）"""
    paras = []
    for pm in re.finditer(r"<w:p(?: [^>]*)?>.*?</w:p>", tc_xml, re.S):
        runs = _runs(pm.group(0))
        text = re.sub(r"\s+", " ", "".join(r["text"] for r in runs)).strip()
        if text:
            paras.append({"runs": runs, "text": text, "size": _para_size(pm.group(0))})
    return paras


def _is_summary_like(p):
    """概述段判定（2026-10-26 锦持式样，用户定）：单独一段、≤50 字——条款标识挂它。
    序号标题句与「质量模式」标记段除外（各有专门形态）。"""
    t = (p["text"] or "").strip()
    if not t or "质量模式" in t or _CN_NUM.match(t):
        return False
    return len(re.sub(r"\s+", "", t)) <= 50


def _is_elaboration_like(p):
    """展开段判定：长段（>50 字）——概述的展开表述，加粗片段即方法。"""
    return len(re.sub(r"\s+", "", p["text"] or "")) > 50


def _entries_from_paras(paras):
    """段落列表 → 条目列表。三种标题形态：
    ① 序号标题句「（一）……」/「1. ……」（五同样式）：序号存 entry['序号']，
       标题句保留原文（含序号），后续段落到下一序号段为正文；
    ② 概述段+展开段（2026-10-26 锦持式样，用户定）：概述=单独一段 ≤50 字
       （可以带句号，不再要求无句末标点），紧随的长段为展开；条款标识挂概述，
       展开内的 **加粗** = 该优势项的方法（「只看做法」的数据源）；
    ③ 小标题段（短+无句末标点，或字号明显大于正文）与其后正文段合并为一条。
    """
    body_size = max((p["size"] for p in paras if len(p["text"]) > 30), default=0)
    entries, i = [], 0
    while i < len(paras):
        p = paras[i]
        i += 1
        m = _CN_NUM.match(p["text"])
        if m:                                   # 形态①：序号标题句
            grp = []
            while i < len(paras) and not _CN_NUM.match(paras[i]["text"]) \
                    and not _is_title_like(paras[i]["text"], paras[i]["size"], body_size):
                grp.append(paras[i])
                i += 1
            runs = [r for g in grp for r in g["runs"]] or p["runs"]   # 序号段无后续正文：自成一条
            entries.append({
                "序号": m.group(0).strip(), "标题": p["text"],
                "文本": _md_bold(runs), "加粗片段": _bold_frags(runs),
                "段落数": 1 + len(grp),
            })
            continue
        if _is_summary_like(p) and i < len(paras) and _is_elaboration_like(paras[i]):
            # 形态②：概述段 + 展开段（锦持式样）——概述作标题（条款标识目标），
            # 展开段全段并入（加粗片段=方法；概述自身格式不计入，防污染方法清单）
            title = p["text"]
            grp = [paras[i]]
            i += 1
            while i < len(paras) and _is_elaboration_like(paras[i]):
                grp.append(paras[i])
                i += 1
            runs = [r for g in grp for r in g["runs"]]
            entries.append({
                "序号": "", "标题": title,
                "文本": _md_bold(runs), "加粗片段": _bold_frags(runs),
                "段落数": 1 + len(grp),
            })
            continue
        title, grp = "", [p]                    # 形态③：小标题合并
        if _is_title_like(p["text"], p["size"], body_size):
            title = p["text"]
            grp = []
            while i < len(paras) and not _is_title_like(paras[i]["text"], paras[i]["size"], body_size):
                grp.append(paras[i])
                i += 1
            if not grp:                         # 小标题后面没正文了：自成一条
                grp = [p]
                title = ""
        runs = [r for g in grp for r in g["runs"]]
        entries.append({
            "序号": "", "标题": title,
            "文本": _md_bold(runs), "加粗片段": _bold_frags(runs),
            "段落数": len(grp),
        })
    return entries


def _extract_modes(opinion):
    """从优势/建议条目拆「质量模式」段（五同样本：嵌在优势单元格末尾）。

    拆分后条目余留原节，模式段进 result['模式'] = [{来源, 文本}]；
    标题/描述的精细切分留给人（模式草稿弹窗里填），程序只负责分离。
    """
    modes = []
    for key in ("主要优势", "主要改进建议"):
        kept = []
        for e in opinion.get(key) or []:
            txt = str(e.get("文本") or "")
            i = txt.find("质量模式")
            if i >= 0:
                head, mode_txt = txt[:i].strip(), txt[i:].strip()
                if head:
                    e["文本"] = head
                    kept.append(e)
                if mode_txt:
                    modes.append({"来源": key, "文本": mode_txt,
                                  "加粗片段": [f for f in (e.get("加粗片段") or []) if f in mode_txt]})
            else:
                kept.append(e)
        opinion[key] = kept
    return modes


def _paras_to_opinion(paras):
    """段落列表 → 意见结论 dict（节检测 + 条目切分 + 自检）。Word 与粘贴入口共用。

    节标题兼容多措辞（组织基本情况/主要的优势和创新点…，2026-10-25 五同样本实测后扩）；
    条目支持序号标题句「（一）……」/「1. ……」（序号存 entry['序号']，标题句保留原文，
    条款回填确认时再剥离——见 index.html confirmClauses）。
    """
    buf = {"基本情况": [], "主要优势": [], "主要改进建议": [], "评审结论": []}
    cur, heading_chars = None, 0
    for p in paras:
        had_prefix = bool(_SEC_PREFIX.match(p["text"]))
        t = _SEC_PREFIX.sub("", p["text"]).strip()
        hit = None
        for variants, key in _OPINION_SECTIONS:
            for v in variants:
                if not v:
                    continue
                # 长变体（≥4 字，如「组织基本情况」）开头即中；短变体（优势/建议/结论）
                # 必须带序号前缀，防正文短句误判——2026-10-25 回归教训
                if t.startswith(v) and (had_prefix or len(v) >= 4):
                    hit = key
                    break
            if hit:
                break
        if hit and len(t) <= 40:               # 节标题行：短行才认，防正文里带关键词误判
            cur = hit
            heading_chars += len(re.sub(r"\s+", "", p["text"]))
            continue
        if cur:
            buf[cur].append(p)
        else:
            heading_chars += len(re.sub(r"\s+", "", p["text"]))   # 节前表标题被消费，计入已捕获
    out = {
        "基本情况": "\n".join(p["text"] for p in buf["基本情况"]).strip(),
        "评审结论": "\n".join(p["text"] for p in buf["评审结论"]).strip(),
        "主要优势": _entries_from_paras(buf["主要优势"]),
        "主要改进建议": _entries_from_paras(buf["主要改进建议"]),
    }
    nz = lambda s: len(re.sub(r"\s+", "", s or ""))
    cell_total = sum(nz(p["text"]) for p in paras)
    cap = (nz(out["基本情况"]) + nz(out["评审结论"]) + heading_chars
           + sum(nz(entry_text(e)) + nz(e.get("标题") or "") for e in out["主要优势"])
           + sum(nz(entry_text(e)) + nz(e.get("标题") or "") for e in out["主要改进建议"]))
    ratio = (cap / cell_total) if cell_total else 1.0
    out["自检"] = {"覆盖": f"{ratio:.0%}"}
    if ratio < 0.95:
        out["自检"]["提示"] = (f"意见结论提取覆盖率仅 {ratio:.0%}，疑似有段落遗漏，"
                               "删除 Word 前请人工核对")
    return out


def _split_opinion_xml(tc_xml):
    """Word 结论表 → 意见结论（_paras_to_opinion 的 docx 包装）"""
    return _paras_to_opinion(_cell_paras(tc_xml))


def split_pasted(text):
    """粘贴文本（组员复盘入口，2026-10-25）→ 同 Word 的意见结论结构。

    约定格式（与 Word 版一一对应，见《00-政府质量奖-标注约定》）：
      一、基本情况 / 二、主要优势 / 三、主要改进建议（节标题独占一行，序号前缀可选）
      每条 = 序号标题句（（一）/ 1.）或小标题行 + 正文行（可多行）；**星号** = 方法，
      句子级（2026-10-27 用户约定）：一个条目内所有 **...** 内容按顺序拼接后按「。」
      切句，一句一方法（边界规则见 _bold_frags）；星号标记在正文里的位置不动
      （正文仍保留 ** 原样，供 MD 写入呈现）。
    """
    paras = []
    for line in (text or "").splitlines():
        t = line.strip()
        if not t:
            continue
        runs = []
        for seg in re.split(r"(\*\*.*?\*\*)", t):
            if not seg:
                continue
            if seg.startswith("**") and seg.endswith("**") and len(seg) > 4:
                runs.append({"text": seg[2:-2], "bold": True})
            else:
                runs.append({"text": seg, "bold": False})
        # 段落 text 用去标记纯文本（与 Word 路径一致：runs 承载加粗，text 不带 **）
        paras.append({"runs": runs, "text": "".join(r["text"] for r in runs), "size": 0})
    return _paras_to_opinion(paras)



def extract_report(path):
    """解析 docx，返回结构化 dict"""
    z = zipfile.ZipFile(str(path))
    xml = z.read("word/document.xml").decode("utf-8")
    body = re.search(r"<w:body>(.*)</w:body>", xml, re.S).group(1)

    result = {
        "企业名称": "", "评分表": [], "澄清": [],
        "意见结论": {"基本情况": "", "主要优势": [], "主要改进建议": [], "评审结论": ""},
        "汇总": [], "总计": {}, "推荐": "", "模式": [],
    }
    paras = []
    for b in _blocks(body):
        if b.startswith("<w:tbl>"):
            rows = _table_rows(b)
            if not rows:
                continue
            header = rows[0]
            if "优势" in header and "可改进之处" in header:
                items, clarifies = _parse_score_table(rows)
                result["评分表"] = items
                result["澄清"] = clarifies
            elif "分值" in header and "系数" in header and "小计" in header:
                items, total, recommend = _parse_summary(rows)
                result["汇总"] = items
                result["总计"] = total
                result["推荐"] = recommend
            elif any("资料评审意见和结论" in c for c in header):
                # 结论表：单行大单元格，内含 一基本情况/二主要优势/三改进建议/四结论
                # 条目版切分：优势/建议保留加粗与小标题（供条款回填），其余为字符串
                tc = re.findall(r"<w:tc(?=[ >]).*?</w:tc>", b, re.S)
                result["意见结论"] = _split_opinion_xml(tc[0]) if tc else _split_opinion([])
            elif len(header) == 1 and len(rows) >= 2:
                # 1 列多行表：行首即节标题（五同「现场评审综合报告」实测结构：
                # 行1 组织基本情况 / 行2 主要优势和创新点 / 行3 主要改进建议）。
                # 拼全部单元格交给统一切分，试出有效意见才认（防误吃随机单列表）。
                trs = re.findall(r"<w:tr(?: [^>]*)?>.*?</w:tr>", b, re.S)
                tcs = []
                for tr in trs:
                    found = re.findall(r"<w:tc(?=[ >]).*?</w:tc>", tr, re.S)
                    if found:
                        tcs.append(found[0])
                if tcs:
                    trial = _split_opinion_xml("".join(tcs))
                    if trial["主要优势"] or trial["主要改进建议"]:
                        result["意见结论"] = trial
        else:
            t = _txt(b)
            if t:
                paras.append(t)

    # 企业名：优先「申报单位：」，其次「申报单位名称：」
    for p in paras:
        m = re.search(r"申报单位[名称]*[：:]\s*(.+)", p)
        if m:
            result["企业名称"] = m.group(1).strip()
            break
    # 模式段分离（「质量模式：」标记，五同样式嵌在优势末尾）
    result["模式"] = _extract_modes(result["意见结论"])
    # 自检提顶层（由结论表单元格内部校验算出，见 _split_opinion_xml）
    result["自检"] = result["意见结论"].pop("自检", {"覆盖": "—"})
    return result


def map_score_items(score_items, mapping):
    """把评分表 23 项按映射归位成 15 过程子条款。

    返回 dict：
      - 直接对应：评分项号即条款号，原样归
      - 自动归：结果项按映射拆到目标子条款
      - 弹窗判断：横切项，待用户选
    mapping = {'自动归': {...}, '弹窗判断': [...]}
    """
    auto = mapping.get("自动归", {}) or {}
    popup = set(mapping.get("弹窗判断", []) or [])
    fix = mapping.get("纠偏", {}) or {}
    direct, autoed, popup_items = [], [], []
    for it in score_items:
        no = it["评分项"]
        # 编号纠偏：评分表「评分项」笔误时，按条款名关键词纠正为标准编号（保留原编号证据）
        name = it.get("条款名", "")
        for kw, correct in fix.items():
            if kw in name and str(no) != str(correct):
                it["原编号"] = no
                it["评分项"] = correct
                no = correct
                break
        if no in popup:
            popup_items.append(it)
        elif no in auto:
            it["归到"] = auto[no]
            autoed.append(it)
        else:
            direct.append(it)
    return {"直接对应": direct, "自动归": autoed, "弹窗判断": popup_items}
