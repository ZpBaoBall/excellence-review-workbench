# -*- coding: utf-8 -*-
"""
项目台账：新建 / 批量导入（台账存 data/ledger.json，不存 md 卡片）
  - make_template()  生成填写用的 xlsx 模板（「下载导入表」时动态生成）
  - read_table()     读 xlsx / csv → 行字典
  - import_rows()    行 → 台账记录，写入 data/ledger.json
界面（main.py）和命令行（python importer.py 表格.xlsx）都走这里，规矩只写一份。
"""
import re
import yaml
import store
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((BASE / "config.yaml").read_text(encoding="utf-8"))
LIB = CFG["库"]["社会兼职"]
LIB_PATH = Path(LIB["路径"])
MODULES_ON = CFG.get("模块", {}).get("启用", ["政府质量奖"])

CAT_CODE = {
    "文件评审": "文审", "现场评审": "现场", "孵化": "孵化", "培训": "培训",
    "评审复盘": "复盘", "标准研讨": "研讨", "个人奖评审": "个人",
    "先进管理办法": "先进", "单项创新评价": "单项", "质量攻关": "攻关", "首席质量官": "首席",
}

# 表格列名 → frontmatter 字段
COLS = [
    ("企业名称", "企业名称", True),
    ("年份", "年份", True),
    ("市级", "区域市级", False),
    ("区/县", "区域区县", False),
    ("行业门类", "行业门类", False),
    ("行业大类", "行业大类", False),
    ("类别", "类别", True),
    ("奖项/项目", "奖项/项目", False),
    ("适用标准", "适用标准", False),
    ("阶段", "阶段", False),
    ("结论", "结论", False),
    ("得分", "得分", False),
    ("评审角色", "评审角色", False),
    ("报告日期", "报告日期", False),
    ("现场日期", "现场日期", False),
    ("备注", "备注", False),
]

def short_name(c: str) -> str:
    return re.sub(r"(股份有限公司|有限责任公司|有限公司|合作社|集团公司|集团)$", "", str(c))


def cat_code(cats) -> str:
    cats = cats if isinstance(cats, list) else ([cats] if cats else [])
    for c in cats:
        if c in CAT_CODE:
            return CAT_CODE[c]
    return "其他"


def next_id(year, cats, module=None) -> str:
    code = cat_code(cats)
    y = str(year) if year else "0000"
    mx = 0
    for d in store.load_ledger():
        m = re.match(rf"{y}-SH-{code}-(\d{{3}})", str(d.get("id", "")))
        if m:
            mx = max(mx, int(m.group(1)))
    return f"{y}-SH-{code}-{mx + 1:03d}"


def norm_row(r: dict) -> dict:
    """表格行 / 表单提交 → 标准字段"""
    d = {}
    for col, key, _req in COLS:
        v = r.get(col, r.get(key, ""))
        if isinstance(v, str):
            v = v.strip()
        d[key] = v
    return d


def build_record(r: dict, module=None) -> dict:
    d = norm_row(r)
    module = module or MODULES_ON[0]

    region = [x for x in [d.get("区域市级"), d.get("区域区县")] if x]
    industry = [x for x in [d.get("行业门类"), d.get("行业大类")] if x]
    cats = d.get("类别")
    if isinstance(cats, str):
        cats = [c.strip() for c in re.split(r"[、,，/;；]", cats) if c.strip()]
    cats = cats or ["待定"]

    year = d.get("年份")
    try:
        year = int(str(year).strip())
    except Exception:
        year = 0

    score = d.get("得分")
    try:
        score = float(str(score).strip()) if str(score).strip() else None
    except Exception:
        score = None

    pid = next_id(year if year else 0, cats)
    comp = str(d.get("企业名称") or "未命名").strip()

    rec = {
        "id": pid,
        "企业名称": comp,
        "type": "评审项目",
        "模块": module,
        "年份": year or None,
        "区域": region or None,
        "行业": industry or None,
        "类别": cats,
        "奖项/项目": d.get("奖项/项目") or None,
        "适用标准": d.get("适用标准") or None,
        "阶段": d.get("阶段") or "文审中",
        "结论": d.get("结论") or None,
        "得分": score,
        "状态": "active",
        "评审角色": d.get("评审角色") or None,
        "报告日期": d.get("报告日期") or None,
        "现场日期": d.get("现场日期") or None,
    }

    todo = []
    if not region:
        todo.append("区域")
    if not industry:
        todo.append("行业")
    if not year:
        todo.append("年份")
    if todo:
        rec["待补字段"] = todo
    return rec


