# -*- coding: utf-8 -*-
"""
SIMS 2026년 사전협의 현황 수집 → 대시보드용 CSV

1) 자격 증명 관리자 정보로 무인 로그인 (sims_login.py)
2) 2026년 협의건 상세화면을 구획(신청정보·접수완료·검토의견·검토완료 등)별로 읽음
3) 메모 화면(읽기 전용)의 메모 내용을 읽고, 처음 보이거나 바뀐 날을 기록
4) dashboard_data/cases_2026.csv, memo_history.csv 생성

  python sims_sync.py            # 전체
  python sims_sync.py --limit 3  # 시험
"""
import argparse
import csv
import io
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from sims_login import BASE, login

HERE = Path(__file__).resolve().parent
RAW = HERE / "sims_detail"
OUT = HERE / "dashboard_data"
LOG = HERE / "sims_downloads" / "download_log.csv"
DETAIL = BASE + "/pri/pria/selectPRIA100Detail.do?winOpen=Y&priId={pid}"
MEMO = BASE + "/pri/pria/selectPRIA100MemoPopup.do?priId={pid}"
FIRST_2026 = 1070
SCAN_AHEAD = 60
STOP_AFTER_EMPTY = 15
DELAY = 0.6

SHORT = {"중소벤처기업부": "중기부", "산업통상부": "산업부", "산업통상자원부": "산업부", "고용노동부": "고용부",
         "과학기술정보통신부": "과기부", "국토교통부": "국토부", "방위사업청": "방사청", "금융위원회": "금융위",
         "지식재산처": "지재처", "해양수산부": "해수부", "개인정보보호위원회": "개인정보위", "기후에너지환경부": "기후부",
         "문화체육관광부": "문체부", "농림축산식품부": "농식품부", "새만금개발청": "새만금청", "보건복지부": "복지부",
         "행정안전부": "행안부", "조달청": "조달청", "식품의약품안전처": "식약처", "재외동포청": "재외동포청", "산림청": "산림청"}

SECTION_JS = r"""
() => {
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const out = []; let cur = '머리';
  const isHead = el => /^(H1|H2|H3|H4)$/.test(el.tagName) || (el.classList && (el.classList.contains('tit') || el.classList.contains('title')));
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
  while (w.nextNode()) {
    const el = w.currentNode;
    if (isHead(el)) { const t = clean(el.innerText); if (t && t.length < 30) cur = t; continue; }
    if (el.tagName === 'DL') {
      el.querySelectorAll('dt').forEach(dt => {
        let dd = dt.nextElementSibling;
        while (dd && dd.tagName !== 'DD' && dd.tagName !== 'DT') dd = dd.nextElementSibling;
        if (dd && dd.tagName === 'DD') out.push([cur, clean(dt.innerText), clean(dd.innerText)]);
      });
    }
  }
  const code = (document.getElementById('priProgrsSttusCode') || {}).value || '';
  return { rows: out, code };
}
"""


def known_ids():
    ids = set()
    if LOG.exists():
        for row in csv.reader(LOG.open(encoding="utf-8-sig")):
            m = re.match(r"PRIA_0*(\d+)", row[0] if row else "")
            if m and int(m.group(1)) >= FIRST_2026:
                ids.add(int(m.group(1)))
    for f in RAW.glob("PRIA_*.json"):
        ids.add(int(f.stem.split("_")[1]))
    return ids


def first(rows, section_kw, label):
    for sec, k, v in rows:
        if section_kw in sec and k == label:
            return v
    return ""


def all_of(rows, label):
    return [(sec, v) for sec, k, v in rows if k == label]


CODE_STAGE = {"01": "접수대기", "02": "접수반려", "03": "접수완료", "04": "검토진행",
              "06": "협의완료(원안동의)", "07": "협의완료(권고안제시)", "08": "재협의대기",
              "09": "재협의진행", "12": "재협의완료", "13": "심의회조정"}
