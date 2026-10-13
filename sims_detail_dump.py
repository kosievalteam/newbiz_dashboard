# -*- coding: utf-8 -*-
"""
SIMS 사전협의 상세화면 수집 (2026년 대시보드용)

로그인(자격 증명 관리자) → 2026년 협의건 상세화면을 차례로 열어
화면의 항목·값 쌍과 모든 표(처리이력, 메모 등)를 그대로 저장한다.
저장: sims_detail/<priId>.json, sims_detail/_html/<priId>.html

  python sims_detail_dump.py            # 2026년 전체
  python sims_detail_dump.py --limit 3  # 시험용 3건
"""
import argparse
import csv
import io
import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from sims_login import BASE, login

DETAIL_URL = BASE + "/pri/pria/selectPRIA100Detail.do?winOpen=Y&priId=PRIA_{n:015d}"
OUT = Path("sims_detail")
LOG = Path("sims_downloads/download_log.csv")
FIRST_2026 = 1070      # 2026년 첫 협의건 번호(다운로드 기록 기준)
SCAN_AHEAD = 60        # 기록 이후 새 건을 찾기 위해 더 훑을 번호 수
DELAY = 0.8

EXTRACT_JS = r"""
() => {
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const pairs = [];
  document.querySelectorAll('dt').forEach(dt => {
    const dd = dt.nextElementSibling;
    if (dd && dd.tagName === 'DD') pairs.push([clean(dt.innerText), clean(dd.innerText)]);
  });
  document.querySelectorAll('tr').forEach(tr => {
    const cells = [...tr.children];
    for (let i = 0; i < cells.length - 1; i++) {
      if (cells[i].tagName === 'TH' && cells[i + 1].tagName === 'TD')
        pairs.push([clean(cells[i].innerText), clean(cells[i + 1].innerText)]);
    }
  });
  const tables = [...document.querySelectorAll('table')].map(t => {
    const cap = clean((t.querySelector('caption') || {}).innerText || (t.previousElementSibling || {}).innerText || '');
    const rows = [...t.querySelectorAll('tr')].map(tr => [...tr.children].map(c => clean(c.innerText)));
    return { caption: cap.slice(0, 80), rows };
  });
  const heads = [...document.querySelectorAll('h1,h2,h3,h4,.tit,.title')].map(h => clean(h.innerText)).filter(Boolean);
  return { pairs, tables, heads, text: clean(document.body ? document.body.innerText : '').slice(0, 20000) };
}
"""


def ids_from_log():
    ids = set()
    if LOG.exists():
        for row in csv.reader(LOG.open(encoding="utf-8-sig")):
            m = re.match(r"PRIA_0*(\d+)", row[0] if row else "")
            if m and int(m.group(1)) >= FIRST_2026:
                ids.add(int(m.group(1)))
    return sorted(ids)


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    (OUT / "_html").mkdir(parents=True, exist_ok=True)

    known = ids_from_log()
    top = max(known) if known else FIRST_2026
    targets = sorted(set(known) | set(range(top + 1, top + 1 + SCAN_AHEAD)))
    if args.limit:
        targets = known[: args.limit]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        login(page)
        print(f"로그인 성공. 대상 {len(targets)}건")
        saved, empty_run = 0, 0
        for n in targets:
            url = DETAIL_URL.format(n=n)
            try:
                page.goto(url, wait_until="networkidle", timeout=60000)
            except Exception as e:
                print(f"  PRIA_{n}: 열기 실패 ({e})")
                continue
            data = page.evaluate(EXTRACT_JS)
            has_case = bool(re.search(r"20\d\d_\d{4}", data["text"]))
            if not has_case:
                if n > top:
                    empty_run += 1
                    if empty_run >= 15:   # 연속 빈 번호면 새 건 탐색 종료
                        break
                continue
            empty_run = 0
            pid = f"PRIA_{n:015d}"
            data["priId"] = pid
            data["url"] = url
            data["collected_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            (OUT / f"{pid}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            (OUT / "_html" / f"{pid}.html").write_text(page.content(), encoding="utf-8")
            saved += 1
            print(f"  {pid}: 저장 (항목 {len(data['pairs'])}, 표 {len(data['tables'])})")
            time.sleep(DELAY)
        browser.close()
    print(f"완료: {saved}건 저장 → {OUT.resolve()}")


if __name__ == "__main__":
    main()
