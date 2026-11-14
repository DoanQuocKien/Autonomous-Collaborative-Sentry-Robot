from pathlib import Path

from tools.check_midterm_page_budget import audit_midterm_report


def test_estimate_does_not_hide_missing_chapters_or_images(tmp_path):
    report = tmp_path/'draft.md'
    report.write_text('# Chương 1 — Intro\n' + 'word '*5000 + '\n![F1](missing.png)')
    result = audit_midterm_report(report)
    assert result['budget_estimate_met']
    assert result['status'] == 'WARN'
    assert not result['structure_complete']
    assert result['broken_assets'][0]['path'] == 'missing.png'
    assert result['rendered_layout_verified'] is False


def test_rendered_budget_requires_pdf_matching_current_source(tmp_path):
    import pytest
    pytest.importorskip('reportlab')
    pytest.importorskip('pypdf')
    from tools.render_midterm_report import render
    font_dir = Path('/usr/share/fonts/truetype/dejavu')
    if not (font_dir/'DejaVuSans.ttf').is_file():
        pytest.skip('PDF export needs DejaVu Sans; use --font-dir on other platforms')
    report = tmp_path/'draft.md'
    pages = ['# Chương %d — Test\nNội dung.' % i for i in range(1, 9)]
    pages += ['# Phụ lục A — Code\nCác module.']
    pages += ['## Tiếp\nNội dung.']*5
    report.write_text('\n<!-- pagebreak -->\n'.join(pages))
    pdf = tmp_path/'draft.pdf'
    render(report, pdf, font_dir)
    result = audit_midterm_report(report, pdf)
    assert result['rendered_pages'] == 14
    assert result['rendered_page_budget_met']
    assert result['status'] == 'PASS'  # short word count does not override actual pages
    report.write_text(report.read_text() + '\nChanged after rendering.')
    result = audit_midterm_report(report, pdf)
    assert not result['rendered_layout_verified']
    assert result['status'] == 'WARN'
