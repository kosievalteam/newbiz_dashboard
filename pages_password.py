# -*- coding: utf-8 -*-
"""GitHub Pages 대시보드를 여는 비밀번호를 Windows 자격 증명 관리자에 저장한다.
  python pages_password.py
이 비밀번호를 아는 사람만 대시보드 내용을 볼 수 있다. SIMS 비밀번호와 다른 것을 쓸 것."""
import keyring

from sims_register import read_secret


def main():
    while True:
        a = read_secret("대시보드 비밀번호(10자 이상): ")
        b = read_secret("한 번 더: ")
        if a != b:
            print("  두 번 입력한 값이 다릅니다."); continue
        if len(a) < 10:
            print("  10자 이상으로 정하세요."); continue
        if not a.isascii() or a != a.strip():
            print("  영문·숫자·기호만 쓰고 앞뒤 공백 없이 입력하세요(한/영 키 확인)."); continue
        break
    try:
        old = keyring.get_credential("sims-dashboard-pages", None)
        if old:
            keyring.delete_password("sims-dashboard-pages", old.username)
    except Exception:
        pass
    keyring.set_password("sims-dashboard-pages", "dashboard", a)
    print(f"저장 완료: 대시보드 비밀번호 {len(a)}자")


if __name__ == "__main__":
    main()
