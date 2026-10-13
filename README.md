# 사전협의 검토현황 2026

SIMS(사전협의관리시스템)와 원드라이브 검토의견서 폴더를 매일 수집해, 검토담당자별 과업 현황을 보여주는 대시보드입니다.

## 구성

| 파일 | 역할 |
|---|---|
| `sims_login.py` | SIMS 무인 로그인 (Windows 자격 증명 관리자의 `sims.go.kr`, `sims.go.kr-2nd`) |
| `sims_sync.py` | 사전협의목록·상세·메모 수집 → `dashboard_data/cases_2026.csv` |
| `onedrive_sync.py` | 원드라이브 단계 폴더(①~⑤) 파일 목록 수집 |
| `build_dashboard_data.py` | 단계별 소요일·경과일 계산, 원드라이브 결합 |
| `build_pages.py` | 화면과 암호화한 데이터를 `docs/`에 생성 (GitHub Pages) |
| `daily_update.ps1` | 위 과정을 차례로 실행하고 푸시 (작업 스케줄러, 매일 10:00) |
| `sims_register.py`, `pages_password.py` | 로그인 정보와 대시보드 비밀번호 등록 |
| `pages_src/dashboard_body.html` | 대시보드 화면 원본 |

## 데이터 보호

- 원본 수집물(`sims_detail/`, `sims_downloads/`, `dashboard_data/`)은 저장소에 올리지 않습니다.
- `docs/data.enc.json`은 AES-256-GCM으로 암호화되어 있으며, 대시보드 비밀번호를 입력해야 브라우저에서 풀립니다.
- 비밀번호는 코드나 저장소에 없습니다.

## 용어

접수(신청일시) → 접수완료(접수대기에서 전환된 일시) → 검토완료(검토의견 등록) → 결과서 수령(검토결과 등록).
경과일은 접수완료일부터 오늘까지의 날수입니다.
