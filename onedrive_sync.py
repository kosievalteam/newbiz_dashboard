# -*- coding: utf-8 -*-
"""
원드라이브 공유 폴더(검토의견서)의 단계별 폴더를 끝까지 훑어
파일별 폴더·이름·올린 날짜·수정한 사람을 dashboard_data/onedrive_files.csv 로 저장한다.
PC에 동기화된 폴더(LOCAL)가 있으면 그것을 읽고, 없으면 웹 공유 링크로 읽는다.
공유 링크는 로그인 없이 열리는 링크여야 한다.
"""
import csv
import io
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

def _link():
    """공유 링크는 저장소에 두지 않는다. Windows 자격 증명 관리자 'sims-onedrive-link' 에서 읽는다."""
    import keyring
    c = keyring.get_credential("sims-onedrive-link", None)
    if not c or not c.password:
        raise SystemExit("원드라이브 공유 링크가 없습니다. 자격 증명 'sims-onedrive-link' 를 등록하세요.")
    return c.password


LINK = None
OUT = Path(__file__).resolve().parent / "dashboard_data"
# PC에 동기화된 원드라이브 폴더 (있으면 웹 공유 링크 대신 이것을 읽는다)
LOCAL = Path.home() / "OneDrive" / "업무자료" / "사전협의" / "'26년 검토의견서"

FETCH_JS = """
async ([api, folder]) => {
  const url = api.replace(/RootFolder=[^&]*/, 'RootFolder=' + encodeURIComponent(folder).replace(/'/g, '%27').replace(/[(]/g, '%28').replace(/[)]/g, '%29'));
  const rows = []; let next = '';
  for (let i = 0; i < 20; i++) {
    const r = await fetch(url + (next ? '&' + next.replace(/^[?]/, '') : ''), {
      method: 'POST', credentials: 'include',
      headers: {'accept': 'application/json;odata=verbose', 'content-type': 'application/json;odata=verbose'},
      body: JSON.stringify({parameters: {RenderOptions: 5707527, AllowMultipleValueFilterForTaxonomyFields: true, AddRequiredFields: true}})
    });
    if (!r.ok) return {error: r.status, rows};
    const d = await r.json(); const ld = d.ListData || d;
    for (const x of (ld.Row || [])) rows.push({
      name: x.FileLeafRef, ref: x.FileRef, folder: x.FSObjType === '1',
      modified: x['Modified.'] || x.Modified, created: x['Created_x0020_Date'] || '',
      editor: (Array.isArray(x.Editor) && x.Editor[0] ? x.Editor[0].title : ''), size: x.File_x0020_Size || ''
    });
    next = ld.NextHref || ''; if (!next) break;
  }
  return {rows};
}
"""


def _row(stage, sub, name, kst, editor):
    """단계 폴더 이름·하위 폴더·파일명에서 담당자·분야·협의번호를 읽어 한 줄로 만든다."""
    who = ""
    for part in sub:
        m = re.search(r"\]\s*([가-힣]{2,4})\s*$", part) or re.search(r"\[([가-힣]{2,4})\]\s*$", part)
        if m:
            who = m.group(1)
            break
    field = next((re.match(r"\[([^\]]+)\]", p_).group(1) for p_ in sub if re.match(r"\[([^\]]+)\]\s*[가-힣]", p_)), "")
    m = re.search(r"(20\d\d)[-_]0*(\d{1,4})", name)
    return {"단계": stage, "단계번호": "①②③④⑤".find(stage[0]) + 1,
            "담당자": who or "미분류", "분야": field,
            "협의번호": f"{m.group(1)}-{int(m.group(2)):04d}" if m else "",
            "하위폴더": "/".join(sub), "파일명": name,
            "업로드일시": kst.strftime("%Y-%m-%d %H:%M") if kst else "",
            "업로드일": kst.strftime("%Y-%m-%d") if kst else "",
            "수정한사람": editor}


def scan_local(root):
    """PC에 동기화된 원드라이브 폴더를 읽는다. 올린 날짜는 파일의 수정 시각(한국 시각)이며, 수정한 사람은 알 수 없다."""
    files = []
    for f in root.rglob("*"):
        if not f.is_file() or (f.name.startswith("_") and f.suffix == ".csv") or f.name.startswith("~$") or f.name.lower() == "desktop.ini":
            continue
        rel = f.relative_to(root).parts
        if len(rel) < 2 or rel[0][:1] not in "①②③④⑤":
            continue
        files.append(_row(rel[0], list(rel[1:-1]), f.name, datetime.fromtimestamp(f.stat().st_mtime), ""))
    return files


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    OUT.mkdir(exist_ok=True)
    # 1) PC에 동기화된 폴더가 있으면 그것을 읽는다 (웹 공유 링크가 막혀도 동작)
    if LOCAL.is_dir():
        files = scan_local(LOCAL)
        print(f"로컬 동기화 폴더에서 읽음: {LOCAL}")
        _write(files)
        return
    # 2) 없으면 웹 공유 링크로 읽는다
    api = {}
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page()
        pg.on("request", lambda r: api.setdefault("url", r.url) if "RenderListDataAsStream" in r.url and "RootFolder=" in r.url else None)
        pg.goto(_link(), wait_until="domcontentloaded", timeout=90000)
        for _ in range(40):
            if "url" in api:
                break
            pg.wait_for_timeout(1000)
        if "url" not in api:
            raise SystemExit("원드라이브 폴더 목록을 열지 못했습니다(공유 링크 확인 필요).")
        pg.wait_for_timeout(3000)
        from urllib.parse import unquote, urlparse, parse_qs
        root = parse_qs(urlparse(api["url"]).query)["RootFolder"][0]
        files, stack = [], [root]
        while stack:
            f = stack.pop()
            res = pg.evaluate(FETCH_JS, [api["url"], f])
            if res.get("error"):
                print("  읽기 실패", res["error"], f[len(root):])
                continue
            for r in res["rows"]:
                if r["folder"]:
                    stack.append(r["ref"])
                else:
                    if r["name"].startswith("_") and r["name"].endswith(".csv"):
                        continue
                    rel = r["ref"][len(root):].strip("/").split("/")
                    if len(rel) < 2:
                        continue
                    kst = datetime.strptime(r["modified"][:19], "%Y-%m-%dT%H:%M:%S") + timedelta(hours=9) if r["modified"] else None
                    files.append(_row(rel[0], rel[1:-1], r["name"], kst, r["editor"]))
        b.close()
    _write(files)


def _write(files):
    if not files:
        raise SystemExit("원드라이브 파일을 하나도 찾지 못했습니다.")
    files.sort(key=lambda x: (x["단계"], x["담당자"], x["파일명"]))
    with (OUT / "onedrive_files.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(files[0].keys()))
        w.writeheader()
        w.writerows(files)
    print(f"원드라이브 파일 {len(files)}개")


if __name__ == "__main__":
    main()
