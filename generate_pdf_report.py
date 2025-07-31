import os
import re
import html
import datetime
from io import BytesIO
from typing import List, Optional, Dict

from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table,
    TableStyle, Image, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# 定数
DEFAULT_FONT_PATHS = [
    "./ipaexg.ttf",
    "/usr/share/fonts/truetype/ipaexg.ttf",
    "C:\\Windows\\Fonts\\ipaexg.ttf"
]
DEFAULT_FONT_NAME    = "IPAexGothic"
DEFAULT_IMAGE_SIZE   = (120, 120)
CARD_COL_WIDTH       = 520
PERSONA_TABLE_WIDTHS = [120, 50, 330]
STRATEGY_TABLE_WIDTHS = [110, 50, 340]
PERSONA_SCORE_COLOR  = "#e67e22"
HEADER_COLOR         = colors.lightblue
STRATEGY_HEADER_COLOR = colors.HexColor("#d9eaf7")

def register_japanese_font(
    font_name: str = DEFAULT_FONT_NAME,
    candidate_paths: List[str] = DEFAULT_FONT_PATHS
) -> None:
    for fp in candidate_paths:
        if os.path.exists(fp):
            pdfmetrics.registerFont(TTFont(font_name, fp))
            return
    raise FileNotFoundError(f"日本語フォント({font_name})が見つかりません。候補: {candidate_paths}")

def extract_persona_names(persona_list: List[str], name_label_patterns: Optional[List[str]] = None) -> List[str]:
    if name_label_patterns is None:
        name_label_patterns = ["名前", "氏名"]
    names = []
    for idx, persona in enumerate(persona_list, start=1):
        found = False
        for label in name_label_patterns:
            m = re.search(rf"{re.escape(label)}[:：]\s*([^\n\(（\-]+)", persona)
            if m:
                names.append(m.group(1).strip())
                found = True
                break
        if not found:
            m2 = re.match(r".*[:：]\s*([^\s（\(\-]+)", persona.split('\n')[0])
            if m2:
                names.append(m2.group(1).strip())
            else:
                names.append(f"ペルソナ{idx}")
    return names

def persona_card_block(
    persona: str,
    img_bytes: Optional[BytesIO],
    styles,
    bg_color: colors.Color = colors.whitesmoke,
    border_color: str = "#4b6584",
    image_size: tuple = DEFAULT_IMAGE_SIZE
):
    lines = [l for l in persona.strip().split("\n") if l.strip()]
    if lines and lines[-1].strip() == "#":
        lines = lines[:-1]
    lines_fmt = []
    for line in lines:
        if ":" in line:
            head, tail = line.split(":", 1)
            lines_fmt.append(f"<b>{html.escape(head.strip())}:</b> {html.escape(tail.strip())}")
        else:
            lines_fmt.append(html.escape(line))
    content = "<br/>".join(lines_fmt)
    card = []
    if img_bytes:
        img = Image(img_bytes, width=image_size[0], height=image_size[1])
        card.append(img)
    card.append(Paragraph(content, styles["PersonaCardText"]))
    table = Table([[card]], colWidths=[CARD_COL_WIDTH])
    table.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 1.5, colors.HexColor(border_color)),
        ('BACKGROUND', (0,0), (-1,-1), bg_color),
        ('LEFTPADDING', (0,0), (-1,-1), 18),
        ('RIGHTPADDING', (0,0), (-1,-1), 18),
        ('TOPPADDING', (0,0), (-1,-1), 16),
        ('BOTTOMPADDING', (0,0), (-1,-1), 16),
    ]))
    return table

def potential_persona_card(text: str, styles):
    return persona_card_block(
        text, img_bytes=None, styles=styles, 
        bg_color=colors.HexColor("#eeeeee"),
        border_color="#555555"
    )

def parse_potential_personas(text: str) -> List[str]:
    if not text:
        return []
    candidates = re.split(
        r'\n\s*(?=\d+\.|\-+\s*\*\*名前\*\*|#|新たな顧客ペルソナ\d|^\s*$)', text
    )
    return [
        c.strip()
        for c in candidates if "名前" in c and len(c.strip()) > 8
    ]

def parse_strategy_eval_block(block: str):
    # 入力フォーマット例：
    # - 市場性 80点 市場が拡大...
    results = []
    for line in block.split("\n"):
        line = line.strip()
        if not line or not any(axis in line for axis in ["市場性","競争優位性","収益性","実現可能性","成長性"]):
            continue
        # 例：- 市場性 80点 理由...
        m = re.match(r'[-\s]*([^\s]+)\s*(\d+)点?[:：]?\s*(.*)', line)
        if m:
            axis, score, reason = m.group(1), m.group(2), m.group(3)
            results.append([axis, f"{score}点", reason])
    return results

