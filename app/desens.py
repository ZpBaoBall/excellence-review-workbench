# -*- coding: utf-8 -*-
"""脱敏模块 —— 原则：能不出网就不出网，出网必过闸，过闸必留痕。

硬约束：任何出网函数必须先调 mask()。本模块不提供「绕过」参数。
规则开关、代号词表、金额档位全部来自 config.yaml，改配置即时生效。

用法：
    from desens import mask, unmask, check_allowed, DesensError
    r = mask(text, scene="政策检索", vendor="workbuddy", task="示例企业政策检索")
    # r.text 已脱敏可外发；r.mapping 用于回收后还原
    plain = unmask(reply_text, r.mapping)

已知局限（机器无解，说明书已载明）：
  1. 唯一性描述抓不到 —— 「临港唯一一家做游艇维修的」没点名却能定位
  2. 小行业天然可识别 —— 全市游艇维修企业仅 11 家，行业+区域已足够窄
  因此 config 把「整篇报告生成」列进禁止出网场景，只走任务包人工搬运。
"""

import json
import random
import re
from datetime import datetime
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parent.parent
CONFIG = BASE / "config.yaml"

_CFG_CACHE = {"mtime": None, "data": None}


def _cfg():
    """读 config.yaml，按 mtime 缓存解析结果。

    备份轮转改即时触发后落在每次写入的热路径上，不能整篇重读；
    mtime 失效策略保持「config 唯一来源、改完即时生效」约定。
    注意：返回对象只读——调用方不得改，改了下一次缓存命中就是脏数据。
    """
    try:
        mt = CONFIG.stat().st_mtime
        if _CFG_CACHE["data"] is None or _CFG_CACHE["mtime"] != mt:
            _CFG_CACHE["data"] = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
            _CFG_CACHE["mtime"] = mt
        return _CFG_CACHE["data"]
    except OSError:
        return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


class DesensError(Exception):
    """拒绝出网时抛出，强制调用方处理，不允许静默放过"""


# ── 实体识别 ──────────────────────────────────────────────
CORP_SUFFIX = r"(?:股份有限公司|有限责任公司|有限公司|集团公司|总公司|分公司|实业公司|公司|集团|实业|工厂|厂)"
GOV_SUFFIX = ("部", "委", "局", "厅", "署", "院", "协会", "学会", "管委会",
              "委员会", "大学", "学院", "研究院", "研究所", "中心", "办公室")
CORP_RE = re.compile(r"[\u4e00-\u9fa5A-Za-z0-9·（）()]{2,20}?" + CORP_SUFFIX)

# 常见姓氏（用于判断称谓前后是不是人名，避免把「总经理表示」的「表示」当人名删掉）
SURNAMES = (
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章"
    "云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝安常乐于"
    "时傅皮齐康伍余元卜顾孟平黄和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒"
    "屈项祝董梁杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支"
    "柯管卢莫经房裘缪干解应宗丁宣邓郁单杭洪包诸左石崔吉钮龚程嵇邢滑裴陆荣翁荀羊惠甄曲"
    "家封芮储靳汲松井段富巫乌焦巴弓牧山谷车侯全班仰秋仲伊宫宁仇栾甘厉戎祖武符刘景詹束"
    "龙叶幸司郜黎薄印宿白怀蒲从鄂索咸籍赖卓蔺屠蒙池乔阴胥能苍双闻莘党翟贡劳姬申扶堵冉"
    "宰郦雍桑桂濮牛寿通边燕冀浦尚农温别庄晏柴瞿阎充慕连茹习宦艾鱼容向古易慎戈廖庾终暨"
    "居衡步都耿满弘匡国文寇广禄阙东欧沃利蔚越隆师巩聂晁冷辛阚那简饶曾沙养鞠须丰巢关蒯"
    "相查后红游权盖益桓公欧阳上官司马诸葛令狐"
)
TITLES = r"(?:总经理|董事长|副总经理|总监|经理|厂长|主任|部长|主管|秘书长)"
NAME_BEFORE = re.compile(r"[" + SURNAMES + r"][\u4e00-\u9fa5]{1,2}(?=" + TITLES + r")")
NAME_AFTER = re.compile(r"(" + TITLES + r")([" + SURNAMES + r"][\u4e00-\u9fa5]{1,2})")

# 地址：前缀限纯中文且不含行政区划字（否则会把「浦东新区临港新片区山海路」整段吞掉，
# 替换后只剩半个区名）。后缀必须是路/街/道等。
ADDR_RE = re.compile(
    r"(?:(?!区|市|省|县|镇|街道|片区|新区)[\u4e00-\u9fa5]){2,8}"
    r"(?:路|街|大道|道|巷|弄|工业区|开发区|园区)"
    r"\d{0,5}(?:号|号楼|弄|栋|幢|层|室)?")

PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)|(?<!\d)0\d{2,3}-?\d{7,8}(?!\d)")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
URL_RE = re.compile(r"https?://[\w\-./?=&%#:+~@]+|www\.[\w\-./?=&%#:+~@]+")
CREDIT_RE = re.compile(
    r"(?:统一社会信用代码|信用代码|纳税人识别号)\s*[:：]?\s*[0-9A-HJ-NPQRTUWXY]{18}")
CERTNO_RE = re.compile(
    r"(?:证书编号|证书号|注册号|批准文号|许可证号)\s*[:：]?\s*[\w\-〔〕()（）]{4,30}")
AMT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(亿元|亿|万元|万|元)")


def known_companies():
    """从台账（内置 data/ledger.json）读取已知企业全称，精确替换比正则兜底更准。
    台账已内置平台、不再是 md，这里改走 store.load_ledger()。"""
    names = []
    try:
        import store
        for d in store.load_ledger():
            n = str(d.get("企业名称") or "").strip().strip("\"'")
            if n and n not in ("待补", ""):
                names.append(n)
    except Exception:
        pass
    return sorted(set(names), key=len, reverse=True)


def _is_gov(s: str) -> bool:
    return any(s.endswith(g) for g in GOV_SUFFIX)


def collect_corps(out, known_all):
    """收集正文中出现的公司名：已知企业优先，正则兜底；去掉互相包含的短名"""
    cands = []
    for k in known_all:
        if k and k in out and k not in cands:
            cands.append(k)
    for m in CORP_RE.finditer(out):
        s = m.group(0)
        if _is_gov(s):
            continue
        if len(s) > 20:
            continue          # 太长多半裹带了上下文，跳过
        # 收敛：正则会从左往右裹带上下文（如「主要客户为上汽乘用车有限公司」），
        # 若其中包含已知企业名，从该已知名处截断
        for k in known_all:
            if k and k in s and s.index(k) > 0:
                s = s[s.index(k):]
                break
        if s not in cands:
            cands.append(s)
    # 去重：短名被长名包含时保留长名（如「上汽乘用车」被「上汽乘用车有限公司」覆盖），
    # 否则替换后会在代号后面漏出「有限公司」尾巴
    return sorted([a for a in cands if not any(b != a and a in b for b in cands)],
                  key=len, reverse=True)


def _wan(num: float, unit: str) -> float:
    if unit in ("亿", "亿元"):
        return num * 10000
    if unit in ("万", "万元"):
        return num
    return num / 10000


def _wan_label(v: float) -> str:
    if v >= 10000:
        return f"{v / 10000:g}亿"
    return f"{v:g}万"


def _tier_label(v: float, tiers) -> str:
    for lo, hi in tiers:
        if lo <= v < hi:
            left = "0" if lo == 0 else _wan_label(lo)
            if hi >= 999999999:
                return f">{left}"
            return f"{left}–{_wan_label(hi)}"
    return "金额区间"


def assign_aliases(names, cfg):
    """分配代号。代号随机=True 时每次重新洗牌，防止跨任务把同一家企业关联起来"""
    d = cfg["脱敏"]
    pool = list(d.get("代号表") or ["甲企业", "乙企业"])
    if d.get("代号随机", True):
        random.shuffle(pool)
    mapping, extra = {}, 0
    for i, n in enumerate(names):
        if i < len(pool):
            mapping[n] = pool[i]
        else:
            extra += 1
            mapping[n] = f"企业{extra:02d}"
    return mapping


def check_allowed(scene: str, length: int, check_len: bool = True):
    """出网前置检查，返回 (是否允许, 原因)

    check_len=False 只用于「指令类」文本（如任务包本身）——它不含企业材料，
    字数限制是针对材料片段的。是否豁免会写进审计日志的任务名，可事后核对。
    """
    d = _cfg()["脱敏"]
    if not d.get("启用", True) or d.get("级别", "严格") == "关闭":
        return True, "脱敏未启用"
    for s in (d.get("禁止出网场景") or []):
        if scene == s:
            return False, f"场景「{scene}」在禁止出网清单内，只能走任务包人工搬运"
    allowed = d.get("允许出网场景") or []
    if allowed and scene not in allowed:
        return False, f"场景「{scene}」不在允许出网清单内（允许：{'、'.join(allowed)}）"
    if check_len:
        cap = int(d.get("片段上限字数", 3000))
        if length > cap:
            return False, f"文本 {length} 字超过片段上限 {cap} 字，请拆分后再送"
    return True, ""


