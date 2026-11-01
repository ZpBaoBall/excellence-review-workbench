# -*- coding: utf-8 -*-
"""自检公共助手（D3 自检固化，2026-10-25）

所有自检共用的三块能力：
  ① 数据态：LedgerGuard（备份→测试→删净→还原+md5 复核）——自包含，不依赖外部干净态
  ② 服务：ensure_service（已在跑就复用；没跑就用同一个解释器子进程拉起，跑完只杀自起的）
  ③ HTTP：get/post/put/del（urllib，UTF-8，瞬锁重试）

路径口径（2026-11-02 迁移落定）：vault / 台账一律读 config.yaml——
程序已独立于 vault 存放（程序=质量管理平台/卓越绩效，vault=ZpBaoball），
位置再变只改 config，本文件无需动。解释器优先用「跑本脚本的这个 python」。
"""
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent          # 程序根（卓越绩效/）
CFG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
VAULT = Path(CFG["vault"]["根"])                         # vault 根（config vault.根）
LEDGER = Path(CFG["程序"]["数据目录"]) / "ledger.json"    # 台账（config 程序.数据目录）
BASE = "http://127.0.0.1:8765"
PY = sys.executable                                      # 用跑本脚本的解释器（venv 自洽）


def luo(key):
    """config 库.社会兼职.落点 → vault 下绝对目录（资料评审库/现场评审库/质量模式库…）"""
    return VAULT / CFG["库"]["社会兼职"]["落点"][key]


def md5(p) -> str:
    h = hashlib.md5()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ── HTTP 客户端（瞬锁/抖动重试 2 次） ─────────────────────────
def _req(method, path, data=None, retry=2):
    url = BASE + path
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None
    last = None
    for i in range(retry + 1):
        try:
            req = urllib.request.Request(url, data=body, method=method,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                return {"_http": e.code, **json.loads(e.read().decode("utf-8"))}
            except Exception:
                return {"_http": e.code}
        except Exception as e:                          # 连接重置等：重试
            last = e
            time.sleep(0.4 * (i + 1))
    raise last


def get(path):
    return _req("GET", path)


def post(path, data=None):
    return _req("POST", path, data or {})


def put(path, data=None):
    return _req("PUT", path, data or {})


def delete(path):
    return _req("DELETE", path)


def quote(s):
    return urllib.parse.quote(str(s))


# ── 服务管理 ────────────────────────────────────────────────
def _probe(timeout=2) -> bool:
    try:
        req = urllib.request.Request(BASE + "/", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


class Service:
    """已在跑 → 复用，不杀（用户还要用）；没跑 → 子进程拉起，stop() 只杀自起的"""

    def __init__(self):
        self.proc = None

    def __enter__(self):
        if _probe():
            print("[服务] 已在运行，复用现有实例")
            return self
        print("[服务] 未运行，拉起子进程（自检专用，跑完自动关闭）…")
        self.proc = subprocess.Popen(
            [PY, str(ROOT / "app" / "main.py")], cwd=str(ROOT),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(40):
            if _probe():
                return self
            time.sleep(0.5)
        raise RuntimeError("服务 20 秒内未就绪")

    def __exit__(self, *exc):
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.kill()
            print("[服务] 自检拉起的子进程已关闭")


# ── 数据态守卫 ──────────────────────────────────────────────
class LedgerGuard:
    """备份当前 ledger → with 块内自由造/删 → 退出时还原 + md5 逐字节复核。

    用法：
        with LedgerGuard():
            ...  # 建测试卡、写测试 MD、随便造
        # 退出即还原，md5 不符会 raise（测试污染被当场抓住）
    """

    def __init__(self):
        self.bak = ROOT / "data" / "tmp-selftest-ledger.json"
        self.orig_md5 = None

    def __enter__(self):
        self.bak.parent.mkdir(parents=True, exist_ok=True)
        self.orig_md5 = md5(LEDGER)
        self.bak.write_bytes(LEDGER.read_bytes())
        return self

    def __exit__(self, *exc):
        self.bak.replace(LEDGER)
        now = md5(LEDGER)
        if now != self.orig_md5:
            raise RuntimeError(f"ledger 还原后 md5 不一致：{self.orig_md5} → {now}（测试污染！）")
        self.bak.unlink(missing_ok=True)


# ── 断言骨架 ────────────────────────────────────────────────
class Checker:
    def __init__(self):
        self.rows = []

    def check(self, name, cond, detail=""):
        cond = bool(cond)
        self.rows.append((name, cond, str(detail)))
        print(f"  {'PASS' if cond else 'FAIL'} | {name}" + (f" | {detail}" if detail else ""))
        return cond

    def eq(self, name, got, want):
        return self.check(name, got == want, f"got={got!r} want={want!r}")

    def summary(self, title="自检结果"):
        n = len(self.rows)
        bad = [r for r in self.rows if not r[1]]
        print(f"\n{'=' * 56}\n{title}: {n - len(bad)}/{n} 通过")
        for name, _, detail in bad:
            print(f"  FAIL | {name} | {detail}")
        return 0 if not bad else 1


def cards():
    """台账全量卡片"""
    return get("/api/projects?all=1")


def card(pid):
    for c in cards():
        if str(c.get("id")) == str(pid):
            return c
    return None
