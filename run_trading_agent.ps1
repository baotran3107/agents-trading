# Order Flow Trading Agent - Windows Service
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# Load required UI assemblies
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# 1. Environment & Config Setup
$scriptDir = $PSScriptRoot
if (-not $scriptDir) { $scriptDir = (Get-Location).Path }
$envPath = Join-Path $scriptDir ".env"
$capturesDir = Join-Path $scriptDir "data\captures"
$msgConfigPath = Join-Path $scriptDir "config\messages.json"
$promptFilePath = Join-Path $scriptDir "prompts\plan_prompt.txt"
$schemaFilePath = Join-Path $scriptDir "config\daily_plan_schema.json"

if (-not (Test-Path $capturesDir)) {
    New-Item -ItemType Directory -Path $capturesDir -Force | Out-Null
}

# Load .env variables
if (Test-Path $envPath) {
    Get-Content $envPath | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $idx = $line.IndexOf("=")
            if ($idx -gt 0) {
                $key = $line.Substring(0, $idx).Trim()
                $val = $line.Substring($idx + 1).Trim().Trim('"').Trim("'")
                [Environment]::SetEnvironmentVariable($key, $val, "Process")
            }
        }
    }
}

$botToken = $env:TELEGRAM_BOT_TOKEN
$chatId = $env:TELEGRAM_CHAT_ID
$modelName = if ($env:ARGON_MODEL) { $env:ARGON_MODEL } else { "gemini-3.8-flash-medium" }
$symbol = "XAUUSD"

if (-not $botToken -or -not $chatId) {
    Write-Host "[ERROR] Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID in .env file!" -ForegroundColor Red
    pause
    exit 1
}

$telegramEndpoint = "https://" + ("api", "telegram", "org" -join ".") + "/bot" + $botToken

# Load Messages & Prompt Template
$msgContent = [System.IO.File]::ReadAllText($msgConfigPath, [System.Text.Encoding]::UTF8)
$msg = $msgContent | ConvertFrom-Json

$promptTemplate = [System.IO.File]::ReadAllText($promptFilePath, [System.Text.Encoding]::UTF8)

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  ORDER FLOW TRADING AGENT - WINDOWS SERVICE" -ForegroundColor Green
Write-Host "  Chat ID: $chatId | Model: $modelName" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 2. Telegram Helper Functions
function Send-TelegramText([string]$text, [string]$replyMarkupJson = "") {
    $url = "$telegramEndpoint/sendMessage"
    $body = @{
        chat_id = $chatId
        text = $text
        parse_mode = "Markdown"
    }
    if ($replyMarkupJson) {
        $body["reply_markup"] = $replyMarkupJson
    }
    try {
        Invoke-RestMethod -Uri $url -Method Post -Body $body -ContentType "application/x-www-form-urlencoded; charset=utf-8" | Out-Null
    } catch {
        Write-Warning "Telegram send error: $_"
    }
}

function Send-TelegramPhotoWithPlan([string]$imagePath, [string]$caption, [string]$replyMarkupJson = "") {
    $url = "$telegramEndpoint/sendPhoto"
    Write-Host "[*] Sending image and plan to Telegram..." -ForegroundColor Cyan

    $curlExe = if (Test-Path "$env:SystemRoot\System32\curl.exe") { "$env:SystemRoot\System32\curl.exe" } else { "curl" }

    $argsList = @(
        "-s",
        "-X", "POST", $url,
        "-F", "chat_id=$chatId",
        "-F", "photo=@$imagePath",
        "-F", "caption=$caption",
        "-F", "parse_mode=Markdown"
    )
    if ($replyMarkupJson) {
        $argsList += "-F"
        $argsList += "reply_markup=$replyMarkupJson"
    }

    & $curlExe @argsList | Out-Null
}

function Answer-CallbackQuery([string]$callbackQueryId, [string]$toastText) {
    $url = "$telegramEndpoint/answerCallbackQuery"
    try {
        Invoke-RestMethod -Uri $url -Method Post -Body @{
            callback_query_id = $callbackQueryId
            text = $toastText
        } | Out-Null
    } catch {
        Write-Warning "Callback query error: $_"
    }
}