class Result:
    def __init__(self, text, mapping, stats, scene, vendor, task):
        self.text = text
        self.mapping = mapping
        self.stats = stats
        self.scene = scene
        self.vendor = vendor
        self.task = task

    @property
    def replaced(self):
        return sum(self.stats.values())

    def to_dict(self):
        return {"text": self.text, "mapping": self.mapping, "stats": self.stats,
                "scene": self.scene, "vendor": self.vendor, "task": self.task,
                "replaced": self.replaced}


def mask(text: str, scene: str, vendor: str = "-", task: str = "-",
         region: str = "", extra_names=None, audit: bool = True,
         check_len: bool = True, keep_companies: bool = False) -> Result:
    """出网前强制调用。不合规直接抛 DesensError。audit=False 用于界面预览（不写日志）。

    keep_companies=True 仅用于「政策检索」：政策是公开信息，委托方已确认
    检索企业名（查企业是否在公开公示中）不涉密，故跳过企业名称→代号。
    其余脱敏规则（人名/地址/电话/金额等）照常执行，审计留痕不受影响。"""
    cfg = _cfg()
    d = cfg["脱敏"]
    ok, why = check_allowed(scene, len(text or ""), check_len=check_len)
    if not ok:
        raise DesensError(why)
    if not d.get("启用", True) or d.get("级别", "严格") == "关闭":
        return Result(text or "", {}, {}, scene, vendor, task)

    rules = d.get("规则") or {}
    tiers = d.get("金额档位") or [[0, 1000], [1000, 10000]]
    out = text or ""
    stats = {}

    def bump(k, n=1):
        stats[k] = stats.get(k, 0) + n

    # 1 企业名称 → 代号（政策检索场景 keep_companies=True 时保留企业名，其余照常）
    mapping = {}
    if rules.get("企业名称") == "代号" and not keep_companies:
        known = list(known_companies())
        if extra_names:
            known = list(extra_names) + [n for n in known if n not in extra_names]
        cands = collect_corps(out, known)
        mapping = assign_aliases(cands, cfg)
        for real, alias in mapping.items():
            if real and real in out:
                c = out.count(real)
                out = out.replace(real, alias)
                bump("企业名称", c)

    # 2 人名 → 角色（先「人名+称谓」，再「称谓+人名」）
    if rules.get("人名") == "角色":
        out, n1 = NAME_BEFORE.subn("", out)
        out, n2 = NAME_AFTER.subn(lambda m: m.group(1), out)
        if n1 + n2:
            bump("人名", n1 + n2)

    # 3 直接删除类（放在地址之前，否则「证书编号」的「号」会被地址正则吃掉）
    for label, rx in (("电话", PHONE_RE), ("邮箱", EMAIL_RE), ("网址", URL_RE),
                      ("统一社会信用代码", CREDIT_RE), ("证书编号", CERTNO_RE)):
        if rules.get(label) == "删除":
            out, n = rx.subn("", out)
            if n:
                bump(label, n)

    # 4 地址 → 降精度到区
    if rules.get("地址") in ("隐藏", "删除"):
        # 只隐藏门牌路名，区名保留 —— 区名不敏感，且任务包的「区域」字段本就会单独给出。
        # 不做「替换成区名」是因为原文往往已带区名，替换会出现「浦东新浦东新区」这类重复。
        repl = "" if rules.get("地址") == "删除" else "【地址已脱敏】"
        out, n = ADDR_RE.subn(repl, out)
        if n:
            bump("地址", n)

    # 5 金额 → 区间
    if rules.get("金额") == "区间":
        out, n = AMT_RE.subn(lambda m: _tier_label(_wan(float(m.group(1)), m.group(2)), tiers), out)
        if n:
            bump("金额", n)

    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)

    if audit:
        _audit(scene, vendor, task, sum(stats.values()), len(text or ""), len(out), stats)
    return Result(out, mapping, stats, scene, vendor, task)


def unmask(text: str, mapping: dict) -> str:
    """回收外部产出后把代号换回真名"""
    if not text or not mapping:
        return text or ""
    out = text
    for real, alias in sorted(mapping.items(), key=lambda kv: -len(kv[1])):
        out = out.replace(alias, real)
    return out


def _audit(scene, vendor, task, replaced, src_len, out_len, stats):
    d = _cfg()["脱敏"]
    p = Path(d.get("审计日志") or (BASE / "data/desens-audit.log"))
    p.parent.mkdir(parents=True, exist_ok=True)
    detail = ";".join(f"{k}×{v}" for k, v in stats.items()) or "无"
    line = (f"{datetime.now():%Y-%m-%d %H:%M:%S}|{scene}|{vendor}|"
            f"替换{replaced}处({detail})|原文{src_len}字|脱敏后{out_len}字|{task}")
    with p.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    return line


