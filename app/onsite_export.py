# -*- coding: utf-8 -*-
"""现场评审核实内容 → Word 导出（R4，2026-10-25；2026-10-28 全量版）

范围 = 现场 MD「## 现场核实信息」节**除「### 开场白」外的全部块**——普通条款块
（数字条款号）+ 两类派生伪条目块（「报告主要优势条款·*」「报告主要建议条款·*」，
2026-10-28 起优势/可改进之处已落盘，块里有完整内容可导）；组长项目的开场白走
「## 开场白」节单独导出（### 开场白块跳过，防重复）。
每条：H2 条款号+条款名，三栏（文审优势 / 可改进之处 / 现场核实）分段；三栏值
**跨行完整捕获**（到下一个 `- ` 行为止，普通块的多行续文原样进）。纯本地生成，不出网。
"""
import re


def parse_onsite_terms(md_text):
    """现场 MD → (terms, opening)。terms = [{条款号,条款名,优势,可改进,现场核实}]"""
    txt = md_text or ""
    mo = re.search(r"(?ms)^## 开场白\s*$(.*?)(?=^## |\Z)", txt)
    opening = mo.group(1).strip() if mo else ""
    m = re.search(r"(?ms)^## 现场核实信息\s*$(.*?)(?=^## |\Z)", txt)
    if not m:
        return [], opening
    body = m.group(1)
    terms = []
    for hm in re.finditer(r"(?m)^### (.+?)\s*$(.*?)(?=^### |\Z)", body, re.S):
        no, _, name = hm.group(1).strip().partition(" ")
        if no.startswith("开场白"):
            continue                      # 开场白在 ## 节单独导出，### 块不重复导
        seg = hm.group(2)

        def grab(label):
            # 跨行捕获：到下一个 "- " 行或块尾（普通块续文/伪条目多行全文都完整进）
            mm = re.search(rf"- {label}：(.*?)(?=\n- |\Z)", seg, flags=re.S)
            return mm.group(1).strip() if mm else ""

        terms.append({"条款号": no, "条款名": name,
                      "优势": grab("文审优势") or grab("优势"), "可改进": grab("可改进之处"),
                      "现场核实": grab("现场核实")})
    return terms, opening


def build_docx(company, terms, opening=""):
    """组装导出 docx（python-docx，2026-10-25 装入 venv）"""
    from docx import Document
    d = Document()
    d.add_heading(f"{company} · 现场评审核实内容", level=1)
    if opening:
        d.add_heading("开场白", level=2)
        d.add_paragraph(opening)
    for t in terms:
        d.add_heading(f"{t['条款号']} {t['条款名']}".strip(), level=2)
        for label, key in (("文审优势", "优势"), ("可改进之处", "可改进"), ("现场核实", "现场核实")):
            p = d.add_paragraph()
            run = p.add_run(f"{label}：")
            run.bold = True
            # 多行值（普通块续文/伪条目落盘全文）按段内换行渲染，不并成一行
            segs = str(t.get(key) or "（空）").split("\n")
            for i, s in enumerate(segs):
                if i:
                    p.add_run().add_break()
                p.add_run(s)
    return d
