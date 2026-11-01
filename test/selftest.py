# -*- coding: utf-8 -*-
"""API 级自检（D3 自检固化，2026-10-25）

覆盖 5 类核心 + 提取回归（从 pwtest2-10 共 9 个临时目录收编）：
  S0 提取规则回归   三样本 docx（B45条款/五同复刻/锦持式样）+ 粘贴切分——纯函数级，不起服务
                    （2026-10-27 增：H4 概述双向兼容、_md_bold 空加粗、终版折叠 merge_onsite_final）
                    （2026-10-27 增：派生伪条目——优势栏回退/报告主要优势·建议条款/往返/建块/去重/折叠）
  S1 台账 CRUD+判重 建/改/删 + 同企业同年份同奖项跳过 + 跨年不误杀
  S2 按年归位      新建不传历史项目 → 按企业名自动兜底关联
  S3 备份轮转双桶   rotate 结构 + inbox-done 回执不误删 + 归档目录不碰
  S4 上传即删      /api/import 读完删临时文件（A4 行为）
  S5 复盘写入链     paste-extract → write-review(现场) → review-note → export-onsite-docx
                    → 终版链：更新同一现场文件（不新建）+ 折叠旧现场核实信息 + 归口唯一化删文审
                    → 终版已写=写入日期（复盘门禁信号源，仅终版写入置位）
  S5b 阶段一链      write-onsite（条款核实+信息导出）→ 终版已写不置位（复盘保持灰）
  S5c 复盘闭环链     终版后：practice-confirm（MD 落痕+台账「做法确认」）→ mode-draft（40 库+
                    台账「模式草稿」）→ review-note（台账「四问已答」）→ write-onsite 400 关门
  S7 派生伪条目链   report-terms 读取派生（报告主要优势/建议条款·大条款）+ 优势栏回退
                    → onsite-note 保存落盘（优势/可改进之处=节全文，2026-10-28 内容落盘）
                    → 重读 round-trip + 去重 → 导出含伪条目三栏 → 自愈回填空块（幂等/只填空行）
  S8 归档与配置     PUT 阶段=归档（复盘 tab 归档按钮同接口）+ config 预留模块删除核查

数据态：全量测试包在 LedgerGuard 里（备份→造→删净→还原+md5 复核），
测试 MD 造在 20/30/40 库，退出前手动删净（只删本测试造的，文件名带 ST 标记）。
服务：已在跑就复用；没跑就子进程拉起，跑完只杀自起的。

运行：venv python test/selftest.py      （退出码 0=全过，1=有 FAIL）
"""
import io
import os
import re
import sys
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))       # import _helper
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

import _helper as H  # noqa: E402

CK = H.Checker()
MD20, MD30, MD40 = H.luo("资料评审库"), H.luo("现场评审库"), H.luo("质量模式库")
FIX = Path(__file__).resolve().parent / "fixtures"

# 测试企业名统一带「ST自检」标记——清理时按标记删，绝不误伤真实数据
ST_COMP = "上海ST自检数据有限公司"
ST_COMP2 = "上海ST自检历史有限公司"


def section(title):
    print(f"\n{'─' * 56}\n{title}")


