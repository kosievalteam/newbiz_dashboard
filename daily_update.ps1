# SIMS 사전협의 검토현황 매일 수집 (작업 스케줄러, 매일 10:00)
# SIMS 목록·상세·메모와 원드라이브 단계 폴더를 수집해 dashboard_data 에 CSV를 만든다.
# 이어서 GitHub Pages용 화면과 암호화 데이터를 docs 에 만들어 푸시한다(무인).
# Claude 아티팩트 대시보드에 올리는 일은 Claude Code 세션이 맡는다.
# 기록: dashboard_data\logs\update_YYYYMMDD.log
$ErrorActionPreference = "Continue"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$OutputEncoding = [Text.Encoding]::UTF8
$logDir = Join-Path $here "dashboard_data\logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir ("update_" + (Get-Date -Format "yyyyMMdd") + ".log")
function Log($msg) { "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $msg" | Out-File -FilePath $log -Append -Encoding utf8 }
function Run($name, $script) {
    Log "$name 시작"
    $out = & python $script 2>&1 | ForEach-Object { "$_" }
    $out | Out-File -FilePath $log -Append -Encoding utf8
    if ($LASTEXITCODE -ne 0) { Log "$name 실패 (종료코드 $LASTEXITCODE)"; return $false }
    return $true
}

$ok = Run "SIMS 수집" "sims_sync.py"
if (-not $ok) { Log "오류: SIMS 수집 실패로 중단"; exit 1 }
$od = Run "원드라이브 수집" "onedrive_sync.py"
if (-not $od) { Log "경고: 원드라이브 수집 실패, 이전 파일 목록을 그대로 씀" }
$ok = Run "가공" "build_dashboard_data.py"
if (-not $ok) { Log "오류: 가공 실패"; exit 1 }
# GitHub Pages 대시보드: 암호화한 데이터와 화면을 docs 에 만들고 푸시한다
$pg = Run "Pages 만들기" "build_pages.py"
if ($pg -and (Test-Path (Join-Path $here ".git"))) {
    git add -A docs 2>&1 | Out-Null
    git commit -m ("data: " + (Get-Date -Format "yyyy-MM-dd HH:mm") + " 수집분") 2>&1 | ForEach-Object { "$_" } | Out-File -FilePath $log -Append -Encoding utf8
    $push = git push origin main 2>&1 | ForEach-Object { "$_" }
    $push | Out-File -FilePath $log -Append -Encoding utf8
    if ($LASTEXITCODE -ne 0) { Log "경고: GitHub 푸시 실패" } else { Log "GitHub 푸시 완료" }
} else { Log "경고: Pages 만들기 또는 저장소 준비가 안 되어 GitHub 푸시를 건너뜀" }
Log "완료"
