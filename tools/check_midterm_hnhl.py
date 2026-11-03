"""Check saved HNHL midterm evidence, missing metrics and local document links.

Offline document/data check only; does not execute models or robot tests.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from tools.build_midterm_hnhl import ROOT, OUT, collect, evidence_bytes
from tools.build_midterm_hnhl_update import collect_update
from tools.export_midterm_hnhl_doc import blocks


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def check():
    _, _, original = collect()
    assert read_json(OUT/'metrics.json') == original, '01/11 metrics drift; review/rebuild snapshot'
    update = collect_update()
    assert read_json(OUT/'update-2026-11-03.json') == update, '03/11 addendum drift; review/rebuild'
    assert original['reid']['rank1'] is None
    assert original['tracking']['id_switches'] is None
    assert not update['acceptance']['w5_fully_accepted']
    assert not update['acceptance']['rtx4050_combined_budget_accepted']
    assert not update['link']['latency_target_met']
    assert not update['link']['raw_frame_latency_samples_available']
    assert update['acceptance']['d3_id_switches_per_minute'] is None
    assert update['acceptance']['osnet_fp16_rank1'] is None
    assert update['d5_640']['backpack']['recall'] == 1
    assert update['d5_640']['footwear']['recall'] < .9
    assert update['d5_640']['footwear']['precision'] < .8
    assert update['d5_640']['bag']['recall'] < .9
    assert update['d5_640']['bag']['precision'] < .8
    assert update['d5_640']['wire']['recall'] < .8
    followup_path = OUT/'session-followup-2026-11-03.json'
    followup_sources = 0
    if followup_path.exists():
        followup = read_json(followup_path)
        assert {p['number'] for p in followup['pull_requests'] if p['merged']} == {93, 95, 96}
        assert followup['validation']['passed'] == 26
        assert not followup['validation']['new_d3_data']
        assert not followup['validation']['new_t1_accuracy']
        assert not followup['validation']['robot_trials']
        for source in followup['sources'].values():
            assert hashlib.sha256(evidence_bytes(ROOT/source['path'])).hexdigest() == source['sha256'], 'post-merge source drift'
            followup_sources += 1
        log = (ROOT/followup['validation']['log']).read_text(encoding='utf-8-sig')
        assert re.search(r'26 passed', log), 'targeted test log differs'
    for source in update['evidence'].values():
        assert hashlib.sha256(evidence_bytes(ROOT/source['path'])).hexdigest() == source['sha256']
    word = OUT/'HNHL-Chuong-5.docx'
    verification = read_json(OUT/'verification.json')
    word_sha = hashlib.sha256(word.read_bytes()).hexdigest()
    assert word_sha == verification['word']['sha256'], 'Word changed since visual review; render again'
    assert verification['word']['visually_reviewed_pages'] == [1, 2, 3]
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
          'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'}
    with ZipFile(word) as package:
        doc = ET.fromstring(package.read('word/document.xml'))
        sources = [item[1] for page in blocks(original) for item in page if item[0] == 'image']
        for index, source in enumerate(sources, 1):
            assert package.read(f'word/media/image{index}.png') == (OUT/source).read_bytes(), 'Word/Markdown figure differs'
    paragraphs = [''.join(p.itertext()) for p in doc.findall('.//w:p', ns)]
    markdown = (OUT/'chapter-05.md').read_text(encoding='utf-8')
    paragraph_count = 0
    for page in blocks(original):
        for item in page:
            if item[0] in ('image', 'table'):
                continue
            assert item[1] in paragraphs, 'Word text differs from original builder'
            if item[0] not in ('title', 'subtitle'):
                assert item[1] in markdown, 'Word/Markdown narrative differs'
            paragraph_count += 1
    assert len(doc.findall('.//wp:inline', ns)) == 3
    assert len(doc.findall('.//w:tbl', ns)) == 2
    count = 0
    docs = list(OUT.glob('*.md')) + [OUT.parent/'week-05.md', OUT.parent/'midterm-chapter-05.md']
    for path in docs:
        for url in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
            if '://' in url or url.startswith('#'):
                continue
            target = path.parent/unquote(url.split('#')[0])
            assert target.exists(), f'broken link: {path}: {url}'
            count += 1
    return dict(checked_date='2026-11-03', evidence_sources_checked=len(update['evidence']),
                postmerge_sources_checked=followup_sources,
                source_hashes_match=True, both_saved_snapshots_match=True,
                missing_acceptance_preserved=True, local_links_checked=count,
                original_word_sha256=word_sha, original_word_visual_review_preserved=True,
                word_markdown_paragraphs_checked=paragraph_count,
                additional_figure_sha256=hashlib.sha256((OUT/'figures/F9_single_models.png').read_bytes()).hexdigest(),
                figure_visual_review_not_automated=True,
                inference_rerun=False, application_tests_rerun=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    result = check()
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
