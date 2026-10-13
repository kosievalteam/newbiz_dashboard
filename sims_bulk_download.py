# -*- coding: utf-8 -*-
"""
SIMS(사전협의관리시스템) 의견서·결과서 일괄 다운로드

[사용 방법]
 1) 설치
    pip install playwright
    playwright install chromium
 2) 실행
    python sims_bulk_download.py
 3) 열린 크롬 창에서 직접 로그인 → 사전협의목록에서
    신청년도 2023~2026, 부처구분 '중앙부처' 선택 후 [검색]
 4) 목록 1페이지가 보이면 터미널에서 Enter
    → 이후 모든 페이지를 돌며 자동 다운로드
"""
import csv
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE = "https://sims.go.kr"
DETAIL_URL = BASE + "/pri/pria/selectPRIA100Detail.do?winOpen=Y&priId={pri_id}"

OUT_DIR = Path("sims_downloads")
OPINION_DIR = OUT_DIR / "의견서"
RESULT_DIR = OUT_DIR / "결과서"
LOG_FILE = OUT_DIR / "download_log.csv"
PROFILE_DIR = Path("sims_browser_profile")  # 로그인 세션 유지용

DELAY = 1.0  # 서버 부하 방지용 대기(초)
FILE_LABELS = {"의견서 다운로드": OPINION_DIR, "결과서 다운로드": RESULT_DIR}
PRI_ID_RE = re.compile(r"PRIA_\d+")
DOWN_RE = re.compile(r"fn_egov_downFile\('([^']+)'\s*,\s*'?(\d+)'?\)")