# 3. Dual Monitor Screen Capture Function
function Capture-DualScreens() {
    $timestamp = (Get-Date).ToString("yyyyMMdd_HHmmss")
    $leftPath = Join-Path $capturesDir "chart_left_$timestamp.png"
    $rightPath = Join-Path $capturesDir "chart_right_$timestamp.png"
    $stitchedPath = Join-Path $capturesDir "chart_stitched_$timestamp.png"

    $allScreens = [System.Windows.Forms.Screen]::AllScreens | Sort-Object { $_.Bounds.X }

    if ($allScreens.Count -ge 2) {
        $leftMon = $allScreens[0]
        $rightMon = $allScreens[1]
        Write-Host "[*] Detected 2 monitors:" -ForegroundColor Green
        Write-Host "    - Left (VP & Footprint): $($leftMon.Bounds.Width)x$($leftMon.Bounds.Height)"
        Write-Host "    - Right (Bookmap):       $($rightMon.Bounds.Width)x$($rightMon.Bounds.Height)"

        # 1. Capture Left Screen
        $bmpLeft = New-Object System.Drawing.Bitmap($leftMon.Bounds.Width, $leftMon.Bounds.Height)
        $gLeft = [System.Drawing.Graphics]::FromImage($bmpLeft)
        $gLeft.CopyFromScreen($leftMon.Bounds.X, $leftMon.Bounds.Y, 0, 0, $bmpLeft.Size)
        $bmpLeft.Save($leftPath, [System.Drawing.Imaging.ImageFormat]::Png)
        $gLeft.Dispose()

        # 2. Capture Right Screen
        $bmpRight = New-Object System.Drawing.Bitmap($rightMon.Bounds.Width, $rightMon.Bounds.Height)
        $gRight = [System.Drawing.Graphics]::FromImage($bmpRight)
        $gRight.CopyFromScreen($rightMon.Bounds.X, $rightMon.Bounds.Y, 0, 0, $bmpRight.Size)
        $bmpRight.Save($rightPath, [System.Drawing.Imaging.ImageFormat]::Png)
        $gRight.Dispose()

        # 3. Stitch side-by-side
        $bannerHeight = 40
        $totalWidth = $bmpLeft.Width + $bmpRight.Width
        $maxHeight = [Math]::Max($bmpLeft.Height, $bmpRight.Height)
        $totalHeight = $maxHeight + $bannerHeight

        $stitchedBmp = New-Object System.Drawing.Bitmap($totalWidth, $totalHeight)
        $gStitched = [System.Drawing.Graphics]::FromImage($stitchedBmp)

        $bgBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(20, 24, 32))
        $gStitched.FillRectangle($bgBrush, 0, 0, $totalWidth, $totalHeight)

        $gStitched.DrawImage($bmpLeft, 0, $bannerHeight, $bmpLeft.Width, $bmpLeft.Height)
        $gStitched.DrawImage($bmpRight, $bmpLeft.Width, $bannerHeight, $bmpRight.Width, $bmpRight.Height)

        $font = New-Object System.Drawing.Font("Arial", 14, [System.Drawing.FontStyle]::Bold)
        $textBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
        $gStitched.DrawString($msg.header_left, $font, $textBrush, 20, 10)
        $gStitched.DrawString($msg.header_right, $font, $textBrush, ($bmpLeft.Width + 20), 10)

        $stitchedBmp.Save($stitchedPath, [System.Drawing.Imaging.ImageFormat]::Png)

        $font.Dispose()
        $textBrush.Dispose()
        $bgBrush.Dispose()
        $gStitched.Dispose()
        $bmpLeft.Dispose()
        $bmpRight.Dispose()
        $stitchedBmp.Dispose()
    } else {
        $mon = $allScreens[0]
        Write-Host "[*] Detected 1 monitor: $($mon.Bounds.Width)x$($mon.Bounds.Height)" -ForegroundColor Yellow
        $bmp = New-Object System.Drawing.Bitmap($mon.Bounds.Width, $mon.Bounds.Height)
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.CopyFromScreen($mon.Bounds.X, $mon.Bounds.Y, 0, 0, $bmp.Size)
        $bmp.Save($stitchedPath, [System.Drawing.Imaging.ImageFormat]::Png)
        $g.Dispose()
        $bmp.Dispose()
    }

    return $stitchedPath
}

# 4. Cleanup captures folder
function Cleanup-Captures() {
    try {
        [System.GC]::Collect()
        [System.GC]::WaitForPendingFinalizers()
        Get-ChildItem -Path $capturesDir -Include "*.png", "*.jpg", "*.jpeg" -File -Recurse | Remove-Item -Force -ErrorAction SilentlyContinue
        Write-Host "[*] Cleaned up temporary files in data/captures" -ForegroundColor Gray
    } catch {
        Write-Warning "Could not delete temporary captures: $_"
    }
}

# 5. Core Trigger Function
$script:isAnalyzing = $false

