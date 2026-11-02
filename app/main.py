# -*- coding: utf-8 -*-
"""
卓越绩效评审工作台 · Web 服务
启动后浏览器打开 http://127.0.0.1:<端口>

── 函数索引（2026-10-25 加；改代码后顺手更新）────────────────────
台账：
  _backup_file            写入前备份 + 即时轮转（A4，keep=5 见 config「安全」）
  load_projects/find_project/find_company_history/_norm_company
  api_projects(/search)   台账查询（?all=1 含停用）；api_create/api_update/api_delete
                          （api_update 内含判重、按年归位、改名联动重命名）
  api_import/api_template 表格批量导入（企业+年份+奖项判重）/ 下载导入模板
报告与提取：
  resolve_report/_obsidian_preprocess   报告路径解析 + Obsidian 语法预处理
  api_file               报告预览 HTML + 做法索引（parse_practices）+ obsidian_uri
  api_asset              报告内嵌图片
  api_extract-docx       Word 提取（docx_extract：条目切分/加粗/自检）+ 归位条款清单
  api_write-review       文审 MD 写入（review_writer：按条款分节、程序节/手写节分离、提取日志）
  api_reports/auto-link  已有报告按年归位批量关联（只补空）
  api_clause-note        条款心得 → 条款文件「## 心得」
  api_review-note        复盘沉淀四问 → 报告 MD「## 复盘沉淀」（_append_to_section）；台账「四问已答」=日期
  api_practice-confirm   复盘做法确认 → 报告 MD「## 复盘沉淀」callout + 台账「做法确认」=日期（闭环①）
                         （2026-10-30 R4：同日重复确认就地改写不追加；零条不落 callout 只置位台账）
  api_mode-card          读 40 库模式卡（复盘 tab 预填模式名/说明，2026-10-30 R3-a）
  api_mode-draft         模式草稿 → 40-质量模式库；台账「模式草稿」=日期（闭环②）
                         （2026-10-30 R3-c：程序区/用户区分离，用户批注不丢）
  _write_mode_card       模式卡写入（程序区/用户区分离 + 双关联 + 写前备份）
  _ensure_fm_line        MD frontmatter 补/改一行（30 库报告 ↔ 40 库模式卡互指，R5）
  _replace_callout       「## 复盘沉淀」节内当日 callout 就地替换（做法确认去重，R4）
现场评审（B3）：
  api_onsite-score/write-onsite/onsite-report-terms/onsite-note/opening
                         （write-onsite：终版已写后 400 关门——终版=环节终点，修正走重传终版；
                          2026-10-30 R6：产物文件名规范化为 YYYYMMDD-企业名.md，去掉「-现场评审」后缀）
  _parse_opening/_write_opening_into_md   开场白条款化（组长）
  _parse_advantage_map/_onsite_terms_with_derived
                                  主要优势/建议节 → 派生伪条目（报告主要优势/建议条款·大条款）
条款库：parse_clause_filename/api_clauses/api_clause（扫 10-条款与心得，按标准前缀过滤）
字典与枚举：parse_dicts/build_trees/api_dicts(_tree)/api_enums（config.yaml 唯一来源）
政策（存卡已废止，仅留检索任务包）：api_policy_pack/packs/download/collect，CRUD 为死代码
脱敏：api_desens_status/log/preview/rotate（出网强制过闸，审计在 data/desens-audit.log）
互链：sync_report_links（同企业报告「## 相关评审记录」双向维护）
启动：文件尾部 main（uvicorn，端口/路径均以 config.yaml 为准）
"""
import os
import re
import sys
import json
import glob
import time
import shutil
import yaml
import markdown
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, File, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import importer  # 新建 / 批量导入共用同一套台账格式
import desens   # 脱敏：出网强制过闸 + 审计 + 备份轮转
import policy    # 政策检索：任务包（P4 政策内联用）
import store     # 台账 / 字典 数据存储（内置平台，JSON）
import docx_extract  # B1 文审提取：Word 资料评审报告解析 + 23 项归位
import review_writer  # B2 文审写入：提取结果 + 归位选择 → 企业评审 MD
import onsite_export  # R4 现场核实内容 → Word 导出（python-docx）

BASE = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((BASE / "config.yaml").read_text(encoding="utf-8"))
LIB = CFG["库"]["社会兼职"]
LIB_PATH = Path(LIB["路径"])
BACKUP = Path(CFG["程序"]["备份目录"])
STATIC = Path(__file__).resolve().parent / "static"


def _backup_file(fp: Path):
    """写入前备份单个文件，并按保留份数**即时轮转**（A4：不再只等启动时那次）。

    备份失败直接抛错——备份没做成=数据保护失效，不让主流程静默继续。
    轮转内部按 mtime 缓存 config，热路径开销可忽略；同秒多文件按文件名时间戳排序，不会误删。
    """
    if CFG.get("安全", {}).get("写入前备份", True):
        BACKUP.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fp, BACKUP / f"{datetime.now():%Y%m%d-%H%M%S}-{fp.name}")
        desens.rotate_backup()


def _retry_io(fn, what=""):
    """Windows 瞬锁（杀毒/索引器，连续快写约 2/230）指数退避重试——与 store.save_ledger 同模式。
    写入失败必须可见：重试耗尽才抛错，不静默吞（报告/心得/模式 MD 都是真源）。
    2026-10-26 补：此前仅 save_ledger 有重试，其余 write_text/unlink 裸奔，
    QA 复跑时撞到过写端点 500（疑与此相关）。"""
    last = None
    for i in range(4):                        # 1 次正写 + 3 次退避（0.05/0.1/0.2s）
        try:
            return fn()
        except PermissionError as e:
            last = e
            time.sleep(0.05 * (2 ** i))
    raise last


def _unlink_retry(fp: Path, what=""):
    """删除的退避重试版：成功后清理动作，失败只警告不抛——
    主流程（写新文件/改台账）已成功，不能因清理失败把 200 变 500；残骸可人工清。"""
    try:
        _retry_io(lambda: fp.unlink(missing_ok=True), what)
    except PermissionError as e:
        print(f"[警告] {what or '删除文件'}失败（重试后仍被锁）：{fp.name} · {e}")

# 模块开关：只有 config.yaml 里 模块.启用 打开的模块才进入台账与图表
MODULES_ON = CFG.get("模块", {}).get("启用", ["政府质量奖"])
MODULES_REG = CFG.get("模块", {}).get("登记", {})

app = FastAPI(title="卓越绩效评审工作台")


def load_projects(only_enabled: bool = True):
    items = []
    for d in store.load_ledger():
        if only_enabled and d.get("模块") and d["模块"] not in MODULES_ON:
            continue
        items.append(dict(d))
    return items


def find_project(pid: str):
    """台账内定位一条项目索引，返回 (下标, 记录)。找不到返回 (None, None)。"""
    for i, d in enumerate(store.load_ledger()):
        if str(d.get("id", "")) == pid:
            return i, d
    return None, None


def _norm_company(name: str) -> str:
    """去掉公司后缀，用于同名/简称匹配（如「上海五同同步带有限公司」≈「上海五同同步带」）"""
    return re.sub(r"(股份有限公司|有限责任公司|有限公司|合作社|集团公司|集团)$",
                  "", str(name or "").strip())


def find_company_history(name: str) -> List[dict]:
    """按企业名称（含去后缀简称）在台账里找该企业的历史项目，供新建时追溯"""
    q = (name or "").strip()
    if not q:
        return []
    base = _norm_company(q)
    out = []
    for d in store.load_ledger():
        nm = str(d.get("企业名称") or "").strip()
        if not nm:
            continue
        if nm == q or _norm_company(nm) == base or q in nm or nm in q:
            out.append({"id": d.get("id"), "企业名称": nm, "年份": d.get("年份"),
                        "类别": d.get("类别"), "奖项/项目": d.get("奖项/项目"),
                        "得分": d.get("得分"), "结论": d.get("结论"), "阶段": d.get("阶段")})
    return out


@app.get("/api/projects/search")
def api_projects_search(q: str = ""):
    """新建项目时按企业名称检索历史项目（含简称匹配），便于管理与追溯"""
    return find_company_history(q)


# ── 报告源文件（「来源文件」= 台账项目指向的报告/现场记录 md）────────
REPORT_BASE = "."
REPORT_SUBDIRS = [
    "政府质量奖-资料评审库",
    "政府质量奖-现场评审库",
]
COMPANY_SUFFIX_RE = re.compile(
    r"(股份有限公司|有限责任公司|有限公司|合作社|集团公司|公司|集团|工厂|研究院|研究所)")


def _as_list(v):
    return [] if v is None else (v if isinstance(v, list) else [v])


# ── 提取结果缓存（B3 现场评审用）────────────────────────────
# 文审提取时把完整结果（评分表/澄清/汇总/意见结论）落 data/tmp/{id}-extract.json，
# 现场评审阶段读它勾选条款，不用重新上传 Word；阶段归档时自动删除。
TMP_DIR = BASE / "data" / "tmp"


def _extract_cache_path(pid: str) -> Path:
    return TMP_DIR / f"{pid}-extract.json"


def save_extract_cache(pid: str, data: dict):
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    _extract_cache_path(pid).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_extract_cache(pid: str):
    p = _extract_cache_path(pid)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def remove_extract_cache(pid: str):
    p = _extract_cache_path(pid)
    if p.exists():
        p.unlink()


def list_report_files() -> List[dict]:
    """列出可作「来源文件」的项目源文件（相对 LIB_PATH 路径 + 文件名）。
    白名单目录（政府质量奖-资料评审库/政府质量奖-现场评审库）下的 md 全收；
    其他位置只收文件名含企业后缀的，过滤掉表述库、全流程等知识类笔记。"""
    out = []
    root = LIB_PATH / REPORT_BASE
    if not root.exists():
        return out
    for dirpath, _dirnames, filenames in os.walk(root):
        rel = str(Path(dirpath).relative_to(LIB_PATH)).replace("\\", "/")
        for fn in filenames:
            if not fn.lower().endswith(".md"):
                continue
            in_whitelist = any(rel == d or rel.startswith(d + "/") for d in REPORT_SUBDIRS)
            if not in_whitelist and not COMPANY_SUFFIX_RE.search(fn):
                continue
            out.append({"路径": f"{rel}/{fn}", "文件名": fn})
    return sorted(out, key=lambda x: x["文件名"])


def resolve_report(rel_path: str) -> Path:
    """相对路径 → vault 内文件，防路径穿越"""
    p = (LIB_PATH / rel_path).resolve()
    if not str(p).startswith(str(LIB_PATH.resolve())):
        raise HTTPException(400, "路径越界")
    return p


@app.get("/api/reports")
def api_reports():
    """列报告源文件，供「来源文件」下拉选择"""
    return list_report_files()


IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico"}
_ASSET_CACHE: Dict[str, Any] = {}


def _find_vault_file(name: str, base_dir: Path):
    """按文件名在 vault 内定位（先相对源文件目录，再全库），返回相对 LIB_PATH 的 posix 路径。找不到返回 None。"""
    key = (name, str(base_dir))
    if key in _ASSET_CACHE:
        return _ASSET_CACHE[key]
    cands = [base_dir / name]
    try:
        cands += sorted(base_dir.rglob(name))
    except Exception:
        pass
    try:
        cands += sorted(LIB_PATH.rglob(name))
    except Exception:
        pass
    rel = None
    for c in cands:
        if c.is_file():
            try:
                rel = c.resolve().relative_to(LIB_PATH.resolve()).as_posix()
            except ValueError:
                continue
            break
    _ASSET_CACHE[key] = rel
    return rel


def _obsidian_preprocess(txt: str, base_dir: Path) -> str:
    """把 Obsidian 双链/嵌入语法转成 HTML，再交给 markdown 渲染。"""
    import html as _html

    # callout 标题（> [!note]- 标题）→ 加粗标题，正文仍按 blockquote 渲染
    _CALL_LABEL = {"note": "笔记", "tip": "提示", "warning": "警告", "important": "重要",
                   "info": "信息", "example": "示例", "quote": "引用", "success": "成功",
                   "danger": "危险", "abstract": "摘要", "todo": "待办", "question": "问题"}

    def repl_callout(m):
        ctype = m.group(1).lower()
        title = m.group(2).strip()
        label = _CALL_LABEL.get(ctype, ctype)
        return f"> **{title or label}**"

    txt = re.sub(r"^>\s*\[!([A-Za-z]+)\][+-]?\s*(.*)$", repl_callout, txt, flags=re.M)
    # ==高亮==
    txt = re.sub(r"==([^=\n]+)==", r"<mark>\1</mark>", txt)

    def repl_embed(m):
        inner = m.group(1).strip()
        name = inner.split("|")[0].split("#")[0].strip()
        size = inner.split("|", 1)[1].strip() if "|" in inner else ""
        if not name:
            return ""
        ext = Path(name).suffix.lower()
        if ext in IMAGE_EXT:
            rel = _find_vault_file(name, base_dir)
            if rel:
                style = f' style="width:{size}px"' if size.isdigit() else ""
                return (f'<img src="/api/asset?path={_html.escape(rel, quote=True)}" '
                        f'alt="{_html.escape(Path(name).stem, quote=True)}"{style}>')
            return f'<span class="missing-embed">图片未找到：{_html.escape(name)}</span>'
        return f'<div class="embed-note">📄 嵌入：{_html.escape(name)}</div>'

    def repl_link(m):
        inner = m.group(1).strip()
        parts = inner.split("|", 1)
        target = parts[0].split("#")[0].strip()
        alias = parts[1].strip() if len(parts) > 1 else target
        return (f'<span class="wiki-link" title="{_html.escape(target, quote=True)}">'
                f'{_html.escape(alias)}</span>')

    txt = re.sub(r"!\[\[([^\]]+)\]\]", repl_embed, txt)
    txt = re.sub(r"\[\[([^\]]+)\]\]", repl_link, txt)
    return txt


