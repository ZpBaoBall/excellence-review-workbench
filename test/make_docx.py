# -*- coding: utf-8 -*-
"""自检测试用 docx 生成器（纯标准库拼 XML，不依赖 python-docx）

生成三个样本到 test/fixtures/：
  ① B45条款样本.docx    —— 单行单列结论表 + 「一、二、三、四」节标题 + 小标题段 + 段内加粗
  ② 多行表式样样本.docx   —— 1列3行表（行=节）+ 中文序号加粗标题句「（一）」+ 质量模式尾段
  ③ 概述式样样本.docx   —— 概述段（≤50字、可带句号）+ 展开段，展开内加粗 = 方法
                          （2026-10-27 用户约定：方法按「。」断句，一句一方法——
                           加粗重新标成「完整句子+。」，示范用户复盘时的标注方式）

被 selftest.py / e2e.js 共用；改了 docx_extract 的切分规则时，先来这里确认样本仍覆盖旧形态。
运行：venv python test/make_docx.py
"""
import zipfile
from pathlib import Path

OUT = Path(__file__).resolve().parent / "fixtures"
OUT.mkdir(exist_ok=True)

CT = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>'''

RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>'''


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def para(spans, size=None):
    """spans=[(文本, 加粗?)]；size=半磅（18pt→36）。每个 run 独立 rPr。"""
    runs = []
    for t, b in spans:
        rpr = ""
        if b or size:
            inner = ("<w:b/>" if b else "") + (f'<w:sz w:val="{size}"/>' if size else "")
            rpr = f"<w:rPr>{inner}</w:rPr>"
        runs.append(f'<w:r>{rpr}<w:t xml:space="preserve">{esc(t)}</w:t></w:r>')
    return f"<w:p>{''.join(runs)}</w:p>"


def cell(paras):
    return f"<w:tc>{''.join(paras)}</w:tc>"


def write_docx(name, body):
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f'<w:body>{body}</w:body></w:document>')
    out = OUT / name
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CT)
        z.writestr("_rels/.rels", RELS)
        z.writestr("word/document.xml", doc)
    print("DOCX_OK", out)
    return out


# ── 样本①：B45 条款样本（单行单列结论表 + 一二三四节 + 小标题 + 段内加粗）──
def make_b45():
    paras = []
    paras.append(para([("申报单位：上海B45条款回填测试有限公司", False)]))
    paras.append("<w:tbl><w:tr><w:tc>")
    paras.append(para([("资料评审意见和结论", False)]))
    paras.append(para([("一、基本情况", False)], size=36))
    paras.append(para([("该企业为条款回填功能测试用虚拟企业，不存在真实业务。", False)]))
    paras.append(para([("二、主要优势", False)], size=36))
    paras.append(para([("战略引领发展", False)], size=36))     # 小标题（大字号）
    paras.append(para([("该企业实施", False), ("“技术创新驱动、质量品牌引领”总体战略", True),
                       ("，以技术创新构建", False), ("核心壁垒", True), ("，实现高质量、可持续发展。", False)]))
    paras.append(para([("顾客精准经营", False)], size=36))     # 小标题
    paras.append(para([("建立了", False), ("差异化顾客关系管理体系", True), ("，设立", False),
                       ("400 投诉热线与客户经理通道", True), ("，近 3 年顾客满意度持续提升。", False)]))
    paras.append(para([("三、主要改进建议", False)], size=36))
    paras.append(para([("报告中对方法的表述缺少制度引用，建议做些", False), ("制度梳理及完善", True), ("。", False)]))
    paras.append(para([("四、资料评审结论", False)], size=36))
    paras.append(para([("同意进入资料评审下一环节。", False)]))
    paras.append("</w:tc></w:tr></w:tbl>")
    return write_docx("B45条款样本.docx", "".join(paras))


# ── 样本②：多行表式样（1列3行表 行=节 + 中文序号加粗标题句 + 质量模式尾段）──
def make_wutong():
    rows = []
    rows.append(cell([
        para([("组织基本情况：", True)], size=32),
        para([("上海示例阀门制造有限公司创立于1988年，员工220人，专注工业阀门设计制造。", False)]),
    ]))
    rows.append(cell([
        para([("主要的优势和创新点：", True)], size=30),
        para([("（一）围绕四大战略方向，聚焦引进人才、留住人才为目标，建立人才发展规划，为员工提供发展平台", True)]),
        para([("公司围绕总体战略规划发展，建立了人才发展规划，近三年引进人才30余人。", False)]),
        para([("（二）制度筑基、平台聚智、创新驱动，打造技术实力", True)]),
        para([("公司通过技术评估机制不断开展技术创新，形成8项核心技术。", False)]),
        para([("质量模式：同心四阶双驱 质量管理模式", True)], size=28),
        para([("公司以「同心」筑牢组织质量文化根基，以「四阶质量门」设置全流程刚性管控节点。", False)]),
    ]))
    rows.append(cell([
        para([("主要的改进建议：", True)], size=30),
        para([("1. 进一步加强知识管理体系建设。", False)]),
        para([("系统梳理公司38年发展的知识积累，推动分散知识集成化。", False)]),
    ]))
    body = ('<w:p><w:r><w:t>申报单位：上海示例阀门制造有限公司</w:t></w:r></w:p>'
            f'<w:tbl>{"".join(f"<w:tr>{r}</w:tr>" for r in rows)}</w:tbl>')
    return write_docx("多行表式样样本.docx", body)


