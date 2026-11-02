# -*- coding: utf-8 -*-
"""文审提取结果 → 文审报告 MD 组装（B2）

把 B1 提取的意见结论（基本情况 / 主要优势 / 主要改进建议），组装成文审报告 MD。
纯文本组装，不写文件、不联网；写入由 main.py 负责。

文审报告 MD 结构（用户定稿 2026-10-21）：
  frontmatter（标准 / 企业名称 / 报告日期）
  ## 基本情况
  ## 主要优势（按条款分节，2026-10-24 条款回填版）
  ## 主要改进建议（同上）

条款回填（2026-10-24 想法 2）：优势/建议条目可带「条款」字段（提取时用户输入），
落 MD 时为 `### 条款号 条款名` 小节，同条款多条进同节，未归位进 `### 未归位`。

概述 H4 化（2026-10-27 用户定）：条款内条目概述从 bullet 加粗行（`- **概述**`+缩进
续行）改为 `#### 概述` 小节标题 + 空行 + 展开段（每个展开段一个自然段，句内 **加粗**
保留）——Obsidian 大纲 H3 条款→H4 概述层级导航；以后按条款行做统计检索时 H4 是天然
子单元。parse_practices 双向兼容：新 H4 格式与旧 bullet 格式都能读出做法索引。

程序节/手写节分离（重跑安全）：程序节=基本情况/主要优势/主要改进建议（可被重新提取覆盖）；
手写节=复盘沉淀/开场白/现场核实信息/相关评审记录等（merge_sections 原样保留）。

现场终版合并（merge_onsite_final，2026-10-27 用户定；2026-10-28 折叠规则修订；
2026-10-30 R1 折叠内容再修订）：终版=在已有现场报告上更新，旧「现场核实信息」节里的
**普通条款块**不再原位保留——逐条款块折叠成 callout 归档到文尾，块内**只留三栏**
（优势/可改进之处/现场核实）+ 块标题行，丢掉「相关条款：[[...]]」双链行；「### 开场白」块
与派生伪条目块（「报告主要优势条款·*」「报告主要建议条款·*」）**不折叠**，保持 live 原位留在
→「现场核实信息」节里（伪条目优势/可改进之处已落盘，终版里要继续看得到）。程序节由新提取全覆盖。

做法清单换源（parse_practices，2026-10-30 R2 用户拍板）：方法不再只来自加粗片段，
而从**每条优势/建议的正文全文**按「。」切句（终版正文无加粗也能出方法）；
条目结构 = {概述, 全文, 方法}。

模式卡（build_mode_card / parse_mode_card，2026-10-30 R3-c 用户拍板）：40-质量模式库
的模式卡分**程序区 / 用户区**——用户区用 `<!-- 用户区开始/结束 -->` 标记圈起来，
程序只替换标记之外的程序区，用户手写批注永不丢。

"""
import re
from datetime import datetime
from pathlib import Path

from docx_extract import as_entries, entry_text


def load_clauses(lib_path, std_code="GBT19580"):
    """扫条款库，返回 {条款号: 条款名}（按适用标准编号前缀过滤）"""
    d = Path(lib_path) / "10-政府质量奖" / "10-条款与心得"
    out = {}
    if not d.exists():
        return out
    for f in d.glob("*.md"):
        stem = f.name[:-3]
        parts = stem.split("-")
        if len(parts) < 3 or parts[0] != std_code:
            continue
        m = re.match(r"^(\d+(?:\.\d+)*)(.*)$", "-".join(parts[2:]))
        if not m:
            continue
        out[m.group(1)] = m.group(2)
    return out


def _as_list(v):
    """兼容字符串/列表：段落列表统一成 list（旧字符串也兜底）"""
    if isinstance(v, str):
        return [v] if v.strip() else []
    return list(v or [])


# 程序节：重新提取可覆盖（2026-10-30 R5 用户拍板：去掉「质量模式」——模式内容归
# 40-质量模式库，现场报告 MD 不再生成「## 质量模式」节，只留 frontmatter 双向关联）
PROG_TITLES = ("基本情况", "主要优势", "主要改进建议")


