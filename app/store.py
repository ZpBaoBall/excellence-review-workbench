# -*- coding: utf-8 -*-
"""
数据存储：台账（ledger.json）与 字典（dicts.json）的读写。

台账 + 字典已「内置平台」：不再是 Obsidian 里的 md，而是程序侧 JSON 文件，
随程序一起备份（见 config 的「安全」段与 desens.rotate_backup）。
内容类（条款与心得 / 资料评审 / 现场评审 / 质量模式）仍存 md，由 Obsidian 管理。
"""
import json
import time
import yaml
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((BASE / "config.yaml").read_text(encoding="utf-8"))
# 数据目录：台账/字典（git 跟踪，随知识库文件夹走，换机器拷 vault 即带走）。
# 取 config「程序.数据目录」；未配置时回退程序侧 data/（仅剩缓存/日志等残渣）。
DATA = Path(CFG.get("程序", {}).get("数据目录") or (BASE / "data"))
LEDGER_JSON = DATA / "ledger.json"
DICTS_JSON = DATA / "dicts.json"


def load_ledger():
    """读台账（list[dict]，每项一条兼职项目索引）"""
    if not LEDGER_JSON.exists():
        return []
    return json.loads(LEDGER_JSON.read_text(encoding="utf-8"))


def save_ledger(items):
    """写台账（原子写：先落临时文件再替换，避免半截损坏）。

    Windows 上 replace 偶发 PermissionError[WinError 5]（杀毒/索引器瞬锁目标文件，
    连续快写时约 2/230 概率，QA 2026-10-24 实测）——指数退避重试 3 次；
    重试耗尽才抛错：写入失败必须可见，不静默吞（台账是唯一真源）。"""
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
    if not DICTS_JSON.exists():
        return {}
    return json.loads(DICTS_JSON.read_text(encoding="utf-8"))
