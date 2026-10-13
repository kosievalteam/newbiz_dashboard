# -*- coding: utf-8 -*-
"""
SIMS 무인 로그인 공통 모듈

비밀번호는 Windows 자격 증명 관리자에서 읽는다(파일·코드에 저장하지 않음).
  cmdkey /generic:sims.go.kr /user:<아이디> /pass        (1차 비밀번호 입력 프롬프트)
  cmdkey /generic:sims.go.kr-2nd /user:2nd /pass         (2차 4자리 비밀번호 입력 프롬프트)

단독 실행 시 로그인 → 사전협의목록까지 이동해 화면 구조를 점검한다.
  python sims_login.py
"""
import re
import sys
import io

import keyring
from playwright.sync_api import sync_playwright

BASE = "https://sims.go.kr"
LOGIN_URL = BASE + "/uat/uia/egovLoginUsr.do"


def get_creds():
    c1 = keyring.get_credential("sims.go.kr", None)
    c2 = keyring.get_credential("sims.go.kr-2nd", None)
    if not c1 or not c1.password:
        raise SystemExit("자격 증명 'sims.go.kr'이 없습니다. cmdkey로 먼저 등록하세요.")
    return c1.username, c1.password, (c2.password if c2 else None)


def login(page):
    """로그인 성공 시 True. 실패 사유는 예외 메시지로 알림."""
    uid, pw, pw2 = get_creds()
    page.on("dialog", lambda d: (print(f"[알림창] {d.message}"), d.accept()))
    page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)
    page.wait_for_function("typeof jsSHA !== 'undefined' && typeof actionLogin === 'function'", timeout=30000)
    page.fill("#id", uid)
    page.fill("#encPw", pw)
    page.evaluate("actionLogin('first')")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(2500)

    # 2차 비밀번호 화면
    if page.locator("button.cert_action").is_visible():
        if not pw2:
            raise SystemExit("2차 비밀번호가 필요합니다. 'sims.go.kr-2nd' 자격 증명을 등록하세요.")
        for i, ch in enumerate(pw2[:4], 1):
            page.fill(f"#encScdPw{i}", ch)
        page.evaluate("actionLogin('second')")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2500)
    elif page.locator("button.cert_regist").is_visible():
        raise SystemExit("2차 비밀번호가 아직 등록되지 않은 계정입니다. 브라우저에서 한 번 등록하세요.")

    html = page.content()
    ok = "로그아웃" in html or "logout" in html.lower()
    if not ok:
        for fr in page.frames:
            try:
                if "로그아웃" in fr.content():
                    ok = True
                    break
            except Exception:
                pass
    if not ok:
        raise SystemExit("로그인 실패: 아이디·비밀번호를 확인하세요. (현재 URL: %s)" % page.url)
    return True


def _inspect():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        login(page)
        print("로그인 성공:", page.url)
        # 메뉴에서 사전협의목록 찾기
        targets = []
        for fr in page.frames:
            try:
                for a in fr.locator("a").all():
                    t = (a.inner_text() or "").strip()
                    if "사전협의" in t:
                        targets.append((t, a.get_attribute("href"), a.get_attribute("onclick")))
            except Exception:
                pass
        for t in targets[:30]:
            print("메뉴:", t)
        browser.close()


if __name__ == "__main__":
    _inspect()