# ── S0 提取规则回归（纯函数级） ─────────────────────────────
def s0_extract_rules():
    section("S0 提取规则回归（三样本 + 粘贴切分 + 句子级方法）")
    if not (FIX / "B45条款样本.docx").exists():
        import subprocess
        subprocess.run([H.PY, str(Path(__file__).resolve().parent / "make_docx.py")],
                       check=True, capture_output=True)
    import docx_extract as de

    # ① B45 条款样本：小标题段 + 段内加粗
    r = de.extract_report(str(FIX / "B45条款样本.docx"))
    op = r["意见结论"]
    CK.eq("S0a B45 优势条目数", len(op["主要优势"]), 2)
    CK.eq("S0b B45 建议条目数", len(op["主要改进建议"]), 1)
    CK.eq("S0c B45 加粗片段（半句加粗缝合成 1 句）", op["主要优势"][0]["加粗片段"],
          ["“技术创新驱动、质量品牌引领”总体战略核心壁垒"])
    CK.eq("S0d B45 自检覆盖", r["自检"]["覆盖"], "100%")
    CK.check("S0e B45 无模式段", len(r["模式"]) == 0)

    # ② 五同复刻样本：1列多行表 + 中文序号标题句 + 质量模式尾段
    r2 = de.extract_report(str(FIX / "五同复刻样本.docx"))
    op2 = r2["意见结论"]
    CK.eq("S0f 五同 优势条目数", len(op2["主要优势"]), 2)
    CK.eq("S0g 五同 序号字段", op2["主要优势"][0].get("序号"), "（一）")
    CK.check("S0h 五同 序号标题句保留", "人才发展规划" in op2["主要优势"][0]["标题"])
    CK.eq("S0i 五同 模式段拆出", len(r2["模式"]), 1)
    CK.eq("S0j 五同 自检覆盖", r2["自检"]["覆盖"], "100%")

    # ③ 粘贴切分（组员入口）
    paste = ("一、基本情况\n某企业为自检粘贴样本。\n\n二、主要优势\n"
             "（一）战略清晰聚焦\n公司制定三年发展战略，建立**战略解码机制**。\n"
             "顾客响应迅速\n建立**24小时投诉响应**机制。\n")
    op3 = de.split_pasted(paste)
    CK.eq("S0k 粘贴 优势条目数", len(op3["主要优势"]), 2)
    CK.eq("S0l 粘贴 加粗片段（星号法）", op3["主要优势"][0]["加粗片段"], ["战略解码机制"])
    CK.eq("S0m 粘贴 小标题断条", op3["主要优势"][1]["标题"], "顾客响应迅速")

    # ④ 锦持式样本（2026-10-26）：概述段（≤50字、可带句号）+ 展开段（加粗=方法）
    r4 = de.extract_report(str(FIX / "锦持式样样本.docx"))
    op4 = r4["意见结论"]
    CK.eq("S0n 锦持 优势条目数", len(op4["主要优势"]), 3)
    CK.eq("S0o 锦持 建议条目数", len(op4["主要改进建议"]), 1)
    CK.check("S0p 锦持 概述段识别（句号结尾也认）",
             op4["主要优势"][0]["标题"].endswith("。")
             and "深耕专业领域" in op4["主要优势"][0]["标题"],
             repr(op4["主要优势"][0]["标题"][:30]))
    CK.check("S0q 锦持 方法只来自展开段（3 个完整句）",
             len(op4["主要优势"][0]["加粗片段"]) == 3
             and not any("深耕" in f for f in op4["主要优势"][0]["加粗片段"])
             and all(f.endswith("。") for f in op4["主要优势"][0]["加粗片段"]),
             str(op4["主要优势"][0]["加粗片段"])[:80])
    CK.eq("S0r 锦持 自检覆盖", r4["自检"]["覆盖"], "100%")

    # ⑤ 锦持式样全链：MD 分节 bullet（概述加粗行）+ 做法索引（概述↔方法配对）
    import review_writer as rw
    op4["主要优势"][0]["条款"] = "4.3"
    op4["主要优势"][1]["条款"] = "4.4.3"
    md = rw.build_md("上海锦持汽车零部件再制造有限公司", "2026-08-25", "GBT19580 卓越",
                     op4, {"4.3": "顾客与市场", "4.4.3": "技术与知识"})
    CK.check("S0s MD H4 = 概述小节标题（2026-10-27 新格式：H3 条款→H4 概述）",
             "#### 深耕专业领域" in md and "\n**公司实施" in md
             and "- **" not in md, md[md.find("### 4.3"):][:120])
    CK.check("S0s2 现场终版 frontmatter 带现场日期",
             "现场日期: 2026-08-25" in rw.build_md("甲", "2026-08-25", "GBT19580 卓越", op4,
                                                   doc_title="现场评审"), "")
    pr = rw.parse_practices(md)
    adv = [g for g in pr if g["类型"] == "优势"]
    CK.eq("S0t 做法索引：方法挂到所属概述（3 组含未归位）", len(adv), 3)
    # 2026-10-30 R2 用户拍板：方法来源从「加粗片段」换成「正文全文按。切句」——
    # 4.3 展开段全文 5 句（3 句加粗 + 2 句未加粗）→ 5 法；4.4.3 全文 3 句 → 3 法
    CK.check("S0u 配对正确：4.3→深耕 5 法 / 4.4.3→构建 3 法（全文切句，含未加粗句）",
             adv[0]["标题"] == "4.3 顾客与市场"
             and adv[0]["条目"][0]["概述"].startswith("深耕专业领域")
             and len(adv[0]["条目"][0]["方法"]) == 5
             and adv[1]["标题"] == "4.4.3 技术与知识"
             and len(adv[1]["条目"][0]["方法"]) == 3,
             str([(g["标题"], len(g["条目"][0]["方法"])) for g in adv]))
    # R2 新结构：全文非空且不含 ** 星号（方法从全文切出，句尾带「。」）
    CK.check("S0u2 R2 条目含「全文」（纯文本、无加粗星号、保留换行）",
             "**" not in adv[0]["条目"][0]["全文"]
             and adv[0]["条目"][0]["全文"].startswith("公司实施“技术创新驱动")
             and all(m.endswith("。") for m in adv[0]["条目"][0]["方法"]),
             repr(adv[0]["条目"][0]["全文"][:40]))
    # R2 根因：正文**没有加粗**的终版（锦持式样）也能出方法（旧逻辑此处全 0）
    no_bold = rw.parse_practices("## 主要优势\n\n### 4.2 战略\n\n#### 概述甲\n\n"
                                 "公司建立战略解码机制。并明确责任主体与节奏。\n")
    CK.check("S0u3 R2 无加粗正文也能出方法（锦持终版 0 方法的根因已修）",
             len(no_bold[0]["条目"][0]["方法"]) == 2
             and no_bold[0]["条目"][0]["全文"] == "公司建立战略解码机制。并明确责任主体与节奏。",
             str(no_bold[0]["条目"][0]))
    # R2 回退：条目没有正文（旧 bullet 只有加粗概述）→ 方法退回加粗切句，不丢
    only_ov = rw.parse_practices("## 主要优势\n\n### 4.2 战略\n\n- **只有概述没有正文。**\n")
    CK.check("S0u4 R2 无正文条目回退旧加粗切句逻辑（方法不丢）",
             only_ov[0]["条目"][0]["方法"] == ["只有概述没有正文。"]
             and only_ov[0]["条目"][0]["全文"] == "", str(only_ov[0]["条目"][0]))

    # ⑤b H4 双向兼容（2026-10-27 用户定：旧 bullet 格式不能读不了）
    old_md = ("## 主要优势\n\n### 4.3 顾客与市场\n\n"
              "- **深耕专业领域，聚集关键客户群体，不断增进细分市场的竞争优势。**\n"
              "  公司**实施**** ****“技术创新驱动、场景融合赋能”**的总体战略，以技术创新构建核心壁垒。\n\n"
              "- **构建全价值链再制造能力体系。**\n"
              "  公司**依托核心能力，构建了全流程再制造工艺链。**\n")
    pro = rw.parse_practices(old_md)
    CK.check("S0t2 旧 bullet 兼容：概述+方法照常取出",
             len(pro) == 1 and pro[0]["标题"] == "4.3 顾客与市场"
             and len(pro[0]["条目"]) == 2
             and pro[0]["条目"][0]["概述"].startswith("深耕专业领域")
             and pro[0]["条目"][1]["概述"] == "构建全价值链再制造能力体系。"
             and len(pro[0]["条目"][1]["方法"]) == 1,
             str([(i["概述"][:12], len(i["方法"])) for i in pro[0]["条目"]]))
    pro2 = rw.parse_practices("## 主要优势\n\n- 甲公司**实施战略。**\n")   # 旧平铺（无 ### 分节）
    CK.check("S0t3 旧平铺兼容（无分节也取方法；R2 后按全文切句）",
             pro2[0]["标题"] == "（未按条款分节）"
             and pro2[0]["条目"][0]["方法"] == ["甲公司实施战略。"])
    # ⑤b2 节名变体兼容（2026-10-27 QA 抓跟进）：手工收库报告用 Word 原措辞
    #      「## 主要优势与创新点」——前缀匹配也要识别（用户已按新结构手工加粗，
    #      实测文件：政府质量奖-现场评审库/20260828-上海五同同步带有限公司.md）
    var = rw.parse_practices("## 主要优势与创新点\n\n围绕战略方向。\n\n"
                             "  公司**建立人才发展规划**，近三年引进人才30余人。\n")
    CK.check("S0t6 节名变体「主要优势与创新点」按优势识别（无分节也取方法）",
             len(var) == 1 and var[0]["类型"] == "优势"
             and var[0]["标题"] == "（未按条款分节）"
             and var[0]["条目"][0]["方法"] == ["围绕战略方向。",
                                              "公司建立人才发展规划，近三年引进人才30余人。"], str(var))
    var2 = rw.parse_practices("## 主要优势与创新点\n\n### 4.4.1 人力资源\n\n"
                              "- **概述行**\n  公司**实施继任计划。**\n")
    CK.check("S0t6b 变体节名 + 条款分节照常切组",
             var2[0]["标题"] == "4.4.1 人力资源"
             and var2[0]["条目"][0]["方法"] == ["公司实施继任计划。"])
    var3 = rw.parse_practices("## 组织基本情况\n\n无关正文。\n\n## 质量模式\n\n- **质量模式：甲**\n")
    CK.check("S0t7 无关节名不误扫（放宽有界）", len(var3) == 0, str(var3))
    # ⑤c _md_bold 根因修复：空加粗 run（单独加粗的空格）不产 **，防 MD 解析失败裸露 **
    CK.eq("S0t4 _md_bold 空加粗按普通文本",
          de._md_bold([{"text": "甲", "bold": False}, {"text": "  ", "bold": True},
                       {"text": "乙", "bold": True}]),
          "甲  **乙**")
    CK.eq("S0t5 _md_bold 非空加粗仍加星", de._md_bold([{"text": "甲", "bold": True}]), "**甲**")

    # ⑥ 句子级方法规则（2026-10-27 用户约定）：加粗按「。」断句，一句一方法
    CK.eq("S0v 半句加粗缝合成 1 个方法",
          de._bold_frags([{"text": "实施", "bold": True}, {"text": "非加粗粘连", "bold": False},
                          {"text": "“战略句”", "bold": True}]),
          ["实施“战略句”"])
    CK.eq("S0w 按。切句 + 未终止尾巴保留",
          de._bold_frags([{"text": "第一句。", "bold": True}, {"text": "第二句。", "bold": True},
                          {"text": "未终止尾巴", "bold": True}]),
          ["第一句。", "第二句。", "未终止尾巴"])
    CK.eq("S0x 空/纯。片段丢弃",
          de._bold_frags([{"text": "   ", "bold": True}, {"text": "。", "bold": True},
                          {"text": "。", "bold": True}, {"text": "真方法句。", "bold": True}]),
          ["真方法句。"])
    CK.eq("S0x2 纯标点片段丢弃（句尾孤立半角 .，真文件遗留形态）",
          de._bold_frags([{"text": "第一法。", "bold": True}, {"text": ".", "bold": True}]),
          ["第一法。"])
    CK.eq("S0x3 纯标点片段丢弃（、，。不成方法）",
          de._bold_frags([{"text": "、", "bold": True}, {"text": "，", "bold": True},
                          {"text": "。", "bold": True}]),
          [])
    CK.eq("S0x4 引号片段不误杀（含文字即留）",
          de._bold_frags([{"text": "“引号片段”", "bold": True}]),
          ["“引号片段”"])
    op5 = de.split_pasted("二、主要优势\n（一）战略清晰聚焦\n"
                          "公司制定三年发展战略，建立**战略解码机制。明确责任主体与节奏。**持续迭代复盘。\n")
    CK.eq("S0y 粘贴 星号内多句切分", op5["主要优势"][0]["加粗片段"],
          ["战略解码机制。", "明确责任主体与节奏。"])
    pr2 = rw.parse_practices("## 主要优势\n\n### 4.2 战略\n\n"
                             "- **战略概述**\n  公司制定**战略解码机制。**并**明确责任主体与节奏。**对**尾巴。**\n")
    # 2026-10-30 R2：方法从「正文全文」切句（含非加粗部分），故是完整句而非加粗片段
    CK.eq("S0z 做法索引 全文按。切句（R2：含非加粗部分的完整句）", pr2[0]["条目"][0]["方法"],
          ["公司制定战略解码机制。", "并明确责任主体与节奏。", "对尾巴。"])
    pr3 = rw.parse_practices("## 主要优势\n\n### 4.2 战略\n\n"
                             "- **战略概述**\n  公司制定**战略解码机制。****.**\n")
    CK.eq("S0z2 做法索引 纯标点方法丢弃", pr3[0]["条目"][0]["方法"],
          ["公司制定战略解码机制。"])

    # ⑥ 终版折叠 merge_onsite_final（2026-10-27 用户定；2026-10-28 规则修订：普通条款块
    #    整块折叠保留全部行，伪条目块/开场白块不折叠、live 留在「现场核实信息」节里）
    old_final_md = (
        "---\n标准: GBT19580 卓越\n企业名称: 上海ST自检数据有限公司\n"
        "报告日期: 2026-09-18\n现场日期: 2026-08-25\n---\n\n"
        "# 上海ST自检数据有限公司 · 现场评审\n\n"
        "## 基本情况\n\n旧基本情况段落。\n\n"
        "## 主要优势\n\n### 4.3 顾客与市场\n\n- **旧优势概述**\n  旧展开。\n\n"
        "## 主要改进建议\n\n### 4.5 过程管理\n\n- **旧建议**\n\n"
        "## 提取日志\n\n- 2026-10-27 10:27 提取自 旧文件.docx：优势 3 条 / 建议 1 条\n\n"
        "## 现场核实信息\n\n"
        "### 开场白\n\n- 现场核实：组长开场内容（live 不折叠）\n\n"
        "### 4.2 战略\n\n相关条款：[[GBT19580-卓越-4.2战略]]\n\n"
        "- 文审优势：1. 旧文审优势内容（应保留进折叠）。\n"
        "- 可改进之处：建议量化战略目标。\n"
        "- 现场核实：战略解码机制运行有效。\n\n"
        "## 复盘沉淀\n\n> [!note]- 2026-10-28 复盘沉淀\n> 手写复盘内容\n")
    prog_final = rw.build_md("上海ST自检数据有限公司", "2026-08-25", "GBT19580 卓越",
                             {"基本情况": "新基本情况。",
                              "主要优势": [{"标题": "新优势概述", "文本": "公司**实施新方法。**",
                                            "条款": "4.3"}],
                              "主要改进建议": []},
                             {"4.3": "顾客与市场"}, doc_title="现场评审")
    out_final = rw.merge_onsite_final(old_final_md, prog_final,
                                      "2026-10-30 11:00 提取自 终版样本.docx：优势 1 条 / 建议 0 条",
                                      "2026-08-25")
    fold = out_final[out_final.find("> [!note]- 原现场核实记录"):]
    live_sec = out_final[out_final.find("## 现场核实信息"):]
    live_sec = live_sec[:live_sec.find("\n## ")] if "## 现场核实信息" in out_final else ""
    CK.check("S0z3 终版：程序节被新提取覆盖",
             "#### 新优势概述" in out_final and "旧优势概述" not in out_final)
    CK.check("S0z4 终版：普通条款块不在原位保留（开场白块 live 留下）",
             "### 4.2 战略" not in live_sec and "组长开场内容" in live_sec,
             live_sec[:120].replace("\n", "⏎"))
    CK.check("S0z5 折叠块在文尾（提取日志/复盘沉淀之后）",
             out_final.find("> [!note]- 原现场核实记录") > out_final.rfind("## 复盘沉淀")
             and out_final.find("> [!note]- 原现场核实记录") > out_final.rfind("## 提取日志"),
             out_final[-80:].replace("\n", "⏎"))
    CK.check("S0z6 折叠块标题带文件名日期",
             "> [!note]- 原现场核实记录（2026-08-25，终版写入时折叠归档）" in fold, "")
    # 2026-10-30 R1 用户拍板：块内**只留三栏**——优势（标签统一写「优势」，源「文审优势」
    # 也认）/ 可改进之处 / 现场核实；丢掉「相关条款：[[...]]」双链行；保留块标题行
    CK.check("S0z7 R1 折叠只留三栏：块标题+优势/可改进之处/现场核实，开场白不折叠",
             "> ### 4.2 战略" in fold
             and "> - 优势：1. 旧文审优势内容（应保留进折叠）。" in fold
             and "> - 可改进之处：建议量化战略目标。" in fold
             and "> - 现场核实：战略解码机制运行有效。" in fold
             and "开场白" not in fold and "组长开场内容" not in fold, fold[:200])
    CK.check("S0z7b R1 折叠块丢掉「相关条款：[[...]]」双链行（用户：存档只留我负责的部分）",
             "相关条款" not in fold and "[[GBT19580-卓越-4.2战略]]" not in fold, fold[:200])
    CK.check("S0z7c R1 折叠块不再出现旧标签「文审优势」（写出统一为「优势」）",
             "- 文审优势：" not in fold, "")
    # 优势标签双兼容（派生伪条目块落的是 `- 优势：`）：同样只留三栏，空值行也保留
    fold_pseudo = rw._fold_onsite_terms(
        "### 4.3.2 顾客和市场的了解\n\n"
        "相关条款：[[GBT19580-卓越-4.3.2顾客和市场的了解]]\n\n"
        "- 优势：派生优势全文。\n- 可改进之处：\n- 现场核实：已核实。\n", "2026-08-25")
    CK.check("S0z7d R1「- 优势：」标签同样只留三栏（空值行也保留、丢双链行）",
             "> - 优势：派生优势全文。" in fold_pseudo
             and "> - 可改进之处：" in fold_pseudo
             and "> - 现场核实：已核实。" in fold_pseudo
             and "相关条款" not in fold_pseudo, fold_pseudo)
    # 派生伪条目块（报告主要优势条款·*）是 live 块——不进折叠
    fold_live = rw._fold_onsite_terms(
        "### 报告主要优势条款·4.3 顾客与市场\n\n- 优势：伪条目全文。\n", "2026-08-25")
    CK.eq("S0z7e R1 派生伪条目块不折叠（live 原位保留，与开场白同规则）", fold_live, "")
    CK.check("S0z8 折叠块：三栏值取自块内跨行捕获（与导出 grab() 同口径）",
             "> - 可改进之处：建议量化战略目标。" in fold
             and "> - 现场核实：战略解码机制运行有效。" in fold, "")
    CK.check("S0z9 手写节（复盘沉淀）原位保留", "## 复盘沉淀" in out_final and "手写复盘内容" in out_final)
    CK.check("S0z10 提取日志正常追加",
             len(re.findall(r"提取自", out_final)) == 2
             and "2026-10-30 11:00 提取自 终版样本.docx" in out_final)
    CK.check("S0z11 无旧现场 MD 不折叠",
             "[!note]- 原现场核实记录" not in rw.merge_onsite_final("", prog_final, "log"))

    # ⑦ 「我负责的条款」派生伪条目（2026-10-27 用户定）：细条款按条款号前两段
    #    （4.3.2→4.3）命中「## 主要优势」/「## 主要改进建议」的 H3 大条款时，列表
    #    末尾追加「报告主要优势条款·4.3 / 报告主要建议条款·4.5」；条款条目优势栏
    #    回退用块内自己的「文审优势」行（不再用节全文预填）；伪条目内容读取时现派生
    import main as M
    dv_md = (
        "# 上海ST自检数据有限公司 · 现场评审\n\n"
        "## 主要优势\n\n### 4.3 顾客与市场\n\n#### 深耕顾客细分市场\n\n"
        "公司**实施**顾客细分方法，建立顾客信息库。\n\n"
        "### 4.4.1 人力资源\n\n#### 优化职能配置\n\n公司**制定**人力资源规划。\n\n"
        "## 主要改进建议\n\n### 4.5 过程管理\n\n**建议完善过程管理制度引用。**\n\n"
        "## 现场核实信息\n\n### 4.3.2 顾客和市场的了解\n\n"
        "- 文审优势：块内自有优势：按区域细分四大市场。\n"
        "- 可改进之处：建议展开需求了解方法。\n- 现场核实：\n\n"
        "### 4.5.1 过程管理的实施\n\n- 可改进之处：建议补充过程绩效指标。\n- 现场核实：\n\n"
        "## 复盘沉淀\n\n> [!note]- 2026-10-28 复盘沉淀\n> 手写复盘内容\n")
    dv_terms = M._onsite_terms_with_derived(dv_md)
    CK.eq("S0z12 派生条目顺序（细条款→伪优势→伪建议，追加末尾）",
          [t["条款号"] for t in dv_terms],
          ["4.3.2", "4.5.1", "报告主要优势条款·4.3", "报告主要建议条款·4.5"])
    CK.check("S0z13 优势栏回退：细条款用块内自己的文审优势行（非节全文）",
             dv_terms[0]["优势"] == "块内自有优势：按区域细分四大市场。"
             and "深耕顾客细分市场" not in dv_terms[0]["优势"])
    CK.check("S0z14 伪优势条目：条款号/条款名取 H3，优势=主要优势节全文（纯文本化）",
             dv_terms[2]["条款名"] == "顾客与市场"
             and dv_terms[2]["优势"] == "深耕顾客细分市场\n公司实施顾客细分方法，建立顾客信息库。",
             repr(dv_terms[2]["优势"]))
    CK.check("S0z15 伪建议条目：可改进之处=主要改进建议节全文",
             dv_terms[3]["条款名"] == "过程管理"
             and dv_terms[3]["可改进之处"] == "建议完善过程管理制度引用。")
    CK.check("S0z16 三段 H3（4.4.1）不触发伪条目（列大条款即可）",
             not any(t["条款号"] == "报告主要优势条款·4.4.1" for t in dv_terms))
    # 保存建块 + 往返 + 去重（2026-10-28 用户定内容落盘：优势行带节全文，不再空行）
    dv_saved = M._write_note_into_md(dv_md, "报告主要优势条款·4.3", "组长核实：顾客细分运行有效。")
    CK.check("S0z17 保存落盘：优势行=主要优势节全文 + 现场核实行（建在节末尾、复盘沉淀之前）",
             "### 报告主要优势条款·4.3 顾客与市场\n\n"
             "- 优势：深耕顾客细分市场\n公司实施顾客细分方法，建立顾客信息库。\n"
             "- 可改进之处：\n- 现场核实：组长核实：顾客细分运行有效。" in dv_saved
             and dv_saved.index("### 报告主要优势条款·4.3") > dv_saved.index("### 4.5.1")
             and dv_saved.index("### 报告主要优势条款·4.3") < dv_saved.index("## 复盘沉淀"),
             dv_saved[dv_saved.index("### 报告主要优势条款"):][:120])
    dv_rt = [t for t in M._parse_onsite_terms(dv_saved)
             if t["条款号"] == "报告主要优势条款·4.3"]
    CK.eq("S0z18 round-trip：伪块重读条款号正确（不散架）", len(dv_rt), 1)
    CK.check("S0z18b round-trip：条款名/现场核实重读正确",
             bool(dv_rt) and dv_rt[0]["条款名"] == "顾客与市场"
             and dv_rt[0]["现场核实"] == "组长核实：顾客细分运行有效。")
    dv_terms2 = M._onsite_terms_with_derived(dv_saved)
    dv_pa2 = next(t for t in dv_terms2 if t["条款号"] == "报告主要优势条款·4.3")
    CK.check("S0z19 去重：已有伪块不重复追加 + 优势取块内落盘内容（落盘优先、单一真源下沉到块）",
             [t["条款号"] for t in dv_terms2].count("报告主要优势条款·4.3") == 1
             and dv_pa2["优势"] == "深耕顾客细分市场\n公司实施顾客细分方法，建立顾客信息库。"
             and dv_pa2["现场核实"] == "组长核实：顾客细分运行有效。")
    # 自愈旧数据（2026-10-28 用户定）：旧代码建的空行块 → 读取路径回填；幂等；非空不动
    dv_empty = dv_saved.replace(
        "- 优势：深耕顾客细分市场\n公司实施顾客细分方法，建立顾客信息库。", "- 优势：")
    CK.check("S0z19a 前置：回退成旧代码的空行块", "- 优势：\n- 可改进之处：" in dv_empty)
    healed, n_fill = M._fill_pseudo_block_lines(dv_empty)
    CK.check("S0z19b 自愈：空优势行回填节全文（可改进之行仍留空）",
             n_fill == 1 and "- 优势：深耕顾客细分市场\n公司实施顾客细分方法，建立顾客信息库。" in healed
             and "- 可改进之处：\n- 现场核实：组长核实：顾客细分运行有效。" in healed,
             healed[healed.index("### 报告主要优势条款"):][:120])
    healed2, n_fill2 = M._fill_pseudo_block_lines(healed)
    CK.check("S0z19c 自愈幂等：填过不再写", n_fill2 == 0 and healed2 == healed)
    dv_marked = healed.replace("- 优势：深耕顾客细分市场\n公司实施顾客细分方法，建立顾客信息库。",
                               "- 优势：用户手改内容")
    healed3, n_fill3 = M._fill_pseudo_block_lines(dv_marked)
    CK.check("S0z19d 自愈只填空行：非空行（用户手改）不被重写",
             n_fill3 == 0 and "用户手改内容" in healed3)
    # 折叠交互（2026-10-28 新规则）：伪条目块**不折叠**——live 留在现场核实信息节里
    dv_prog = rw.build_md("上海ST自检数据有限公司", "2026-08-25", "GBT19580 卓越",
                          {"基本情况": "新基本情况。",
                           "主要优势": [{"标题": "新优势概述", "文本": "公司**实施新方法。**",
                                         "条款": "4.3"}],
                           "主要改进建议": []},
                          {"4.3": "顾客与市场"}, doc_title="现场评审")
    dv_out = rw.merge_onsite_final(dv_saved, dv_prog,
                                   "2026-10-30 11:00 提取自 终版样本.docx：优势 1 条 / 建议 0 条",
                                   "2026-08-25")
    dv_fold = dv_out[dv_out.find("> [!note]- 原现场核实记录"):]
    dv_live = dv_out[dv_out.find("## 现场核实信息"):]
    dv_live = dv_live[:dv_live.find("\n## ")] if "## 现场核实信息" in dv_out else ""
    CK.check("S0z20 折叠新规则：伪条目块不折叠、live 留节里（含落盘优势全文）",
             "> ### 报告主要优势条款·4.3" not in dv_fold
             and "### 报告主要优势条款·4.3 顾客与市场" in dv_live
             and "- 优势：深耕顾客细分市场" in dv_live
             and "> ### 4.3.2" in dv_fold, dv_fold[:160])
    CK.check("S0z21 伪条目路径查引用内层 H3 号（报告主要优势条款·4.3 → 4.3）",
             M._PSEUDO_RE.match("报告主要优势条款·4.3").group(2) == "4.3"
             and M._PSEUDO_RE.match("报告主要建议条款·4.5").group(2) == "4.5")