@app.get("/api/asset")
def api_asset(path: str = ""):
    """按 vault 相对路径回传图片等资源（供 ![[图片]] 嵌入预览）"""
    if not path:
        raise HTTPException(404, "缺少 path")
    p = resolve_report(path)
    if not p.exists() or not p.is_file():
        raise HTTPException(404, "资源不存在")
    return FileResponse(p)


@app.get("/api/file")
def api_file(path: str = ""):
    """读报告源文件 md → HTML（工作台内只读预览）。
    附带：做法索引（「只看做法」视图数据源）+ Obsidian 一键跳转 URI。"""
    if not path:
        raise HTTPException(400, "缺少 path")
    p = resolve_report(path)
    if not p.exists():
        raise HTTPException(404, "文件不存在")
    txt = p.read_text(encoding="utf-8")
    txt = _obsidian_preprocess(txt, p.parent)
    html = markdown.markdown(txt, extensions=["tables", "fenced_code"])
    # 「只看做法」：按条款分组的加粗片段（旧报告无则空，前端降级提示）
    practices = review_writer.parse_practices(txt)
    # Obsidian 跳转：vault 名 + 相对 vault 根的路径（config 的 vault 段）
    vault_root = Path(CFG.get("vault", {}).get("根", str(LIB_PATH)))   # vault 根来自 config(迁移后 LIB_PATH 即库根)
    try:
        rel = p.relative_to(vault_root).as_posix()
    except ValueError:
        rel = p.name
    uri = (f"obsidian://open?vault={quote(CFG.get('vault', {}).get('名称', ''))}"
           f"&file={quote(rel)}")
    return {"路径": path, "文件名": p.name, "html": html,
            "做法": practices, "obsidian_uri": uri}


class ModeDraftBody(BaseModel):
    project_id: str = ""
    模式名称: str = ""
    说明: str = ""
    做法: list = []      # [{条款, 做法:[...]}]


MODE_DIR_REL = "政府质量奖-质量模式库"


def _mode_card_path(comp: str) -> Path:
    """模式卡文件路径（40-质量模式库/{企业名}-模式.md）"""
    return LIB_PATH / MODE_DIR_REL / f"{comp}-模式.md"


def _write_mode_card(rec: dict, comp: str, name: str, desc: str,
                     practices=None, report_rel: str = "", source: str = "") -> tuple:
    """写 40-质量模式库模式卡 → (相对路径, 文件路径)。

    2026-10-30 R3-c 用户拍板：模式卡分**程序区 / 用户区**——用户区（批注、复盘优化区）
    用 `<!-- 用户区开始/结束 -->` 标记圈起来，程序只替换标记之外的程序区，
    用户手写内容原样保留（原来整文件覆盖会把批注冲掉）。写入前先备份。
    """
    fp = _mode_card_path(comp)
    fp.parent.mkdir(parents=True, exist_ok=True)
    old = fp.read_text(encoding="utf-8") if fp.exists() else ""
    if fp.exists():
        _backup_file(fp)
    src = source or f"{rec.get('id', '')} · 复盘勾选"
    txt = review_writer.build_mode_card(old, comp, src,
                                        datetime.now().strftime("%Y-%m-%d"),
                                        name, desc, practices, report_rel)
    _retry_io(lambda: fp.write_text(txt, encoding="utf-8"), "写模式卡")
    return str(fp.relative_to(LIB_PATH)).replace("\\", "/"), fp


@app.get("/api/mode-card")
def api_mode_card(project_id: str = ""):
    """读该项目的模式卡（40-质量模式库）→ 复盘 tab 预填模式名/说明。

    2026-10-30 R3-a 用户拍板：模式草稿弹窗不再以内存变量 CUR_EXTRACT 为唯一来源
    （刷新页面即丢），模式内容以 40 库模式卡为准，这里读回来预填。
    """
    idx, rec = find_project(project_id)
    if idx is None:
        raise HTTPException(404, f"未找到项目 {project_id}")
    comp = str(rec.get("企业名称") or "").strip()
    fp = _mode_card_path(comp)
    if not comp or not fp.exists():
        return {"ok": True, "存在": False, "模式名称": "", "说明": "",
                "路径": "", "文件": ""}
    info = review_writer.parse_mode_card(fp.read_text(encoding="utf-8"))
    rel = str(fp.relative_to(LIB_PATH)).replace("\\", "/")
    return {"ok": True, "存在": True, "路径": rel, "文件": fp.name, **info}


@app.post("/api/mode-draft")
def api_mode_draft(body: ModeDraftBody):
    """复盘 → 模式草稿（R5，2026-10-25）：勾选做法 + 模式名称/说明 → 写 40-质量模式库。
    模式通常不涉及条款（用户定）；入选做法按条款分组留痕，供 Obsidian 精修。
    台账「模式草稿」=今天（2026-10-28 用户定：复盘四步闭环②的信号源，覆盖式——
    再生成即「更新模式草稿」，日期跟着刷新）。
    2026-10-30 R3-c 用户拍板：不再整文件覆盖——用户区（批注、复盘优化区）用标记
    圈起来原样保留，程序只重写程序区；模式名/说明为空时不写空的 `## ` 节。"""
    idx, rec = find_project(body.project_id)
    if idx is None:
        raise HTTPException(404, f"未找到项目 {body.project_id}")
    name = (body.模式名称 or "").strip()
    desc = (body.说明 or "").strip()
    comp = str(rec.get("企业名称") or "").strip()
    # 双关联（R5）：模式卡 frontmatter 指向本项目的 30 库现场报告
    report_rel = _find_onsite_report(rec) or ""
    rel, fp = _write_mode_card(rec, comp, name, desc, body.做法 or [], report_rel)
    # 台账闭环②信号：模式草稿已生成（覆盖式，再生成即更新日期）
    _backup_file(store.ledger_file())
    items = store.load_ledger()
    items[idx]["模式草稿"] = datetime.now().strftime("%Y-%m-%d")
    store.save_ledger(items)
    return {"ok": True, "路径": rel, "文件": fp.name}


@app.get("/api/export-onsite-docx")
def api_export_onsite_docx(project_id: str = ""):
    """现场评审核实内容导出 Word（R4，2026-10-25）。
    范围 = 现场 MD「现场核实信息」节全部条款（= 写入时勾选的「我负责的条款」）；
    每条三栏：文审优势/可改进之处/现场核实；组长含开场白。纯本地，不出网。"""
    idx, rec = find_project(project_id)
    if idx is None:
        raise HTTPException(404, f"未找到项目 {project_id}")
    rel = _find_onsite_report(rec)
    if not rel:
        raise HTTPException(400, "未找到现场评审报告")
    fp = resolve_report(rel)
    if not fp.exists():
        raise HTTPException(404, f"报告文件不存在：{rel}")
    terms, opening = onsite_export.parse_onsite_terms(fp.read_text(encoding="utf-8"))
    if not terms:
        raise HTTPException(400, "现场报告里没有「现场核实信息」节（无可导出条款）")
    comp = str(rec.get("企业名称") or "").strip()
    doc = onsite_export.build_docx(comp, terms, opening)
    out = BASE / "data" / "tmp" / f"现场核实-{comp}-{datetime.now():%Y%m%d-%H%M%S}.docx"
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    return FileResponse(str(out), filename=out.name)


OPENING_REL = "10-组织类19580/50-评审实务/现场评审开场白.md"


@app.get("/api/opening")
def api_opening():
    """现场评审开场白（组长进场用）。固定标准话术，纯本地读取、不脱敏、不出网。"""
    fp = LIB_PATH / OPENING_REL
    if not fp.exists():
        for c in LIB_PATH.rglob("现场评审开场白.md"):
            if c.is_file():
                fp = c
                break
    if not fp.exists():
        return {"ok": False, "提示": "未找到现场评审开场白：10-组织类19580/50-评审实务/现场评审开场白.md"}
    txt = fp.read_text(encoding="utf-8")
    body = re.sub(r"^---\s*\n.*?\n---\s*\n", "", txt, count=1, flags=re.S)
    body = _obsidian_preprocess(body, fp.parent)
    html = markdown.markdown(body, extensions=["tables", "fenced_code"])
    return {"ok": True, "路径": str(fp.relative_to(LIB_PATH)).replace("\\", "/"),
            "文件名": fp.name, "html": html, "文本": body}


# ── 标准条款库（笔记/Exp）─────────────────
CLAUSE_DIR = "笔记/Exp"


def parse_clause_filename(fn: str):
    """条款文件名 → {编号, 缩写, 条款号, 条款名, 标准}。
    命名：{去斜杠编号}-{缩写}-{条款号}{条款名}.md，如 GBT19580-卓越-4.4.2人力资源.md"""
    stem = fn[:-3] if fn.lower().endswith(".md") else fn
    parts = stem.split("-")
    if len(parts) < 3:
        return None
    code, abbr = parts[0], parts[1]
    m = re.match(r"^(\d+(?:\.\d+)*)(.*)$", "-".join(parts[2:]))
    if not m:
        return None
    return {"编号": code, "缩写": abbr, "条款号": m.group(1), "条款名": m.group(2),
            "标准": f"{code} {abbr}"}


def parse_frontmatter(fp: Path) -> dict:
    txt = fp.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", txt, re.S)
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except Exception:
        return {}


def _clause_sortkey(x):
    return [int(p) for p in str(x.get("条款号", "")).split(".") if p.isdigit()]


@app.get("/api/clauses")
def api_clauses(std: str = ""):
    """扫条款库，解析文件名 + frontmatter，按「适用标准」过滤（条款号自带层级，前端据此下钻）"""
    d = LIB_PATH / CLAUSE_DIR
    out = []
    if not d.exists():
        return out
    want = (std or "").strip()
    for f in sorted(d.glob("*.md")):
        info = parse_clause_filename(f.name)
        if not info:
            continue
        try:
            fm = parse_frontmatter(f)
        except Exception:
            fm = {}
        item = {
            "标准": str(fm.get("标准") or info["标准"]),
            "条款号": str(fm.get("条款号") or info["条款号"]),
            "条款名": str(fm.get("条款名") or info["条款名"]),
            "对应条款": str(fm.get("对应条款") or ""),
            "文件": str(f.relative_to(LIB_PATH)).replace("\\", "/"),
        }
        if want and item["标准"] != want:
            continue
        out.append(item)
    out.sort(key=_clause_sortkey)
    return out


@app.get("/api/clause")
def api_clause(path: str = ""):
    """读条款文件（剥离 frontmatter，只渲染正文：原文 + 心得）"""
    if not path:
        raise HTTPException(400, "缺少 path")
    fp = resolve_report(path)
    if not fp.exists():
        raise HTTPException(404, "条款文件不存在")
    txt = fp.read_text(encoding="utf-8")
    fm = parse_frontmatter(fp)
    body = re.sub(r"^---\s*\n.*?\n---\s*\n", "", txt, count=1, flags=re.S)
    body = _obsidian_preprocess(body, fp.parent)
    html = markdown.markdown(body, extensions=["tables", "fenced_code"])
    return {"文件": path, "文件名": fp.name, "html": html,
            "标准": fm.get("标准"), "条款号": str(fm.get("条款号") or ""),
            "条款名": fm.get("条款名"), "对应条款": str(fm.get("对应条款") or "")}


class NoteBody(BaseModel):
    path: str = ""
    note: str = ""


def _append_to_section(txt: str, section_title: str, block: str) -> str:
    """把 block 追加到 `## section_title` 节末尾；无此节则新建——
    新建时插在「## 相关评审记录」**之前**（该节由 sync_report_links 维护且位于文尾，
    插它后面会被互链刷新当尾段删掉）。"""
    marker = f"## {section_title}"
    if marker in txt:
        i = txt.index(marker)
        rest = txt[i:]
        nxt = rest.find("\n## ", len(marker))
        head, body = txt[:i], (rest[:nxt] if nxt != -1 else rest)
        tail = rest[nxt + 1:] if nxt != -1 else ""
        return (head + body.rstrip() + "\n\n" + block.rstrip() + "\n" + tail).rstrip() + "\n"
    links = "## 相关评审记录"
    if links in txt:
        i = txt.index(links)
        return txt[:i].rstrip() + f"\n\n{marker}\n\n{block.rstrip()}\n\n" + txt[i:]
    return txt.rstrip() + f"\n\n{marker}\n\n{block.rstrip()}\n"


