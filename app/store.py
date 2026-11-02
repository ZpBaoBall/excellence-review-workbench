# -*- coding: utf-8 -*-
"""
数据存储：台账（ledger）与 字典（dicts）的读写。

台账 + 字典已「内置平台」：不再是 Obsidian 里的 md，而是程序侧数据文件，
随程序一起备份（见 config 的「安全」段与 desens.rotate_backup）。
内容类（条款与心得 / 资料评审 / 现场评审 / 质量模式）仍存 md，由 Obsidian 管理。

存储类型（config「存储.类型」，2026-11-02 开源就绪）：
  json（默认）  ledger.json / dicts.json 两个文件；原子写 + 瞬锁退避重试
  sqlite        单文件 workbench.db（documents 表按 key 存 JSON 文档，事务写入）
                ——数据仍以 JSON 文档形态整体保存；按字段查询/多端并发属网络库范畴，
                留作社区共建（见 README「明确不做」）
两种模式只在本文件内分支，main.py / 前端 / 测试的调用口径（load/save）完全一致；
写前备份统一走 ledger_file()，main.py 的 _backup_file 两种模式都快照到正确文件。
"""
import json
import sqlite3
import time
import yaml
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((BASE / "config.yaml").read_text(encoding="utf-8"))
# 数据目录：台账/字典（换机器拷程序目录即带走）。
# 取 config「程序.数据目录」；未配置时回退程序侧 data/（仅剩缓存/日志等残渣）。
DATA = Path(CFG.get("程序", {}).get("数据目录") or (BASE / "data"))
STORAGE_TYPE = (CFG.get("存储") or {}).get("类型", "json")     # json | sqlite
LEDGER_JSON = DATA / "ledger.json"
DICTS_JSON = DATA / "dicts.json"
DB_PATH = DATA / "workbench.db"          # sqlite 模式单文件库

_DOC_KEYS = {"ledger", "dicts"}          # documents 表允许的 key（防误存）


def ledger_file():
    """台账当前的实际存储文件——json=ledger.json / sqlite=workbench.db。
    main.py 写前备份与启动自检统一走这里，两种模式口径一致。"""
    return DB_PATH if STORAGE_TYPE == "sqlite" else LEDGER_JSON


# ── sqlite 模式（documents 表：key → JSON 文档，事务写入） ──
def _doc_load(key, default):
    if key not in _DOC_KEYS or not DB_PATH.exists():
        return default
    con = sqlite3.connect(DB_PATH)
    try:
        row = con.execute("SELECT value FROM documents WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default
    finally:
        con.close()


def _doc_save(key, value):
    if key not in _DOC_KEYS:
        raise ValueError(f"未知存储 key：{key}")
    DATA.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    try:
        con.execute("CREATE TABLE IF NOT EXISTS documents"
                    " (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        con.execute("INSERT OR REPLACE INTO documents(key, value) VALUES (?, ?)",
                    (key, json.dumps(value, ensure_ascii=False)))
        con.commit()
    finally:
        con.close()


def load_ledger():
    """读台账（list[dict]，每项一条兼职项目索引）"""
    if STORAGE_TYPE == "sqlite":
        return _doc_load("ledger", [])
    if not LEDGER_JSON.exists():
        return []
    return json.loads(LEDGER_JSON.read_text(encoding="utf-8"))


def save_ledger(items):
    """写台账。
    json 模式：原子写（先落临时文件再替换，避免半截损坏）+ Windows 瞬锁退避重试；
    sqlite 模式：事务提交（天然原子）。
    Windows 上 replace 偶发 PermissionError[WinError 5]（杀毒/索引器瞬锁目标文件，
    连续快写时约 2/230 概率，QA 2026-10-24 实测）——指数退避重试 3 次；
    重试耗尽才抛错：写入失败必须可见，不静默吞（台账是唯一真源）。"""
    if STORAGE_TYPE == "sqlite":
        _doc_save("ledger", items)
        return
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = LEDGER_JSON.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    last = None
    for i in range(4):                        # 1 次正写 + 3 次退避（0.05/0.1/0.2s）
        try:
            tmp.replace(LEDGER_JSON)
            return
        except PermissionError as e:
            last = e
            time.sleep(0.05 * (2 ** i))
    raise last


def load_dicts():
    """读字典（区域/行业/类别 三张表的行数组）"""
    if STORAGE_TYPE == "sqlite":
        return _doc_load("dicts", {})
    if not DICTS_JSON.exists():
        return {}
    return json.loads(DICTS_JSON.read_text(encoding="utf-8"))


def save_dicts(d):
    """写字典（当前运行时只读；写入口使 sqlite 模式与未来的字典维护功能对称）"""
    if STORAGE_TYPE == "sqlite":
        _doc_save("dicts", d)
        return
    DATA.mkdir(parents=True, exist_ok=True)
    DICTS_JSON.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