# ── S1 台账 CRUD + 判重 ────────────────────────────────────
def s1_crud_dedup():
    section("S1 台账 CRUD + 判重")
    fields = {"企业名称": ST_COMP, "年份": 2026, "类别": ["文件评审"],
              "市级": "上海市", "区/县": "浦东新区",
              "行业门类": "制造业", "行业大类": "C34 通用设备制造业",
              "奖项/项目": "区政府质量奖", "适用标准": "GBT19580 卓越"}
    r = H.post("/api/projects", {"fields": fields})
    pid = r.get("id", "")
    CK.check("S1a 建卡（id 三段式）", bool(re.match(r"^2026-SH-文审-\d+$", pid)), pid)

    c = H.card(pid)
    CK.eq("S1b 行业拆分键落库", (c or {}).get("行业"), ["制造业", "C34 通用设备制造业"])
    CK.eq("S1c 区域拆分键落库", (c or {}).get("区域"), ["上海市", "浦东新区"])

    r2 = H.put(f"/api/projects/{H.quote(pid)}", {"fields": {"阶段": "报告已出", "结论": "推荐"}})
    c2 = H.card(pid)
    CK.eq("S1d 改卡（阶段+结论）", ((c2 or {}).get("阶段"), (c2 or {}).get("结论")),
          ("报告已出", "推荐"))

    r3 = H.post("/api/projects", {"fields": fields})          # 同企业+同年份+同奖项
    CK.eq("S1e 判重拦截（400）", r3.get("_http"), 400)

    f2025 = dict(fields, 年份=2025)
    r4 = H.post("/api/projects", {"fields": f2025})           # 跨年不误杀
    pid2 = r4.get("id", "")
    CK.check("S1f 跨年建卡不误杀", bool(re.match(r"^2025-SH-文审-\d+$", pid2)), pid2)

    H.delete(f"/api/projects/{H.quote(pid2)}")
    CK.check("S1g 删卡", H.card(pid2) is None)

    # 判重另一形态：表内重复行（走 /api/import，S4 顺带覆盖）——这里只验库内判重日志
    CK.check("S1h 判重返回可读原因", "卡片" in str(r3) or "检查" in str(r3), str(r3)[:80])
    H.delete(f"/api/projects/{H.quote(pid)}")       # 主卡也删（S5 还要建同名卡，防撞判重）
    CK.check("S1i 主卡删除", H.card(pid) is None)
    return pid