def _ensure_fm_line(md_text: str, key: str, value: str) -> str:
    """在 MD 的 frontmatter 里补/改一行「key: value」（已有则就地改写，不重复加）。

    2026-10-30 R5 用户拍板：30 库现场报告 ↔ 40 库模式卡双关联，frontmatter 互指
    （主理人已手工为锦持/五同做过这两条，代码要能自动保持）。
    """
    if not value or not (md_text or "").lstrip().startswith("---"):
        return md_text
    fm, body = review_writer.split_frontmatter(md_text)
    lines = review_writer.merge_frontmatter(fm, {key: value})
    return "---\n" + "\n".join(lines).strip() + "\n---\n" + body


def _replace_callout(txt: str, section_title: str, title_prefix: str, new_block: str):
    """把「## section_title」节内首条以 title_prefix 开头的 callout 块**就地替换**。

    2026-10-30 R4 用户拍板：同日重复确认不再追加第二条 callout（用户连点 6 次
    留下 6 条「做法确认（0 条）」空 callout）——定位到当日那块就地改写。
    callout 块 = 起始行 + 其后连续的 `>` 引用行（含空 `>` 行）。
    找不到该块返回 None（调用方改为追加）。
    """
    marker = f"## {section_title}"
    i = txt.find(marker)
    if i == -1:
        return None
    rest = txt[i + len(marker):]
    nxt = rest.find("\n## ")
    sec = rest[:nxt] if nxt != -1 else rest
    lines = sec.split("\n")
    for k, ln in enumerate(lines):
        if not ln.startswith(title_prefix):
            continue
        j = k
        while j + 1 < len(lines) and lines[j + 1].startswith(">"):
            j += 1
        block = new_block.rstrip("\n").split("\n")
        new_sec = "\n".join(lines[:k] + block + lines[j + 1:])
        tail = rest[nxt:] if nxt != -1 else ""
        return txt[:i + len(marker)] + new_sec + tail
    return None


class ReviewNoteBody(BaseModel):
    project_id: str = ""
    note: str = ""


@app.post("/api/review-note")
def api_review_note(body: ReviewNoteBody):
    """复盘沉淀：写 callout（> [!note]- 日期 复盘沉淀）到项目报告 MD 的「## 复盘沉淀」节。
    手写节——程序永不覆盖（merge_sections 只动程序节）；四问内容由前端组织成文传入。
    台账「四问已答」=今天（2026-10-28 用户定：复盘四步闭环③的信号源，覆盖式——
    补写即刷新；旧「写复盘沉淀」表单与本接口同体，同样置位）。"""
    note = (body.note or "").strip()
    if not note:
        raise HTTPException(400, "复盘内容为空")
    idx, rec = find_project(body.project_id)
    if idx is None:
        raise HTTPException(404, f"未找到项目 {body.project_id}")
    srcs = _as_list(rec.get("来源文件"))
    if not srcs:
        raise HTTPException(400, "该项目还没有关联报告 MD，无法写复盘沉淀")
    fp = resolve_report(srcs[0])
    if not fp.exists():
        raise HTTPException(404, f"报告文件不存在：{srcs[0]}")
    txt = fp.read_text(encoding="utf-8")
    _backup_file(fp)
    date = datetime.now().strftime("%Y-%m-%d")
    # callout 多行：Obsidian 引用块每行都要 > 前缀，空行给 >
    quoted = "\n".join(f"> {ln}" if ln.strip() else ">" for ln in note.split("\n"))
    callout = f"> [!note]- {date} 复盘沉淀\n{quoted}\n"
    _retry_io(lambda: fp.write_text(_append_to_section(txt, "复盘沉淀", callout), encoding="utf-8"), "写复盘沉淀")
    # 台账闭环③信号：四问已答（覆盖式，补写即刷新日期）
    _backup_file(store.ledger_file())
    items = store.load_ledger()
    items[idx]["四问已答"] = date
    store.save_ledger(items)
    return {"ok": True, "文件": fp.name}


class PracticeConfirmBody(BaseModel):
    project_id: str = ""
    做法: list = []      # [{条款, 做法:[...]}]（与模式草稿的 picked 同构）


@app.post("/api/practice-confirm")
def api_practice_confirm(body: PracticeConfirmBody):
    """复盘·做法确认（2026-10-28 用户定，四步闭环①）：勾选的做法落痕到报告 MD
    「## 复盘沉淀」节（callout，Obsidian 可见可搜），台账「做法确认」=今天。
    2026-10-30 R4 用户拍板（两条）：
      · **同日重复确认不重复追加**——先定位当日那块 callout 就地改写（_replace_callout），
        没有才追加（用户连点 6 次，节里留下 6 条「做法确认（0 条）」空记录，根因在此）；
      · **零勾选不写 callout**——保持「## 复盘沉淀」节干净，但台账「做法确认」照常
        置位（闭环信号不能缺，否则归档门禁永远卡住）；回执带「未落痕」=true 以示区别。
    基于终版内容确认：终版未写入时前端按钮置灰，后端不另设卡口（写进的是手写节，无破坏性）。"""
    idx, rec = find_project(body.project_id)
    if idx is None:
        raise HTTPException(404, f"未找到项目 {body.project_id}")
    srcs = _as_list(rec.get("来源文件"))
    if not srcs:
        raise HTTPException(400, "该项目还没有关联报告 MD，无法做法确认")
    fp = resolve_report(srcs[0])
    if not fp.exists():
        raise HTTPException(404, f"报告文件不存在：{srcs[0]}")
    groups = []
    for g in (body.做法 or []):
        items_ = [str(f).strip() for f in (g.get("做法") or []) if str(f or "").strip()]
        if items_:
            groups.append({"条款": str(g.get("条款") or "未归位").strip(), "做法": items_})
    n = sum(len(g["做法"]) for g in groups)
    date = datetime.now().strftime("%Y-%m-%d")
    if n == 0:
        # 零条：不落空 callout（2026-10-30 R4 用户拍板），只置位台账闭环信号
        _backup_file(store.ledger_file())
        items = store.load_ledger()
        items[idx]["做法确认"] = date
        store.save_ledger(items)
        return {"ok": True, "文件": fp.name, "条数": 0, "未落痕": True}
    lines = [f"> [!note]- {date} 做法确认（{n} 条）"]
    for g in groups:
        lines.append(">")
        lines.append(f"> **{g['条款']}**")
        lines += [f"> - {f}" for f in g["做法"]]
    callout = "\n".join(lines) + "\n"
    txt = fp.read_text(encoding="utf-8")
    # 同日重复确认 → 就地改写当日那块（不再一条条追加）
    new_txt = _replace_callout(txt, "复盘沉淀", f"> [!note]- {date} 做法确认", callout)
    if new_txt is None:
        new_txt = _append_to_section(txt, "复盘沉淀", callout)
    _backup_file(fp)
    _retry_io(lambda: fp.write_text(new_txt, encoding="utf-8"), "写做法确认")
    # 台账闭环①信号：做法已确认（覆盖式，再次确认即刷新日期）
    _backup_file(store.ledger_file())
    items = store.load_ledger()
    items[idx]["做法确认"] = date
    store.save_ledger(items)
    return {"ok": True, "文件": fp.name, "条数": n, "未落痕": False}


@app.post("/api/clause-note")
def api_clause_note(body: NoteBody):
    """追加心得：写 callout（> [!note]- 日期 复盘）到条款文件「## 心得」区，不改原文"""
    note = (body.note or "").strip()
    if not note:
        raise HTTPException(400, "心得内容为空")
    fp = resolve_report(body.path)
    if not fp.exists():
        raise HTTPException(404, "条款文件不存在")
    txt = fp.read_text(encoding="utf-8")
    if "## 心得" not in txt:
        txt = txt.rstrip() + "\n\n## 心得\n"
    _backup_file(fp)
    date = datetime.now().strftime("%Y-%m-%d")
    idx = txt.index("## 心得")
    head = txt[:idx]
    rest = txt[idx:].replace("（复盘时追加）", "").rstrip()
    callout = f"> [!note]- {date} 复盘\n> {note}\n"
    _retry_io(lambda: fp.write_text(head + rest + "\n\n" + callout + "\n", encoding="utf-8"), "写条款心得")
    return {"ok": True, "文件": body.path, "日期": date}


@app.post("/api/extract-docx")
async def api_extract_docx(file: UploadFile = File(...)):
    """B1 文审提取：上传 Word 评审报告，解析四段结构 + 提取评分表 23 项 + 按映射归位 15 子条款"""
    tmp = BASE / "data" / "tmp" / f"extract-{datetime.now():%Y%m%d-%H%M%S}.docx"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(await file.read())
    try:
        r = docx_extract.extract_report(tmp)
    except Exception as e:
        raise HTTPException(400, f"Word 解析失败：{e}")
    finally:
        # 读完即删；失败只警告不抛——解析已成功，不能因清理失败把 200 变 400
        _unlink_retry(tmp, "删 Word 临时文件")
    mapping = CFG.get("标准库", {}).get("评分项映射表", {})
    r["归位"] = docx_extract.map_score_items(r.get("评分表", []), mapping)
    # 15 个过程子条款（供前端归位单选下拉），按条款号排序
    r["子条款"] = [{"条款号": k, "条款名": v}
                   for k, v in sorted(review_writer.load_clauses(LIB_PATH).items(),
                                      key=lambda kv: [int(p) for p in kv[0].split(".") if p.isdigit()])]
    # 12 个归位条款（优势/建议回填条款号用，config「条款归位.清单」）
    r["归位条款"] = CFG.get("条款归位", {}).get("清单", [])
    return r


class WriteReviewBody(BaseModel):
    id: str = ""
    企业名称: str = ""
    意见结论: dict = {}
    总计: dict = {}
    报告日期: str = ""  # 前端直补的日期（台账缺失时由用户填入）
    评分表: list = []   # B3：文审提取时一并传入，落缓存供现场评审勾选
    澄清: list = []
    汇总: list = []
    推荐: str = ""
    来源文件名: str = ""  # 提取自检/提取日志用（Word 不留存，只记名）
    目标: str = ""        # "现场" = 组长复盘终版写 政府质量奖-现场评审库；空=文审（政府质量奖-资料评审库）
    模式: list = []       # 提取识别的质量模式段（→ MD「## 质量模式」节）
    灵魂考问: str = ""    # 复盘四问答文本（→ 「## 复盘沉淀」节 callout）


class PasteBody(BaseModel):
    text: str = ""
    project_id: str = ""


@app.post("/api/paste-extract")
def api_paste_extract(body: PasteBody):
    """组员复盘粘贴入口（2026-10-25）：纯文本按约定格式切分，结构同 Word 提取。
    约定见《00-政府质量奖-标注约定》：节标题独占一行；序号标题句（（一）/1.）+正文；
    **星号**=方法。"""
    if not (body.text or "").strip():
        raise HTTPException(400, "粘贴内容为空")
    opinion = docx_extract.split_pasted(body.text)
    self_check = opinion.get("自检") or {"覆盖": "—"}
    modes = docx_extract._extract_modes(opinion)
    opinion.pop("自检", None)
    return {"意见结论": opinion, "模式": modes, "自检": self_check,
            "归位条款": CFG.get("条款归位", {}).get("清单", [])}


