# -*- coding: utf-8 -*-
"""
GitHub Pages용 대시보드 만들기 → docs/index.html, docs/data.enc.json

데이터(dash_cases_2026.csv, dash_onedrive.csv)는 비밀번호로 암호화해 올린다.
(Pages 주소는 저장소가 비공개여도 누구나 열 수 있으므로, 비밀번호를 아는 사람만 내용을 본다.)
비밀번호는 Windows 자격 증명 관리자 'sims-dashboard-pages' 에서 읽는다.  → python pages_password.py 로 등록

암호화: PBKDF2-SHA256(60만 회) → AES-256-GCM. 브라우저의 WebCrypto로 푼다.
"""
import base64
import io
import json
import os
import sys
from pathlib import Path

import keyring
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

HERE = Path(__file__).resolve().parent
DATA = HERE / "dashboard_data"
DOCS = HERE / "docs"
BODY = HERE / "pages_src" / "dashboard_body.html"
ITER = 600_000

SHELL = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>사전협의 검토현황 2026</title>
<style>
:root{
  --color-bg:#f7f8f6; --color-panel:#ffffff; --color-fg:#1c2421; --color-fg-muted:#5f6b66; --color-border-line:#dfe4e0;
  --color-ok:#1f7a4d; --color-warn:#b25e00; --color-bad:#c0362c;
  --cds-chart-grid:#e6eae7; --cds-chart-axis:#aab3ae; --cds-chart-muted:#c3cbc6;
  --cds-surface-popover:#ffffff; --cds-border:#d5dbd7; --cds-shadow-popover:0 6px 20px rgba(20,30,25,.14); --cds-text-secondary:#5f6b66;
  --cds-radius:10px; --cds-dur-slow:.3s;
  --cds-gap-xs:4px; --cds-gap-sm:8px; --cds-gap-md:14px; --cds-gap-lg:20px; --cds-gap-xl:30px;
  --cds-pad-xs:4px; --cds-pad-sm:8px; --cds-pad-md:14px; --cds-pad-lg:18px;
  --cds-font-size-caption:.8rem; --cds-font-size-body:.9rem; --cds-font-size-heading:1.02rem; --cds-font-size-title:1.75rem;
  --cds-font-weight-medium:600;
  --font-anthropic-sans:"Pretendard","Noto Sans KR","Malgun Gothic",system-ui,sans-serif;
  --font-anthropic-serif:"Noto Serif KR","Nanum Myeongjo",Georgia,serif;
  --c0:#2f6f5e; --c1:#c77d2a; --c2:#7b8794; --c3:#3d6fb4; --c4:#8a5aa8; --c5:#5a9e8f; --c6:#b0566b; --c7:#9a8f3c;
}
@media (prefers-color-scheme: dark){ :root{
  --color-bg:#141917; --color-panel:#1c2320; --color-fg:#e8eeea; --color-fg-muted:#9aa7a1; --color-border-line:#2e3834;
  --color-ok:#5fc592; --color-warn:#f0a44b; --color-bad:#f0766c;
  --cds-chart-grid:#28312d; --cds-chart-axis:#55625c; --cds-chart-muted:#44504a;
  --cds-surface-popover:#232b28; --cds-border:#36413c; --cds-shadow-popover:0 6px 20px rgba(0,0,0,.5); --cds-text-secondary:#9aa7a1;
  --c0:#63b39d; --c1:#e3a25a; --c2:#9aa6b2; --c3:#79a5e3; --c4:#b68fd0; --c5:#84c4b6; --c6:#d98b9d; --c7:#c9bf6a;
  color-scheme:dark;
}}
*{box-sizing:border-box}
body{margin:0;background:var(--color-bg);color:var(--color-fg);font-family:var(--font-anthropic-sans);font-size:14px;line-height:1.45}
#dash-root{max-width:1280px;margin-inline:auto;padding-inline:clamp(16px,3vw,32px);padding-block:24px 48px}
.dash-skeleton{color:transparent!important;background:var(--cds-chart-grid);border-radius:4px}
[hidden]{display:none!important}
#lock{max-width:22rem;margin:18vh auto 0;padding:24px;background:var(--color-panel);border:1px solid var(--color-border-line);border-radius:var(--cds-radius);display:flex;flex-direction:column;gap:12px}
#lock h1{font-family:var(--font-anthropic-serif);font-weight:400;font-size:1.3rem;margin:0}
#lock p{margin:0;color:var(--color-fg-muted);font-size:.85rem}
#lock input{font:inherit;padding:9px 11px;border:1px solid var(--color-border-line);border-radius:8px;background:var(--color-bg);color:var(--color-fg)}
#lock button{font:inherit;padding:9px 11px;border:0;border-radius:8px;background:var(--color-fg);color:var(--color-bg);cursor:pointer}
#lock label{font-size:.82rem;color:var(--color-fg-muted);display:flex;gap:6px;align-items:center}
#lock .err{color:var(--color-bad);min-height:1.2em}
#topbar{max-width:1280px;margin-inline:auto;padding:10px clamp(16px,3vw,32px) 0;display:flex;justify-content:flex-end}
#topbar button{font:inherit;font-size:.8rem;background:none;border:1px solid var(--color-border-line);color:var(--color-fg-muted);border-radius:999px;padding:3px 10px;cursor:pointer}
</style>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"></script>
</head>
<body>
<div id="lock">
  <h1>사전협의 검토현황 2026</h1>
  <p>내부 자료입니다. 비밀번호를 입력하면 열립니다.</p>
  <input id="pw" type="password" autocomplete="current-password" aria-label="비밀번호" placeholder="비밀번호">
  <label><input id="keep" type="checkbox"> 이 브라우저에 기억하기</label>
  <button id="open" type="button">열기</button>
  <div class="err" id="err" role="alert"></div>