# ── S2 按年归位 ────────────────────────────────────────────
def s2_year_link():
    section("S2 按年归位（同企业不同年份互挂）")
    f24 = {"企业名称": ST_COMP2, "年份": 2024, "类别": ["孵化"],
           "市级": "上海市", "区/县": "浦东新区",
           "行业门类": "制造业", "行业大类": "C34 通用设备制造业",
           "奖项/项目": "区政府质量奖"}
    r24 = H.post("/api/projects", {"fields": f24})
    pid24 = r24.get("id", "")
    CK.check("S2a 建 2024 卡", bool(re.match(r"^2024-SH-孵化-\d+$", pid24)), pid24)

    f26 = dict(f24, 年份=2026, 类别=["现场评审"], 现场日期="2026-08-25")
    r26 = H.post("/api/projects", {"fields": f26})            # 不传历史项目 → 自动兜底
    pid26 = r26.get("id", "")
    hist = r26.get("历史") or []
    CK.check("S2b 新建自动挂历史项目", any(h.get("id") == pid24 for h in hist),
             f"历史={[h.get('id') for h in hist]}")
    c26 = H.card(pid26)
    CK.eq("S2c 台账历史项目字段", (c26 or {}).get("历史项目"), [pid24])

    for p in (pid24, pid26):
        H.delete(f"/api/projects/{H.quote(p)}")
    CK.check("S2d 清理两张卡", H.card(pid24) is None and H.card(pid26) is None)


# ── S3 备份轮转双桶 ────────────────────────────────────────
def s3_backup_rotate():
    section("S3 备份轮转双桶 + inbox-done 保护")
    bk = H.ROOT / "backup"
    before_dirs = {p.name for p in bk.iterdir() if p.is_dir()}

    # 造假回执：7 份（keep=5）——若正则误伤会当场现形
    fake = [f"inbox-done-20261025-12000{i}-ST自检假回执{i}.md" for i in range(7)]
    for name in fake:
        (bk / name).write_text("ST自检假回执，跑完即删\n", encoding="utf-8")
    # 造假代码备份 7 份（keep=5）
    fake_code = [f"main-20261025-12000{i}-ST自检假.html" for i in range(7)]
    for name in fake_code:
        (bk / name).write_text("<html>ST自检假</html>\n", encoding="utf-8")

    rot = H.post("/api/desens/rotate")
    CK.check("S3a rotate 双桶结构",
             "自动备份" in rot and "代码备份" in rot
             and "删除" in rot["自动备份"] and "保留" in rot["代码备份"], str(rot)[:100])

    alive = [n for n in fake if (bk / n).exists()]
    CK.eq("S3b inbox-done 回执零误删（A4 回归）", len(alive), 7)

    left_code = [n for n in fake_code if (bk / n).exists()]
    CK.check("S3c 假代码备份被轮转（≤5）", len(left_code) <= 5, f"剩 {len(left_code)}")

    after_dirs = {p.name for p in bk.iterdir() if p.is_dir()}
    CK.check("S3d 归档目录集合不变", before_dirs == after_dirs,
             f"差集 {before_dirs ^ after_dirs}")

    for name in fake + fake_code:                              # 清理（只删自己造的）
        (bk / name).unlink(missing_ok=True)
    CK.check("S3e 假文件清理净", not any((bk / n).exists() for n in fake + fake_code))