# ── 样本③：概述式样复刻（2026-10-26 用户定：概述段 ≤50 字 + 展开段，展开内加粗=方法；
#    2026-11-02 开源脱敏：企业名换虚构「上海示例包装材料有限公司」，行业内容同步中性化）──
# 2026-10-27 用户约定升级：方法 = 加粗文字按「。」断句，一句一方法——本样本把加粗
# 重新标成「完整句子+。」（示范用户复盘时的标注方式）：优势 1 展开段标 3 个完整句，
# 优势 2/3 与建议段各标 1-2 个完整句；未标加粗的正文句不计入方法。
def make_overview_style():
    paras = []
    paras.append(para([("浦东新区政府质量奖资料评审报告", True)], size=36))
    paras.append(para([("申报单位：上海示例包装材料有限公司", False)]))
    paras.append("<w:tbl><w:tr><w:tc>")
    paras.append(para([("资料评审意见和结论", True)], size=28))
    paras.append(para([("一、基本情况", False)]))
    paras.append(para([("上海示例包装材料有限公司是一家专注于环保包装材料制造业务的企业。", False)]))
    paras.append(para([("二、主要优势", False)]))
    # 优势 1：概述段（sz32）+ 展开段（3 个完整加粗句）
    paras.append(para([("深耕专业领域，聚焦关键客户群体，不断增进细分市场的竞争优势。", False)], size=32))
    paras.append(para([
        ("公司实施“技术创新驱动、场景融合赋能、质量品牌引领、绿色低碳发展”的总体战略，"
         "以技术创新构建核心壁垒，以保险场景融合拓展市场空间，以质量提升打造品牌优势，"
         "以绿色发展践行社会责任，实现企业高质量、可持续发展。", True),
        ("公司结合包装材料制造核心业务、产品特点与战略发展方向，"
         "采用“客户类型、市场区域、销售渠道、产品品类”多维度细分方法，"
         "对目标市场与顾客群体进行精准细分，确定当前及未来的目标顾客群与细分市场。", True),
        ("针对不同的顾客群和细分市场，公司建立了差异化的、多渠道的顾客需求了解方法，"
         "并建立顾客信息收集的全渠道体系，包括市场调研、客户访谈、问卷调查、销售对接反馈、"
         "售后投诉与建议、行业展会、合作洽谈会、线上反馈渠道等，全面收集当前及以往顾客的相关信息与反馈。", False),
        ("建立统一的顾客档案与信息库，对顾客信息进行分类、整理、存储与分析，形成结构化的顾客需求数据库。", True),
        ("基于对顾客市场的了解，建立了差异化的顾客关系管理体系，针对不同顾客群制定对应的顾客关系维护策略，"
         "明确顾客接触渠道与服务标准，建立高效的顾客投诉处理机制，提升顾客满意度与忠诚度；"
         "设立 400 投诉热线、客户经理投诉通报、总经理邮箱等多渠道投诉受理方式，"
         "授权一线客户经理与服务人员第一时间处理客户投诉，最大限度减少顾客不满意。", False),
    ]))
    # 优势 2：概述段 + 展开段（2 个完整加粗句）
    paras.append(para([("构建全价值链精益制造能力体系，形成显著的绿色制造竞争优势。", False)], size=32))
    paras.append(para([
        ("公司依托精益生产核心能力，构建了覆盖原料检验、成型加工、印刷复合、分切包装、成品检测的"
         "全流程制造工艺链，关键工序实现自动化作业与全过程数据记录。", True),
        ("针对产品特性，建立了批次溯源与质量一致性管控机制，对每批原料实行来源登记、"
         "缺陷分级、可用性评估，确保产品性能达到或超过标准要求。", True),
        ("通过绿色包装业务，公司显著降低了资源消耗与碳排放，形成了区别于一般制造企业的绿色制造竞争优势，"
         "也为行业提供了可参考的质量管理实践。", False),
    ]))
    # 优势 3：概述段 + 展开段（1 个完整加粗句）
    paras.append(para([("人才梯队与技能认证双轮驱动", False)], size=32))
    paras.append(para([
        ("公司建立了“关键岗位继任计划 + 技能等级认证”的人才培养双机制，"
         "对成型工艺、质量管控、客户服务等关键岗位实行梯队化管理，每年开展技能等级认定与岗位轮换。", True),
        ("通过内训师制度与师带徒机制，将核心工艺经验固化为可传承的组织知识，"
         "关键岗位人才保留率持续提升，为企业规模化发展提供了稳定的人才保障。", False),
    ]))
    paras.append(para([("三、主要改进建议", False)]))
    # 建议：概述段 + 展开段（1 个完整加粗句）
    paras.append(para([("知识管理与经验沉淀机制有待健全。", False)], size=32))
    paras.append(para([
        ("调研发现公司尚未建立系统化的知识管理机制，工艺经验、顾客需求洞察等核心知识"
         "主要依赖个人经验传承，存在流失风险。", False),
        ("建议建立结构化的知识库与案例复盘机制，将关键工艺参数、故障处理案例、顾客需求模式等"
         "纳入统一管理，明确知识的采集、评审、更新与推广应用流程，把个人经验转化为组织资产。", True),
    ]))
    paras.append("</w:tc></w:tr></w:tbl>")
    return write_docx("概述式样样本.docx", "".join(paras))


if __name__ == "__main__":
    make_b45()
    make_wutong()
    make_overview_style()
    print("FIXTURES_DONE")
