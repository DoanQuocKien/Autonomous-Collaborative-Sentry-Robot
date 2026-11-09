"""Mid-Term Report Page Budget and Verification Tool (Week 6, kouun-rokku).

Audits the merged Mid-Term Report draft against:
- Page budget constraints (10-15 pages total, 14.5 planned).
- Word count per chapter.
- Completeness of required chapters (Ch 1 - 8 + Appendix A).
- Tracking of figures (F1-F21).
- Citation of evidence files and references.

Usage:
    python -m tools.check_midterm_page_budget
    python -m tools.check_midterm_page_budget --file reports/midterm_report_draft.md
"""
import argparse
import json
from pathlib import Path
import re
from typing import Dict, List, Tuple


def audit_midterm_report(report_path: Path) -> Dict:
    if not report_path.exists():
        raise FileNotFoundError(f"Report file not found: {report_path}")

    text = report_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Split into chapters based on Markdown headers '# Chương' or '# Phụ lục'
    chapter_regex = re.compile(r"^#\s+(Chương\s+\d+|Phụ lục\s+[A-Z])\s*[-—:]?\s*(.*)$")
    
    chapters = []
    current_ch = None
    current_content = []

    for line in lines:
        m = chapter_regex.match(line.strip())
        if m:
            if current_ch:
                chapters.append((current_ch, "\n".join(current_content)))
            current_ch = m.group(1) + ": " + m.group(2).strip()
            current_content = [line]
        else:
            if current_content is not None:
                current_content.append(line)

    if current_ch:
        chapters.append((current_ch, "\n".join(current_content)))

    # Budget target mapping (Mid-Term Report Plan §1)
    budget_target = {
        "Chương 1": {"pages": 1.0, "owner": "KR"},
        "Chương 2": {"pages": 1.5, "owner": "KR"},
        "Chương 3": {"pages": 2.0, "owner": "DQK"},
        "Chương 4": {"pages": 1.5, "owner": "DQK (+KR)"},
        "Chương 5": {"pages": 3.5, "owner": "HNHL (+KR, DQK)"},
        "Chương 6": {"pages": 1.5, "owner": "KR (+DQK)"},
        "Chương 7": {"pages": 1.5, "owner": "KR (+HNHL, DQK)"},
        "Chương 8": {"pages": 1.0, "owner": "DQK"},
        "Phụ lục A": {"pages": 1.0, "owner": "KR (+HNHL, DQK)"},
    }

    # Verify required chapter completeness
    found_chapter_keys = set()
    for title, _ in chapters:
        for b_key in budget_target:
            if title.startswith(b_key):
                found_chapter_keys.add(b_key)
                break
    missing_chapters = sorted([k for k in budget_target if k not in found_chapter_keys])

    # Validate referenced image assets relative to report path
    report_dir = report_path.parent
    image_regex = re.compile(r"!\[(.*?)\]\((.*?)\)")
    image_refs = image_regex.findall(text)

    verified_assets = []
    broken_assets = []
    for alt, img_rel_path in image_refs:
        # Strip anchors or query strings if any
        clean_path = img_rel_path.split("#")[0].split("?")[0].strip()
        asset_file = report_dir / clean_path
        if asset_file.exists():
            verified_assets.append({"alt": alt, "path": clean_path, "resolved": str(asset_file)})
        else:
            broken_assets.append({"alt": alt, "path": clean_path, "attempted": str(asset_file)})

    # Count words and estimate pages (~450 Vietnamese words per page with tables/code)
    WORDS_PER_PAGE = 450.0

    chapter_stats = []
    total_words = 0

    for title, content in chapters:
        # Match prefix to budget key
        key = None
        for b_key in budget_target:
            if title.startswith(b_key):
                key = b_key
                break

        words = len(re.findall(r"\b[\w\-]+\b", content, re.UNICODE))
        total_words += words
        est_pages = round(words / WORDS_PER_PAGE, 2)
        target_pages = budget_target[key]["pages"] if key else 0.0
        owner = budget_target[key]["owner"] if key else "Unassigned"

        figures_in_ch = re.findall(r"F\d+", content)

        chapter_stats.append({
            "chapter": title,
            "owner": owner,
            "target_pages": target_pages,
            "words": words,
            "estimated_pages": est_pages,
            "figures_count": len(set(figures_in_ch)),
            "figures": sorted(list(set(figures_in_ch))),
        })

    # Find all referenced figures across entire document
    all_figures = sorted(list(set(re.findall(r"F\d+", text))))
    total_est_pages = round(total_words / WORDS_PER_PAGE, 1)

    budget_pass = 10.0 <= total_est_pages <= 15.0
    structure_pass = len(missing_chapters) == 0
    assets_pass = len(broken_assets) == 0

    overall_pass = budget_pass and structure_pass and assets_pass

    return {
        "status": "PASS" if overall_pass else "WARN",
        "file": str(report_path),
        "total_word_count": total_words,
        "total_estimated_pages": total_est_pages,
        "page_budget_range": [10.0, 15.0],
        "budget_estimate_met": budget_pass,
        "structure_complete": structure_pass,
        "missing_chapters": missing_chapters,
        "assets_verified": assets_pass,
        "broken_assets": broken_assets,
        "verified_assets_count": len(verified_assets),
        "chapter_count": len(chapters),
        "figures_referenced": all_figures,
        "figures_count": len(all_figures),
        "chapter_breakdown": chapter_stats,
        "rendered_layout_verified": False,
        "rendered_layout_note": "Word count estimate only (~450 words/p); actual 10-15 rendered page compliance unverified until layout is rendered.",
    }


def main():
    parser = argparse.ArgumentParser(description="Check page budget and structure of Mid-Term Report.")
    parser.add_argument("--file", type=Path, default=Path("reports/midterm_report_draft.md"), help="Path to merged report.")
    args = parser.parse_args()

    summary = audit_midterm_report(args.file)
    print(f"[MidTermAudit] Report: {summary['file']}")
    print(f"  Status: {summary['status']}")
    print(f"  Word count estimate: {summary['total_estimated_pages']} pages ({summary['total_word_count']} words, target 10-15 pages)")
    print(f"  Chapters present: {summary['chapter_count']}/9 (Missing: {summary['missing_chapters'] if summary['missing_chapters'] else 'None'})")
    print(f"  Referenced figures: {summary['figures_count']} ({', '.join(summary['figures_referenced'])})")
    print(f"  Asset link integrity: {'PASS (all ' + str(summary['verified_assets_count']) + ' images exist)' if summary['assets_verified'] else 'FAIL: ' + str(len(summary['broken_assets'])) + ' missing'}")
    if summary['broken_assets']:
        for b in summary['broken_assets']:
            print(f"    - Missing: {b['path']} (attempted: {b['attempted']})")
    print(f"  Rendered compliance note: {summary['rendered_layout_note']}")
    print("\n--- Chapter Breakdown ---")
    for ch in summary["chapter_breakdown"]:
        print(f"  {ch['chapter'][:40]:<40} | Owner: {ch['owner']:<15} | Target: {ch['target_pages']} p | Est: {ch['estimated_pages']} p ({ch['words']} words) | Figs: {len(ch['figures'])}")


if __name__ == "__main__":
    main()
