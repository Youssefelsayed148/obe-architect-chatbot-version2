$ErrorActionPreference = "Stop"

$BASE_URL = "http://127.0.0.1:8080"
$VERIFY_TOKEN = "verify_me"
$PHONE = "wa:15559990001"
$PROJECT_NAME = "obe-wa-e2e"

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$REPO_ROOT = Split-Path -Parent $SCRIPT_DIR
$FIXTURES_DIR = Join-Path $REPO_ROOT "tests/fixtures"

$composeArgs = @("-p", $PROJECT_NAME, "-f", "docker-compose.yml", "-f", "docker-compose.e2e.yml")
$checks = @()

function Add-Check([string]$name, [bool]$ok, [string]$detail) {
  $script:checks += [PSCustomObject]@{
    Name = $name
    Ok = $ok
    Detail = $detail
  }
}

function Get-DbValue([string]$sql) {
  $escaped = $sql.Replace('"', '\"')
  $value = docker compose @composeArgs exec -T db psql -U obe_user -d obe_bot -t -A -c "$escaped"
  return ($value | Out-String).Trim()
}

function Invoke-WebhookFixture([string]$fixtureName) {
  $fixturePath = Join-Path $FIXTURES_DIR $fixtureName
  if (!(Test-Path $fixturePath)) {
    throw "Missing fixture: $fixturePath"
  }
  $resp = curl.exe -sS -w "__CODE__%{http_code}" -X POST "$BASE_URL/webhook/whatsapp" -H "Content-Type: application/json" --data-binary "@$fixturePath"
  $idx = $resp.LastIndexOf("__CODE__")
  if ($idx -lt 0) {
    throw "Failed to parse HTTP status for fixture $fixtureName"
  }
  $body = $resp.Substring(0, $idx)
  $code = $resp.Substring($idx + 8)
  return @{ Body = $body; Code = $code }
}

Write-Host "==> Starting stack (docker compose up -d --build)"
docker compose @composeArgs down -v --remove-orphans | Out-Null
docker compose @composeArgs up -d --build | Out-Host

Write-Host "==> Waiting for /health"
$healthOk = $false
for ($i = 0; $i -lt 60; $i++) {
  try {
    $healthResp = curl.exe -sS -o NUL -w "%{http_code}" "$BASE_URL/health"
    if ($healthResp -eq "200") {
      $healthOk = $true
      break
    }
  } catch {
    Start-Sleep -Seconds 2
    continue
  }
  Start-Sleep -Seconds 2
}
Add-Check "Health endpoint reachable" $healthOk "GET /health -> 200"
if (-not $healthOk) {
  Write-Host ""
  Write-Host "RESULT: FAIL"
  $checks | Format-Table -AutoSize | Out-Host
  exit 1
}

Write-Host "==> Running pytest (unit + integration) in compose app container"
docker compose @composeArgs run --rm --no-deps -v "${REPO_ROOT}:/workspace" -w /workspace app sh -lc "pip install --no-cache-dir -r requirements-dev.txt >/tmp/pip-install.log && python -m pytest -q"
if ($LASTEXITCODE -eq 0) {
  Add-Check "Pytest unit + integration" $true "python -m pytest -q passed"
} else {
  Add-Check "Pytest unit + integration" $false "python -m pytest -q failed"
}

Write-Host "==> Checking webhook GET verification"
$verifyResp = curl.exe -sS -w "__CODE__%{http_code}" "$BASE_URL/webhook/whatsapp?hub.verify_token=$VERIFY_TOKEN&hub.challenge=abc123"
$verifyIdx = $verifyResp.LastIndexOf("__CODE__")
$verifyBody = $verifyResp.Substring(0, $verifyIdx)
$verifyCode = $verifyResp.Substring($verifyIdx + 8)
$verifyOk = ($verifyCode -eq "200" -and $verifyBody -eq "abc123")
Add-Check "Webhook GET verification" $verifyOk "GET /webhook/whatsapp challenge echo"

Write-Host "==> Cleaning existing test conversation rows for deterministic run"
Get-DbValue "DELETE FROM messages WHERE conversation_id IN (SELECT id FROM conversations WHERE external_user_id='$PHONE' AND channel='whatsapp');" | Out-Null
Get-DbValue "DELETE FROM conversations WHERE external_user_id='$PHONE' AND channel='whatsapp';" | Out-Null
Get-DbValue "DELETE FROM email_outbox WHERE event_type='handoff_requested' AND event_key LIKE 'handoff_requested:%';" | Out-Null