# ── S4 上传即删 ────────────────────────────────────────────
def s4_upload_delete():
    section("S4 上传即删（import 读完删临时文件）")
    import openpyxl
    import _helper as H2

    tmp_xlsx = H.ROOT / "data" / "tmp-selftest-import.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["企业名称", "年份", "市级", "区/县", "行业门类", "行业大类",
               "类别", "奖项/项目", "适用标准"])
    ws.append([ST_COMP, 2027, "上海市", "浦东新区", "制造业", "C34 通用设备制造业",
               "文件评审", "区政府质量奖", "GBT19580 卓越"])
    ws.append([ST_COMP, 2027, "上海市", "浦东新区", "制造业", "C34 通用设备制造业",
               "文件评审", "区政府质量奖", "GBT19580 卓越"])   # 表内重复行
    wb.save(str(tmp_xlsx))

    boundary = f"----st{int(time.time() * 1000)}"
    with open(tmp_xlsx, "rb") as f:
        payload = f.read()
    body = (b"--" + boundary.encode() +
           b'\r\nContent-Disposition: form-data; name="file"; filename="st-import.xlsx"\r\n'
           b"Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n"
           + payload + b"\r\n--" + boundary.encode() + b"--\r\n")
    import urllib.request
    req = urllib.request.Request(H2.BASE + "/api/import", data=body, method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    import json as _json
    with urllib.request.urlopen(req, timeout=60) as resp:
        rj = _json.loads(resp.read().decode("utf-8"))
    CK.eq("S4a 导入 1 张（重复行跳过）", len(rj.get("items") or []), 1)
    CK.check("S4b 跳过原因=表内重复行",
             any("表内" in str(s.get("原因")) for s in (rj.get("跳过") or [])),
             str(rj.get("跳过"))[:80])

    leftovers = list((H.ROOT / "data").glob("upload-*.xlsx"))
    CK.eq("S4c 临时上传文件即删", len(leftovers), 0)
    tmp_xlsx.unlink(missing_ok=True)

    # 清掉刚建的卡（LedgerGuard 还原 ledger 兜底，双保险）
    items = rj.get("items") or []
    if not items:
        CK.check("S4a' 导入返回 items 非空", False, f"rj={str(rj)[:120]}")
    for m in items:
        H.delete(f"/api/projects/{H.quote(m['id'])}")
    CK.check("S4d 导入卡已清", all(H.card(m["id"]) is None for m in items))


def _cleanup_st(comp=ST_COMP):
    """本测试造的 MD 全清（20/30/40 库，按企业名匹配）"""
    for d in (MD20, MD30, MD40):
        for p in list(d.glob("*" + comp + "*")):
            p.unlink(missing_ok=True)


# ── S5 复盘写入链 ──────────────────────────────────────────
def s5_review_chain():
    section("S5 复盘写入链（粘贴→归位→写现场→复盘→导出）")
    # ① paste-extract
    paste = ("二、主要优势\n（一）战略清晰聚焦\n公司制定三年发展战略，建立**战略解码机制**。\n"
             "三、主要改进建议\n1. 知识管理待加强\n建议完善**知识盘点机制**。\n")
    pe = H.post("/api/paste-extract", {"text": paste, "project_id": ""})
    op = pe.get("意见结论") or {}
    CK.eq("S5a paste 优势条目", len(op.get("主要优势") or []), 1)
    CK.eq("S5b paste 加粗片段", (op.get("主要优势") or [{}])[0].get("加粗片段"), ["战略解码机制"])
    CK.check("S5c paste 归位条款清单 12 项", len(pe.get("归位条款") or []) == 12,
             str(len(pe.get("归位条款") or [])))

    # ② 建卡 → write-review（目标=现场）
    f = {"企业名称": ST_COMP, "年份": 2026, "类别": ["文件评审", "现场评审"],
         "市级": "上海市", "区/县": "浦东新区",
         "行业门类": "制造业", "行业大类": "C34 通用设备制造业",
         "奖项/项目": "区政府质量奖", "适用标准": "GBT19580 卓越",
         "现场日期": "2026-08-25", "阶段": "归档"}
    pid = H.post("/api/projects", {"fields": f}).get("id", "")
    CK.check("S5d 建现场测试卡", bool(pid), pid)

    opinion = {"基本情况": "ST自检现场终版样本。",
               "主要优势": [{"标题": "（一）战略清晰聚焦", "文本": "公司制定三年发展战略，建立**战略解码机制**。",
                             "条款": "4.2", "序号": "（一）"}],
               "主要改进建议": []}
    wr = H.post("/api/write-review", {"id": pid, "企业名称": ST_COMP, "意见结论": opinion,
                                      "报告日期": "2026-08-25", "目标": "现场",
                                      "模式": [{"来源": "优势", "文本": "质量模式：ST自检模式"}],
                                      "灵魂考问": ""})
    rel = wr.get("路径", "")
    # 2026-10-30 R6 用户拍板：文件名规范化为「YYYYMMDD-企业名.md」，不带「-现场评审」后缀
    CK.check("S5e write-review 现场路径（现场库 + 文件名无「-现场评审」后缀）",
             "现场评审库" in rel and "-现场评审.md" not in rel
             and rel.endswith("20260825-" + ST_COMP + ".md"), rel)

    md_path = (H.VAULT / rel) if rel else None   # rel 是 vault 根相对路径
    md = md_path.read_text(encoding="utf-8") if md_path and md_path.exists() else ""
    CK.check("S5f H1 带「· 现场评审」", "# " + ST_COMP + " · 现场评审" in md)
    CK.check("S5g 条款分节 ### 4.2", "### 4.2 战略" in md)
    CK.check("S5h 概述进 H4 小节标题（2026-10-27 新格式；序号剥离属前端 confirmClauses，由 e2e.js 覆盖）",
             "#### （一）战略清晰聚焦" in md or "#### 战略清晰聚焦" in md, "")
    # 2026-10-30 R5 用户拍板：模式不进 30 库现场报告 MD——模式只存在于 40 库模式卡
    md40_st = MD40 / (ST_COMP + "-模式.md")
    CK.check("S5i R5 30 库现场 MD 不含「## 质量模式」节", "## 质量模式" not in md, md[:80])
    CK.check("S5i2 R5 模式自动带入 40 库模式卡（含模式名）",
             md40_st.exists() and "ST自检模式" in md40_st.read_text(encoding="utf-8"),
             md40_st.read_text(encoding="utf-8")[:120] if md40_st.exists() else "卡不存在")
    CK.check("S5i3 R5 双关联：报告 frontmatter 指向模式卡",
             f"关联模式: 政府质量奖-质量模式库/{ST_COMP}-模式.md" in md, "")
    CK.check("S5i4 R5 双关联：模式卡 frontmatter 指向报告",
             md40_st.exists() and f"关联报告: {rel}" in md40_st.read_text(encoding="utf-8"),
             md40_st.read_text(encoding="utf-8")[:200] if md40_st.exists() else "卡不存在")
    CK.check("S5i5 R3-a 台账「模式草稿」已随终版写入置位",
             bool((H.card(pid) or {}).get("模式草稿")), str((H.card(pid) or {}).get("模式草稿")))
    CK.check("S5j 提取日志行", bool(re.search(r"\d{4}-\d{2}-\d{2}.{0,30}提取自", md)),
             md[md.find("提取"):][:40] if "提取" in md else "无日志行")
    CK.check("S5j2 现场终版 frontmatter 带现场日期", "现场日期: 2026-08-25" in md)

    # ③ 补一个「现场核实信息」节（模拟现场填过）→ 测导出
    if md_path and md_path.exists():
        txt = md_path.read_text(encoding="utf-8")
        txt += ("\n## 现场核实信息\n\n### 4.2 战略\n\n- 现场核实：战略解码机制运行有效，"
                "年度战略复盘会见证。\n")
        md_path.write_text(txt, encoding="utf-8")

    # ④ review-note（复盘沉淀）
    rn = H.post("/api/review-note", {"project_id": pid, "note": "ST自检复盘：长见识一条。"})
    CK.check("S5k review-note ok", rn.get("ok") is True, str(rn)[:80])
    md_after = md_path.read_text(encoding="utf-8") if md_path and md_path.exists() else ""
    CK.check("S5l 复盘沉淀 callout 落节", "复盘 · 灵魂考问" in md_after or "复盘沉淀" in md_after)
    CK.check("S5m 现场核实节未被覆盖", "战略解码机制运行有效" in md_after)

    # ⑤ export-onsite-docx
    import urllib.request
    req = urllib.request.Request(H.BASE + "/api/export-onsite-docx?project_id=" + H.quote(pid))
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            blob = resp.read()
            ctype = resp.headers.get("Content-Type", "")
        CK.check("S5n 导出 docx 200", resp.status == 200, f"{resp.status} {ctype}")
        CK.check("S5o 导出是非空 docx（PK 头）",
                 blob[:2] == b"PK" and len(blob) > 3000, f"{len(blob)} bytes")
        CK.check("S5p 导出含条款名", "战略" in _docx_text(blob), "文本检索")
    except urllib.error.HTTPError as e:
        CK.check("S5n 导出 docx 200", False, f"HTTP {e.code}: {e.read()[:120]}")

    # ⑥ 终版链（2026-10-27 用户定）：先挂一份 20 库文审报告进来源文件（模拟双存），
    #    再写一次现场终版 → 应更新同一文件（不新建）+ 折叠旧现场核实信息到文尾
    #    + 删 20 库文审报告 + 来源文件只留现场 rel（报告归口唯一化）
    md20 = MD20 / ("20240918-" + ST_COMP + ".md")
    md20.parent.mkdir(parents=True, exist_ok=True)
    md20.write_text("# 旧文审报告（ST自检造，应由终版写入删除）\n", encoding="utf-8")
    rel20 = "政府质量奖-资料评审库/20240918-" + ST_COMP + ".md"
    rel30 = "政府质量奖-现场评审库/20260825-" + ST_COMP + ".md"
    H.put(f"/api/projects/{H.quote(pid)}", {"fields": {"来源文件": [rel20, rel30]}})
    wr2 = H.post("/api/write-review", {"id": pid, "企业名称": ST_COMP, "意见结论": opinion,
                                       "报告日期": "2026-08-25", "目标": "现场",
                                       "模式": [], "来源文件名": "终版样本.docx", "灵魂考问": ""})
    CK.check("S5r 终版二次写入 ok", wr2.get("ok") is True, str(wr2)[:100])
    CK.eq("S5r2 终版更新同一文件（不新建）", wr2.get("文件"), "20260825-" + ST_COMP + ".md")
    st30 = list(MD30.glob("*" + ST_COMP + "*.md"))
    CK.check("S5r3 30 库该企业唯一现场文件", len(st30) == 1, str([p.name for p in st30]))
    md_final = md_path.read_text(encoding="utf-8") if md_path and md_path.exists() else ""
    CK.check("S5r4 现场核实信息不在原位保留", "## 现场核实信息" not in md_final)
    fold = md_final[md_final.find("> [!note]- 原现场核实记录"):]
    CK.check("S5r5 折叠块在文尾（复盘沉淀/提取日志之后）",
             md_final.find("> [!note]- 原现场核实记录") > md_final.rfind("## 复盘沉淀")
             and md_final.find("> [!note]- 原现场核实记录") > md_final.rfind("## 提取日志"),
             md_final[-60:].replace("\n", "⏎"))
    CK.check("S5r6 折叠块标题带文件名日期",
             "> [!note]- 原现场核实记录（2026-08-25，终版写入时折叠归档）" in fold, "")
    CK.check("S5r7 折叠块含条款块+现场核实行",
             "> ### 4.2 战略" in fold and "> - 现场核实：战略解码机制运行有效" in fold, fold[:160])
    CK.check("S5r8 复盘沉淀原位保留（手写节不碰）", "ST自检复盘：长见识一条。" in md_final)
    CK.eq("S5r9 提取日志累计两条", len(re.findall(r"提取自", md_final)), 2)
    CK.check("S5r10 20 库文审报告已删（归口唯一化）", not md20.exists())
    c_final = H.card(pid) or {}
    CK.eq("S5r11 来源文件只留现场 rel", c_final.get("来源文件"), [rel30])
    CK.check("S5r12 已删除文审回执", wr2.get("已删除文审") == [rel20], str(wr2.get("已删除文审")))
    # S5r13 现场日期回写（2026-10-28 用户定）：写入弹窗里的现场日期，确认写入后代入卡片
    # 字段，不再去「编辑」里重复输入。清空卡片现场日期→带日期写入→断言回写到位
    H.put(f"/api/projects/{H.quote(pid)}", {"fields": {"现场日期": ""}})
    CK.eq("S5r13a 前置：卡片现场日期已清空", (H.card(pid) or {}).get("现场日期"), "")
    wr3 = H.post("/api/write-review", {"id": pid, "企业名称": ST_COMP, "意见结论": opinion,
                                       "报告日期": "2026-08-25", "目标": "现场",
                                       "模式": [], "来源文件名": "终版样本.docx", "灵魂考问": ""})
    CK.check("S5r13b 带日期现场写入 ok", wr3.get("ok") is True, str(wr3)[:100])
    CK.eq("S5r13 现场日期回写卡片（不再重复输入）",
          (H.card(pid) or {}).get("现场日期"), "2026-08-25")
    # S5r14 终版已写=写入日期（2026-10-28 用户定：复盘门禁信号源=终版写入）——仅 write-review
    #   目标=现场 置位（与现场日期回写同分支、覆盖式）；阶段一 write-onsite 不置（见 S5b）
    CK.eq("S5r14 终版已写=本次写入日期（复盘门禁信号源）",
          (H.card(pid) or {}).get("终版已写"), "2026-08-25")

    # ⑦ 清理：删卡 + 删测试 MD（20/30/40 库，含 R5 自动带入生成的模式卡）
    H.delete(f"/api/projects/{H.quote(pid)}")
    _cleanup_st()
    stray = MD30 / "20260825-上海ST自检数据有限公司.md"
    stray.unlink(missing_ok=True)
    CK.check("S5q 测试卡与 MD 清理净", H.card(pid) is None and not stray.exists()
             and not list(MD40.glob("*" + ST_COMP + "*")))


# ── S5b 阶段一写入链（write-onsite：复盘门禁必须保持灰） ──────
def s5b_onsite_stage_one():
    section("S5b 阶段一写入链（write-onsite 不置终版已写 → 复盘保持灰）")
    # 2026-10-28 用户定：阶段一（类别 文件评审→现场评审 → 勾选条款 → /api/write-onsite）
    # 只是条款核实与信息导出，产物虽含 30 库现场报告，「终版已写」也绝不置位——
    # 复盘门禁信号源只认终版写入（/api/write-review 目标=现场，见 S5r14）。
    # ① 文审卡 + 20 库文审报告（write-onsite 的基底：首次迁移取文审全文）
    f = {"企业名称": ST_COMP, "年份": 2026, "类别": ["文件评审", "现场评审"],
         "市级": "上海市", "区/县": "浦东新区",
         "行业门类": "制造业", "行业大类": "C34 通用设备制造业",
         "奖项/项目": "区政府质量奖", "适用标准": "GBT19580 卓越",
         "报告日期": "2026-08-25", "阶段": "文审中"}
    pid = H.post("/api/projects", {"fields": f}).get("id", "")
    CK.check("S5b1 建阶段一测试卡（文审态）", bool(pid), pid)
    md20 = MD20 / ("20260825-" + ST_COMP + ".md")
    md20.parent.mkdir(parents=True, exist_ok=True)
    md20.write_text("# " + ST_COMP + " · 资料评审\n\n## 主要优势\n\n### 4.2 战略\n\n"
                    "#### 战略清晰聚焦\n\n公司制定三年发展战略，建立**战略解码机制**。\n",
                    encoding="utf-8")
    rel20 = "政府质量奖-资料评审库/20260825-" + ST_COMP + ".md"
    H.put(f"/api/projects/{H.quote(pid)}", {"fields": {"来源文件": [rel20]}})
    CK.eq("S5b2 前置：终版已写未设置", (H.card(pid) or {}).get("终版已写"), None)
    # ② 阶段一写入：write-onsite（勾选条款留空=最小验证）→ 产物=30 库现场 MD + 来源只留现场
    wo = H.post("/api/write-onsite", {"id": pid, "企业名称": ST_COMP,
                                      "现场日期": "2026-08-25", "结论": "", "勾选条款": []})
    CK.check("S5b3 write-onsite ok", wo.get("ok") is True, str(wo)[:100])
    rel_wo = wo.get("路径", "")
    CK.check("S5b4 产物落现场评审库", "现场评审库" in rel_wo, rel_wo)
    # 2026-10-30 R6 用户拍板：文件名规范化「YYYYMMDD-企业名.md」，去掉「-现场评审」后缀
    CK.check("S5b4b R6 write-onsite 文件名不带「-现场评审」后缀",
             "-现场评审.md" not in rel_wo
             and rel_wo.endswith("20260825-" + ST_COMP + ".md"), rel_wo)
    c_wo = H.card(pid) or {}
    CK.check("S5b5 阶段一不置终版已写（复盘门禁信号源保持灰）",
             not c_wo.get("终版已写"), repr(c_wo.get("终版已写")))
    CK.eq("S5b6 来源只留现场报告（归口唯一化）", c_wo.get("来源文件"), [rel_wo])
    CK.check("S5b7 20 库文审报告被迁移删除", not md20.exists())
    # ③ 清理：删卡 + 删测试 MD（文件名带 ST 标记）
    H.delete(f"/api/projects/{H.quote(pid)}")
    _cleanup_st()
    CK.check("S5b8 测试卡与 MD 清理净", H.card(pid) is None and not md20.exists()
             and not list(MD30.glob("*" + ST_COMP + "*.md")))


# ── S5c 复盘四步闭环（practice-confirm / mode-draft / review-note 置位 + write-onsite 关门）──
def s5c_review_closed_loop():
    section("S5c 复盘四步闭环（做法确认/模式草稿/四问已答 置位 + 终版后 write-onsite 400 关门）")
    # 2026-10-28 用户定：终版写入 = 关现场环节 + 开复盘；复盘三步各自留痕（MD callout +
    # 台账日期信号，覆盖式），三步全齐才可归档（门禁在前端，后端供信号字段）；
    # 终版后 write-onsite 400 关门（重建会截掉提取日志/折叠归档块，修正走终版重传）。
    import review_writer as rw
    today = time.strftime("%Y-%m-%d")
    # ① 建现场卡 + 写终版（有结构化优势：### 4.2 + 加粗方法）
    f = {"企业名称": ST_COMP, "年份": 2026, "类别": ["现场评审"],
         "市级": "上海市", "区/县": "浦东新区",
         "行业门类": "制造业", "行业大类": "C34 通用设备制造业",
         "奖项/项目": "区政府质量奖", "适用标准": "GBT19580 卓越",
         "现场日期": "2026-08-25", "阶段": "现场中"}
    pid = H.post("/api/projects", {"fields": f}).get("id", "")
    CK.check("S5c1 建闭环测试卡", bool(pid), pid)
    opinion = {"基本情况": "ST自检闭环样本。",
               "主要优势": [{"标题": "（一）战略清晰聚焦", "文本": "公司建立**战略解码机制**。",
                             "条款": "4.2", "序号": "（一）"}],
               "主要改进建议": []}
    wr = H.post("/api/write-review", {"id": pid, "企业名称": ST_COMP, "意见结论": opinion,
                                      "报告日期": "2026-08-25", "目标": "现场",
                                      "模式": [], "来源文件名": "闭环样本.docx", "灵魂考问": ""})
    rel = wr.get("路径", "")
    CK.check("S5c2 终版写入 ok", wr.get("ok") is True, rel)
    md_path = H.VAULT / rel
    # ② 闭环① 做法确认：callout 落「复盘沉淀」节 + 台账置位
    pc = H.post("/api/practice-confirm", {"project_id": pid,
                                          "做法": [{"条款": "4.2 战略", "做法": ["战略解码机制。"]}]})
    CK.check("S5c3 practice-confirm ok", pc.get("ok") is True, str(pc)[:80])
    CK.eq("S5c4 做法确认条数回执", pc.get("条数"), 1)
    md1 = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    CK.check("S5c5 做法确认 callout 落「复盘沉淀」节",
             f"> [!note]- {today} 做法确认（1 条）" in md1 and "> **4.2 战略**" in md1
             and "> - 战略解码机制。" in md1, "")
    CK.eq("S5c6 台账「做法确认」=今天", (H.card(pid) or {}).get("做法确认"), today)
    # ②b R4 同日重复确认 → 就地改写（不追加第二条 callout）
    pc1b = H.post("/api/practice-confirm", {"project_id": pid,
                                            "做法": [{"条款": "4.2 战略",
                                                      "做法": ["战略解码机制。", "改进做法乙。"]}]})
    md1b = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    CK.check("S5c6a R4 同日二次确认：条数回执更新为 2", pc1b.get("条数") == 2, str(pc1b)[:80])
    CK.check("S5c6b R4 同日二次确认：MD 里只有一条当日 callout（就地改写不追加）",
             md1b.count(f"> [!note]- {today} 做法确认") == 1
             and "（1 条）" not in md1b and "（2 条）" in md1b
             and "> - 改进做法乙。" in md1b,
             str(md1b.count(f"> [!note]- {today} 做法确认")))
    # ②c R4 零条：不写 callout（不留空记录），但台账照常置位
    pc0 = H.post("/api/practice-confirm", {"project_id": pid, "做法": []})
    CK.check("S5c6c R4 零条：回执「未落痕」=true、条数 0",
             pc0.get("条数") == 0 and pc0.get("未落痕") is True, str(pc0)[:80])
    md1c = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    CK.check("S5c6d R4 零条：MD 里没有空的「做法确认（0 条）」callout",
             "做法确认（0 条）" not in md1c, md1c[-200:] if md1c else "")
    CK.eq("S5c6e R4 零条：台账「做法确认」仍置位今天",
          (H.card(pid) or {}).get("做法确认"), today)
    # ③ 闭环② 模式草稿：40 库落文件 + 台账置位
    md40 = MD40 / (ST_COMP + "-模式.md")
    md40.parent.mkdir(parents=True, exist_ok=True)
    if md40.exists():
        md40.unlink()                       # 清掉同企业旧模式卡，保证测的是本次写入
    mdg = H.post("/api/mode-draft", {"project_id": pid, "模式名称": "ST自检闭环模式",
                                     "说明": "ST自检闭环说明。",
                                     "做法": [{"条款": "4.2 战略", "做法": ["战略解码机制。"]}]})
    CK.check("S5c7 mode-draft ok", mdg.get("ok") is True, str(mdg)[:80])
    CK.check("S5c8 模式文件落 40 库", md40.exists(), md40.name)
    CK.eq("S5c9 台账「模式草稿」=今天", (H.card(pid) or {}).get("模式草稿"), today)
    mt1 = md40.read_text(encoding="utf-8") if md40.exists() else ""
    CK.check("S5c8b R3-c 模式卡有程序区（模式名+说明+入选做法）",
             "## ST自检闭环模式" in mt1 and "ST自检闭环说明。" in mt1
             and "## 入选做法（按条款）" in mt1 and "- 战略解码机制。" in mt1, mt1[:200])
    CK.check("S5c8c R3-c 模式卡有用户区标记与空「复盘优化区」",
             "<!-- 用户区开始 -->" in mt1 and "<!-- 用户区结束 -->" in mt1
             and "## 复盘优化区（留空，复盘时填写）" in mt1, "")
    CK.eq("S5c8d R3-a 模式卡可读回模式名/说明（复盘 tab 预填数据源）",
          (rw.parse_mode_card(mt1)["模式名称"], rw.parse_mode_card(mt1)["说明"]),
          ("ST自检闭环模式", "ST自检闭环说明。"))
    CK.eq("S5c8e R3-c 用户区内容在标记之间（默认空复盘优化区）",
          rw.parse_mode_card(mt1)["用户区"], "## 复盘优化区（留空，复盘时填写）")
    # R3-c 关键：用户在用户区写了批注 → 再次更新模式卡后批注仍在
    mt_user = mt1.replace("<!-- 用户区开始 -->\n## 复盘优化区（留空，复盘时填写）\n<!-- 用户区结束 -->",
                          "<!-- 用户区开始 -->\n## 复盘优化区\n\n我的手写批注：这个模式要配案例佐证。\n"
                          "<!-- 用户区结束 -->")
    md40.write_text(mt_user, encoding="utf-8")
    H.post("/api/mode-draft", {"project_id": pid, "模式名称": "ST自检闭环模式（改名）",
                               "说明": "更新后的说明。", "做法": []})
    mt2 = md40.read_text(encoding="utf-8")
    CK.check("S5c8f R3-c 用户区批注在更新后原样保留（程序区被替换）",
             "我的手写批注：这个模式要配案例佐证。" in mt2
             and "## ST自检闭环模式（改名）" in mt2 and "更新后的说明。" in mt2
             and "## 复盘优化区" in mt2, mt2[:260])
    CK.check("S5c8g R3-c 用户区标记仍在且只有一对",
             mt2.count("<!-- 用户区开始 -->") == 1 and mt2.count("<!-- 用户区结束 -->") == 1, "")
    # R3-c 空模式名：不写空的 `## ` 节（只写入选做法与用户区）
    H.post("/api/mode-draft", {"project_id": pid, "模式名称": "", "说明": "",
                               "做法": [{"条款": "4.2 战略", "做法": ["零名称做法。"]}]})
    mt3 = md40.read_text(encoding="utf-8")
    CK.check("S5c8h R3-c 模式名为空：不写空的 `## ` 节，只留入选做法+用户区",
             "## \n" not in mt3 and "## 入选做法（按条款）" in mt3
             and "- 零名称做法。" in mt3 and "我的手写批注" in mt3, mt3[:200])
    # ④ 闭环③ 四问：review-note → 台账置位
    rn = H.post("/api/review-note", {"project_id": pid, "note": "ST自检四问：长见识一条。"})
    CK.check("S5c10 review-note ok", rn.get("ok") is True, str(rn)[:80])
    CK.eq("S5c11 台账「四问已答」=今天", (H.card(pid) or {}).get("四问已答"), today)
    md2 = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    CK.check("S5c12 做法确认与四问同节共存（手写节内追加不互删）",
             "做法确认（2 条）" in md2 and "ST自检四问" in md2, "")
    # ⑤ 关门：终版已写后 write-onsite 400（阶段一重建有破坏性）
    wo = H.post("/api/write-onsite", {"id": pid, "企业名称": ST_COMP,
                                      "现场日期": "2026-08-25", "结论": "", "勾选条款": []})
    CK.eq("S5c13 终版后 write-onsite 400 关门", wo.get("_http"), 400)
    CK.check("S5c14 关门文案指向终版重传", "提取并写入终版" in str(wo.get("detail", "")),
             str(wo.get("detail", ""))[:60])
    # ⑥ 清理：删卡 + 删测试 MD（30 库终版 + 40 库模式卡，均带 ST 标记）
    H.delete(f"/api/projects/{H.quote(pid)}")
    _cleanup_st()
    CK.check("S5c15 测试卡与 MD 清理净", H.card(pid) is None and not md40.exists()
             and not list(MD30.glob("*" + ST_COMP + "*.md")))


# ── S7 派生伪条目 HTTP 链（report-terms 读取派生 + onsite-note 保存建块）──
def s7_derived_terms_http():
    section("S7 派生伪条目 HTTP 链（读取派生 + 保存建块 + 往返）")
    md30 = MD30 / ("20260827-" + ST_COMP + "-派生.md")
    md30.parent.mkdir(parents=True, exist_ok=True)
    md30.write_text(
        "---\n标准: GBT19580 卓越\n企业名称: 上海ST自检数据有限公司\n"
        "报告日期: 2026-08-27\n现场日期: 2026-08-27\n---\n\n"
        "# 上海ST自检数据有限公司 · 现场评审\n\n"
        "## 主要优势\n\n### 4.3 顾客与市场\n\n#### 深耕顾客细分市场\n\n"
        "公司**实施**顾客细分方法，建立顾客信息库。\n\n"
        "## 主要改进建议\n\n### 4.5 过程管理\n\n**建议完善过程管理制度引用。**\n\n"
        "## 现场核实信息\n\n### 4.3.2 顾客和市场的了解\n\n"
        "相关条款：[[GBT19580-卓越-4.3.2顾客和市场的了解]]\n\n"
        "- 文审优势：块内自有优势：按区域细分四大市场。\n"
        "- 可改进之处：建议展开需求了解方法。\n- 现场核实：\n\n"
        "### 4.5.1 过程管理的实施\n\n- 可改进之处：建议补充过程绩效指标。\n- 现场核实：\n",
        encoding="utf-8")
    rel30 = "政府质量奖-现场评审库/20260827-" + ST_COMP + "-派生.md"
    f = {"企业名称": ST_COMP, "年份": 2026, "类别": ["现场评审"],
         "市级": "上海市", "区/县": "浦东新区",
         "行业门类": "制造业", "行业大类": "C34 通用设备制造业",
         "奖项/项目": "区政府质量奖", "适用标准": "GBT19580 卓越",
         "现场日期": "2026-08-27", "来源文件": [rel30]}
    pid = H.post("/api/projects", {"fields": f}).get("id", "")
    CK.check("S7a 建派生测试卡", bool(pid), pid)

    j = H.get("/api/onsite-report-terms?project_id=" + H.quote(pid))
    CK.check("S7b report-terms ok", j.get("ok") is True, str(j)[:80])
    terms = j.get("条款") or []
    CK.eq("S7c 读取即派生（细条款→伪优势→伪建议，追加末尾）",
          [t.get("条款号") for t in terms],
          ["4.3.2", "4.5.1", "报告主要优势条款·4.3", "报告主要建议条款·4.5"])
    t432 = terms[0] if terms else {}
    CK.check("S7d 优势栏回退：细条款用块内文审优势行（无文审优势预填键）",
             t432.get("优势") == "块内自有优势：按区域细分四大市场。"
             and "文审优势" not in t432, str(t432)[:80])
    pa = next((t for t in terms if t.get("条款号") == "报告主要优势条款·4.3"), {})
    CK.check("S7e 伪优势条目内容=主要优势节全文",
             pa.get("条款名") == "顾客与市场"
             and pa.get("优势") == "深耕顾客细分市场\n公司实施顾客细分方法，建立顾客信息库。",
             str(pa)[:100])
    ps = next((t for t in terms if t.get("条款号") == "报告主要建议条款·4.5"), {})
    CK.check("S7f 伪建议条目内容进可改进之处",
             ps.get("条款名") == "过程管理"
             and ps.get("可改进之处") == "建议完善过程管理制度引用。", str(ps)[:100])
    CK.eq("S7g 细条款路径取条款字典（双链）", t432.get("路径"),
          "笔记/Exp/GBT19580-卓越-4.3.2顾客和市场的了解.md")
    CK.check("S7g2 伪条目路径按内层 H3 号查字典（当前库无两位段大条款文件→空）",
             pa.get("路径") == "" or "-4.3" in str(pa.get("路径")), str(pa.get("路径")))

    # 二次读取：去重（不重复追加）
    j2 = H.get("/api/onsite-report-terms?project_id=" + H.quote(pid))
    CK.eq("S7h 二次读取去重（伪条目各只一条）",
          [t.get("条款号") for t in (j2.get("条款") or [])],
          ["4.3.2", "4.5.1", "报告主要优势条款·4.3", "报告主要建议条款·4.5"])

    # 保存伪条目核实内容 → MD 建块 → 重读往返
    wn = H.post("/api/onsite-note", {"id": pid, "核实": {
        "报告主要优势条款·4.3": "组长核实：顾客细分方法运行有效。",
        "报告主要建议条款·4.5": "组长核实：制度梳理已立项。"}})
    CK.check("S7i 保存伪条目 ok", wn.get("ok") is True, str(wn)[:80])
    CK.eq("S7i2 保存建块计 2 条更新", wn.get("更新"), 2)
    md_after = md30.read_text(encoding="utf-8")
    CK.check("S7j 保存落盘：优势/可改进之处行=节全文 + 现场核实行（2026-10-28 内容落盘）",
             "### 报告主要优势条款·4.3 顾客与市场" in md_after
             and "- 优势：深耕顾客细分市场\n公司实施顾客细分方法，建立顾客信息库。" in md_after
             and "- 现场核实：组长核实：顾客细分方法运行有效。" in md_after
             and "### 报告主要建议条款·4.5 过程管理" in md_after
             and "- 可改进之处：建议完善过程管理制度引用。" in md_after
             and "- 现场核实：组长核实：制度梳理已立项。" in md_after, "")
    j3 = H.get("/api/onsite-report-terms?project_id=" + H.quote(pid))
    terms3 = j3.get("条款") or []
    CK.eq("S7k 保存后重读：条款号 round-trip + 不重复追加",
          [t.get("条款号") for t in terms3],
          ["4.3.2", "4.5.1", "报告主要优势条款·4.3", "报告主要建议条款·4.5"])
    pa3 = next((t for t in terms3 if t.get("条款号") == "报告主要优势条款·4.3"), {})
    ps3 = next((t for t in terms3 if t.get("条款号") == "报告主要建议条款·4.5"), {})
    CK.check("S7l 往返：现场核实/优势重读正确（块内落盘内容优先）",
             pa3.get("现场核实") == "组长核实：顾客细分方法运行有效。"
             and pa3.get("优势") == "深耕顾客细分市场\n公司实施顾客细分方法，建立顾客信息库。"
             and ps3.get("现场核实") == "组长核实：制度梳理已立项。"
             and ps3.get("可改进之处") == "建议完善过程管理制度引用。",
             str((pa3.get("现场核实"), ps3.get("现场核实"))))

    # 导出全量（2026-10-28 用户定）：伪条目块三栏内容进 docx（含非数字条款号标题）——
    # 必须在下面自愈变异测试之前跑（S7m5 会把优势行改成手改内容）
    import urllib.request
    req = urllib.request.Request(H.BASE + "/api/export-onsite-docx?project_id=" + H.quote(pid))
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            blob = resp.read()
        text = _docx_text(blob)
        CK.check("S7n 导出含伪条目块内容（条款号+优势全文+可改进+现场核实）",
                 "报告主要优势条款·4.3" in text and "深耕顾客细分市场" in text
                 and "顾客信息库" in text and "报告主要建议条款·4.5" in text
                 and "建议完善过程管理制度引用" in text
                 and "组长核实：顾客细分方法运行有效" in text
                 and "组长核实：制度梳理已立项" in text, text[:80])
    except urllib.error.HTTPError as e:
        CK.check("S7n 导出含伪条目块内容", False, f"HTTP {e.code}: {e.read()[:120]}")

    # 自愈旧数据（2026-10-28 用户定）：手工清空伪块优势行 → report-terms 读取时回填 MD；
    # 幂等（再读不重写）；只填空行（手改内容不被覆盖）
    txt_now = md30.read_text(encoding="utf-8")
    md30.write_text(txt_now.replace(
        "- 优势：深耕顾客细分市场\n公司实施顾客细分方法，建立顾客信息库。", "- 优势："),
        encoding="utf-8")
    j4 = H.get("/api/onsite-report-terms?project_id=" + H.quote(pid))
    healed_txt = md30.read_text(encoding="utf-8")
    CK.check("S7m2 自愈：读取时回填空优势行（节全文落盘）",
             "- 优势：深耕顾客细分市场\n公司实施顾客细分方法，建立顾客信息库。" in healed_txt,
             healed_txt[healed_txt.index("### 报告主要优势条款"):][:100])
    pa4 = next((t for t in (j4.get("条款") or []) if t.get("条款号") == "报告主要优势条款·4.3"), {})
    CK.check("S7m3 自愈后读取：优势=回填内容",
             pa4.get("优势") == "深耕顾客细分市场\n公司实施顾客细分方法，建立顾客信息库。")
    mt1 = md30.stat().st_mtime_ns
    H.get("/api/onsite-report-terms?project_id=" + H.quote(pid))
    CK.check("S7m4 自愈幂等：再读不重写（mtime 不变）",
             md30.stat().st_mtime_ns == mt1
             and md30.read_text(encoding="utf-8") == healed_txt)
    md30.write_text(healed_txt.replace(
        "- 优势：深耕顾客细分市场\n公司实施顾客细分方法，建立顾客信息库。", "- 优势：手改保留"),
        encoding="utf-8")
    H.get("/api/onsite-report-terms?project_id=" + H.quote(pid))
    CK.check("S7m5 自愈只填空行：手改内容不被覆盖",
             "- 优势：手改保留" in md30.read_text(encoding="utf-8"))

    # 清理：删卡 + 删测试 MD（LedgerGuard 还原 ledger 兜底，双保险）
    H.delete(f"/api/projects/{H.quote(pid)}")
    md30.unlink(missing_ok=True)
    CK.check("S7m 测试卡与 MD 清理净", H.card(pid) is None and not md30.exists())


# ── S8 归档 API + config 预留模块删除 ───────────────────────
def s8_archive_and_config():
    section("S8 归档 API（PUT 阶段=归档）+ config 预留模块删除")
    # ① 归档 API：复盘 tab「归档」按钮走的同一接口（现场中 → 归档）
    f = {"企业名称": ST_COMP, "年份": 2026, "类别": ["现场评审"],
         "市级": "上海市", "区/县": "浦东新区",
         "行业门类": "制造业", "行业大类": "C34 通用设备制造业",
         "奖项/项目": "区政府质量奖", "适用标准": "GBT19580 卓越",
         "现场日期": "2026-08-25", "阶段": "现场中"}
    pid = H.post("/api/projects", {"fields": f}).get("id", "")
    CK.check("S8a 建归档测试卡（现场中）", bool(pid), pid)
    CK.eq("S8a2 前置：阶段=现场中", (H.card(pid) or {}).get("阶段"), "现场中")
    r = H.put(f"/api/projects/{H.quote(pid)}", {"fields": {"阶段": "归档"}})
    CK.check("S8b PUT 阶段=归档 ok（复盘 tab 归档按钮同接口）", r.get("ok") is True, str(r)[:80])
    CK.eq("S8b2 卡片阶段=归档", (H.card(pid) or {}).get("阶段"), "归档")
    r2 = H.put(f"/api/projects/{H.quote(pid)}", {"fields": {"阶段": "归档"}})
    CK.check("S8b3 重复归档不报错（幂等）", r2.get("ok") is True, str(r2)[:80])
    H.delete(f"/api/projects/{H.quote(pid)}")
    CK.check("S8b4 清理归档测试卡", H.card(pid) is None)

    # ② config：预留「政府质量奖个人」TAB 已删（2026-10-28 用户定：DB31T598 个人
    #    已在「适用标准」里覆盖）；台账/字典无该奖项引用
    import yaml
    cfg = yaml.safe_load((H.ROOT / "config.yaml").read_text(encoding="utf-8"))
    reg = (cfg.get("模块", {}).get("登记", {}) or {})
    CK.check("S8c config：政府质量奖个人 模块已删", "政府质量奖个人" not in reg,
             str(list(reg.keys())))
    CK.check("S8c2 config：DB31T598 个人 适用标准保留（覆盖口径不变）",
             any("DB31T598" in str(s) for s in (cfg.get("适用标准") or [])), "")
    CK.check("S8c3 台账无「政府质量奖个人奖」奖项引用",
             all("政府质量奖个人奖" not in str(c.get("奖项/项目") or "") for c in H.cards()), "")


def _docx_text(blob):
    """docx 字节 → 全文（自检导出内容用）"""
    out = []
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    out = re.sub(r"<[^>]+>", "", xml)
    return out


# ── 主流程 ─────────────────────────────────────────────────
def main():
    print("=" * 56)
    print("评审工作台 API 级自检（D3）")
    print(f"台账: {H.LEDGER}")
    print(f"解释器: {H.PY}")
    if not (FIX / "B45条款样本.docx").exists():
        import subprocess
        subprocess.run([H.PY, str(Path(__file__).resolve().parent / "make_docx.py")],
                       check=True, capture_output=True)
        print("fixtures 已生成")

    s0_extract_rules()                    # 纯函数级，不需要服务
    with H.Service():
        with H.LedgerGuard():
            before_ids = {str(c.get("id")) for c in H.cards()}
            s1_crud_dedup()
            s2_year_link()
            s3_backup_rotate()
            s4_upload_delete()
            s5_review_chain()
            s5b_onsite_stage_one()
            s5c_review_closed_loop()
            s7_derived_terms_http()
            s8_archive_and_config()
            # 双保险：LedgerGuard 的 md5 之外，显式核对卡集合（块内删卡失败也逃不过）
            after_ids = {str(c.get("id")) for c in H.cards()}
            CK.check("S6a 块内测试卡全部清净", after_ids == before_ids,
                     f"残留 {after_ids - before_ids}")
        # LedgerGuard 退出即还原；服务还活着（Service 在最外层），复核还原后台账
        CK.check("S6b 还原后台账卡集合不变",
                 {str(c.get("id")) for c in H.cards()} == before_ids,
                 f"差异 { {str(c.get('id')) for c in H.cards()} ^ before_ids }")
    return CK.summary("SELFTEST")


if __name__ == "__main__":
    sys.exit(main())