def _year_of(rec) -> int:
    """记录/行的年份取整数（空/异常 → 0，与 build_record 的 0 兜底一致）"""
    try:
        return int(str(rec.get("年份") or "").strip())
    except Exception:
        return 0


def import_rows(rows, module=None):
    """行 → 台账记录，写入 data/ledger.json。

    A3 判重：键 = 企业名（去后缀归一化）+ 年份 + 奖项/项目，三者全同才算重复。
    同企业不同年份（连续两年申报）是不同项目，不误杀；库内已有或表内重复行跳过，
    并在 skipped 里报告原因，不静默丢弃。
    """
    items = store.load_ledger()
    made, skipped = [], []
    seen = set()
    for r in rows:
        comp = str(r.get("企业名称") or "").strip()
        if not comp:
            continue
        d = norm_row(r)
        award = str(d.get("奖项/项目") or "").strip()
        key = (short_name(comp), _year_of(d), award)
        if key in seen:
            skipped.append({"企业": comp, "年份": d.get("年份") or "", "奖项": award,
                            "原因": "表内重复行"})
            continue
        dup = next((x for x in items
                    if short_name(x.get("企业名称") or "") == key[0]
                    and _year_of(x) == key[1]
                    and str(x.get("奖项/项目") or "").strip() == key[2]), None)
        if dup:
            skipped.append({"企业": comp, "年份": d.get("年份") or "", "奖项": award,
                            "原因": f"库内已有卡片 {dup.get('id')}"})
            seen.add(key)
            continue
        rec = build_record(r, module)
        items.append(rec)
        made.append({"id": rec["id"], "企业": rec["企业名称"]})
        seen.add(key)
    store.save_ledger(items)
    return {"made": made, "skipped": skipped}


# ── 表格读写 ──────────────────────────────────────────────
def read_table(path: Path):
    """xlsx / csv → 行字典列表"""
    p = Path(path)
    rows = []
    if p.suffix.lower() in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(p, data_only=True)
        ws = wb[wb.sheetnames[0]]
        head = None
        for row in ws.iter_rows(values_only=True):
            if head is None:
                if row and row[0]:
                    head = [str(c).strip() if c else "" for c in row]
                continue
            if not any(row):
                continue
            rows.append({head[i]: (row[i] if i < len(row) and row[i] is not None else "")
                         for i in range(len(head))})
    else:
        import csv
        with open(p, encoding="utf-8-sig", newline="") as f:
            for i, r in enumerate(csv.DictReader(f)):
                rows.append({k: v for k, v in r.items()})
    return rows