@app.post("/api/write-review")
def api_write_review(body: WriteReviewBody):
    """B2 文审写入：组装报告 MD（基本情况/主要优势/主要改进建议）→ 写 政府质量奖-资料评审库 → 回填台账。
    目标=现场（组长复盘终版，2026-10-27 用户定）：写 政府质量奖-现场评审库——**在已有现场报告上
    更新（不是新建）**，旧「现场核实信息」折叠归档到文尾（merge_onsite_final）；写入成功后
    来源文件里的文审报告（20 库）物理删除（报告归口唯一化：先备份再删）。评分项、澄清不写。
    台账另回填「终版已写」=本次写入日期（2026-10-28 用户定：复盘门禁信号源，仅本分支置位；
    阶段一 /api/write-onsite 不置——复盘在终版写入前保持灰）。
    2026-10-30 R5 用户拍板：目标=现场时**不再把 `## 质量模式` 节写进 30 库报告**
    （modes 不传 build_md）——模式只存在于 40-质量模式库的模式卡；报告 frontmatter
    补一行「关联模式」指向模式卡（双关联）；body.模式 非空时顺手把模式内容写进模式卡
    （2026-10-30 R3-a：模式自动带入，复盘 tab 从模式卡读回预填，不依赖内存）。"""
    idx, rec = find_project(body.id)
    if idx is None:
        raise HTTPException(404, f"未找到项目 {body.id}")

    # 企业名以台账为准（项目身份）；Word/粘贴里识别到的名字仅兜底
    # （2026-10-25 修复：曾因优先用提取名把别家报告写进本项目文件）
    comp = str(rec.get("企业名称") or "").strip() or (body.企业名称 or "").strip()
    std = str(rec.get("适用标准") or "").strip() or "GBT19580 卓越"
    # 日期：优先前端直补，其次台账已有值
    date = (body.报告日期 or "").strip() or str(rec.get("报告日期") or "").strip()
    if not date:
        raise HTTPException(400, "台账缺少「报告日期」，无法命名文件")

    clause_names = {str(c.get("号")): str(c.get("名") or "")
                    for c in (CFG.get("条款归位", {}).get("清单", []) or [])}
    # 目标库：默认文审 20 库；「现场」= 组长复盘终版写 30 库（2026-10-25）
    to_onsite = (body.目标 or "").strip() == "现场"
    if to_onsite:
        date = (body.报告日期 or "").strip() or str(rec.get("现场日期") or "").strip()
        if not date:
            raise HTTPException(400, "台账缺少「现场日期」，无法命名现场报告文件")
    # 质量模式归 40 库模式卡（R5）：现场终版 MD 不传 modes，故不生成「## 质量模式」节；
    # 文审分支（20 库）行为不变，仍保留该节
    prog_md = review_writer.build_md(comp, date, std, body.意见结论, clause_names,
                                     modes=[] if to_onsite else (body.模式 or []),
                                     doc_title="现场评审" if to_onsite else "资料评审")

    out_dir = LIB_PATH / ("政府质量奖-现场评审库" if to_onsite else "政府质量奖-资料评审库")
    out_dir.mkdir(parents=True, exist_ok=True)
    # 终版 = 在已有现场报告上更新（不是新建）：通配发现 30 库已有文件（容忍
    # 「-现场评审」等任意后缀，见 _find_onsite_report_file）；无则按约定名新建
    old_fp = _find_onsite_report_file(rec) if to_onsite else None
    if old_fp is not None:
        fp, fname = old_fp, old_fp.name
    else:
        fname = normalize_filename(comp, date, ".md")
        fp = out_dir / fname
    # 折叠块日期：旧现场 MD 文件名日期（^(\d{8})- → yyyy-mm-dd），缺省今天
    fold_date = datetime.now().strftime("%Y-%m-%d")
    mfold = re.match(r"^(\d{4})(\d{2})(\d{2})-", fp.name)
    if mfold:
        fold_date = f"{mfold.group(1)}-{mfold.group(2)}-{mfold.group(3)}"

    _backup_file(store.ledger_file())
    if fp.exists():
        _backup_file(fp)

    # 程序节/手写节分离：重跑提取只覆盖程序节，手写节（复盘沉淀等）原样保留；
    # 现场终版另把旧「现场核实信息」折叠归档到文尾（merge_onsite_final）
    n_adv = len(docx_extract.as_entries((body.意见结论 or {}).get("主要优势")))
    n_sug = len(docx_extract.as_entries((body.意见结论 or {}).get("主要改进建议")))
    log_line = (f"{datetime.now():%Y-%m-%d %H:%M} 提取自 "
                f"{(body.来源文件名 or '（未记录）').strip()}：优势 {n_adv} 条 / 建议 {n_sug} 条")
    old_md = fp.read_text(encoding="utf-8") if fp.exists() else ""
    if to_onsite:
        md = review_writer.merge_onsite_final(old_md, prog_md, log_line, fold_date)
    else:
        md = review_writer.merge_sections(old_md, prog_md, log_line)
    # 灵魂考问（复盘四问答）→ 复盘沉淀节 callout（手写节，程序永不覆盖）
    soul = (body.灵魂考问 or "").strip()
    if soul:
        quoted = "\n".join(f"> {ln}" if ln.strip() else ">" for ln in soul.split("\n"))
        callout = f"> [!note]- {datetime.now():%Y-%m-%d} 复盘 · 灵魂考问\n{quoted}\n"
        md = _append_to_section(md, "复盘沉淀", callout)
    # 双关联（R5）：现场报告 frontmatter 指向 40 库模式卡（已有则不重复加）
    if to_onsite:
        md = _ensure_fm_line(md, "关联模式", f"{MODE_DIR_REL}/{comp}-模式.md")

    _retry_io(lambda: fp.write_text(md, encoding="utf-8"), "写报告 MD")

    # 回填台账
    items = store.load_ledger()
    rel = str(fp.relative_to(LIB_PATH)).replace("\\", "/")
    srcs = _as_list(items[idx].get("来源文件"))
    removed = []
    if to_onsite:
        # 报告归口唯一化（2026-10-27 用户定）：一个企业的报告要么文审要么现场——
        # 终版写入成功后，来源文件里的文审报告（20 库）物理删除（先备份），
        # 来源文件只留现场 rel（含清掉重复的 30 库条目——如不带后缀的旧约定名文件）
        for r in list(srcs):
            if "政府质量奖-资料评审库" in str(r) or "20-资料评审库" in str(r):
                old_rp = resolve_report(str(r))
                if old_rp.exists():
                    _backup_file(old_rp)
                    _unlink_retry(old_rp, "删被终版取代的文审报告")
                removed.append(str(r))
        srcs = [r for r in srcs if str(r) == rel]
    if rel not in srcs:
        srcs.append(rel)
    items[idx]["来源文件"] = srcs
    # 前端直补的报告日期，台账缺失时回填
    if body.报告日期 and not items[idx].get("报告日期"):
        items[idx]["报告日期"] = body.报告日期
    # 现场日期回写（2026-10-28 用户定：写入弹窗里的现场日期确认写入后代入卡片字段，
    # 不再去「编辑」里重复输入）——以最近一次现场写入为准（覆盖式）；文审路径不动
    if to_onsite and date:
        items[idx]["现场日期"] = date
        # 终版已写（2026-10-28 用户定：复盘门禁信号源=终版写入，而非阶段一）：
        # 仅本分支（write-review 目标=现场，即「上传现场评审终版 Word→文字提取→归位→写入」）
        # 置位，值=本次写入日期（覆盖式）；/api/write-onsite（阶段一：条款核实与信息导出）
        # 绝不设置——复盘在其后保持灰，直到终版写入才开（前端门禁 canReview 读此字段）
        items[idx]["终版已写"] = date
        # 类别自动归位(同上):终版写入后类别变为 现场评审
        items[idx]["类别"] = ["现场评审"]
    score = str((body.总计 or {}).get("得分", "") or "").strip()
    if score:
        try:
            items[idx]["得分"] = float(score)
        except Exception:
            items[idx]["得分"] = score
    # 评审结论含「现场」（同意进入现场评审）→ 阶段推进到「现场中」
    conclusion = str((body.意见结论 or {}).get("评审结论", "") or "").strip()
    if "现场" in conclusion:
        items[idx]["阶段"] = "现场中"
    if not items[idx].get("适用标准"):
        items[idx]["适用标准"] = std
    # 模式自动带入 40 库模式卡（2026-10-30 R3-a 用户拍板：终版写入即把质量模式段
    # 写进模式卡，复盘 tab 的「② 模式草稿」从模式卡读回预填，不再依赖内存变量
    # CUR_EXTRACT——刷新/切卡即丢）。程序区/用户区分离，用户批注不丢（R3-c）。
    if to_onsite and body.模式:
        mraw = str((body.模式 or [{}])[0].get("文本") or "")
        mname, mdesc = review_writer.split_mode_text(mraw)
        if mname or mdesc:
            _write_mode_card(rec, comp, mname, mdesc, [], rel,
                             source=f"{body.id} · 终版自动带入")
            # 台账闭环②信号：模式草稿（覆盖式，再生成即刷新日期）
            items[idx]["模式草稿"] = datetime.now().strftime("%Y-%m-%d")
    store.save_ledger(items)

    # B3：评分表/澄清非空时，把完整提取结果落缓存，供现场评审阶段勾选条款用
    if body.评分表 or body.澄清:
        save_extract_cache(body.id, {
            "企业名称": comp, "标准": std, "报告日期": date,
            "评分表": body.评分表, "澄清": body.澄清,
            "汇总": body.汇总, "总计": body.总计, "推荐": body.推荐,
            "意见结论": body.意见结论,
        })

    try:
        sync_report_links(body.id)
    except Exception:
        pass

    return {"ok": True, "文件": fname, "路径": rel, "得分": score, "已删除文审": removed}


# ── B3 现场评审 ───────────────────────────────────────────
class OnsitePick(BaseModel):
    条款号: str = ""      # 评分项号（展示）
    条款名: str = ""      # 评分表条款名（展示）
    目标文件: str = ""    # 关联条款文件 stem（双链 [[...]]，可为空）
    优势: str = ""
    可改进之处: str = ""
    现场核实: str = ""


class WriteOnsiteBody(BaseModel):
    id: str = ""
    企业名称: str = ""
    现场日期: str = ""
    结论: str = ""
    勾选条款: List[OnsitePick] = []


def _aggregate_terms(direct, autoed):
    """把「直接对应/自动归」的目标条款按条款号去重聚合。

    返回 [{'条款号','条款名','文件','路径','条目':[{'评分项','优势','可改进之处'}]}]
    供现场评审分屏窗体：左栏列条款、右栏显示该条款的提取内容。
    """
    terms = {}

    def _term(no, name, tfile, tpath):
        return terms.setdefault(no, {"条款号": no, "条款名": name,
                                     "文件": tfile, "路径": tpath, "条目": []})

    for d in direct:
        t = _term(d["目标条款号"], d["目标条款名"], d["目标文件"], d["路径"])
        t["条目"].append({"评分项": d.get("评分项"), "优势": d.get("优势"),
                          "可改进之处": d.get("可改进之处")})
    for d in autoed:
        for tg in d["目标"]:
            t = _term(tg["条款号"], tg["条款名"], tg["文件"], tg["路径"])
            t["条目"].append({"评分项": d.get("评分项"), "优势": d.get("优势"),
                              "可改进之处": d.get("可改进之处")})
    term_list = list(terms.values())
    term_list.sort(key=lambda x: [int(p) for p in x["条款号"].split(".") if p.isdigit()])
    return term_list


@app.get("/api/onsite-score")
def api_onsite_score(project_id: str = ""):
    """现场评审：读缓存评分表，按 config 映射归位，返回可勾选结构（含目标条款文件双链）。"""
    idx, rec = find_project(project_id)
    if idx is None:
        raise HTTPException(404, f"未找到项目 {project_id}")
    cache = load_extract_cache(project_id)
    if not cache or not cache.get("评分表"):
        return {"ok": False, "提示": "暂无评分表缓存。请先在「提取Word」上传 Word 提取并写入文审报告，评分表会自动缓存，供现场评审勾选。"}
    std = str(rec.get("适用标准") or cache.get("标准") or "GBT19580 卓越").strip()
    # 条款库：条款号 → {条款名, 文件stem, 路径}（stem 供双链，路径供前端侧栏查阅）
    clause_map = {}
    for c in api_clauses(std):
        clause_map[str(c["条款号"])] = {"条款名": str(c["条款名"]),
                                        "文件": Path(c["文件"]).stem, "路径": str(c["文件"])}
    mapping = (CFG.get("标准库", {}) or {}).get("评分项映射表", {}) or {}
    mapped = docx_extract.map_score_items(cache["评分表"], mapping)

    def _attach(it):
        return {"评分项": it.get("评分项"), "条款名": it.get("条款名"),
                "分值": it.get("分值"), "优势": it.get("优势"),
                "可改进之处": it.get("可改进之处"), "类目": it.get("类目")}

    direct = []
    for it in mapped.get("直接对应", []):
        no = str(it.get("评分项") or "")
        t = clause_map.get(no)
        d = _attach(it)
        d["目标条款号"] = no
        d["目标条款名"] = t["条款名"] if t else it.get("条款名", "")
        d["目标文件"] = t["文件"] if t else ""
        d["路径"] = t["路径"] if t else ""
        direct.append(d)

    autoed = []
    for it in mapped.get("自动归", []):
        d = _attach(it)
        targets = []
        for no in _as_list(it.get("归到")):
            no = str(no)
            t = clause_map.get(no)
            targets.append({"条款号": no, "条款名": t["条款名"] if t else "",
                            "文件": t["文件"] if t else "", "路径": t["路径"] if t else ""})
        d["目标"] = targets
        autoed.append(d)

    popup = [_attach(it) for it in mapped.get("弹窗判断", [])]

    clause_list = [{"条款号": k, "条款名": v["条款名"], "文件": v["文件"], "路径": v["路径"]}
                   for k, v in clause_map.items()]
    clause_list.sort(key=lambda x: [int(p) for p in x["条款号"].split(".") if p.isdigit()])

    term_list = _aggregate_terms(direct, autoed)

    return {"ok": True, "标准": std, "条款库": clause_list,
            "直接对应": direct, "自动归": autoed, "弹窗判断": popup,
            "条款": term_list,
            "勾选条款": _as_list(cache.get("勾选条款")),
            "现场核实": cache.get("现场核实") or {}}