def generate_pdf_report(
    persona_texts: List[str],
    df,
    company_name: str,
    persona_images_bytes: Optional[List[Optional[BytesIO]]] = None,
    new_potential_personas_dict: Optional[Dict[str, str]] = None,
    multi_axis_eval_dict: Optional[Dict[str, str]] = None,
    persona_score_col_pattern: str = "ペルソナ{N}スコア",
    persona_reason_col_pattern: str = "ペルソナ{N}理由",
    idea_name_col: str = "事業アイデア名",
    persona_count: int = 4,
    font_name: str = DEFAULT_FONT_NAME,
) -> BytesIO:
    register_japanese_font()
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=28, leftMargin=28, topMargin=28, bottomMargin=28)
    story = []

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Japanese", fontName=font_name, fontSize=11, leading=16))
    styles.add(ParagraphStyle(name="JapaneseTitle", fontName=font_name, fontSize=20, leading=25, spaceAfter=16, alignment=1))
    styles.add(ParagraphStyle(name="JapaneseHeading2", fontName=font_name, fontSize=14, leading=18, spaceAfter=12, textColor=colors.darkblue))
    styles.add(ParagraphStyle(name="PersonaCardText", fontName=font_name, fontSize=11, leading=16, leftIndent=0, rightIndent=0, spaceAfter=0))
    styles.add(ParagraphStyle(name="MultiAxisTitle", fontName=font_name, fontSize=13, leading=17, spaceAfter=6, textColor=colors.HexColor("#16537e")))

    persona_names = extract_persona_names(persona_texts)

    # 表紙
    story.append(Paragraph(f"{html.escape(company_name)}", styles["JapaneseTitle"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph("事業アイデア評価レポート", styles["JapaneseTitle"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"作成日: {datetime.date.today()}", styles["Japanese"]))
    story.append(Spacer(1, 30))

    # ペルソナ概要
    story.append(Paragraph("【ペルソナ概要】", styles["JapaneseHeading2"]))
    for persona, img_bytes, pname in zip(persona_texts, persona_images_bytes, persona_names):
        story.append(persona_card_block(persona, img_bytes, styles))
        story.append(Spacer(1, 24))

    story.append(PageBreak())

    # 事業アイデア評価（ペルソナ受容性）
    story.append(Paragraph("【事業アイデアごとのスコア・理由】", styles["JapaneseHeading2"]))
    idea_names = df["事業アイデア名"].unique()
    for idea_name in idea_names:
        story.append(Spacer(1, 10))
        story.append(Paragraph(f"<b>■ {html.escape(idea_name)}</b>", styles["JapaneseHeading2"]))
        data = [["ペルソナ名", "スコア", "理由"]]
        idea_df = df[df["事業アイデア名"] == idea_name]
        for idx, row in idea_df.iterrows():
            for i in range(1, persona_count+1):
                pname = persona_names[i-1] if i-1 < len(persona_names) else f"ペルソナ{i}"
                score_raw = str(row.get(f"ペルソナ{i}スコア", ""))
                score_match = re.search(r"(\d{1,3})", score_raw)
                score = f"{score_match.group(1)}点" if score_match else score_raw
                reason = str(row.get(f"ペルソナ{i}理由", ""))
                reason = re.sub(r'^[-\s]*理由[:：]?\s*', '', reason)
                data.append([
                    Paragraph(f"<b>{pname}</b>", styles["Japanese"]),
                    Paragraph(f"<b>{score}</b>", styles["Japanese"]),
                    Paragraph(reason.replace("\n", "<br/>"), styles["Japanese"])
                ])
        table = Table(data, repeatRows=1, colWidths=PERSONA_TABLE_WIDTHS)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), HEADER_COLOR),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('FONTNAME', (0,0), (-1,-1), font_name),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('ALIGN', (1,1), (1,-1), 'CENTER'),
            ('TEXTCOLOR', (1,1), (1,-1), colors.HexColor(PERSONA_SCORE_COLOR)),
            ('FONTSIZE', (1,1), (1,-1), 12),
        ]))
        story.append(table)
        story.append(Spacer(1, 14))

        # 多軸戦略評価テーブルを追加
        if multi_axis_eval_dict and idea_name in multi_axis_eval_dict:
            eval_block = multi_axis_eval_dict[idea_name]
            strategy_rows = parse_strategy_eval_block(eval_block)
            if strategy_rows:
                story.append(Paragraph("この事業アイデアの多軸戦略評価", styles["MultiAxisTitle"]))
                strategy_table_data = [["評価軸", "点数", "理由"]]
                strategy_table_data += [
                    [Paragraph(axis, styles["Japanese"]),
                     Paragraph(score, styles["Japanese"]),
                     Paragraph(reason, styles["Japanese"])]
                    for axis, score, reason in strategy_rows
                ]
                strategy_table = Table(strategy_table_data, repeatRows=1, colWidths=STRATEGY_TABLE_WIDTHS)
                strategy_table.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), STRATEGY_HEADER_COLOR),
                    ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                    ('FONTNAME', (0,0), (-1,-1), font_name),
                    ('VALIGN', (0,0), (-1,-1), 'TOP'),
                    ('ALIGN', (1,1), (1,-1), 'CENTER'),
                    ('FONTSIZE', (1,1), (1,-1), 12),
                    ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#f7fafc")])
                ]))
                story.append(strategy_table)
                story.append(Spacer(1, 20))

    # 新規潜在顧客ペルソナ
    if new_potential_personas_dict:
        story.append(PageBreak())
        story.append(Paragraph("【新規潜在顧客ペルソナ】", styles["JapaneseHeading2"]))
        for idea_name, pers in new_potential_personas_dict.items():
            story.append(Spacer(1, 8))
            story.append(Paragraph(f"■ {html.escape(idea_name)}", styles["JapaneseHeading2"]))
            cards = [potential_persona_card(cardtext, styles) for cardtext in parse_potential_personas(pers)]
            for card in cards:
                story.append(card)
                story.append(Spacer(1, 24))

    doc.build(story)
    buffer.seek(0)
    return buffer