Write-Host "==> Posting inbound text (main menu expected)"
$post1 = Invoke-WebhookFixture "inbound_text.json"
$in1Ok = ($post1.Code -eq "200")
$conversationId = Get-DbValue "SELECT id FROM conversations WHERE channel='whatsapp' AND external_user_id='$PHONE' ORDER BY id DESC LIMIT 1;"
if ([string]::IsNullOrWhiteSpace($conversationId)) {
  Add-Check "Inbound text -> main menu (3 buttons)" $false "Conversation was not created"
  $failed = @($checks | Where-Object { -not $_.Ok })
  foreach ($c in $checks) {
    $status = if ($c.Ok) { "PASS" } else { "FAIL" }
    Write-Host "[$status] $($c.Name) - $($c.Detail)"
  }
  Write-Host "RESULT: FAIL ($($failed.Count) checks failed)"
  exit 1
}
$outCount1 = [int](Get-DbValue "SELECT COUNT(*) FROM messages WHERE conversation_id=$conversationId AND direction='out';")
$menuButtonsCount = [int](Get-DbValue "SELECT COALESCE(jsonb_array_length(payload->'request'->'interactive'->'action'->'buttons'),0) FROM messages WHERE conversation_id=$conversationId AND direction='out' ORDER BY id ASC LIMIT 1;")
$menuButtonsOk = ($in1Ok -and $outCount1 -eq 1 -and $menuButtonsCount -eq 3)
Add-Check "Inbound text -> main menu (3 buttons)" $menuButtonsOk "POST inbound_text.json; outbound buttons=$menuButtonsCount"

Write-Host "==> Posting duplicate message id (idempotency expected)"
$postDup = Invoke-WebhookFixture "duplicate_message.json"
$outCountDup = [int](Get-DbValue "SELECT COUNT(*) FROM messages WHERE conversation_id=$conversationId AND direction='out';")
$dupOk = ($postDup.Code -eq "200" -and $outCountDup -eq 1)
Add-Check "Duplicate message id ignored" $dupOk "No extra outbound rows on duplicate provider_message_id"

Write-Host "==> Posting MENU_PROJECTS button reply"
$post2 = Invoke-WebhookFixture "button_projects.json"
$outCount2 = [int](Get-DbValue "SELECT COUNT(*) FROM messages WHERE conversation_id=$conversationId AND direction='out';")
$listRowsCount = [int](Get-DbValue "SELECT COALESCE(jsonb_array_length((payload->'request'->'interactive'->'action'->'sections'->0->'rows')),0) FROM messages WHERE conversation_id=$conversationId AND direction='out' ORDER BY id DESC LIMIT 1;")
$listOk = ($post2.Code -eq "200" -and $outCount2 -eq 2 -and $listRowsCount -ge 6)
Add-Check "MENU_PROJECTS -> list categories" $listOk "List rows=$listRowsCount (expected >=6)"

Write-Host "==> Posting PROJECT_VILLAS list selection"
$post3 = Invoke-WebhookFixture "list_villas.json"
$outCount3 = [int](Get-DbValue "SELECT COUNT(*) FROM messages WHERE conversation_id=$conversationId AND direction='out';")
$stateAfterVillas = Get-DbValue "SELECT COALESCE(state,'') FROM conversations WHERE id=$conversationId;"
$villasOk = ($post3.Code -eq "200" -and $outCount3 -eq 3 -and $stateAfterVillas -ne "")
Add-Check "PROJECT_VILLAS -> next response emitted" $villasOk "Conversation state after selection='$stateAfterVillas'"

Write-Host "==> Posting MENU_HUMAN button reply"
$post4 = Invoke-WebhookFixture "button_human.json"
$handoffStatus = Get-DbValue "SELECT handoff_status FROM conversations WHERE id=$conversationId;"
$outCount4 = [int](Get-DbValue "SELECT COUNT(*) FROM messages WHERE conversation_id=$conversationId AND direction='out';")
$ackText = Get-DbValue "SELECT COALESCE(payload->'request'->'text'->>'body','') FROM messages WHERE conversation_id=$conversationId AND direction='out' ORDER BY id DESC LIMIT 1;"
$outboxRows = [int](Get-DbValue "SELECT COUNT(*) FROM email_outbox WHERE event_type='handoff_requested' AND event_key='handoff_requested:${conversationId}:wamid-e2e-human-001';")
$handoffOk = ($post4.Code -eq "200" -and $handoffStatus -eq "human" -and $outCount4 -eq 4 -and $outboxRows -eq 1)
Add-Check "MENU_HUMAN -> handoff + single ack + outbox row" $handoffOk "handoff_status=$handoffStatus, outbox_rows=$outboxRows, ack='$ackText'"

Write-Host "==> Posting inbound text after handoff (silence expected)"
$post5 = Invoke-WebhookFixture "inbound_after_handoff.json"
$outCount5 = [int](Get-DbValue "SELECT COUNT(*) FROM messages WHERE conversation_id=$conversationId AND direction='out';")
$afterHandoffOk = ($post5.Code -eq "200" -and $outCount5 -eq 4)
Add-Check "After handoff: ACK only, no outbound bot reply" $afterHandoffOk "Outbound count remains $outCount5"

$failed = @($checks | Where-Object { -not $_.Ok })
Write-Host ""
Write-Host "=================="
Write-Host "E2E CHECK SUMMARY"
Write-Host "=================="
foreach ($c in $checks) {
  $status = if ($c.Ok) { "PASS" } else { "FAIL" }
  Write-Host "[$status] $($c.Name) - $($c.Detail)"
}
Write-Host ""
if ($failed.Count -eq 0) {
  Write-Host "RESULT: PASS"
  exit 0
}

Write-Host "RESULT: FAIL ($($failed.Count) checks failed)"
exit 1