FINAL_CODES = {"02", "06", "07", "12"}
LIST_URL = BASE + "/pri/pria/selectPRIA100View.do?priMenuId=00011"

LIST_JS = r"""
() => [...document.querySelectorAll('table tbody tr')].map(tr => {
  const m = tr.innerHTML.match(/PRIA_\d+/);
  const c = [...tr.children].map(td => (td.innerText || '').replace(/\s+/g, ' ').trim());
  return m ? { priId: m[0], no: c[1], div: c[3], org: c[4], status: c[8], reviewer: c[9] } : null;
}).filter(Boolean)
"""


def crawl_list(page, begin="2026", end="2027", prefix="2026_"):
    """사전협의목록(신청년도 begin~end, SIMS 기본 조건)을 끝까지 넘기며 협의번호가 prefix 인 건을 모은다."""
    page.goto(LIST_URL, wait_until="networkidle", timeout=60000)
    page.select_option("#schPriProgrsReqstBeginYear", begin)
    page.select_option("#schPriProgrsReqstEndYear", end)
    found, n, prev_first = {}, 1, None
    while n < 200:
        with page.expect_navigation(wait_until="networkidle", timeout=60000):
            page.evaluate(f"linkPagePri({n})")
        rows = page.evaluate(LIST_JS)
        if not rows or rows[0]["priId"] == prev_first:
            break
        prev_first = rows[0]["priId"]
        for r in rows:
            if r["no"].startswith(prefix):
                found[r["priId"]] = r
        n += 1
        time.sleep(0.3)
    return found


def to_record(pid, d, memo):
    rows = d["rows"]
    info = lambda label: next((v for s, k, v in rows if s == "신청정보" and k == label), "")
    sec = lambda section, label: next((v for s, k, v in rows if s == section and k == label), "")
    name = next((x for x in (info("내내역사업명"), info("내역사업명"), info("세부사업명")) if x and x != "해당없음"), "")
    code = d.get("code", "")
    rec = {
        "협의번호": info("협의번호").replace("_", "-"),
        "priId": pid,
        "부처": SHORT.get(info("기관명"), info("기관명")),
        "부서": info("부서명"),
        "신청년도": info("신청년도"),
        "신청유형": info("신청유형"),
        "신청분야": info("신청분야"),
        "사업명": name,
        "세부사업명": info("세부사업명"),
        "검토담당자": sec("접수완료", "검토담당자"),
        "신청일시": info("신청일시"),
        "접수반려일시": sec("접수반려", "접수반려일시"),
        "접수반려사유": sec("접수반려", "접수반려사유").rstrip(" -"),
        "접수완료일시": sec("접수완료", "접수완료일시"),
        "검토의견등록일시": sec("검토의견", "등록일시"),
        "검토완료일시": sec("검토완료", "등록일시"),
        "검토결과": sec("검토완료", "검토결과"),
        "회신일시": sec("회신의견", "등록일시"),
        "회신결과": sec("회신의견", "검토결과"),
        "재검토완료일시": sec("(재)검토완료", "등록일시"),
        "재검토결과": sec("(재)검토완료", "(재)검토결과"),
        "상태코드": code,
        "메모": memo,
        "구획": "·".join(dict.fromkeys(s for s, k, v in rows if s != "신청정보")),
    }
    lst = d.get("list") or {}
    rec["구분"] = lst.get("div") or info("구분")
    rec["검토담당자"] = rec["검토담당자"] or lst.get("reviewer", "")
    rec["진행단계"] = CODE_STAGE.get(code) or lst.get("status") or "기타"
    rec["최종결과"] = rec["재검토결과"] or rec["검토결과"]
    return rec