@app.post("/api/write-onsite")
def api_write_onsite(body: WriteOnsiteBody):
    """B3 现场写入：文审报告全文保留 + 现场核实信息 → 写 政府质量奖-现场评审库 → 台账回填。
    阶段不自动推进（现场结束要复盘，归档由用户手动改）。
    门禁（2026-10-28 用户定）：终版已写后本接口 400 关门——write-onsite 重建会截掉
    「现场核实信息」之后的提取日志/折叠归档块，有破坏性；终版后的修正统一走
    「重新上传终版 Word → 提取并写入终版」（write-review 目标=现场，在原文件上更新）。"""
    idx, rec = find_project(body.id)
    if idx is None:
        raise HTTPException(404, f"未找到项目 {body.id}")
    if str(rec.get("终版已写") or "").strip():
        raise HTTPException(400, f"终版已写入（{rec['终版已写']}），现场评审环节已关闭；"
                                 f"如需修正请重新上传终版 Word 走「提取并写入终版」")

    comp = (body.企业名称 or "").strip() or str(rec.get("企业名称") or "").strip()
    # 基底：优先文审报告（首次迁移）；文审已删（再次更新）则用现有现场报告截取「现场核实信息」之前的部分
    review_rel = None
    for rel in _as_list(rec.get("来源文件")):
        if "政府质量奖-资料评审库" in str(rel):
            review_rel = str(rel)
            break
    onsite_rel0 = _find_onsite_report(rec)
    if review_rel:
        review_fp = resolve_report(review_rel)
        if not review_fp.exists():
            raise HTTPException(404, f"文审报告文件不存在：{review_rel}")
        review_txt = review_fp.read_text(encoding="utf-8")
    elif onsite_rel0:
        ofp0 = resolve_report(onsite_rel0)
        if not ofp0.exists():
            raise HTTPException(404, f"现场报告文件不存在：{onsite_rel0}")
        txt0 = ofp0.read_text(encoding="utf-8")
        m0 = re.search(r"^## 现场核实信息\s*$", txt0, flags=re.M)
        review_txt = txt0[:m0.start()] if m0 else txt0
    else:
        raise HTTPException(400, "未找到文审报告或现场报告，无法生成。请先在报告页「提取 Word」并写入文审报告 MD")

    # 日期：弹窗现场日期优先；缺则从现有现场报告文件名解析（默认关联原文件）；再缺台账/报告日期
    date = (body.现场日期 or "").strip()
    if not date and onsite_rel0:
        m1 = re.match(r"^(\d{8})-", Path(onsite_rel0).name)
        if m1:
            d1 = m1.group(1)
            date = f"{d1[:4]}-{d1[4:6]}-{d1[6:]}"
    if not date:
        date = str(rec.get("现场日期") or "").strip() or str(rec.get("报告日期") or "").strip()
    if not date:
        raise HTTPException(400, "缺少现场日期（现场日期/报告日期均无），无法命名文件")

    picked = [dict(p) for p in body.勾选条款]
    # 组长项目：现场评审报告 MD 开头预设空的「## 开场白」（内容用户自行在 MD 补充）
    lead = "组长" in str(rec.get("评审角色") or "")
    md = review_writer.build_onsite_md(comp, date, review_txt, picked, lead=lead)

    out_dir = LIB_PATH / "政府质量奖-现场评审库"
    out_dir.mkdir(parents=True, exist_ok=True)
    # 2026-10-30 R6 用户拍板：文件名规范化为「YYYYMMDD-企业名.md」，去掉「-现场评审」后缀
    # （与 write-review 现场分支、与 20 库文审报告统一口径）；_find_onsite_report_file 里的
    # 「-现场评审」通配是存量文件兼容，保留不动
    fname = normalize_filename(comp, date, ".md")
    fp2 = out_dir / fname

    _backup_file(store.ledger_file())
    if fp2.exists():
        _backup_file(fp2)

    _retry_io(lambda: fp2.write_text(md, encoding="utf-8"), "写现场 MD")

    # 台账回填：报告唯一化——现场报告取代文审报告（文审 md 物理删除=迁移，先备份）；阶段不动
    items = store.load_ledger()
    rel2 = str(fp2.relative_to(LIB_PATH)).replace("\\", "/")
    removed = []
    for rel in _as_list(items[idx].get("来源文件")):
        if rel == rel2 or ("政府质量奖-资料评审库" not in str(rel) and "20-资料评审库" not in str(rel)):
            continue
        old_fp = resolve_report(rel)
        if old_fp.exists():
            _backup_file(old_fp)
            _unlink_retry(old_fp, "删被取代的文审报告")
            removed.append(str(rel))
    items[idx]["来源文件"] = [rel2]
    # 类别自动归位(2026-11-02 老张定):现场报告写入成功后,类别随流程变为 现场评审
    items[idx]["类别"] = ["现场评审"]
    # 现场日期：弹窗给了就直接覆盖台账（改日期 → 台账同步跟随文件名）
    if (body.现场日期 or "").strip():
        items[idx]["现场日期"] = body.现场日期.strip()
    if (body.结论 or "").strip():
        items[idx]["结论"] = body.结论.strip()
    store.save_ledger(items)

    # 改日期重建 → 旧现场报告文件删除，政府质量奖-现场评审库只保留唯一一份（先备份）
    if onsite_rel0 and onsite_rel0 != rel2:
        old_ofp = resolve_report(onsite_rel0)
        if old_ofp.exists():
            _backup_file(old_ofp)
            _unlink_retry(old_ofp, "删被取代的旧现场报告")
            removed.append(str(onsite_rel0))

    # 勾选结果持久化到缓存：现场评审核实窗体左栏只列这些条款（我负责的条款）
    cache = load_extract_cache(body.id)
    if cache is not None:
        cache["勾选条款"] = picked
        save_extract_cache(body.id, cache)

    try:
        sync_report_links(body.id)
    except Exception:
        pass

    return {"ok": True, "文件": fname, "路径": rel2, "已删除文审": removed}


def _find_onsite_report(rec: dict):
    """找项目的现场评审报告相对路径"""
    for rel in _as_list(rec.get("来源文件")):
        if "政府质量奖-现场评审库" in str(rel):
            return str(rel)
    return None


def _find_onsite_report_file(rec: dict):
    """发现已有现场报告**文件**（30 库）——终版「在已有现场报告上更新，不是新建」。

    文件名通配容忍任意后缀（2026-10-27 用户定）：用户现存现场报告带「-现场评审」
    后缀（write-onsite 约定名），而约定名没有——旧代码按约定名生成，终版写成了
    新文件。发现优先级：
      ① 台账「来源文件」里的 30 库条目（文件存在才算——用户跟踪的真源）
      ② 30 库里通配 glob：{YYYYMMDD}-{企业名}*.md（日期取现场日期，缺省报告日期），
         再退化为 *{企业名}*.md；多命中优先带「-现场评审」后缀的（write-onsite
         产物、含现场核实信息），否则按名序取最后一个
    返回 Path 或 None（都没有 → 调用方按约定名新建）。
    """
    rel = _find_onsite_report(rec)
    if rel:
        cand = resolve_report(rel)
        if cand.exists():
            return cand
    comp = str(rec.get("企业名称") or "").strip()
    if not comp:
        return None
    date = str(rec.get("现场日期") or rec.get("报告日期") or "").strip().replace("-", "")
    out_dir = LIB_PATH / "政府质量奖-现场评审库"
    gcomp = glob.escape(comp)
    pats = [f"{date}-{gcomp}*.md", f"*-{gcomp}*.md"] if date else [f"*-{gcomp}*.md"]
    for pat in pats:
        hits = sorted(out_dir.glob(pat))
        if not hits:
            continue
        suf = [p for p in hits if p.name.endswith("-现场评审.md")]
        return (suf or hits)[-1]
    return None


# 派生伪条目条款号：报告主要优势条款·4.3 / 报告主要建议条款·4.5（·后为 H3 大条款号）
_PSEUDO_RE = re.compile(r"^报告主要(优势|建议)条款·([\d.]+)$")
# 「## 现场核实信息」### 块标题：数字条款号（4.3.2）或伪条目前缀（报告主要优势条款·4.3）
# ——两者都要能 round-trip：伪条目块保存后重读，条款号/条款名不能散架
_TERM_HEAD_RE = re.compile(r"^((?:报告主要优势条款|报告主要建议条款)·[\d.]+|[\d.]+)\s*(.*)$")


def _parse_onsite_terms(txt: str):
    """解析现场报告「## 现场核实信息」下的 ### 条款块（核实窗体左栏数据源，MD 为唯一真源）。

    优势行双标签兼容：普通条款块用「- 文审优势：」，派生伪条目块（2026-10-28 内容
    落盘）用「- 优势：」——两者都能读回（伪条目块保存时把派生全文写进行里）。
    """
    m = re.search(r"^## 现场核实信息\s*$", txt, flags=re.M)
    if not m:
        return []
    sec = txt[m.end():]
    sec = re.split(r"^## ", sec, flags=re.M)[0]   # 到下一个二级标题为止
    out = []
    for b in re.split(r"^### ", sec, flags=re.M)[1:]:
        lines = b.strip("\n").splitlines()
        if not lines:
            continue
        head = lines[0].strip()
        hm = _TERM_HEAD_RE.match(head)
        no = hm.group(1) if hm else ""
        name = hm.group(2).strip() if hm else head
        link = re.search(r"相关条款：\[\[([^\]]+)\]\]", b)

        def grab(tag):
            mm = re.search(rf"- {tag}：(.*?)(?=\n- |\Z)", b, flags=re.S)
            return mm.group(1).strip() if mm else ""

        out.append({"条款号": no, "条款名": name,
                    "目标文件": link.group(1).strip() if link else "",
                    "优势": grab("文审优势") or grab("优势"), "可改进之处": grab("可改进之处"),
                    "现场核实": grab("现场核实")})
    return out


def _pseudo_term_name(txt: str, no: str) -> str:
    """伪条目条款号 → H3 条款名（保存建块用；非伪条目/节里找不到返回空串）。"""
    m = _PSEUDO_RE.match(str(no or ""))
    if not m:
        return ""
    sec_map = _parse_advantage_map(txt, "主要优势" if m.group(1) == "优势" else "主要改进建议")
    return (sec_map.get(m.group(2)) or {}).get("条款名", "")


def _append_onsite_block(txt: str, block: List[str]) -> str:
    """把 ### 条款块追加到「## 现场核实信息」节末尾（无该节则新建于文尾）。

    节内已有块原样保留（只末尾追加，不重排）；与下一节之间留空行。
    """
    marker = "## 现场核实信息"
    i = txt.find(marker)
    if i == -1:                                    # 无该节（理论不至此）：文尾新建
        return txt.rstrip() + f"\n\n{marker}\n\n" + "\n".join(block) + "\n"
    rest = txt[i + len(marker):]
    m = re.search(r"(?m)^## ", rest)               # 节末尾 = 下一个二级标题之前
    end = i + len(marker) + (m.start() if m else len(rest))
    head, tail = txt[:end].rstrip("\n"), txt[end:]
    body = "\n\n" + "\n".join(block).rstrip() + "\n"
    return head + body + (("\n" + tail.lstrip("\n")) if tail.strip() else "")


def _pseudo_derived(txt: str, no: str):
    """伪条目条款号 → (行标签, 派生全文, H3条款名)；非伪条目或节里无该 H3 → ("", "", "")。

    行标签 = 「优势」（报告主要优势条款·X）或「可改进之处」（报告主要建议条款·X）
    ——落盘/自愈时内容写进块里这个标签的行；派生全文 = 对应节 H3 全文（纯文本化，
    见 _parse_advantage_map）。供 _write_pseudo_note_into_md / _fill_pseudo_block_lines 共用。
    """
    m = _PSEUDO_RE.match(str(no or ""))
    if not m:
        return "", "", ""
    kind = m.group(1)
    sec_map = _parse_advantage_map(txt, "主要优势" if kind == "优势" else "主要改进建议")
    info = sec_map.get(m.group(2)) or {}
    label = "优势" if kind == "优势" else "可改进之处"
    return label, str(info.get("全文") or ""), str(info.get("条款名") or "")


def _write_note_into_md(txt: str, no: str, note: str) -> str:
    """把现场核实文本写回 MD 中「### {no} 」块的「- 现场核实：」行。

    派生伪条目（条款号以「报告主要优势条款·」/「报告主要建议条款·」开头）走
    _write_pseudo_note_into_md：内容落盘（2026-10-28 用户定）——除「现场核实」外，
    把当前派生内容同步写入块的「优势：」/「可改进之处：」行。
    普通条款块：块不存在时（理论不至此）在「## 现场核实信息」节末尾建标准三行结构块。
    """
    if _PSEUDO_RE.match(str(no or "")):
        return _write_pseudo_note_into_md(txt, str(no), note)
    lines = txt.splitlines()
    out, in_block, done, found = [], False, False, False
    head_re = re.compile(r"^### " + re.escape(no) + r"(\s|$)")
    for ln in lines:
        if ln.startswith("### "):
            if in_block and not done:
                out.append(f"- 现场核实：{note}")
                done = True
            in_block = bool(head_re.match(ln))
            found = found or in_block
        elif in_block and not done and ln.startswith("- 现场核实："):
            out.append(f"- 现场核实：{note}")
            done = True
            continue
        out.append(ln)
    if in_block and not done:
        out.append(f"- 现场核实：{note}")
        done = True
    if found:
        return "\n".join(out) + ("\n" if txt.endswith("\n") else "")
    # 块不存在 → 建标准三行结构块（伪条目条款号唯一，·后大条款号不同不会串块）
    block = [f"### {no}".rstrip(), "", "- 文审优势：", "- 可改进之处：",
             f"- 现场核实：{note}"]
    return _append_onsite_block(txt, block)