def read_audit(limit=200):
    d = _cfg()["脱敏"]
    p = Path(d.get("审计日志") or (BASE / "data/desens-audit.log"))
    if not p.exists():
        return []
    rows = []
    for ln in [x.strip() for x in p.read_text(encoding="utf-8").splitlines() if x.strip()][-limit:]:
        c = ln.split("|")
        rows.append({
            "时间": c[0] if len(c) > 0 else "", "场景": c[1] if len(c) > 1 else "",
            "发给": c[2] if len(c) > 2 else "", "替换": c[3] if len(c) > 3 else "",
            "字数": (c[4] + " → " + c[5]) if len(c) > 5 else "",
            "任务": c[6] if len(c) > 6 else "",
        })
    return list(reversed(rows))


def preview(text: str, scene: str = "文本摘要", region: str = ""):
    """界面预览：复用 mask 的全部逻辑，只关掉审计写入"""
    try:
        r = mask(text, scene=scene, vendor="预览", task="预览", region=region, audit=False)
        return {"ok": True, "text": r.text, "stats": r.stats,
                "mapping": r.mapping, "replaced": r.replaced}
    except DesensError as e:
        return {"ok": False, "原因": str(e)}


def rotate_backup(keep: int = None):
    r"""按 config 的 保留份数 轮转清理。只动两类「时间戳-文件名」形式的自动备份：
    ① 自动备份（`\d{8}-\d{6}-` 时间戳前缀，ledger/MD 写前快照，任意扩展名）
    ② 代码备份（`index-`/`main-`/`importer-` 等字母前缀 + 内嵌时间戳段，**仅 .html/.py**）
    整库备份目录、人工归档目录、inbox-done-*.md 等政策回收回执一律不碰
    （双模式白名单 + is_file 天然排除；代码备份限扩展名是硬安全线——
     曾因未限扩展名把 inbox-done-*.md 当代码备份误删过 7 份，2026-10-23 修）。

    排序按文件名（时间戳编码在名字里）而非 mtime——同一秒内多个备份 mtime 相同会误删。
    返回分桶统计，便于界面/日志核对。"""
    cfg = _cfg()
    keep = keep if keep is not None else int(cfg.get("安全", {}).get("备份保留份数", 5))
    bk = Path(cfg["程序"]["备份目录"])
    if not bk.exists():
        return {"自动备份": {"删除": 0, "保留": 0}, "代码备份": {"删除": 0, "保留": 0},
                "说明": "备份目录不存在"}

    def _trim(pat):
        files = [f for f in bk.iterdir() if f.is_file() and pat.match(f.name)]
        files.sort(key=lambda f: f.name, reverse=True)   # 名字即时间戳，新的在前
        dead = files[keep:]
        for f in dead:
            try:
                f.unlink()
            except Exception:
                pass
        return {"扫描到": len(files), "保留": min(keep, len(files)), "删除": len(dead)}

    return {"自动备份": _trim(re.compile(r"^\d{8}-\d{6}-.+$")),
            "代码备份": _trim(re.compile(r"^[A-Za-z][\w-]*-\d{8}-\d{6}-.+\.(?:html|py)$"))}


if __name__ == "__main__":
    import sys
    demo = (
        "上海某某制造有限公司位于浦东新区临港新片区山海路123号，"
        "总经理张建国，电话 13812345678，邮箱 jinchi@example.com，网址 https://jinchi.example.com，"
        "统一社会信用代码 91310115MA1K3XXX8H，证书编号：XK06-001-00001。"
        "2024 年营业收入 3.2 亿元，主要客户为上汽乘用车有限公司。"
    )
    if len(sys.argv) > 1 and sys.argv[1] == "--rotate":
        print(json.dumps(rotate_backup(), ensure_ascii=False))
        sys.exit(0)
    try:
        r = mask(demo, scene="条款校验", vendor="demo", task="自测", region="浦东新区")
        print("=== 脱敏后 ===")
        print(r.text)
        print("\n=== 统计 ===", json.dumps(r.stats, ensure_ascii=False))
        print("=== 映射 ===", json.dumps(r.mapping, ensure_ascii=False))
        print("\n=== 还原验证 ===")
        print(unmask(r.text, r.mapping))
        print("\n=== 禁止场景验证 ===")
        try:
            mask(demo, scene="整篇报告生成", task="应当被拒绝")
            print("未拒绝 —— 异常！")
        except DesensError as e:
            print("已拒绝：", e)
    except DesensError as e:
        print("拒绝出网：", e)
