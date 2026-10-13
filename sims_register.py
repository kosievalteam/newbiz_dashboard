# -*- coding: utf-8 -*-
"""
SIMS 로그인 정보를 Windows 자격 증명 관리자에 저장한다.
입력한 비밀번호는 화면에 보이지 않으며, 파일에 남지 않는다.

  python sims_register.py
"""
import getpass
import sys

import keyring

try:
    import msvcrt
except ImportError:  # Windows가 아니면 기본 방식
    msvcrt = None


def read_secret(prompt):
    """입력한 글자 수만큼 *를 보여준다. Backspace로 지울 수 있다."""
    if msvcrt is None or not sys.stdin.isatty():
        return getpass.getpass(prompt)
    sys.stdout.write(prompt)
    sys.stdout.flush()
    buf = []
    while True:
        ch = msvcrt.getwch()
        if ch in ("\r", "\n"):
            sys.stdout.write("\n")
            return "".join(buf)
        if ch == "\x03":
            raise KeyboardInterrupt
        if ch == "\b":
            if buf:
                buf.pop()
                sys.stdout.write("\b \b")
        elif ch in ("\x00", "\xe0"):
            msvcrt.getwch()  # 방향키 등 무시
        else:
            buf.append(ch)
            sys.stdout.write("*")
        sys.stdout.flush()


def ask_pw(label, check):
    while True:
        a = read_secret(f"{label}: ")
        b = read_secret(f"{label} 한 번 더: ")
        if a != b:
            print("  두 번 입력한 값이 다릅니다. 다시 입력하세요.")
            continue
        msg = check(a)
        if msg:
            print("  " + msg)
            continue
        return a


def check_pw(p):
    if not p:
        return "비밀번호가 비어 있습니다."
    if not p.isascii():
        return "영문이 아닌 글자가 있습니다. 한/영 키로 영문 모드로 바꾼 뒤 다시 입력하세요."
    if p != p.strip():
        return "앞뒤에 공백이 있습니다."
    return None


def check_pw2(p):
    if not (len(p) == 4 and p.isdigit()):
        return f"2차 비밀번호는 숫자 4자리여야 합니다. (입력한 길이: {len(p)}자)"
    return None


def main():
    uid = input("SIMS 아이디: ").strip()
    if not uid.isascii():
        print("아이디에 영문이 아닌 글자가 있습니다. 한/영 키를 확인하세요.")
        return
    pw = ask_pw("1차 비밀번호", check_pw)
    pw2 = ask_pw("2차 비밀번호(숫자 4자리)", check_pw2)
    for svc in ("sims.go.kr", "sims.go.kr-2nd"):
        try:
            cred = keyring.get_credential(svc, None)
            if cred:
                keyring.delete_password(svc, cred.username)
        except Exception:
            pass
    keyring.set_password("sims.go.kr", uid, pw)
    keyring.set_password("sims.go.kr-2nd", "2nd", pw2)
    c1 = keyring.get_credential("sims.go.kr", None)
    c2 = keyring.get_credential("sims.go.kr-2nd", None)
    if c1 and c1.username == uid and c1.password == pw and c2 and c2.password == pw2:
        print(f"저장 완료: 아이디 {uid}, 1차 비밀번호 {len(pw)}자, 2차 비밀번호 4자리")
    else:
        print("저장 확인에 실패했습니다. 다시 실행해 주세요.")


if __name__ == "__main__":
    main()