def _write_pseudo_note_into_md(txt: str, no: str, note: str) -> str:
    """伪条目现场核实写回（内容落盘，2026-10-28 用户定）。

    块不存在 → 建完整结构块：「优势：」/「可改进之处：」行写**当前派生内容**
    （报告主要优势条款·X → 优势=主要优势节 X 全文；报告主要建议条款·X → 可改进之处=
    主要改进建议节 X 全文），另一行留空。
    块已存在 → 写「现场核实」行；标签行按当前派生内容刷新（覆盖旧值——节内容更新后
    保存一次即同步；派生为空——节里已无该 H3——时不动原行，不抹掉已落盘的内容）。
    """
    label, full, _name = _pseudo_derived(txt, no)
    lines = txt.splitlines()
    out, in_block, done, found, filled = [], False, False, False, False
    head_re = re.compile(r"^### " + re.escape(no) + r"(\s|$)")
    for ln in lines:
        if ln.startswith("### "):
            if in_block and not done:
                out.append(f"- 现场核实：{note}")
                done = True
            in_block = bool(head_re.match(ln))
            found = found or in_block
        elif in_block and not done and ln.startswith("- 现场核实："):
            out.append(f"- 现场核实：{note}")
            done = True
            continue
        elif in_block and full and not filled and ln.strip().startswith(f"- {label}："):
            out.append(f"- {label}：{full}")     # 标签行 → 当前派生内容（保存即刷新）
            filled = True
            continue
        out.append(ln)
    if in_block and not done:
        out.append(f"- 现场核实：{note}")
        done = True
    if found:
        return "\n".join(out) + ("\n" if txt.endswith("\n") else "")
    # 块不存在 → 建完整结构块（伪条目条款号唯一，·后大条款号不同不会串块）
    name = _pseudo_term_name(txt, no)
    block = [f"### {no} {name}".rstrip(), "",
             f"- 优势：{full if label == '优势' else ''}",
             f"- 可改进之处：{full if label == '可改进之处' else ''}",
             f"- 现场核实：{note}"]
    return _append_onsite_block(txt, block)


def _fill_pseudo_block_lines(txt: str):
    """自愈旧数据（2026-10-28 用户定）：伪条目块的优势/可改进之处**空行**且节能派生
    内容 → 回填 MD。返回 (新txt, 回填行数)。

    幂等：只填空行/缺失行，非空行一律不动（填过不再写——用户手改过的内容不覆盖）；
    派生为空（节里已无该 H3）时空着不动。调用方（api_onsite_report_terms）负责
    写前 _backup_file。只扫「## 现场核实信息」节内的 ### 伪条目块。
    """
    m = re.search(r"^## 现场核实信息\s*$", txt or "", flags=re.M)
    if not m:
        return txt, 0
    start = m.end()
    rest = txt[start:]
    nxt = re.search(r"^## ", rest, flags=re.M)
    body, tail = (rest[:nxt.start()], rest[nxt.start():]) if nxt else (rest, "")
    parts = re.split(r"^### ", body, flags=re.M)
    pre, out_blocks, n_fill = parts[0], [], 0
    for b in parts[1:]:
        lines = b.splitlines()
        head = lines[0].strip() if lines else ""
        hm = _TERM_HEAD_RE.match(head)
        label, full, _ = _pseudo_derived(txt, hm.group(1) if hm else "")
        if not full:
            out_blocks.append("### " + b)      # split 吃掉了 ### 前缀，非伪条目块原样补回
            continue
        mm = re.search(rf"(?m)^- {label}：(.*)$", b)
        if mm and mm.group(1).strip():
            out_blocks.append("### " + b)      # 非空行一律不动（填过不再写）
            continue
        if mm:                                 # 空行 → 行内回填（保留块内其余行原样）
            out_blocks.append("### " + b[:mm.start()] + f"- {label}：{full}" + b[mm.end():])
        else:                                  # 整行缺失 → 插在标题行之后
            hl = b.find("\n")
            ins = f"- {label}：{full}\n"
            out_blocks.append("### " + b[:hl + 1] + ins + b[hl + 1:])
        n_fill += 1
    if not n_fill:
        return txt, 0
    return txt[:start] + pre + "".join(out_blocks) + tail, n_fill


def _parse_opening(txt: str) -> str:
    """取 MD「## 开场白」节的正文（无该节返回空串）。标题含「开场白」即视为该节。"""
    m = re.search(r"^## [^\n]*开场白[^\n]*$", txt, flags=re.M)
    if not m:
        return ""
    sec = txt[m.end():]
    sec = re.split(r"^## ", sec, flags=re.M)[0]
    return sec.strip("\n")


def _write_opening_into_md(txt: str, note: str) -> str:
    """把开场白文本写回 MD 的「## 开场白」章节（整节正文替换，保留标题行）。

    无该章节时（旧报告未预设）：按组长规范在 H1 之后补插空节再写入。
    标题判定与 review_writer.build_onsite_md 一致：含「开场白」的 H2 即视为该节。
    """
    body = (note or "").strip("\n")
    m = re.search(r"^## [^\n]*开场白[^\n]*$", txt, flags=re.M)
    if not m:
        mh = re.search(r"^# .+$", txt, flags=re.M)
        if not mh:
            return txt
        ins = "\n\n## 开场白" + (f"\n\n{body}" if body else "")
        return txt[:mh.end()] + ins + txt[mh.end():]
    nxt = re.search(r"^## ", txt[m.end():], flags=re.M)
    tail_at = m.end() + (nxt.start() if nxt else len(txt) - m.end())
    head = txt[:m.end()].rstrip("\n")
    tail = txt[tail_at:].lstrip("\n")
    new = head + ("\n\n" + body if body else "") + ("\n\n" + tail if tail else "\n")
    return new.rstrip("\n") + "\n"


def _parse_advantage_map(txt: str, section: str = "主要优势"):
    """解析现场 MD「## {section}」节，按 `### 条款号 条款名` 建
    {条款号: {"条款名": 条款名, "全文": 纯文本全文}}。

    派生伪条目的数据源（2026-10-27 用户定）：终版已含文审全文（归口唯一化后
    20 库文件已删），只用现场 MD 自身，不依赖外部文件。section = 主要优势 /
    主要改进建议（同规则解析两节——泛化出节名参数，勿复制粘贴两遍）。
    纯文本化 = 去 MD 标记：**加粗** 去星号、`#### ` H4 概述标题与 `- ` bullet 前缀
    剥成普通行（H4 概述+方法正文保留为文字）。
    """
    m = re.search(rf"^## {re.escape(section)}\s*$", txt or "", flags=re.M)
    if not m:
        return {}
    sec = txt[m.end():]
    sec = re.split(r"^## ", sec, flags=re.M)[0]   # 到下一个二级标题为止
    out = {}
    for b in re.split(r"^### ", sec, flags=re.M)[1:]:
        lines = b.splitlines()
        head = lines[0].strip() if lines else ""
        hm = re.match(r"^(\d+(?:\.\d+)*)\s*(.*)$", head)
        if not hm:
            continue
        body = "\n".join(ln.strip() for ln in lines[1:] if ln.strip())
        body = re.sub(r"\*\*(.+?)\*\*", r"\1", body)        # 去加粗标记（保留文字）
        body = re.sub(r"^####\s*", "", body, flags=re.M)    # H4 概述标题 → 纯文本行
        body = re.sub(r"^-\s+", "", body, flags=re.M)       # bullet 前缀 → 纯文本行
        if body.strip():
            out[hm.group(1)] = {"条款名": hm.group(2).strip(), "全文": body.strip()}
    return out


def _onsite_terms_with_derived(txt: str) -> List[dict]:
    """现场 MD → 核实窗体条款列表 = MD「现场核实信息」已有块 + 派生伪条目。

    伪条目（2026-10-27 用户定）：选中的细条款按条款号前两段（4.3.2 → 4.3）命中
    同一 MD「## 主要优势」/「## 主要改进建议」的 H3 大条款时，在列表末尾追加
    「报告主要优势条款·4.3 顾客与市场 / 报告主要建议条款·4.5 过程管理」——列大
    条款（H3）即可；MD 里已有同名块（上次保存产生的）不重复追加（去重）。
    伪条目的优势/可改进之处（2026-10-28 用户定内容落盘）：**块内已落盘的内容优先**
    （保存时写的「优势：」/「可改进之处：」行），块里是空行（旧数据未落盘）才读取时
    现派生——单一真源从「节」下沉到「块」，节内容更新后保存一次即刷新。
    """
    terms = _parse_onsite_terms(txt)
    sec_maps = {"优势": _parse_advantage_map(txt, "主要优势"),
                "建议": _parse_advantage_map(txt, "主要改进建议")}
    prefixes, existing = set(), set()
    for t in terms:
        no = str(t.get("条款号") or "")
        existing.add(no)
        if not _PSEUDO_RE.match(no):       # 伪条目自身不参与前缀匹配（防自触发）
            prefixes.add(".".join(no.split(".")[:2]))
    for kind in ("优势", "建议"):           # 先优势后建议，统一追加在列表末尾
        for h3, info in sec_maps[kind].items():
            no = f"报告主要{kind}条款·{h3}"
            if h3 in prefixes and no not in existing:
                terms.append({"条款号": no, "条款名": info.get("条款名", ""),
                              "目标文件": "", "优势": "", "可改进之处": "", "现场核实": ""})
    for t in terms:                        # 块内空行才现派生（落盘内容优先，见 docstring）
        m = _PSEUDO_RE.match(str(t.get("条款号") or ""))
        if not m:
            continue
        key = "优势" if m.group(1) == "优势" else "可改进之处"
        if not str(t.get(key) or "").strip():
            info = sec_maps[m.group(1)].get(m.group(2)) or {}
            t[key] = info.get("全文", "")
    return terms


@app.get("/api/onsite-report-path")
def api_onsite_report_path(project_id: str = ""):
    """发现已有现场报告（30 库）——写入弹窗「现场日期自动带出/更新提示」用。

    通配匹配容忍「-现场评审」等任意后缀（见 _find_onsite_report_file）；
    未找到返回空路径（前端留空日期，由后端 400 文案提示）。
    """
    idx, rec = find_project(project_id)
    if idx is None:
        raise HTTPException(404, f"未找到项目 {project_id}")
    fp = _find_onsite_report_file(rec)
    return {"ok": True, "路径": str(fp.relative_to(LIB_PATH)).replace("\\", "/") if fp else "",
            "文件名": fp.name if fp else ""}


@app.get("/api/onsite-report-terms")
def api_onsite_report_terms(project_id: str = ""):
    """核实窗体数据源：解析现场评审报告 MD 的「现场核实信息」章节（### 标题=条款）。

    派生伪条目（2026-10-27 用户定）：选中的细条款（如 4.3.2）按条款号前两段
    （4.3）命中同一 MD「## 主要优势」/「## 主要改进建议」的 H3 大条款时，末尾
    追加「报告主要优势条款·4.3 / 报告主要建议条款·4.5」核实项；伪条目的优势/
    可改进之处以块内落盘内容优先（保存时写入，2026-10-28 用户定内容落盘），
    块里空行（旧数据）才读取时从对应节现派生。
    自愈旧数据（2026-10-28 用户定）：发现伪条目块的优势/可改进之处**空行**且节可
    派生内容 → 回填 MD（幂等：只填空行、填过不再写；写前备份）——修旧代码产生的空块。
    """
    idx, rec = find_project(project_id)
    if idx is None:
        raise HTTPException(404, f"未找到项目 {project_id}")
    fp = _find_onsite_report_file(rec)
    rel = str(fp.relative_to(LIB_PATH)).replace("\\", "/") if fp else ""
    if not fp:
        return {"ok": False, "提示": "未找到现场评审报告。请先在「编辑」里把类别改为「现场评审」并更新。"}
    txt = fp.read_text(encoding="utf-8")
    # 自愈：伪条目块空行回填（n_fill=0 一字不动——幂等，不碰用户已填/手改的内容）
    healed, n_fill = _fill_pseudo_block_lines(txt)
    if n_fill:
        _backup_file(fp)
        _retry_io(lambda: fp.write_text(healed, encoding="utf-8"), "自愈伪条目块内容")
        txt = healed
    terms = _onsite_terms_with_derived(txt)
    std = str(rec.get("适用标准") or "").strip()
    cmap = {str(c["条款号"]): str(c["文件"]) for c in api_clauses(std)} if std else {}
    for t in terms:
        no = str(t.get("条款号") or "")
        m = _PSEUDO_RE.match(no)
        # 伪条目的双链路径取 H3 大条款号在条款字典里的文件（如 4.3 → 条款文件）
        t["路径"] = cmap.get(m.group(2) if m else no, "")
    lead = "组长" in str(rec.get("评审角色") or "")
    return {"ok": True, "报告": rel, "条款": terms, "组长": lead, "开场白": _parse_opening(txt) if lead else ""}


class OnsiteNoteBody(BaseModel):
    id: str = ""
    核实: dict = {}   # 条款号 → 现场核实文本


