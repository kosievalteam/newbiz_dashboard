# -*- coding: utf-8 -*-
"""
dashboard_data/cases_2026.csv → dashboard_data/dash_cases_2026.csv
단계별 소요일(달력일)과 진행 중 건의 경과일(수집 시점 기준)을 붙인다.

단계 정의
  접수 날짜          = 신청일시
  접수완료 전환      = 접수완료일시          (접수대기일수 = 접수완료 - 신청)
  검토완료 날짜      = 검토의견등록일시      (검토일수 = 검토의견등록 - 접수완료)
  결과서 수령 날짜   = 검토완료일시          (결과통보일수 = 검토완료 - 검토의견등록)
  초안 작성 날짜     = 원드라이브 ① 초안 폴더에 그 협의건 파일이 처음 올라온 날
                       (① 에 없고 ③ 수정본 폴더에 있으면 ③ 에 처음 올라온 날)
  경과일             = 접수완료일부터 수집한 날까지의 날수 (대시보드 화면은 여는 날 기준으로 다시 계산)
"""
import csv
import json
from datetime import datetime
from pathlib import Path

D = Path(__file__).resolve().parent / "dashboard_data"
FMT = "%Y-%m-%d %H:%M:%S"
OPEN = ("접수완료", "검토진행", "재협의대기", "재협의진행")  # 접수완료 이후 아직 끝나지 않은 단계


def ts(s):
    s = (s or "").strip()
    for f in (FMT, "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, f)
        except ValueError:
            pass
    return None


def days(a, b):
    return "" if not (a and b) else round((b - a).total_seconds() / 86400, 1)


def main():
    status = json.loads((D / "sync_status.json").read_text(encoding="utf-8"))
    now = ts(status["collected_at"])
    rows = list(csv.DictReader((D / "cases_2026.csv").open(encoding="utf-8")))
    out = []
    # 원드라이브 ① 초안 폴더에 협의건 파일이 처음 올라온 날 = 초안 작성일
    # ① 에 파일이 없고 ③ 수정본 폴더에 있으면 ③ 에 처음 올라온 날로 대신한다
    draft, revised = {}, {}
    if (D / "onedrive_files.csv").exists():
        for f in csv.DictReader((D / "onedrive_files.csv").open(encoding="utf-8")):
            if f["단계번호"] in ("1", "3") and f["협의번호"] and f["업로드일"]:
                d = draft if f["단계번호"] == "1" else revised
                d[f["협의번호"]] = min(f["업로드일"], d.get(f["협의번호"], "9999"))
    for k, v in revised.items():
        draft.setdefault(k, v)
    for r in rows:
        a, b, c, e = ts(r["신청일시"]), ts(r["접수완료일시"]), ts(r["검토의견등록일시"]), ts(r["검토완료일시"])
        stage = r["진행단계"]
        out.append({
            "협의번호": r["협의번호"],
            "구분": r["구분"],
            "신청년도": r.get("신청년도", ""),
            "부처": r["부처"],
            "사업명": r["사업명"],
            "신청유형": r["신청유형"],
            "신청분야": r["신청분야"],
            "검토담당자": r["검토담당자"] or "미배정",
            "진행단계": stage,
            "최종결과": r["최종결과"],
            "접수일": r["신청일시"][:10],
            "접수완료일": r["접수완료일시"][:10],
            "초안작성일": draft.get(r["협의번호"], ""),
            "검토완료일": r["검토의견등록일시"][:10],
            "결과서수령일": r["검토완료일시"][:10],
            "접수월": r["신청일시"][:7],
            "검토완료월": r["검토의견등록일시"][:7],
            "결과서수령월": r["검토완료일시"][:7],
            "접수대기일수": days(a, b),
            "검토일수": days(b, c),
            "결과통보일수": days(c, e),
            "총소요일수": days(a, e),
            "경과일": (now.date() - b.date()).days if (stage in OPEN and b) else "",
            "재협의": "Y" if "(재)" in (r["검토결과"] or "") else "",
            "회신결과": r["회신결과"],
            "재협의완료일": r["재검토완료일시"][:10],
            "접수반려일": r["접수반려일시"][:10],
            "반려사유": r["접수반려사유"],
            "메모": r["메모"],
            "메모확인일": r["메모확인일시"][:10],
            "수집시각": status["collected_at"],
        })
    with (D / "dash_cases_2026.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    print(f"dash_cases_2026.csv {len(out)}건 (수집 {status['collected_at']})")

    # 원드라이브 단계별 업로드: 담당자 폴더가 없는 파일은 SIMS 검토담당자로 채운다
    od_f = D / "onedrive_files.csv"
    if od_f.exists():
        sims = {r["협의번호"]: r for r in out}
        od = list(csv.DictReader(od_f.open(encoding="utf-8")))
        rows2 = []
        for f in od:
            c = sims.get(f["협의번호"], {})
            who = f["담당자"] if f["담당자"] != "미분류" else (c.get("검토담당자") or "미분류")
            parts = f["파일명"].rsplit(".", 1)[0].split("_")
            rows2.append({
                "파일키": f["단계번호"] + "|" + f["하위폴더"] + "|" + f["파일명"],
                "협의번호": f["협의번호"], "단계번호": f["단계번호"], "단계": f["단계"],
                "담당자": who, "담당자출처": "폴더" if f["담당자"] != "미분류" else ("SIMS" if c else ""),
                "사업명": c.get("사업명") or (parts[3] if len(parts) > 3 else f["파일명"]),
                "부처": c.get("부처") or (parts[2] if len(parts) > 2 else ""),
                "SIMS단계": c.get("진행단계", ""),
                "파일명": f["파일명"], "업로드일시": f["업로드일시"], "업로드일": f["업로드일"],
                "수집시각": status["collected_at"],
            })
        with (D / "dash_onedrive.csv").open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows2[0].keys()))
            w.writeheader()
            w.writerows(rows2)
        print(f"dash_onedrive.csv {len(rows2)}개")


if __name__ == "__main__":
    main()