def log(row):
    new = not LOG_FILE.exists()
    with LOG_FILE.open("a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["priId", "구분", "파일명", "결과"])
        w.writerow(row)


def find_list_frame(context):
    """모든 탭·iframe 중 표 행이 가장 많은 프레임(= 사전협의 목록)을 반환"""
    best, best_n = None, -1
    for pg in context.pages:
        for fr in pg.frames:
            try:
                n = fr.locator("table tbody tr").count()
            except Exception:
                continue
            print(f"  [진단] 탭 '{pg.title()[:20]}' 프레임 {fr.url[:70]} 행 {n}")
            if n > best_n:
                best, best_n = fr, n
    return best


def collect_pri_ids_on_page(page, context):
    """현재 목록 페이지에서 협의번호 링크를 눌러 priId 수집 (page는 Page 또는 Frame)"""
    ids = []
    rows = page.locator("table tbody tr")
    if rows.count():
        print("  [진단] 첫 행 HTML:", rows.first.inner_html()[:800])
    for i in range(rows.count()):
        row = rows.nth(i)
        # 행 HTML 안에 priId가 있으면 바로 추출 (onclick, href 등)
        m = PRI_ID_RE.search(row.inner_html())
        if m:
            ids.append(m.group())
            continue
        # 없으면 협의번호 링크(텍스트가 있는 첫 링크)를 클릭해 팝업 URL에서 추출
        links = row.locator("td a").filter(has_text=re.compile(r"\d{4}_\d{4}"))
        btn = links.first
        if links.count() == 0:
            continue
        try:
            with context.expect_page(timeout=10000) as pinfo:
                btn.click()
            popup = pinfo.value
            popup.wait_for_load_state()
            m = PRI_ID_RE.search(popup.url)
            if m:
                ids.append(m.group())
            else:
                print(f"  [경고] {i + 1}번째 행 팝업 URL에서 priId 못 찾음: {popup.url}")
            popup.close()
        except PWTimeout:
            print(f"  [경고] {i + 1}번째 행 팝업 열기 실패")
    return ids


def go_next_page(page, current):
    """다음 페이지 이동. 이동 성공 시 True"""
    nxt = page.locator(f"a:text-is('{current + 1}')")
    if nxt.count() == 0:
        # 페이지 번호 묶음의 끝이면 '다음' 화살표 시도
        nxt = page.locator(
            "a.next, a.btn_next, a[title*='다음'], a:has-text('다음'), a:has-text('>')"
        )
    if nxt.count() == 0:
        return False
    nxt.first.click()
    page.wait_for_load_state("networkidle")
    time.sleep(DELAY)
    return True


def download_files(page, pri_id):
    for attempt in range(3):  # 일시적 네트워크 오류(ERR_NETWORK_IO_SUSPENDED 등) 재시도
        try:
            page.goto(DETAIL_URL.format(pri_id=pri_id))
            break
        except Exception:
            if attempt == 2:
                raise
            time.sleep(5)
    page.wait_for_load_state("networkidle")

    for label, folder in FILE_LABELS.items():
        # <dt><label>의견서 다운로드</label></dt><dd>…<a href="javascript:fn_egov_downFile('FILE_…','0')">
        cell = page.locator(
            f"xpath=//label[normalize-space()='{label}']/ancestor::dt[1]/following-sibling::dd[1]"
        )
        links = cell.first.locator("a[href*='fn_egov_downFile']") if cell.count() else None
        if links is None or links.count() == 0:
            log([pri_id, label, "", "파일 없음"])
            continue

        for k in range(links.count()):
            link = links.nth(k)
            m = DOWN_RE.search(link.get_attribute("href") or "")
            if not m:
                log([pri_id, label, "", "링크 해석 실패"])
                continue
            # 링크 텍스트: "☆ 파일명.hwp [74752 byte]" → 파일명만
            name = re.sub(r"\[\s*\d+\s*byte\s*\]", "", link.inner_text())
            name = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", name.replace("☆", "")).strip()
            try:
                resp = page.context.request.get(
                    BASE + "/cmm/fms/FileDown.do",
                    params={"atchFileId": m.group(1), "fileSn": m.group(2)},
                    timeout=60000,
                )
                if not resp.ok:
                    raise RuntimeError(f"HTTP {resp.status}")
                dest = folder / (name or f"{pri_id}_{m.group(1)}")
                if dest.exists():
                    log([pri_id, label, dest.name, "이미 존재"])
                    continue
                dest.write_bytes(resp.body())
                print(f"  ✔ {label}: {dest.name}")
                log([pri_id, label, dest.name, "완료"])
            except Exception as e:
                print(f"  ✘ {label}: 다운로드 실패 ({e})")
                log([pri_id, label, name, f"실패: {e}"])
            time.sleep(DELAY)


def main():
    for d in (OPINION_DIR, RESULT_DIR):
        d.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(PROFILE_DIR), headless=False, accept_downloads=True
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(BASE)

        input("\n로그인 후 검색 조건(2023~2026, 중앙부처)으로 [검색]하고 Enter를 누르세요...")

        # 1단계: 전체 페이지의 priId 수집
        all_ids, page_no = [], 1
        while True:
            frame = find_list_frame(context)
            ids = collect_pri_ids_on_page(frame, context)
            print(f"[목록 {page_no}페이지] {len(ids)}건 수집")
            all_ids.extend(ids)
            if not go_next_page(frame, page_no):
                break
            page_no += 1

        all_ids = list(dict.fromkeys(all_ids))  # 중복 제거
        print(f"\n총 {len(all_ids)}건 수집 완료. 다운로드 시작\n")

        # 2단계: 상세 화면에서 의견서·결과서 다운로드
        detail = context.new_page()
        for n, pri_id in enumerate(all_ids, 1):
            print(f"({n}/{len(all_ids)}) {pri_id}")
            try:
                download_files(detail, pri_id)
            except Exception as e:  # 한 건 오류로 전체가 멈추지 않도록
                print(f"  [오류] {e}")
                log([pri_id, "-", "", f"오류: {e}"])

        print(f"\n완료. 저장 위치: {OUT_DIR.resolve()}")
        context.close()


if __name__ == "__main__":
    main()