@app.post("/api/onsite-note")
def api_onsite_note(body: OnsiteNoteBody):
    """现场评审核实内容写回现场评审报告 MD（MD 为唯一真源，写前备份）。"""
    idx, rec = find_project(body.id)
    if idx is None:
        raise HTTPException(404, f"未找到项目 {body.id}")
    rel = _find_onsite_report(rec)
    if not rel:
        raise HTTPException(400, "未找到现场评审报告，无法写回核实内容")
    fp = resolve_report(rel)
    if not fp.exists():
        raise HTTPException(404, f"现场报告文件不存在：{rel}")
    _backup_file(fp)
    txt = fp.read_text(encoding="utf-8")
    n = 0
    for no, note in (body.核实 or {}).items():
        if str(no) == "开场白":
            new_txt = _write_opening_into_md(txt, str(note or ""))
        else:
            new_txt = _write_note_into_md(txt, str(no), str(note or ""))
        if new_txt != txt:
            n += 1
        txt = new_txt
    _retry_io(lambda: fp.write_text(txt, encoding="utf-8"), "写现场核实内容")
    return {"ok": True, "更新": n}


def normalize_filename(company: str, date_str: str, ext: str) -> str:
    """紧凑命名：YYYYMMDD-企业全称.扩展名（如 20261017-上海XX有限公司.md）"""
    m = re.match(r"(\d{4})[-/.年]?(\d{1,2})[-/.月]?(\d{1,2})", str(date_str or "").strip())
    if not m:
        raise HTTPException(400, f"日期无法识别：{date_str}")
    d = f"{m.group(1)}{int(m.group(2)):02d}{int(m.group(3)):02d}"
    return f"{d}-{company.strip()}{ext}"


COMPANY_SUFFIXES = ["股份有限公司", "有限责任公司", "有限公司", "公司", "集团",
                    "研究院", "研究所", "工厂", "中心", "厂", "社"]


def _company_core(company: str) -> str:
    """企业名去掉常见后缀，得到简称核（用于判定原文件名是否体现同一企业）"""
    c = str(company or "").strip()
    for s in COMPANY_SUFFIXES:
        if c.endswith(s) and len(c) - len(s) >= 2:
            return c[:-len(s)]
    return c


def _rename_linked_files(items: list, idx: int, new_comp: str, fallback_date: str):
    """改企业名后，同步重命名该项目的来源文件（保留日期前缀，企业名整体替换为新名）"""
    srcs = _as_list(items[idx].get("来源文件"))
    renamed = []
    for rel in srcs:
        src = resolve_report(rel)
        if not src.exists():
            renamed.append(rel)
            continue
        stem = src.stem
        m = re.match(r"^(\d{8})-", stem)
        if m:
            new_name = f"{m.group(1)}-{new_comp}{src.suffix}"
        elif fallback_date:
            try:
                new_name = normalize_filename(new_comp, fallback_date, src.suffix)
            except HTTPException:
                new_name = f"{new_comp}{src.suffix}"
        else:
            new_name = f"{new_comp}{src.suffix}"
        new_path = src.with_name(new_name)
        if new_path != src:
            if new_path.exists():
                i = 2
                while new_path.exists():
                    new_path = src.with_name(f"{src.stem}-{i}{src.suffix}")
                    i += 1
            src.rename(new_path)
        renamed.append(str(new_path.relative_to(LIB_PATH)).replace("\\", "/"))
    items[idx]["来源文件"] = renamed
    return renamed


# ── 报告双向链接 ───────────────────────────────────────────
def _fmt_cell(v):
    if isinstance(v, list):
        v = "·".join(str(x) for x in v if x)
    return v if v not in (None, "", []) else "—"


def _set_report_links(fp: Path, lines: List[str]):
    """在报告 md 最底部维护「## 相关评审记录」段（增量，不碰正文）"""
    txt = fp.read_text(encoding="utf-8")
    section = "## 相关评审记录"
    if section in txt:
        start = txt.index(section)
        rest = txt[start:]
        nxt = rest.find("\n## ", len(section))   # 找下一段标题
        if nxt == -1:
            txt = txt[:start].rstrip() + "\n"
        else:
            txt = (txt[:start] + rest[nxt + 1:]).rstrip() + "\n"
    if lines:
        txt = txt.rstrip() + "\n\n" + section + "\n\n" + "\n".join(lines) + "\n"
    _retry_io(lambda: fp.write_text(txt, encoding="utf-8"), "写报告 MD")


def sync_report_links(pid: str):
    """同企业各项目的报告底部互相写「相关评审记录」双链（双向）。
    触发时机：新建项目建关联、编辑改了历史项目/来源文件。"""
    items = store.load_ledger()
    cur = next((d for d in items if str(d.get("id", "")) == pid), None)
    if not cur:
        return
    company_norm = _norm_company(cur.get("企业名称"))
    hist_ids = set(str(x) for x in _as_list(cur.get("历史项目")))
    group = [d for d in items if _norm_company(d.get("企业名称")) == company_norm]
    for d in items:                            # 历史项目里有但企业名不匹配（改名）也纳入
        if str(d.get("id", "")) in hist_ids and d not in group:
            group.append(d)
    file_of = {}
    for d in group:
        f = _as_list(d.get("来源文件"))
        if f:
            file_of[str(d["id"])] = f[0]
    for d in group:
        fpath = file_of.get(str(d["id"]))
        if not fpath:
            continue
        fp = LIB_PATH / fpath
        if not fp.exists():
            continue
        others = [o for o in group if str(o["id"]) != str(d["id"])]
        lines = []
        for o in others:
            of = file_of.get(str(o["id"]))
            label = Path(of).stem if of else f"{o.get('企业名称','')}（未关联报告）"
            meta = (f"{_fmt_cell(o.get('年份'))} · {_fmt_cell(o.get('类别'))} · "
                    f"{_fmt_cell(o.get('奖项/项目'))} · {_fmt_cell(o.get('得分'))}分 · "
                    f"{_fmt_cell(o.get('结论'))}")
            lines.append(f"- [[{label}]]（{meta}）")
        _set_report_links(fp, lines)


@app.get("/api/projects")
def api_projects(all: int = 0):
    return load_projects(only_enabled=(not all))


@app.get("/api/modules")
def api_modules():
    """模块开关状态：供界面显示当前业务范围与预留业务线"""
    return {
        "启用": MODULES_ON,
        "登记": {
            k: {"说明": v.get("说明", ""), "状态": v.get("状态", ""), "奖项枚举": v.get("奖项枚举", [])}
            for k, v in MODULES_REG.items()
        },
    }


def parse_dicts():
    """字典三张表已内置平台，直接读 data/dicts.json"""
    return store.load_dicts()


def build_trees(dicts: Dict[str, List]):
    """行数组 → 两级树，供界面直接做「市 → 区县」「门类 → 大类」联动"""
    reg: Dict[str, List[str]] = {}
    for r in dicts.get("区域", []):
        if len(r) < 2 or not r[0]:
            continue
        reg.setdefault(r[0], [])
        if r[1] and r[1] not in reg[r[0]]:
            reg[r[0]].append(r[1])
    ind: Dict[str, List[str]] = {}
    for r in dicts.get("行业", []):
        if len(r) < 4 or not r[1]:
            continue
        ind.setdefault(r[1], [])
        v = f"{r[2]} {r[3]}".strip()
        if v and v not in ind[r[1]]:
            ind[r[1]].append(v)
    return {"区域": reg, "行业": ind}


@app.get("/api/dicts")
def api_dicts():
    return parse_dicts()


@app.get("/api/dicts/tree")
def api_dicts_tree():
    """两级字典树：区域 {市:[区县]}、行业 {门类:[大类]}。界面下拉直接用这个"""
    return build_trees(parse_dicts())


@app.get("/api/enums")
def api_enums():
    e = dict(CFG.get("枚举", {}))
    # 奖项枚举按启用模块合并
    awards = []
    for m in MODULES_ON:
        awards += MODULES_REG.get(m, {}).get("奖项枚举", [])
    e["奖项/项目"] = awards or e.get("奖项/项目", [])
    e["模块"] = MODULES_ON
    e["适用标准"] = CFG.get("适用标准", [])
    e["条款类目"] = CFG.get("标准库", {}).get("类目映射表", {})
    return e


class PatchBody(BaseModel):
    fields: Dict[str, Any]


@app.post("/api/projects")
def api_create(body: PatchBody):
    """新建项目卡片。接受前端勾选的「历史项目」id 与「来源文件」；
    未传历史项目时自动按企业检索兜底。创建后同步同企业报告双向链接。"""
    comp = (body.fields.get("企业名称") or "").strip()
    if not comp:
        raise HTTPException(400, "企业名称不能为空")
    raw_hist = body.fields.get("历史项目")
    src_files = _as_list(body.fields.get("来源文件"))
    if raw_hist is None:
        hist = find_company_history(comp)
    else:
        hist = []
        for hid in _as_list(raw_hist):
            _, d = find_project(str(hid))
            if d:
                hist.append({"id": d.get("id"), "企业名称": d.get("企业名称"),
                             "年份": d.get("年份"), "类别": d.get("类别"),
                             "奖项/项目": d.get("奖项/项目"), "得分": d.get("得分"),
                             "结论": d.get("结论"), "阶段": d.get("阶段")})
    made = importer.import_rows([body.fields])["made"]
    if not made:
        raise HTTPException(400, "未能创建卡片，请检查字段")
    if hist or src_files:
        items = store.load_ledger()
        for d in items:
            if str(d.get("id", "")) == made[0]["id"]:
                if hist:
                    d["历史项目"] = [h["id"] for h in hist]
                if src_files:
                    d["来源文件"] = src_files
        store.save_ledger(items)
    if hist or src_files:
        try:
            sync_report_links(made[0]["id"])
        except Exception:
            pass
    return {"ok": True, **made[0], "历史": hist}


@app.post("/api/import")
async def api_import(file: UploadFile = File(...)):
    """上传填写好的 xlsx/csv，批量建卡"""
    tmp = BASE / "data" / f"upload-{datetime.now():%Y%m%d-%H%M%S}-{file.filename}"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(await file.read())
    try:
        rows = importer.read_table(tmp)
    except Exception as e:
        _unlink_retry(tmp, "删上传临时文件")
        raise HTTPException(400, f"表格读取失败：{e}")
    try:
        res = importer.import_rows(rows)
    finally:
        # A4：上传的表格读完即删，不在 data/ 积压（对照 extract-docx）；
        # 失败只警告不抛——建卡已成功，不能因清理失败把 200 变 500
        _unlink_retry(tmp, "删上传临时文件")
    made, skipped = res["made"], res["skipped"]
    return {"ok": True, "count": len(made), "items": made, "跳过": skipped, "读取行数": len(rows)}


@app.get("/api/template")
def api_template():
    """生成 / 下载批量导入模板（动态生成到临时区，不落 80-模板 目录）"""
    p = BASE / "data" / "tmp" / "批量导入-项目台账.xlsx"
    importer.make_template(p, parse_dicts(), api_enums())
    return FileResponse(p, filename="批量导入-项目台账.xlsx")


def _report_company(rel: str) -> str:
    """从报告 MD 解析企业名：frontmatter「企业名称」优先；缺失时按文件名兜底
    （{日期}-{企业名}-{类别}.md → 取中间企业名段）。解析不出返回空串。"""
    fp = LIB_PATH / rel
    try:
        c = str(parse_frontmatter(fp).get("企业名称") or "").strip()
        if c:
            return c
    except Exception:
        pass
    stem = Path(rel).stem
    parts = stem.split("-")
    if len(parts) >= 3:                       # 日期-企业名-类别（企业名内含「-」时取中段）
        return "-".join(parts[1:-1])
    return ""


def _report_year(rel: str):
    """从报告 MD 解析评审年份：frontmatter「现场日期」>「报告日期」> 文件名前缀 YYYYMMDD。

    现场日期=评审实际发生日（最贴近评审年份）；报告日期=出具日（仅跨年出具才偏）；
    文件名兜底供无 frontmatter 的老报告。解析不出返回 None（归位时进 fallback 桶）。
    已确认事实：文审与现场评审不跨年——同企业同年桶内的报告必属同一批评审。
    """
    fp = LIB_PATH / rel
    fm = {}
    try:
        fm = parse_frontmatter(fp)
    except Exception:
        pass
    for k in ("现场日期", "报告日期"):
        m = re.search(r"(\d{4})", str(fm.get(k) or ""))
        if m:
            return int(m.group(1))
    m = re.match(r"^(\d{4})\d{4}-", Path(rel).stem)
    return int(m.group(1)) if m else None