function Trigger-DailyPlanAnalysis() {
    if ($script:isAnalyzing) {
        Send-TelegramText $msg.busy
        return
    }

    $script:isAnalyzing = $true
    try {
        Write-Host ""
        Write-Host "[>>>] Triggering Daily Plan analysis..." -ForegroundColor Yellow
        Send-TelegramText $msg.start

        # 1. Capture dual screens
        $stitchedImage = Capture-DualScreens
        Write-Host "[+] Captured and stitched screens: $stitchedImage" -ForegroundColor Green

        # 2. Prepare prompt for agy
        $todayStr = (Get-Date).ToString("dd/MM/yyyy")
        $prompt = [string]::Format($promptTemplate, $symbol, $stitchedImage, $todayStr)

        Write-Host "[*] Calling agy ($modelName) for analysis..." -ForegroundColor Cyan
        $agyOutput = & agy -p $prompt --model $modelName --dangerously-skip-permissions --disable-slash-commands --output-format json --json-schema $schemaFilePath

        if (-not $agyOutput) {
            throw "CLI agy did not return output!"
        }

        # Parse JSON output from agy
        $rawJsonText = if ($agyOutput -is [array]) { $agyOutput -join [System.Environment]::NewLine } else { [string]$agyOutput }
        $parsedOutput = $rawJsonText | ConvertFrom-Json
        $planData = $null

        if ($parsedOutput.structured_output) {
            $planData = $parsedOutput.structured_output
        } elseif ($parsedOutput.response) {
            if ($parsedOutput.response -is [string]) {
                $rawStr = $parsedOutput.response.Trim()
                $startIdx = $rawStr.IndexOf("{")
                $endIdx = $rawStr.LastIndexOf("}")
                if ($startIdx -ge 0 -and $endIdx -gt $startIdx) {
                    $rawStr = $rawStr.Substring($startIdx, $endIdx - $startIdx + 1)
                }
                $planData = $rawStr | ConvertFrom-Json
            } else {
                $planData = $parsedOutput.response
            }
        }

        if (-not $planData) {
            throw "Unable to extract DailyPlan structure from agy output!"
        }

        # Format plan text according to content.md strictly
        $captionLines = @(
            ($msg.lbl_date + $planData.date),
            ($msg.lbl_overview + $planData.overview),
            ""
        )

        foreach ($p in $planData.plans) {
            $captionLines += ("#Plan " + $p.plan_number + ": " + $p.bias)
            $captionLines += ($msg.lbl_wait + $p.wait_zone_low + " - " + $p.wait_zone_high)
            $captionLines += ($msg.lbl_entry + $p.entry_condition)
            $captionLines += ""
        }

        $finalCaption = ($captionLines -join [System.Environment]::NewLine).Trim()
        Write-Host ""
        Write-Host $finalCaption -ForegroundColor Green
        Write-Host ""

        # Inline button for next update (explicit 2D array for Telegram)
        $planButtonMarkup = '{"inline_keyboard":[[{"text":"' + $msg.btn_plan + '","callback_data":"trigger_plan"}]]}'

        # 3. Send photo and caption to Telegram
        Send-TelegramPhotoWithPlan -imagePath $stitchedImage -caption $finalCaption -replyMarkupJson $planButtonMarkup
        Write-Host "[+] Successfully sent plan to Telegram!" -ForegroundColor Green

    } catch {
        Write-Host "[!] Error during analysis: $_" -ForegroundColor Red
        Send-TelegramText ($msg.err + $_)
    } finally {
        Cleanup-Captures
        $script:isAnalyzing = $false
    }
}

# 6. Startup Message & Telegram Listener
$initMarkup = '{"inline_keyboard":[[{"text":"' + $msg.btn_plan + '","callback_data":"trigger_plan"}]]}'

Send-TelegramText $msg.startup $initMarkup

Write-Host ""
Write-Host "[+] Service is active and listening for Telegram events..." -ForegroundColor Green
Write-Host "    Press Ctrl+C to stop." -ForegroundColor Gray
Write-Host ""

$lastUpdateId = 0

while ($true) {
    try {
        $updateUrl = "$telegramEndpoint/getUpdates?offset=$($lastUpdateId + 1)&timeout=3"
        $response = Invoke-RestMethod -Uri $updateUrl -Method Get -TimeoutSec 10 -ErrorAction Stop

        if ($response.ok -and $response.result) {
            foreach ($upd in $response.result) {
                $lastUpdateId = [int64]$upd.update_id

                # Handle button click
                if ($upd.callback_query) {
                    $cb = $upd.callback_query
                    $cbId = $cb.id
                    $data = $cb.data

                    if ($data -eq "trigger_plan") {
                        Write-Host "[Telegram] Button pressed: Cap nhat lai Plan" -ForegroundColor Yellow
                        Answer-CallbackQuery -callbackQueryId $cbId -toastText $msg.toast
                        Trigger-DailyPlanAnalysis
                    }
                }

                # Handle text command
                if ($upd.message -and $upd.message.text) {
                    $msgText = $upd.message.text.Trim().ToLower()

                    if ($msgText -in @("/start", "/help")) {
                        Send-TelegramText $msg.welcome $initMarkup
                    } elseif ($msgText -eq "/plan") {
                        Write-Host "[Telegram] Received command: /plan" -ForegroundColor Yellow
                        Trigger-DailyPlanAnalysis
                    }
                }
            }
        }
    } catch {
        Start-Sleep -Seconds 2
    }

    Start-Sleep -Milliseconds 500
}