def make_template(out: Path, dicts: dict = None, enums: dict = None):
    """生成填写模板 xlsx：Sheet1 填写区 / Sheet2 可选值 / Sheet3 说明"""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "填写区"

    headers = [c[0] for c in COLS]
    required = {c[0] for c in COLS if c[2]}
    ws.append(headers)

    hf = Font(bold=True, color="FFFFFF")
    hfill = PatternFill("solid", fgColor="2F5597")
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=1, column=i)
        c.font = hf
        c.fill = hfill
        c.alignment = Alignment(horizontal="center")
        ws.column_dimensions[c.column_letter].width = 24 if h in ("企业名称", "奖项/项目", "备注") else 14
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["N"].width = 40

    # 示例行（两行，可直接改成自己的）
    ws.append(["示例：上海XX有限公司", 2025, "上海市", "浦东新区", "制造业",
               "C34 通用设备制造业", "文件评审", "区政府质量奖", "GBT19580 卓越",
               "报告已出", "推荐", 78.5, "组员", "", "", "示例行，填完删掉"])
    ws.append(["", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""])

    # 可选值页
    ws2 = wb.create_sheet("可选值")
    ws2.append(["字段", "可选值（用顿号分隔多选）"])
    ws2.cell(row=1, column=1).font = hf
    ws2.cell(row=1, column=2).font = hf
    ws2.cell(row=1, column=1).fill = hfill
    ws2.cell(row=1, column=2).fill = hfill

    vals = {}
    if dicts:
        vals["市级"] = "、".join([r[0] for r in dicts.get("区域", []) if r and r[0]])
        vals["区/县"] = "、".join([r[1] for r in dicts.get("区域", []) if len(r) > 1 and r[1] not in ("市级",)])
        mens = [r[1] for r in dicts.get("行业", []) if len(r) > 1 and r[1]]
        dls = [f"{r[2]} {r[3]}".strip() for r in dicts.get("行业", []) if len(r) > 3 and r[2]]
        vals["行业门类"] = "、".join(sorted(set(mens)))
        vals["行业大类"] = "、".join(sorted(set(dls))[:60]) + " …（完整清单见工作台「字典」）"
        cats = [r[0] for r in dicts.get("类别", [])]
        vals["类别"] = "、".join(cats)
    if enums:
        for k in ("阶段", "结论", "评审角色", "奖项/项目", "适用标准"):
            if enums.get(k):
                vals[k] = "、".join(enums[k])
    for k, v in vals.items():
        ws2.append([k, v])
    ws2.column_dimensions["A"].width = 14
    ws2.column_dimensions["B"].width = 110

    # 说明页
    ws3 = wb.create_sheet("填写说明")
    notes = [
        ["评审工作台 · 批量导入填写说明", ""],
        ["", ""],
        ["1. 填写区", "第一行是示例，填完请整行删除；只保留你要导入的项目行"],
        ["2. 必填", "企业名称、年份、类别（其余留空的会自动标「待补」，界面里可筛出来补）"],
        ["3. 类别多选", "一次项目既文审又现场，就填「文件评审、现场评审」"],
        ["4. 区域两列", "市级填「上海市」，区/县填「浦东新区」；市级项目区/县留空"],
        ["5. 行业两列", "按 GB/T 4754：门类如「制造业」，大类如「C34 通用设备制造业」；见「可选值」页"],
        ["6. 得分", "填数字即可，不要带「分」字；没有就留空"],
        ["7. 导入方式", "工作台界面点「批量导入」上传本文件；或命令行 python importer.py 本文件.xlsx"],
        ["8. 不会覆盖", "同名企业也会新建卡片（id 递增），不会覆盖已有卡片"],
        ["", ""],
        ["生成时间", datetime.now().strftime("%Y-%m-%d %H:%M")],
    ]
    for r in notes:
        ws3.append(r)
    ws3["A1"].font = Font(bold=True, size=13)
    ws3.column_dimensions["A"].width = 16
    ws3.column_dimensions["B"].width = 90

    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return out


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        rows = read_table(Path(sys.argv[1]))
        res = import_rows(rows)
        made, skipped = res["made"], res["skipped"]
        print(f"导入 {len(made)} 张卡片，跳过 {len(skipped)} 行")
        for m in made:
            print("  ", m["id"], "|", m["企业"])
        for s in skipped:
            print("   跳过:", s["企业"], "|", s["原因"])
    else:
        p = LIB_PATH / LIB["落点"]["模板"] / "批量导入-项目台账.xlsx"
        print("生成模板:", make_template(p))
