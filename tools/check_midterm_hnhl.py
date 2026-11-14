"""Check saved HNHL midterm evidence, missing metrics and local document links.

Offline document/data check only; does not execute models or robot tests.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from tools.build_midterm_hnhl import ROOT, OUT, collect, evidence_bytes
from tools.build_midterm_hnhl_update import collect_update
from tools.export_midterm_hnhl_doc import blocks


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def source_bytes(source):
    """Historical mutable plans are checked at their explicit full Git commit."""
    commit = source.get('git_commit')
    if commit is None:
        return evidence_bytes(ROOT/source['path'])
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('source git_commit must be a full SHA')
    return subprocess.run(['git', 'show', commit + ':' + source['path']], cwd=ROOT,
                          capture_output=True, check=True).stdout.replace(b'\r\n', b'\n')


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
            assert hashlib.sha256(source_bytes(source)).hexdigest() == source['sha256'], 'post-merge source drift'
            followup_sources += 1
        log = (ROOT/followup['validation']['log']).read_text(encoding='utf-8-sig')
        assert re.search(r'26 passed', log), 'targeted test log differs'
    for source in update['evidence'].values():
        assert hashlib.sha256(evidence_bytes(ROOT/source['path'])).hexdigest() == source['sha256']
    latest_path = OUT/'update-2026-11-05.json'
    latest_sources = 0
    if latest_path.exists():
        from tools.build_midterm_hnhl_followup import collect_followup
        latest = read_json(latest_path)
        assert latest == collect_followup(), '05/11 addendum drift; review sources before rebuilding'
        for source in latest['evidence'].values():
            assert hashlib.sha256(source_bytes(source)).hexdigest() == source['sha256'], 'latest source drift'
            latest_sources += 1
        assert latest['camera']['robot_video_available'] is False
        assert latest['acceptance']['d3_id_switches_per_minute'] is None
        assert latest['acceptance']['reid_rank1'] is None
        assert latest['acceptance']['independent_d5_t1'] is False
        assert latest['acceptance']['g2_passed'] is False
        assert latest['f18']['tensorrt_measured'] is False
    recovery_path = OUT/'update-2026-11-06.json'
    team_path = OUT/'update-2026-11-07.json'
    nov09_path = OUT/'update-2026-11-09.json'
    recovery_sources = 0
    if recovery_path.exists():
        from tools.build_midterm_hnhl_recovery import collect_recovery, recovery_chapter_text
        recovery = read_json(recovery_path)
        assert recovery == collect_recovery(), '06/11 addendum drift; review sources'
        for source in recovery['evidence'].values():
            assert hashlib.sha256(source_bytes(source)).hexdigest() == source['sha256'], 'recovery source drift'
            recovery_sources += 1
        assert recovery['camera']['video_restored_reported'] is True
        assert recovery['camera']['hn_hl_hardware_verified'] is False
        assert recovery['d3_preparation']['reviewed_labels'] is False
        assert recovery['acceptance']['new_t1_or_t2_pass'] is False
        if not team_path.exists():
            assert (OUT/'chapter-05-current.md').read_text(encoding='utf-8') == recovery_chapter_text(), 'current chapter drift'
    team_sources = 0
    if team_path.exists():
        from tools.build_midterm_hnhl_team_update import collect_team, team_chapter_text
        team = read_json(team_path)
        assert team == collect_team(), '07/11 team evidence drift'
        for source in team['evidence'].values():
            assert hashlib.sha256(source_bytes(source)).hexdigest() == source['sha256'], 'team source drift'
            team_sources += 1
        assert team['source_pr_merged'] is False
        assert team['source_review_state'] == 'CHANGES_REQUESTED'
        assert not any(team['acceptance'].values())
        assert team['runs']['home_1_3']['withdrawn_distance_fraction']
        assert team['runs']['home_3_1']['not_a_pursuit_test']
        if not nov09_path.exists():
            assert (OUT/'chapter-05-current.md').read_text(encoding='utf-8') == team_chapter_text(team), 'current chapter drift'
    nov09_sources = 0
    if nov09_path.exists():
        from tools.build_midterm_hnhl_nov09 import collect_update as collect_nov09, chapter_text
        nov09 = read_json(nov09_path)
        assert nov09 == collect_nov09(), '09/11 teammate evidence drift'
        for source in nov09['evidence'].values():
            assert hashlib.sha256(source_bytes(source)).hexdigest() == source['sha256'], '09/11 source drift'
            nov09_sources += 1
        assert not nov09['all_new_source_prs_merged']
        assert not any(nov09['acceptance'].values())
        assert not nov09['kr_phase3']['robot_acceptance']
        assert not nov09['plan_proposals']['merged']
        assert not nov09['source_corrections']['physical_cause_known']
        proxy = nov09['link_video_proxy']
        assert not proxy['limit_350ms_proven'] and not proxy['violation_proven']
        assert not proxy['mechanical_stop_measured']
        assert proxy['r1_not_held_at_end_trials'] == [4]
        assert (OUT/'chapter-05-current.md').read_text(encoding='utf-8') == chapter_text(nov09), 'current chapter drift'
    kr_followup_sources = 0
    if (OUT/'followup-pr101-2026-11-09.json').exists():
        from tools.build_midterm_hnhl_pr101_followup import collect_followup, NAME
        kr_followup = read_json(OUT/(NAME+'.json'))
        assert kr_followup == collect_followup(), 'PR101 follow-up drift'
        for source in kr_followup['evidence'].values():
            assert hashlib.sha256(source_bytes(source)).hexdigest() == source['sha256'], 'PR101 source drift'
            kr_followup_sources += 1
        assert not kr_followup['source_pr_merged']
        assert not kr_followup['new_experimental_data']
        assert not any(kr_followup['acceptance'].values())
        assert not kr_followup['validation']['reproductions']['page_audit']['rendered_layout_verified']
    nov10_sources = 0
    nov10_path = OUT/'update-2026-11-10.json'
    if nov10_path.exists():
        from tools.build_midterm_hnhl_nov10 import collect_nov10
        nov10 = read_json(nov10_path)
        assert nov10 == collect_nov10(), '10/11 evidence drift'
        for source in nov10['evidence'].values():
            assert hashlib.sha256(source_bytes(source)).hexdigest() == source['sha256'], '10/11 source drift'
            nov10_sources += 1
        assert not nov10['source_prs_merged']
        assert not any(nov10['acceptance'].values())
        assert sum(c['ranged'] for c in nov10['chairs']) == 0
        assert all(c['median_error_m'] is None for c in nov10['chairs'])
        assert not nov10['tile3_source_available']
        assert nov10['temporal_trunk_prior_m'] != nov10['fusion_trunk_prior_m']
    nov11_sources = 0
    nov11_path = OUT/'update-2026-11-11.json'
    if nov11_path.exists():
        from tools.build_midterm_hnhl_nov11 import collect_nov11
        nov11 = read_json(nov11_path)
        assert nov11 == collect_nov11(), '11/11 post-merge evidence drift'
        for source in nov11['evidence'].values():
            assert hashlib.sha256(source_bytes(source)).hexdigest() == source['sha256'], '11/11 source drift'
            nov11_sources += 1
        assert set(nov11['merged_prs']) == {'99','102','103'}
        assert all(p['merged'] for p in nov11['merged_prs'].values())
        assert not any(nov11['acceptance'].values())
        assert nov11['tile3']['hold_rows'] == 21
        assert nov11['tile3']['all_band_rows_stopped_pursue']
        assert nov11['experiment_B']['code_merged'] and not nov11['experiment_B']['model_adopted']
        assert not nov11['experiment_B']['true_empty_floor_control_available']
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
    docs = (list(OUT.glob('*.md')) + list((OUT.parent/'week-06').glob('*.md'))
            + [OUT.parent/'week-05.md', OUT.parent/'midterm-chapter-05.md'])
    for path in docs:
        for url in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
            if '://' in url or url.startswith('#'):
                continue
            target = path.parent/unquote(url.split('#')[0])
            assert target.exists(), f'broken link: {path}: {url}'
            count += 1
    snapshot_date = next(date for path,date in ((nov11_path,'2026-11-11'),(nov10_path,'2026-11-10'),
        (nov09_path,'2026-11-09'),(team_path,'2026-11-07'),(recovery_path,'2026-11-06'),
        (latest_path,'2026-11-05'),(OUT/'update-2026-11-03.json','2026-11-03')) if path.exists())
    return dict(checked_snapshot_date=snapshot_date, evidence_sources_checked=len(update['evidence']),
                postmerge_sources_checked=followup_sources,
                latest_sources_checked=latest_sources,
                recovery_sources_checked=recovery_sources,
                team_sources_checked=team_sources,
                nov09_sources_checked=nov09_sources,
                kr_followup_sources_checked=kr_followup_sources,
                nov10_sources_checked=nov10_sources,
                nov11_sources_checked=nov11_sources,
                source_hashes_match=True, both_saved_snapshots_match=True,
                missing_acceptance_preserved=True, local_links_checked=count,
                original_word_sha256=word_sha, original_word_visual_review_preserved=True,
                word_markdown_paragraphs_checked=paragraph_count,
                additional_figure_sha256=hashlib.sha256((OUT/'figures/F9_single_models.png').read_bytes()).hexdigest(),
                latest_figure_sha256=hashlib.sha256((OUT/'figures/F18_d5_precision.png').read_bytes()).hexdigest() if latest_path.exists() else None,
                team_figure_sha256=hashlib.sha256((OUT/'figures/F17_home_pilot.png').read_bytes()).hexdigest() if team_path.exists() else None,
                nov10_figure_sha256=hashlib.sha256((OUT/'figures/F10_availability_1109.png').read_bytes()).hexdigest() if nov10_path.exists() else None,
                figure_visual_review_not_automated=True,
                checker_executes_inference=False, checker_executes_application_tests=False)


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
