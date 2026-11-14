"""Render the page-delimited Markdown editor copy to a Vietnamese A4 PDF.

Install requirements-report.txt. Headings, paragraphs, tables, code fences,
Markdown links and local PNG figures are supported; equations use Unicode.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from html import escape
from pathlib import Path
import re


def render(source: Path, out: Path, font_dir: Path) -> None:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                   TableStyle, Image, PageBreak)

    for name, filename in [('VN', 'DejaVuSans.ttf'), ('VN-Bold', 'DejaVuSans-Bold.ttf')]:
        pdfmetrics.registerFont(TTFont(name, str(font_dir / filename)))
    pdfmetrics.registerFontFamily('VN', normal='VN', bold='VN-Bold', italic='VN', boldItalic='VN-Bold')
    navy = colors.HexColor('#16324f')
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle('BodyVN', fontName='VN', fontSize=9.3, leading=14.2, spaceAfter=7))
    styles.add(ParagraphStyle('SmallVN', parent=styles['BodyVN'], fontSize=7.7, leading=11))
    styles.add(ParagraphStyle('CellVN', parent=styles['BodyVN'], fontSize=8.1, leading=11.6, spaceAfter=0))
    styles.add(ParagraphStyle('CaptionVN', parent=styles['SmallVN'], textColor=navy, alignment=TA_CENTER))
    for name, size in [('TitleVN', 19), ('H1VN', 15), ('H2VN', 11.3)]:
        styles.add(ParagraphStyle(name, fontName='VN-Bold', fontSize=size, leading=size+5,
                                  textColor=navy, spaceBefore=6, spaceAfter=10))
    source = Path(source)
    doc = SimpleDocTemplate(str(out), pagesize=A4, rightMargin=43, leftMargin=43,
                            topMargin=47, bottomMargin=40, title='Báo cáo giữa kỳ — Sentry Robot',
                            author='DQK / HNHL / KR', invariant=1)
    width = A4[0] - 86

    def markup(text):
        text = escape(text)
        text = re.sub(r'!\[([^]]*)\]\([^)]*\)', r'\1', text)
        text = re.sub(r'\[([^]]+)\]\(([^)]+)\)', r'\1', text)
        text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'`([^`]+)`', r'\1', text)
        return text

    story = []
    lines = source.read_text(encoding='utf-8').splitlines()
    paragraph = []

    def flush():
        if paragraph:
            story.append(Paragraph(markup(' '.join(paragraph)), styles['BodyVN']))
            paragraph.clear()

    i = 0
    code = False
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('```'):
            flush(); code = not code; i += 1; continue
        if code:
            story.append(Paragraph(escape(line) or ' ', styles['SmallVN']))
        elif line == '<!-- pagebreak -->':
            flush(); story.append(PageBreak())
        elif not line or line == '---':
            flush()
        elif line.startswith('#'):
            flush()
            level = len(line) - len(line.lstrip('#'))
            story.append(Paragraph(markup(line.lstrip('#').strip()), styles['H1VN' if level == 1 else 'H2VN']))
        elif line.startswith('|'):
            flush(); rows = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                cells = [cell.strip() for cell in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?', cell.replace(' ', '')) for cell in cells):
                    rows.append([Paragraph(markup(c), styles['CellVN']) for c in cells])
                i += 1
            count = len(rows[0])
            table = Table(rows, colWidths=[width/count]*count, repeatRows=1, hAlign='LEFT')
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e4edf4')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LINEBELOW', (0, 0), (-1, 0), .7, navy),
                ('LINEBELOW', (0, 1), (-1, -1), .25, colors.HexColor('#cad4dd')),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ]))
            story += [table, Spacer(1, 8)]
            continue
        elif line.startswith('!['):
            flush()
            match = re.fullmatch(r'!\[([^]]*)\]\(([^)]+)\)', line)
            if not match:
                raise ValueError('Unsupported image syntax: '+line)
            path = source.parent / match.group(2)
            iw, ih = ImageReader(str(path)).getSize()
            scale = min(width/iw, 183/ih)
            story += [Image(str(path), width=iw*scale, height=ih*scale),
                      Paragraph(markup(match.group(1)), styles['CaptionVN']), Spacer(1, 6)]
        elif line.startswith('- '):
            flush(); story.append(Paragraph('• ' + markup(line[2:]), styles['BodyVN']))
        else:
            paragraph.append(line)
        i += 1
    flush()

    def page(canvas, doc):
        canvas.saveState()
        canvas.setFont('VN', 7.4); canvas.setFillColor(navy)
        canvas.drawString(43, A4[1]-28, 'CS532  /  AUTONOMOUS COLLABORATIVE SENTRY ROBOT')
        canvas.drawRightString(A4[0]-43, 23, f'KR editor • snapshot 14/11/2026  |  {doc.page}')
        canvas.restoreState()
    doc.build(story, onFirstPage=page, onLaterPages=page)
    from pypdf import PdfReader
    metadata = dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                    pdf_sha256=hashlib.sha256(Path(out).read_bytes()).hexdigest(),
                    pages=len(PdfReader(out).pages), renderer='reportlab; DejaVu Sans')
    Path(str(out)+'.json').write_text(json.dumps(metadata, indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('reports/midterm_report_draft.md'))
    parser.add_argument('--out', type=Path, default=Path('reports/midterm_report.pdf'))
    parser.add_argument('--font-dir', type=Path, default=Path('/usr/share/fonts/truetype/dejavu'))
    args = parser.parse_args()
    render(args.source, args.out, args.font_dir)


if __name__ == '__main__':
    main()