@app.post("/api/reports/auto-link")
def api_auto_link():
    """批量关联：按企业名把报告 MD 自动填进项目卡「来源文件」（只补空，不覆盖，幂等可重复点）。

    场景：先导入/建卡（企业知识库还没建），之后报告陆续就绪，点一次即完成关联。
    - 匹配口径：_norm_company 归一化（去公司后缀），与「历史项目」同算法
    - 一个项目卡可关联多个报告（文审+现场）；报告 frontmatter 企业名缺失时按文件名兜底
    - 双关联（2026-10-23 用户纠正「一个企业一份 MD」旧观点后增强）：
      同企业不同年份的卡片自动互填「历史项目」（merge 并集，不覆盖用户手工勾选），
      卡片层 + 报告层（sync_report_links）双向可达，便于跨年份追溯。
    - 按年归位（2026-10-23 第二次增强）：报告年份解析优先级 现场日期>报告日期>文件名前缀；
      同企业同年份报告精确挂到该年卡片；无同年份报告或卡片未填年份时 fallback 挂该企业
      全部报告并在结果里标注。文审与现场不跨年，同年桶即同一批评审的完整档案。
      已知边界：报告 frontmatter 无奖项字段，同年同企业多奖项时各卡会互挂同年全部报告。
    """
    items = store.load_ledger()
    reports = list_report_files()
    by_company, unparsed = {}, []
    for r in reports:
        c = _report_company(r["路径"])
        if c:
            by_company.setdefault(_norm_company(c), []).append(
                {"路径": r["路径"], "文件名": r["文件名"], "年份": _report_year(r["路径"])})
        else:
            unparsed.append(r["文件名"])
    # 同企业分组（全量卡片，含已有关联的）——供「历史项目」互填与报告互链
    groups = {}
    for d in items:
        groups.setdefault(_norm_company(d.get("企业名称")), []).append(d)
    hist_changed = []
    for norm, grp in groups.items():
        if len(grp) < 2:
            continue
        ids = {str(x.get("id")) for x in grp}
        for d in grp:
            me = str(d.get("id"))
            cur = [str(x) for x in _as_list(d.get("历史项目"))]
            merged = list(dict.fromkeys(cur + sorted(ids - {me})))
            if merged != cur:
                d["历史项目"] = merged
                hist_changed.append({"id": me, "企业": d.get("企业名称"),
                                     "历史项目": merged})
    if CFG.get("安全", {}).get("写入前备份", True) and (
            any(not _as_list(d.get("来源文件")) for d in items) or hist_changed):
        _backup_file(store.ledger_file())
    linked, no_match = [], []
    for d in items:
        if _as_list(d.get("来源文件")):
            continue                            # 已有关联，不覆盖
        cands = by_company.get(_norm_company(d.get("企业名称")), [])
        if not cands:
            no_match.append(f"{d.get('id')} {d.get('企业名称')}")
            continue
        try:
            year = int(str(d.get("年份") or "").strip())
        except Exception:
            year = 0
        if year:
            exact = [c for c in cands if c["年份"] == year]
            rest = [c for c in cands if c["年份"] != year]
            if exact:
                picked, mode = exact, f"精确：{year} 年"
            else:
                picked, mode = rest, f"fallback：无 {year} 年报告，已挂全部 {len(rest)} 份"
        else:
            picked, mode = cands, f"fallback：卡片未填年份，已挂全部 {len(cands)} 份"
        d["来源文件"] = [c["路径"] for c in picked]
        linked.append({"id": d.get("id"), "企业": d.get("企业名称"),
                       "归位": mode, "报告": [c["文件名"] for c in picked]})
    if linked or hist_changed:
        store.save_ledger(items)
    # 报告底部互链：同企业每组刷一次（sync_report_links 内部按组全量重写，幂等）
    for norm, grp in groups.items():
        if any(_as_list(x.get("来源文件")) for x in grp):
            try:
                sync_report_links(str(grp[0].get("id")))
            except Exception:
                pass
    return {"ok": True, "关联": linked, "无匹配": no_match,
            "历史项目": hist_changed, "无法解析企业名的报告": unparsed}


EDITABLE_FIELDS = {"企业名称", "类别", "阶段", "结论", "得分", "奖项/项目", "适用标准", "报告日期", "现场日期", "评审角色", "来源文件", "历史项目", "区域", "行业"}


@app.put("/api/projects/{pid}")
def api_update(pid: str, body: PatchBody):
    """编辑台账字段（企业名称/阶段/结论/得分/来源文件/历史项目等）。
    改企业名称时，同步重命名该项目的来源文件（文件名里的企业名跟着变）。"""
    idx, _ = find_project(pid)
    if idx is None:
        raise HTTPException(404, f"未找到项目 {pid}")
    for k in body.fields:
        if k not in EDITABLE_FIELDS:
            raise HTTPException(403, f"字段「{k}」不可在工作台修改")
    _backup_file(store.ledger_file())
    items = store.load_ledger()
    old_comp = str(items[idx].get("企业名称") or "").strip()
    new_comp = str(body.fields.get("企业名称") or "").strip()
    old_stage = items[idx].get("阶段")
    for k, v in body.fields.items():
        if k in ("区域", "行业"):
            # 2026-10-25 补：建卡只认拆分键（市级/区县、行业门类/大类），
            # 编辑侧放行数组与「A、B」字符串两种口径，让「待补字段」可修
            if isinstance(v, str):
                v = [x.strip() for x in re.split(r"[、,，/;；\s]+", v) if x.strip()]
            items[idx][k] = v or None
            continue
        if k == "得分":
            try:
                v = float(str(v).strip()) if str(v).strip() else None
            except Exception:
                v = None
        items[idx][k] = v
    renamed = []
    if "企业名称" in body.fields and new_comp and new_comp != old_comp:
        cats = _as_list(items[idx].get("类别"))
        date_key = "现场日期" if "现场评审" in cats else "报告日期"
        fallback = str(items[idx].get(date_key) or "").strip()
        renamed = _rename_linked_files(items, idx, new_comp, fallback)
    store.save_ledger(items)
    # 阶段推进到「归档」时，删除该项目的提取缓存（现场报告已落成，缓存无用了，减少冗余）
    if items[idx].get("阶段") == "归档" and old_stage != "归档":
        remove_extract_cache(pid)
    if "历史项目" in body.fields or "来源文件" in body.fields or "企业名称" in body.fields:
        try:
            sync_report_links(pid)
        except Exception:
            pass
    return {"ok": True, "id": pid, "更名文件": renamed}


@app.delete("/api/projects/{pid}")
def api_delete(pid: str):
    """删除台账记录（不删报告文件）；同步清理其他项目「历史项目」里对该 id 的引用"""
    idx, rec = find_project(pid)
    if idx is None:
        raise HTTPException(404, f"未找到项目 {pid}")
    _backup_file(store.ledger_file())
    items = store.load_ledger()
    removed = items.pop(idx)
    for d in items:
        hist = _as_list(d.get("历史项目"))
        if pid in hist:
            d["历史项目"] = [x for x in hist if x != pid]
    store.save_ledger(items)
    return {"ok": True, "id": pid, "企业": removed.get("企业名称")}


# ── 政策库 ────────────────────────────────────────────────
class PolicyBody(BaseModel):
    fields: Dict[str, Any]


class PackBody(BaseModel):
    区域: List[str] = []
    行业: List[str] = []
    关联项目: str = ""
    补充要求: str = ""
    检索意图: str = ""


@app.get("/api/policies")
def api_policies():
    return policy.load_policies()


@app.get("/api/policy/dicts")
def api_policy_dicts():
    return CFG.get("政策枚举", {})


@app.get("/api/policy/health")
def api_policy_health():
    """时效体检：失效/即将失效/缺文号/缺来源/长期未复核"""
    return policy.health_report()


@app.post("/api/policies")
def api_policy_create(body: PolicyBody):
    if not str(body.fields.get("标题") or "").strip():
        raise HTTPException(400, "政策标题不能为空")
    try:
        return {"ok": True, **policy.create_policy(body.fields)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.put("/api/policies/{pid}")
def api_policy_update(pid: str, body: PolicyBody):
    try:
        return policy.update_policy(pid, body.fields)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.delete("/api/policies/{pid}")
def api_policy_delete(pid: str):
    try:
        return policy.delete_policy(pid)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.post("/api/policy/pack")
def api_policy_pack(body: PackBody):
    """生成政策检索任务包到 exchange/outbox（过脱敏闸；检索意图可含企业名用于查公开公示）"""
    try:
        p = policy.make_search_pack(body.区域, body.行业, body.补充要求, body.关联项目, body.检索意图)
    except RuntimeError as e:   # 脱敏拒绝
        raise HTTPException(400, str(e))
    return {"ok": True, "文件": p.name, "路径": str(p), "大小": p.stat().st_size}


@app.get("/api/policy/packs")
def api_policy_packs():
    """列出 exchange/outbox 里的任务包（按时间倒序），供界面取用"""
    out = []
    for f in sorted(policy.OUTBOX.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        out.append({"name": f.name,
                    "时间": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")})
    return out


# ── 脱敏 ──────────────────────────────────────────────────
@app.get("/api/desens/status")
def api_desens_status():
    d = CFG.get("脱敏", {})
    return {
        "启用": d.get("启用", True),
        "级别": d.get("级别", "严格"),
        "允许出网场景": d.get("允许出网场景", []),
        "禁止出网场景": d.get("禁止出网场景", []),
        "片段上限字数": d.get("片段上限字数", 3000),
        "规则": d.get("规则", {}),
        "代号随机": d.get("代号随机", True),
    }


@app.get("/api/desens/log")
def api_desens_log(limit: int = 200):
    """出网审计记录。程序当前不主动出网，记录主要来自任务包生成"""
    return desens.read_audit(limit)


class PreviewBody(BaseModel):
    文本: str = ""
    场景: str = "文本摘要"
    区域: str = ""


@app.post("/api/desens/preview")
def api_desens_preview(body: PreviewBody):
    """预览脱敏效果（不写审计日志）"""
    return desens.preview(body.文本, body.场景, body.区域)


@app.post("/api/desens/rotate")
def api_desens_rotate(keep: int = None):
    """按 config 的 保留份数 清理自动备份。整库备份与人工归档目录不动"""
    return desens.rotate_backup(keep)


@app.post("/api/policy/collect")
def api_policy_collect():
    """回收 exchange/inbox 里智能体产出的政策卡片"""
    return policy.collect_inbox()


@app.get("/api/policy/pack/{name}")
def api_policy_pack_download(name: str):
    p = policy.OUTBOX / name
    if not p.exists():
        raise HTTPException(404, "任务包不存在")
    return FileResponse(p, filename=name)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


def _check_paths():
    """启动路径自检（2026-11-02 迁移落定后加）：核验 config 关键路径，缺失即中文提示。
    只提示不退出——程序目录类缺失会自动创建；vault/各库缺失多半是迁移没落定，
    提示出来避免「静默建错地方」。路径口径全在 config.yaml，改配置即可，无需动代码。"""
    checks = [
        ("vault 根", Path(CFG["vault"]["根"])),
        ("数据目录", store.DATA),
        ("备份目录", Path(CFG["程序"]["备份目录"])),
        ("交换区 outbox", Path(CFG["程序"]["交换区"]["outbox"])),
        ("资料评审库", LIB_PATH / REPORT_SUBDIRS[0]),
        ("现场评审库", LIB_PATH / REPORT_SUBDIRS[1]),
        ("质量模式库", LIB_PATH / MODE_DIR_REL),
        ("条款库", LIB_PATH / CLAUSE_DIR),
    ]
    missing = [(name, p) for name, p in checks if not Path(p).exists()]
    if missing:
        print(f"[路径自检] ⚠ {len(missing)}/{len(checks)} 项未找到：")
        for name, p in missing:
            print(f"           - {name}：{p}")
        print("           配置在 config.yaml（程序.* / vault.根 / 库.社会兼职.落点）；"
              "若刚迁移，请确认目录真实位置后改配置。")
    else:
        print(f"[路径自检] {len(checks)} 项关键路径全部就绪")


if __name__ == "__main__":
    import uvicorn
    import socket
    import threading
    import webbrowser

    port = int(CFG["程序"]["端口"])
    # 启动前探测端口：已被占用（多半已有实例在跑）→ 友好提示后退出，不甩堆栈
    _sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _busy = _sock.connect_ex(("127.0.0.1", port)) == 0
    _sock.close()
    if _busy:
        print(f"端口 {port} 已被占用——工作台多半已在运行。")
        print(f"直接在浏览器打开：http://127.0.0.1:{port}")
        # 有人看护（控制台）才等回车，且最多 30 秒自动退；后台/管道场景直接退——
        # 2026-10-26 教训：无超时的 input() 会养出永不退出的僵尸实例（一天踩了三次）
        if sys.stdin.isatty():
            try:
                import msvcrt
                for _ in range(100):
                    if msvcrt.kbhit():
                        msvcrt.getch()
                        break
                    time.sleep(0.3)
            except Exception:
                pass
        raise SystemExit(0)
    _check_paths()
    rot = desens.rotate_backup()   # 启动时清理一次（A4 起即时轮转已兜底，此为双保险）
    print(f"评审工作台启动: http://127.0.0.1:{port}")
    print(f"台账数据: {store.ledger_file()}（{store.STORAGE_TYPE} 模式）")
    print(f"脱敏级别: {CFG.get('脱敏', {}).get('级别', '严格')} | 备份轮转: "
          f"自动 {rot['自动备份']['删除']} 删/{rot['自动备份']['保留']} 留, "
          f"代码 {rot['代码备份']['删除']} 删/{rot['代码备份']['保留']} 留")
    threading.Timer(1.5, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