</div>
<div id="topbar" hidden><button id="relock" type="button">잠그기</button></div>
<div id="dash-root" hidden>
__BODY_HTML__
</div>
<script>
// ---- 대시보드 페이지가 쓰는 dash 인터페이스 (독립 실행용) ----
(function () {
  const store = {}, calcs = {}, subs = [];
  let unlocked = false;
  window.dash = {
    colors: ['var(--c0)', 'var(--c1)', 'var(--c2)', 'var(--c3)', 'var(--c4)', 'var(--c5)', 'var(--c6)', 'var(--c7)'],
    data(id) {
      if (!unlocked) return { status: 'loading', data: [] };
      if (store[id]) return { status: 'ok', data: store[id] };
      const c = calcs[id];
      if (c) {
        if (!c.done) { c.value = c.fn(...c.inputs.map((i) => window.dash.data(i).data)); c.done = true; }
        return { status: 'ok', data: c.value };
      }
      return { status: 'missing', data: [] };
    },
    calc(id, def) { calcs[id] = { inputs: def.inputs, fn: def.fn, done: false }; },
    onData(fn) { subs.push(fn); fn(); },
    setLink() {}, refresh() {}, params() { return {}; }, setParams() {}, resetParams() {}
  };
  window.__dashLoad = (tables) => { Object.assign(store, tables); unlocked = true; for (const c of Object.values(calcs)) c.done = false; subs.forEach((f) => f()); };
  let t; window.addEventListener('resize', () => { clearTimeout(t); t = setTimeout(() => unlocked && subs.forEach((f) => f()), 150); });
})();
</script>
__BODY_SCRIPTS__
<script>
(function () {
  const b64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
  const $ = (id) => document.getElementById(id);
  const KEY = 'sims-dash-pw';
  async function unlock(pw, quiet) {
    try {
      const r = await fetch('data.enc.json?t=' + Date.now(), { cache: 'no-store' });
      if (!r.ok) throw new Error('data');
      const j = await r.json();
      const base = await crypto.subtle.importKey('raw', new TextEncoder().encode(pw), 'PBKDF2', false, ['deriveKey']);
      const key = await crypto.subtle.deriveKey({ name: 'PBKDF2', salt: b64(j.salt), iterations: j.iter, hash: 'SHA-256' }, base, { name: 'AES-GCM', length: 256 }, false, ['decrypt']);
      const plain = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: b64(j.iv) }, key, b64(j.ct));
      const bundle = JSON.parse(new TextDecoder().decode(plain));
      const tables = {};
      for (const [id, csv] of Object.entries(bundle.tables)) tables[id] = d3.csvParse(csv);
      $('lock').hidden = true; $('dash-root').hidden = false; $('topbar').hidden = false;
      window.__dashLoad(tables);
      return true;
    } catch (e) {
      if (!quiet) $('err').textContent = e.message === 'data' ? '데이터 파일을 불러오지 못했습니다.' : '비밀번호가 맞지 않습니다.';
      return false;
    }
  }
  async function go() {
    const pw = $('pw').value; if (!pw) return;
    $('err').textContent = ''; $('open').disabled = true;
    const ok = await unlock(pw, false);
    $('open').disabled = false;
    if (ok && $('keep').checked) { try { localStorage.setItem(KEY, pw); } catch (e) {} }
  }
  $('open').addEventListener('click', go);
  $('pw').addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); });
  $('relock').addEventListener('click', () => { try { localStorage.removeItem(KEY); } catch (e) {} location.reload(); });
  let saved = null; try { saved = localStorage.getItem(KEY); } catch (e) {}
  if (saved) unlock(saved, true).then((ok) => { if (!ok) { try { localStorage.removeItem(KEY); } catch (e) {} } });
})();
</script>
</body>
</html>
"""


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    cred = keyring.get_credential("sims-dashboard-pages", None)
    if not cred or not cred.password:
        raise SystemExit("대시보드 비밀번호가 없습니다. 먼저 python pages_password.py 를 실행하세요.")
    DOCS.mkdir(exist_ok=True)

    # 1) 데이터 암호화
    status = json.loads((DATA / "sync_status.json").read_text(encoding="utf-8"))
    bundle = {"updated": status["collected_at"], "tables": {
        "sims_2026": (DATA / "dash_cases_2026.csv").read_text(encoding="utf-8"),
        "onedrive_files": (DATA / "dash_onedrive.csv").read_text(encoding="utf-8"),
    }}
    salt, iv = os.urandom(16), os.urandom(12)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER).derive(cred.password.encode("utf-8"))
    ct = AESGCM(key).encrypt(iv, json.dumps(bundle, ensure_ascii=False).encode("utf-8"), None)
    enc = lambda b: base64.b64encode(b).decode()
    (DOCS / "data.enc.json").write_text(json.dumps({"v": 1, "iter": ITER, "salt": enc(salt), "iv": enc(iv), "ct": enc(ct)}), encoding="utf-8")

    # 2) 화면: 대시보드 본문에서 <script> 는 따로 떼어 dash 인터페이스 뒤에 둔다
    body = BODY.read_text(encoding="utf-8")
    scripts, html, pos = [], [], 0
    while True:
        a = body.find("<script>", pos)
        if a < 0:
            html.append(body[pos:])
            break
        b = body.index("</script>", a) + len("</script>")
        html.append(body[pos:a])
        scripts.append(body[a:b])
        pos = b
    page = SHELL.replace("__BODY_HTML__", "".join(html)).replace("__BODY_SCRIPTS__", "\n".join(scripts))
    (DOCS / "index.html").write_text(page, encoding="utf-8")
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    print(f"docs 생성 완료 (데이터 {status['collected_at']}, 암호문 {len(ct):,}바이트)")


if __name__ == "__main__":
    main()