def _clause_sections(entries, clause_names):
    """条目按条款分组落节：`### 条款号 条款名`，同条款多条进同节，未归位进「未归位」节。

    H4 概述格式（2026-10-27 用户定，Obsidian 大纲导航：H3 条款 → H4 概述）：
      #### 概述
      （空行）
      展开段（每个展开段一个自然段；句内 **加粗方法** 保留）
    概述作 H4 小节标题（条款标识挂它；按条款行做统计检索时 H4 是天然子单元），
    展开段平铺为自然段（parse_practices 认这个结构：概述=H4 文本，方法=该 H4 块
    到下个 ####/### 之间的加粗片段）；无标题条目纯正文平铺（并入所在条款节）。
    """
    groups, order = {}, []
    for e in as_entries(entries):
        c = str(e.get("条款") or "").strip()
        g = c or "未归位"
        if g not in groups:
            groups[g] = []
            order.append(g)
        groups[g].append(e)
    lines = []
    for g in order:
        if g == "未归位":
            lines.append("### 未归位（复盘时补条款号）")
        else:
            lines.append(f"### {g} {clause_names.get(g, '')}".rstrip())
        lines.append("")
        for e in groups[g]:
            title = str(e.get("标题") or "").strip()
            segs = [s.strip() for s in str(e.get("文本") or "").split("\n") if s.strip()]
            if title:
                lines.append(f"#### {title}")
                lines.append("")
            for seg in segs:
                lines.append(seg)
                lines.append("")
        lines.append("")
    return lines