def rebuild():
    """저장된 원본(sims_detail)으로 CSV만 다시 만든다."""
    recs = []
    for f in sorted(RAW.glob("PRIA_*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if not any(k == "협의번호" and v.startswith("2026") for s, k, v in d["rows"]):
            continue
        recs.append(to_record(f.stem, d, d.get("memo", "")))
    return recs


def write_outputs(records, now, limit):
    # 메모 이력: 메모가 처음 보이거나 바뀐 날을 남긴다
    hist_f = OUT / "memo_history.csv"
    hist = list(csv.DictReader(hist_f.open(encoding="utf-8"))) if hist_f.exists() else []
    last = {}
    for h in hist:
        last[h["협의번호"]] = h["메모"]
    for r in records:
        if r["메모"] and last.get(r["협의번호"]) != r["메모"]:
            hist.append({"협의번호": r["협의번호"], "메모": r["메모"], "확인일시": now})
            last[r["협의번호"]] = r["메모"]
    with hist_f.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["협의번호", "메모", "확인일시"])
        w.writeheader()
        w.writerows(hist)
    first_seen = {}
    for h in hist:
        first_seen.setdefault(h["협의번호"], {})[h["메모"]] = h["확인일시"]
    for r in records:
        r["메모확인일시"] = first_seen.get(r["협의번호"], {}).get(r["메모"], "") if r["메모"] else ""

    if records and not limit:
        cols = list(records[0].keys())
        records.sort(key=lambda r: r["협의번호"])
        with (OUT / "cases_2026.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(records)
        (OUT / "sync_status.json").write_text(json.dumps({"collected_at": now, "count": len(records)}, ensure_ascii=False), encoding="utf-8")
    print(f"완료: 2026년 {len(records)}건")
    if limit:
        for r in records:
            print(json.dumps({k: v for k, v in r.items() if k != "부서"}, ensure_ascii=False))




def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--rebuild", action="store_true", help="수집 없이 저장된 원본으로 CSV만 다시 만듦")
    args = ap.parse_args()
    if args.rebuild:
        records = rebuild()
        write_outputs(records, json.loads((OUT / "sync_status.json").read_text(encoding="utf-8"))["collected_at"], False)
        print(f"재계산 완료: {len(records)}건")
        return
    RAW.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    records = []
    refresh_all = datetime.now().weekday() == 0  # 월요일에는 끝난 건도 다시 읽음
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        login(page)
        listing = crawl_list(page)
        print(f"[{now}] 로그인 성공, 목록 {len(listing)}건")
        if len(listing) < 50 and not args.limit:
            raise SystemExit(f"목록이 {len(listing)}건뿐입니다. 목록 화면 구조가 바뀌었는지 확인하세요.")
        items = sorted(listing.values(), key=lambda r: r["no"])
        if args.limit:
            items = items[: args.limit]
        for it in items:
            pid = it["priId"]
            raw_f = RAW / f"{pid}.json"
            old = json.loads(raw_f.read_text(encoding="utf-8")) if raw_f.exists() else None
            if (old and not refresh_all and old.get("code") in FINAL_CODES
                    and (old.get("list") or {}).get("status") == it["status"]):
                records.append(to_record(pid, old, old.get("memo", "")))
                continue
            try:
                page.goto(DETAIL.format(pid=pid), wait_until="networkidle", timeout=60000)
                d = page.evaluate(SECTION_JS)
            except Exception as e:
                print(f"  {pid}: 상세 실패 ({e})")
                if old:
                    records.append(to_record(pid, old, old.get("memo", "")))
                continue
            memo = ""
            try:
                page.goto(MEMO.format(pid=pid), wait_until="networkidle", timeout=60000)
                memo = (page.locator("#memoCn").input_value() if page.locator("#memoCn").count() else "").strip()
            except Exception as e:
                print(f"  {pid}: 메모 읽기 실패 ({e})")
            d["list"] = it
            raw_f.write_text(json.dumps({"collected_at": now, **d, "memo": memo}, ensure_ascii=False, indent=1), encoding="utf-8")
            rec = to_record(pid, d, memo)
            records.append(rec)
            print(f"  {rec['협의번호']} {rec['진행단계']} {rec['검토담당자']}")
            time.sleep(DELAY)
        browser.close()

    write_outputs(records, now, args.limit)


if __name__ == "__main__":
    main()