def build_md(company, report_date, std, opinion, clause_names=None, modes=None, doc_title="资料评审"):
    """组装报告 MD 文本（文审/现场终版通用）。

    modes = [{'来源','文本'}]（提取识别的质量模式段 → 「## 质量模式」节，程序节可覆盖）。
    doc_title = 资料评审 / 现场评审（组长复盘终版写现场 MD 用）。
    """
    clause_names = clause_names or {}
    lines = ["---", f"标准: {std}", f"企业名称: {company}", f"报告日期: {report_date}"]
    if doc_title == "现场评审":
        lines.append(f"现场日期: {report_date}")   # 终版日期即现场日期（回台账/文件名同源）
    lines += ["---", ""]
    lines.append(f"# {company} · {doc_title}")
    lines.append("")

    base = (opinion.get("基本情况") or "").strip()
    if base:
        lines.append("## 基本情况")
        lines.append("")
        lines.append(base)
        lines.append("")

    for key in ("主要优势", "主要改进建议"):
        entries = as_entries(opinion.get(key))
        if not entries:
            continue
        lines.append(f"## {key}")
        lines.append("")
        # 「条款」键存在 = 走过归位弹窗（哪怕没选）→ 按条款分节，空者进「未归位」；
        # 无该键 = 旧数据/旧流程 → 平铺兼容
        if any("条款" in e for e in entries):
            lines.extend(_clause_sections(entries, clause_names))
        else:
            for e in entries:
                for seg in str(e.get("文本") or "").split("\n"):
                    if seg.strip():
                        lines.append(f"- {seg.strip()}")
            lines.append("")

    if modes:
        lines.append("## 质量模式")
        lines.append("")
        for m in modes:
            txt = str(m.get("文本") or "").strip()
            if txt:
                lines.append(f"- {txt}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _split_sections(md_text):
    """按 `## ` 切段：返回 (head, [(title, body), ...])；frontmatter+H1 归 head"""
    parts = re.split(r"(?m)^(## .+)$", md_text or "")
    head = parts[0] if parts else ""
    secs = []
    for i in range(1, len(parts), 2):
        secs.append((parts[i][3:].strip(), parts[i + 1] if i + 1 < len(parts) else ""))
    return head, secs


def merge_sections(old_text, prog_md, log_line=None):
    """重跑提取时合并（程序节/手写节分离的核心）。

    - 程序节（基本情况/主要优势/主要改进建议）：用 prog_md 的新版**覆盖**
    - 手写节（复盘沉淀/开场白/现场核实信息/相关评审记录等）：old 里原样保留
    - 提取日志：追加一行（log_line）；old 无此节则新建
    """
    old_head, old_secs = _split_sections(old_text)
    _, new_secs = _split_sections(prog_md)
    head = old_head if old_head.strip() else _split_sections(prog_md)[0]
    new_prog = {t: b for t, b in new_secs if t in PROG_TITLES}
    log_body, kept = "", []
    for t, b in old_secs:
        if t in PROG_TITLES:
            continue
        if t == "提取日志":
            log_body = b
            continue
        kept.append((t, b))
    out = head.rstrip() + "\n"
    for t in PROG_TITLES:                  # 程序节按固定序拼
        if t in new_prog:
            out += f"\n## {t}\n{new_prog[t].rstrip()}\n"
    for t, b in kept:                      # 手写节保持原顺序
        out += f"\n## {t}\n{b.rstrip()}\n"
    if log_line:
        if log_body.strip():
            log_body = log_body.rstrip() + f"\n- {log_line}\n"
        else:
            log_body = f"- {log_line}\n"
        out += f"\n## 提取日志\n\n{log_body.rstrip()}\n"
    return out.rstrip() + "\n"


# 派生伪条目块标题（2026-10-28 用户定：终版折叠时这类块保持 live 原位，不折叠）
_PSEUDO_BLOCK_RE = re.compile(r"^报告主要(?:优势|建议)条款·")


def _onsite_blocks(sec_body):
    """切「现场核实信息」节正文为 ### 块列表：[(head, block_text), ...]。

    block_text 含「### 」前缀与原块全部行（re.split 吃掉的前缀补回）；
    空标题块（光杆 ###）丢弃——无归档价值也无 live 价值。
    """
    out = []
    for b in re.split(r"^### ", sec_body or "", flags=re.M)[1:]:
        lines = b.splitlines()
        head = lines[0].strip() if lines else ""
        if not head:
            continue
        out.append((head, ("### " + b).rstrip("\n")))
    return out


def _is_live_onsite_block(head):
    """终版合并时保持 live 原位的块（2026-10-28 用户定）：开场白块 + 两类伪条目块。

    普通条款块（数字条款号，如 4.2 / 4.3.2）不 live——折叠归档到文尾。
    """
    return head.startswith("开场白") or bool(_PSEUDO_BLOCK_RE.match(head))


def _onsite_live_blocks(sec_body):
    """节正文 → 只保留 live 块（开场白/伪条目）的正文（无 live 块返回空串）。"""
    live = [blk for head, blk in _onsite_blocks(sec_body) if _is_live_onsite_block(head)]
    return "\n\n".join(live)


def _onsite_field(block: str, labels) -> str:
    """条款块正文 → 某栏的值（跨行捕获：到下一个 `- ` 行或块尾）。

    取值口径与 onsite_export.parse_onsite_terms 的 grab() 一致（同一套正则）。
    标签按顺序尝试：普通条款块用 `- 文审优势：`（阶段一 build_onsite_md 写的），
    派生伪条目块用 `- 优势：`（派生内容落盘）——两种都认。
    """
    for lab in labels:
        mm = re.search(rf"- {re.escape(lab)}：(.*?)(?=\n- |\Z)", block or "", flags=re.S)
        if mm:
            val = mm.group(1).strip()
            if val:
                return val
    return ""


def _quote_lines(text: str, prefix: str) -> list:
    """多行文本 → Obsidian callout 引用行（首行带 prefix，其余行各自加 '> '）。"""
    lines = str(text or "").split("\n")
    out = [f"{prefix}{lines[0]}"]
    for ln in lines[1:]:
        out.append(f"> {ln}" if ln.strip() else ">")
    return out


def _fold_onsite_terms(sec_body, fold_date=""):
    """旧「现场核实信息」节正文 → 折叠 callout 文本（终版归档用）。

    2026-10-30 用户拍板（R1）：块内**只留三栏**——优势 / 可改进之处 / 现场核实：
      - 优势标签兼容两种：`- 文审优势：`（阶段一 build_onsite_md 写的）与 `- 优势：`
        （派生伪条目块落的），取值口径与 onsite_export.parse_onsite_terms 的 grab()
        一致（跨行捕获到下一个 `- ` 行或块尾）；
      - **丢掉** `相关条款：[[...]]` 双链行（用户原话：存档「仅保留我负责条款的部分
        即可，即优势、可改进之处及核实内容」）；
      - **保留块标题行** `### 条款号 条款名`（折叠块里要能认出是哪条）；
      - 空值也保留该行（如 `- 可改进之处：` 空）。
    折叠 callout 的标题行格式保持现状不变：
    `> [!note]- 原现场核实记录（{日期}，终版写入时折叠归档）`。
    「### 开场白」块与派生伪条目块（报告主要优势条款·*/报告主要建议条款·*）**不折叠**
    （由 merge_onsite_final 保持 live 原位留在「现场核实信息」节里）。
    无有效条款块返回空串（无旧现场 MD / 空节 / 全是 live 块 → 不折叠）。
    """
    blocks = [(head, blk) for head, blk in _onsite_blocks(sec_body)
              if not _is_live_onsite_block(head)]
    if not blocks:
        return ""
    date = (fold_date or "").strip() or datetime.now().strftime("%Y-%m-%d")
    q = [f"> [!note]- 原现场核实记录（{date}，终版写入时折叠归档）"]
    for head, blk in blocks:
        q.append(">")
        q.append(f"> ### {head}")
        q.append(">")
        q.extend(_quote_lines(_onsite_field(blk, ("文审优势", "优势")), "> - 优势："))
        q.extend(_quote_lines(_onsite_field(blk, ("可改进之处",)), "> - 可改进之处："))
        q.extend(_quote_lines(_onsite_field(blk, ("现场核实",)), "> - 现场核实："))
    return "\n".join(q).rstrip() + "\n"


def merge_onsite_final(old_text, prog_md, log_line=None, fold_date=""):
    """现场终版专用合并（2026-10-27 用户定：终版=在已有现场报告上更新，不是新建；
    2026-10-28 折叠规则修订：只折叠普通条款块，伪条目/开场白块保持 live 原位）。

    与 merge_sections 的差异：旧「现场核实信息」节里的**普通条款块**不再原位保留——
    整块折叠成 callout（保留全部行，见 _fold_onsite_terms）归档到文尾（提取日志之后）；
    「### 开场白」块与派生伪条目块（报告主要优势条款·*/报告主要建议条款·*）**不折叠**，
    留在「现场核实信息」节里继续展示（伪条目优势/可改进之处已落盘，P1）。
    - 程序节（基本情况/主要优势/主要改进建议/质量模式）：prog_md 新版**全覆盖**
    - 其他手写节（复盘沉淀/开场白/相关评审记录等）：old 里原样保留
    - 提取日志：正常追加（log_line）；old 无此节则新建
    - fold_date：旧现场 MD 文件名日期（缺省今天）——只影响折叠块标题
    无旧现场 MD（old_text 为空）时不折叠，行为同 merge_sections。
    """
    old_head, old_secs = _split_sections(old_text)
    _, new_secs = _split_sections(prog_md)
    head = old_head if old_head.strip() else _split_sections(prog_md)[0]
    new_prog = {t: b for t, b in new_secs if t in PROG_TITLES}
    log_body, kept, fold_src = "", [], ""
    for t, b in old_secs:
        if t in PROG_TITLES:
            continue
        if t == "提取日志":
            log_body = b
            continue
        if t == "现场核实信息":
            fold_src = b          # 普通条款块折叠归档到文尾（伪条目/开场白块不折叠）
            live = _onsite_live_blocks(b)
            if live.strip():       # 有 live 块（伪条目/开场白）→ 节保留，只留这些块
                kept.append((t, "\n" + live))
            continue
        kept.append((t, b))
    out = head.rstrip() + "\n"
    for t in PROG_TITLES:                  # 程序节按固定序拼
        if t in new_prog:
            out += f"\n## {t}\n{new_prog[t].rstrip()}\n"
    for t, b in kept:                      # 手写节保持原顺序
        out += f"\n## {t}\n{b.rstrip()}\n"
    if log_line:
        if log_body.strip():
            log_body = log_body.rstrip() + f"\n- {log_line}\n"
        else:
            log_body = f"- {log_line}\n"
        out += f"\n## 提取日志\n\n{log_body.rstrip()}\n"
    fold = _fold_onsite_terms(fold_src, fold_date)
    if fold:
        out += "\n" + fold
    return out.rstrip() + "\n"


def _frags_to_methods(frags):
    """加粗片段列表 → 句子级方法列表（2026-10-27 用户约定，与 docx_extract._bold_frags 同规则）：
    按顺序拼接 → 按「。」切句，一句一方法；保留各自句尾「。」；未终止的尾巴
    （最后一段无「。」）也保留；空/纯空白/纯标点片段丢弃（光秃秃的标点不是
    「加粗的文字」，带文字的引号片段等不误杀）。

    2026-10-30（R2）：本函数同时承担「正文全文切句」——传 [全文] 即得全文的句子级
    方法（加粗与否无关），故实现保持对任意文本成立。"""
    text = "".join(f for f in frags if f)
    if not text.strip():
        return []
    parts = re.split(r"。", text)
    out = []
    for i, seg in enumerate(parts):
        seg = seg.strip()
        if not seg or not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", seg):
            continue
        out.append(seg + "。" if i < len(parts) - 1 else seg)
    return out


def _plain_body(text: str) -> str:
    """MD 正文块 → 纯文本（R2 的「全文」口径）：去 `**` 加粗星号、去 bullet `- ` 前缀、
    去行首缩进，**保留换行**（段落边界）；首尾空行去掉。"""
    out = []
    for ln in str(text or "").splitlines():
        s = ln.strip()
        s = re.sub(r"^[-*+]\s+", "", s)        # 去 bullet 前缀（- / * / +）
        s = s.replace("**", "")                 # 去加粗星号
        out.append(s)
    while out and not out[0]:
        out.pop(0)
    while out and not out[-1]:
        out.pop()
    return "\n".join(out)


def _text_to_methods(full_text: str) -> list:
    """正文全文 → 句子级方法列表（2026-10-30 用户拍板 R2：清单换源）。

    规则与 _frags_to_methods 同款：按「。」切句，一句一方法，保留句尾「。」；
    纯标点/空白片段丢弃；末段无句号也保留。"""
    return _frags_to_methods([full_text])


def _make_item(overview: str, body: str, fallback_src: str = "") -> dict:
    """组装一条做法条目（R2 新结构）：{概述, 全文, 方法}。

    - 全文 = 该条正文纯文本（不含概述本身）
    - 方法 = 全文按「。」切句（不再只依赖加粗——示例终版正文无加粗也能出方法）
    - 回退：该条**没有正文**时（旧的 bullet 格式只有加粗概述），方法退回旧的
      加粗切句逻辑（_frags_to_methods），全文为该 bullet 的纯文本正文
    """
    full = _plain_body(body)
    if full:
        methods = _text_to_methods(full)
    else:
        methods = _frags_to_methods(re.findall(r"\*\*(.+?)\*\*", fallback_src or body))
    return {"概述": overview, "全文": full, "方法": methods}


def parse_practices(md_text):
    """从报告 MD 提取「做法索引」（「只看做法」视图 + 复盘 tab 清单的数据源）。

    扫「主要优势*/主要改进建议*」节（2026-10-27 起前缀匹配：容忍 Word 原措辞变体
    如「主要优势与创新点」），按 `### 条款号 条款名` 子节分组；
    组内两种条目格式（双向兼容）：
      - H4 格式（新）：`#### 概述` 小节标题 + 展开段——概述=H4 文本，全文=该 H4 块
        到下个 ####/### 之间的正文纯文本，方法=全文按「。」切句；H4 之前的散段
        （无标题条目）按概述为空串收编，方法不丢；
      - bullet 格式（旧）：bullet 首行 `**概述**` + 缩进续行 → 该条概述，其余正文
        为全文，方法同样按全文切句。
    2026-10-30 用户拍板（R2）：方法**不再只依赖加粗**——终版正文没加粗也能出方法
    （示例终版 5 组全 0 方法的根因）；条目结构扩展为 {概述, 全文, 方法}。
    返回 [{类型, 标题, 条目:[{概述, 全文, 方法:[...]}]}]；
    旧格式（无 ### 分节 / bullet 无加粗概述）→ 概述为空串，整节正文作一条，前端降级展示。
    """
    _, secs = _split_sections(md_text or "")
    out = []
    for title, body in secs:
        # 节名前缀匹配（2026-10-27 QA 抓跟进）：手工收库报告用 Word 原措辞
        # 「## 主要优势与创新点」——startswith 两个主名即认，不放宽过度误扫无关节
        kind = ("优势" if title.startswith("主要优势")
                else "建议" if title.startswith("主要改进建议") else None)
        if not kind:
            continue
        parts = re.split(r"(?m)^(### .+)$", body)
        if len(parts) == 1:                     # 无 ### 子节（旧平铺格式）
            out.append({"类型": kind, "标题": "（未按条款分节）",
                        "条目": [_make_item("", body, body)]})
            continue
        for i in range(1, len(parts), 2):
            head = parts[i][4:].strip()
            sub = parts[i + 1] if i + 1 < len(parts) else ""
            items = []
            h4_parts = re.split(r"(?m)^(#### .+)$", sub)
            if len(h4_parts) > 1:               # H4 格式（2026-10-27 起）
                pre = h4_parts[0]               # 首个 #### 之前的散段=无标题条目
                if pre.strip():
                    items.append(_make_item("", pre, pre))
                for j in range(1, len(h4_parts), 2):
                    overview = h4_parts[j][5:].strip()
                    blk = h4_parts[j + 1] if j + 1 < len(h4_parts) else ""
                    items.append(_make_item(overview, blk, blk))
            else:                               # 旧 bullet 格式（无 #### 子标题）
                for bullet in re.split(r"(?m)^(?=- )", sub):
                    if not bullet.strip():
                        continue
                    m = re.match(r"- \*\*(.+?)\*\*", bullet)          # 新格式：概述加粗在 bullet 首
                    if m:
                        overview, rest = m.group(1), bullet[m.end():]
                    else:                                             # 旧格式：无概述行
                        overview, rest = "", bullet
                    items.append(_make_item(overview, rest, bullet))
            out.append({"类型": kind, "标题": head, "条目": items})
    return out


# ── 模式卡（40-质量模式库）：程序区 / 用户区分离 ──────────────────────
# 2026-10-30 用户拍板（R3-c）：模式草稿不再整文件覆盖——用户区（批注、复盘优化区）
# 用显式 HTML 注释标记圈起来，程序只替换标记之外的程序区，用户区原样保留。
MODE_USER_BEGIN = "<!-- 用户区开始 -->"
MODE_USER_END = "<!-- 用户区结束 -->"
MODE_TAIL = "> 本文件为复盘草稿（2026-10-25 R5 生成），去 Obsidian 精修后即为正式模式卡。"
MODE_USER_DEFAULT = "## 复盘优化区（留空，复盘时填写）"
MODE_PRACTICE_HEAD = "入选做法（按条款）"


def split_frontmatter(md_text: str):
    """MD → (frontmatter 行列表, 正文)。无 frontmatter 时返回 ([], 原文)。"""
    txt = md_text or ""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", txt, re.S)
    if not m:
        return [], txt
    return m.group(1).splitlines(), txt[m.end():]


def merge_frontmatter(lines, updates) -> list:
    """frontmatter 行 → 合并后的行列表：已有键**就地改写**（不重复加），缺键补在末尾。"""
    out = list(lines or [])
    for key, val in (updates or {}).items():
        if val is None or val == "":
            continue
        hit = False
        for i, ln in enumerate(out):
            if re.match(rf"^{re.escape(key)}\s*:", ln):
                out[i] = f"{key}: {val}"
                hit = True
                break
        if not hit:
            out.append(f"{key}: {val}")
    return out


def split_mode_text(raw: str):
    """质量模式原文 → (模式名称, 说明)。

    「质量模式：」标记之后的第一行=名称，其余=说明；无标记时整段按首行/其余切。
    与前端 openModeDraftModal 的切分口径一致（2026-10-30 R3-a：数据源换成模式卡，
    但切分规则沿用同一套，避免两边理解分叉）。"""
    text = str(raw or "").replace("**", "").strip()
    mi = text.find("质量模式：")
    body = text[mi + len("质量模式："):].strip() if mi >= 0 else text
    nl = body.find("\n")
    if nl >= 0:
        return body[:nl].strip(), body[nl + 1:].strip()
    return body, ""


def parse_mode_card(md_text: str) -> dict:
    """模式卡 MD → {模式名称, 说明, 用户区}（供复盘 tab 预填，2026-10-30 R3-a）。

    程序区 = 用户区标记之外的部分；模式名称 = 程序区里第一个非「入选做法」二级标题，
    说明 = 该标题到下一个二级标题之间的正文。"""
    _fm, body = split_frontmatter(md_text or "")
    user = ""
    if MODE_USER_BEGIN in body and MODE_USER_END in body:
        i = body.index(MODE_USER_BEGIN)
        j = body.index(MODE_USER_END)
        user = body[i + len(MODE_USER_BEGIN):j].strip()
        prog = body[:i]
    else:
        prog = body
    name, desc = "", ""
    secs = re.split(r"(?m)^(## .+)$", prog)
    for i in range(1, len(secs), 2):
        head = secs[i][3:].strip()
        if head.startswith(MODE_PRACTICE_HEAD):
            continue
        name = head
        desc = (secs[i + 1] if i + 1 < len(secs) else "").strip()
        break
    return {"模式名称": name, "说明": desc, "用户区": user}


def _mode_program_zone(name: str, desc: str, practices) -> str:
    """模式卡程序区：`## {模式名称}` + 说明 + `## 入选做法（按条款）`。

    模式名/说明为空时**不写空的 `## ` 节**（2026-10-30 R3-c 用户拍板），
    只写入选做法与用户区。"""
    out = []
    nm = str(name or "").strip()
    if nm:
        out += [f"## {nm}", ""]
    ds = str(desc or "").strip()
    if ds:
        out += [ds, ""]
    picked = [g for g in (practices or []) if (g.get("做法") or [])]
    if picked:
        out += [f"## {MODE_PRACTICE_HEAD}", ""]
        for g in picked:
            out += [f"### {g.get('条款') or '未归位'}", ""]
            out += [f"- {f}" for f in (g.get("做法") or [])]
            out += [""]
    return "\n".join(out).rstrip()


def build_mode_card(old_text: str, company: str, source: str, date: str,
                    name: str, desc: str, practices=None, report_rel: str = "") -> str:
    """模式卡组装（程序区 / 用户区分离，2026-10-30 R3-c 用户拍板）→ 新文件全文。

    规则：
      - 卡**不存在** → 新建：frontmatter + `# {企业名} · 管理模式` + 程序区
        （`## {模式名称}` + 说明 + `## 入选做法（按条款）`）+ 用户区标记
        （内含空节 `## 复盘优化区（留空，复盘时填写）`）+ 尾部提示行；
      - 卡**已存在且有用户区标记** → 只替换标记之外的程序区内容，用户区原样保留；
      - 卡**已存在但没有标记**（如某企业现有卡）→ 首次更新时把现有正文整体视为用户区
        （用标记包起来，原文保留），程序区另写——不丢任何旧内容。
    旧正文首行若就是同名 H1（`# {企业名} · 管理模式`），不再重复输出一次
    （标题由本函数在规范位置统一给出），其余内容逐字保留。
    """
    old_text = old_text or ""
    fm_old, body = split_frontmatter(old_text)
    marked = (MODE_USER_BEGIN in body and MODE_USER_END in body)
    if marked:
        i = body.index(MODE_USER_BEGIN)
        j = body.index(MODE_USER_END)
        pre = body[:i]
        user = body[i + len(MODE_USER_BEGIN):j].strip("\n")
        post = body[j + len(MODE_USER_END):]
    else:
        pre, user, post = body, None, ""
    # H1：沿用原文的（避免同一文件两个 H1），没有则按约定生成
    mh = re.search(r"(?m)^# .+$", pre or "")
    h1 = mh.group(0).strip() if mh else f"# {company} · 管理模式"
    if not marked:
        # 旧正文整体视为用户区（原文保留）
        user = (body or "").strip("\n")
        if user.startswith(h1 + "\n"):
            user = user[len(h1) + 1:].lstrip("\n")
        post = ""
    if not (user or "").strip():
        user = MODE_USER_DEFAULT
    fm = merge_frontmatter(fm_old, {
        "类型": "模式",
        "企业名称": company,
        "来源": source,
        "提取日期": date,
        "关联报告": report_rel,
    })
    prog = _mode_program_zone(name, desc, practices)
    tail = (post or "").strip() or MODE_TAIL
    parts = ["---", "\n".join(fm).strip(), "---", "", h1, ""]
    if prog:
        parts += [prog, ""]
    parts += [MODE_USER_BEGIN, user.strip(), MODE_USER_END, "", tail, ""]
    return "\n".join(parts).rstrip() + "\n"


def build_onsite_md(company, onsite_date, review_md_text, picked, lead=False):
    """组装现场评审报告 MD（B3）。

    现场评审报告 = 文审报告全文（原样保留）+「## 现场核实信息」章节。
    - 文审报告标题「# {company} · 资料评审」改为「# {company} · 现场评审」
    - frontmatter 追加「现场日期」字段
    - lead=True（评审角色为组长）时，在 H1 之后预设一个空的「## 开场白」标题，
      具体内容由用户在现场评审前自行在 MD 里补充；基底已含开场白章节则不重复插入
      （条款更新重建时保留用户已补的内容）
    - 追加现场核实信息：每条 = 条款名 + 优势/可改进之处（文审评分表自动带入）
      + 现场核实（现场新增）+ 关联条款双链 [[条款文件stem]]

    picked = [{'条款号','条款名','目标文件','优势','可改进之处','现场核实'}]
    纯文本组装，不写文件、不联网；写入由 main.py 负责。
    """
    txt = (review_md_text or "").rstrip() + "\n"

    # 1. 标题：资料评审 → 现场评审
    txt = txt.replace(f"# {company} · 资料评审", f"# {company} · 现场评审", 1)

    # 2. frontmatter 追加「现场日期」（已有则不重复加——再次更新时基底可能已含）
    if onsite_date and txt.startswith("---"):
        end = txt.find("\n---", 3)
        if end != -1 and "现场日期:" not in txt[:end]:
            txt = txt[:end] + f"\n现场日期: {onsite_date}" + txt[end:]

    # 3. 组长项目：H1 之后预设空的「## 开场白」（内容用户后续自行补；已有则不重复插）
    if lead and not re.search(r"^## [^\n]*开场白[^\n]*$", txt, flags=re.M):
        mh = re.search(r"^# .+$", txt, flags=re.M)
        if mh:
            txt = txt[:mh.end()] + "\n\n## 开场白" + txt[mh.end():]

    # 4. 现场核实信息章节
    lines = [txt.rstrip(), "", "## 现场核实信息", ""]
    if not picked:
        lines.append("（未勾选条款）")
        lines.append("")
    for it in picked:
        no = str(it.get("条款号") or "").strip()
        name = str(it.get("条款名") or "").strip()
        lines.append(f"### {no} {name}".rstrip())
        lines.append("")
        tfile = str(it.get("目标文件") or "").strip()
        if tfile:
            lines.append(f"相关条款：[[{tfile}]]")
            lines.append("")
        adv = str(it.get("优势") or "").strip()
        if adv:
            lines.append(f"- 文审优势：{adv}")
        sug = str(it.get("可改进之处") or "").strip()
        if sug:
            lines.append(f"- 可改进之处：{sug}")
        onsite = str(it.get("现场核实") or "").strip()
        lines.append(f"- 现场核实：{onsite}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
