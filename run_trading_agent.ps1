# Order Flow Trading Agent - Windows Service
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# Load required UI assemblies
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# Enable Per-Monitor DPI Awareness so secondary monitor coordinates and resolutions are physical and not blank
try {
    Add-Type -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();' -Name "DpiAwareHelper" -Namespace "NativeDpi" -ErrorAction SilentlyContinue
    [NativeDpi.DpiAwareHelper]::SetProcessDPIAware() | Out-Null
    Write-Host "[*] DPI awareness enabled for multi-monitor capture." -ForegroundColor Gray
} catch {}

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

# Reusable 2-row action keyboard markup: [🔄 Cập nhật lại Plan] and [📸 Chụp màn hình]
$actionButtonsMarkup = '{"inline_keyboard":[[{"text":"' + $msg.btn_plan + '","callback_data":"trigger_plan"}],[{"text":"' + $msg.btn_capture + '","callback_data":"trigger_capture"}]]}'

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
        $body.Remove("parse_mode")
        try {
            Invoke-RestMethod -Uri $url -Method Post -Body $body -ContentType "application/x-www-form-urlencoded; charset=utf-8" | Out-Null
        } catch {
            Write-Warning "Telegram send text error: $_"
        }
    }
}

function Send-TelegramPhoto([string]$imagePath, [string]$caption = "", [string]$replyMarkupJson = "") {
    $url = "$telegramEndpoint/sendPhoto"
    Write-Host "[*] Sending image to Telegram: $imagePath" -ForegroundColor Cyan

    $curlExe = if (Test-Path "$env:SystemRoot\System32\curl.exe") { "$env:SystemRoot\System32\curl.exe" } else { "curl" }

    # Ensure forward slashes for Windows curl compatibility
    $curlImagePath = $imagePath.Replace("\", "/")

    $tempCaptionFile = $null
    $tempMarkupFile = $null

    $argsList = @(
        "-s",
        "-X", "POST", $url,
        "-F", "chat_id=$chatId",
        "-F", "photo=@$curlImagePath"
    )

    if ($caption) {
        $tempCaptionFile = Join-Path $capturesDir ("cap_" + [System.IO.Path]::GetRandomFileName() + ".txt")
        [System.IO.File]::WriteAllText($tempCaptionFile, $caption, [System.Text.Encoding]::UTF8)
        $curlCaptionPath = $tempCaptionFile.Replace("\", "/")
        $argsList += "-F"
        $argsList += "caption=<$curlCaptionPath"
        $argsList += "-F"
        $argsList += "parse_mode=Markdown"
    }

    if ($replyMarkupJson) {
        $tempMarkupFile = Join-Path $capturesDir ("btn_" + [System.IO.Path]::GetRandomFileName() + ".json")
        [System.IO.File]::WriteAllText($tempMarkupFile, $replyMarkupJson, [System.Text.Encoding]::UTF8)
        $curlMarkupPath = $tempMarkupFile.Replace("\", "/")
        $argsList += "-F"
        $argsList += "reply_markup=<$curlMarkupPath"
    }

    $rawResp = & $curlExe @argsList
    $respText = if ($rawResp -is [array]) { $rawResp -join "" } else { [string]$rawResp }

    # Fallback without Markdown formatting if Telegram rejected Markdown parsing
    if ($caption -and (-not $respText.Contains('"ok":true'))) {
        Write-Warning "Telegram send with Markdown failed ($respText). Retrying without parse_mode..."
        $argsListFallback = @(
            "-s",
            "-X", "POST", $url,
            "-F", "chat_id=$chatId",
            "-F", "photo=@$curlImagePath",
            "-F", "caption=<$curlCaptionPath"
        )
        if ($tempMarkupFile) {
            $argsListFallback += "-F"
            $argsListFallback += "reply_markup=<$curlMarkupPath"
        }
        $rawResp = & $curlExe @argsListFallback
        $respText = if ($rawResp -is [array]) { $rawResp -join "" } else { [string]$rawResp }
    }

    # Clean up temp files
    if ($tempCaptionFile -and (Test-Path $tempCaptionFile)) {
        Remove-Item -Path $tempCaptionFile -Force -ErrorAction SilentlyContinue
    }
    if ($tempMarkupFile -and (Test-Path $tempMarkupFile)) {
        Remove-Item -Path $tempMarkupFile -Force -ErrorAction SilentlyContinue
    }

    if ($respText.Contains('"ok":true')) {
        Write-Host "[+] Successfully sent photo to Telegram!" -ForegroundColor Green
        return $true
    } else {
        Write-Host "[!] Telegram sendPhoto error: $respText" -ForegroundColor Red
        if ($caption) {
            Send-TelegramText $caption $replyMarkupJson
        }
        return $false
    }
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

        return @{
            Left = $leftPath
            Right = $rightPath
            Stitched = $stitchedPath
            IsDual = $true
        }
    } else {
        $mon = $allScreens[0]
        Write-Host "[*] Detected 1 monitor: $($mon.Bounds.Width)x$($mon.Bounds.Height)" -ForegroundColor Yellow
        $bmp = New-Object System.Drawing.Bitmap($mon.Bounds.Width, $mon.Bounds.Height)
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.CopyFromScreen($mon.Bounds.X, $mon.Bounds.Y, 0, 0, $bmp.Size)
        $bmp.Save($stitchedPath, [System.Drawing.Imaging.ImageFormat]::Png)
        $g.Dispose()
        $bmp.Dispose()

        return @{
            Left = $stitchedPath
            Right = $stitchedPath
            Stitched = $stitchedPath
            IsDual = $false
        }
    }
}

# 4. Cleanup captures folder
function Cleanup-Captures() {
    try {
        [System.GC]::Collect()
        [System.GC]::WaitForPendingFinalizers()
        Get-ChildItem -Path $capturesDir -Include "*.png", "*.jpg", "*.jpeg", "*.txt" -File -Recurse | Remove-Item -Force -ErrorAction SilentlyContinue
        Write-Host "[*] Cleaned up temporary files in data/captures" -ForegroundColor Gray
    } catch {
        Write-Warning "Could not delete temporary captures: $_"
    }
}

# 5. Core Trigger Function: Daily Plan Analysis
$script:isProcessing = $false

function Trigger-DailyPlanAnalysis() {
    if ($script:isProcessing) {
        Send-TelegramText $msg.busy
        return
    }

    $script:isProcessing = $true
    try {
        Write-Host ""
        Write-Host "[>>>] Triggering Daily Plan analysis..." -ForegroundColor Yellow
        Send-TelegramText $msg.start

        # 1. Capture dual screens
        $caps = Capture-DualScreens
        Write-Host "[+] Captured dual screens: Left=$($caps.Left), Right=$($caps.Right)" -ForegroundColor Green

        # 2. Prepare prompt for agy
        $todayStr = (Get-Date).ToString("dd/MM/yyyy")
        $prompt = [string]::Format($promptTemplate, $symbol, $caps.Stitched, $todayStr)

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

        # 3. Send 2 separate photos to Telegram
        if ($caps.IsDual) {
            # Photo 1: Left Monitor (VP & Footprint)
            Send-TelegramPhoto -imagePath $caps.Left -caption $msg.caption_left

            Start-Sleep -Milliseconds 800

            # Photo 2: Right Monitor (Bookmap) with the Daily Plan caption and action buttons
            Send-TelegramPhoto -imagePath $caps.Right -caption $finalCaption -replyMarkupJson $actionButtonsMarkup
        } else {
            Send-TelegramPhoto -imagePath $caps.Stitched -caption $finalCaption -replyMarkupJson $actionButtonsMarkup
        }

    } catch {
        Write-Host "[!] Error during analysis: $_" -ForegroundColor Red
        Send-TelegramText ($msg.err + $_)
    } finally {
        Cleanup-Captures
        $script:isProcessing = $false
    }
}

# 6. Capture-Only Trigger Function (Instant capture without AI delay)
function Trigger-ScreenCaptureOnly() {
    if ($script:isProcessing) {
        Send-TelegramText $msg.busy
        return
    }

    $script:isProcessing = $true
    try {
        Write-Host ""
        Write-Host "[>>>] Triggering Instant Screen Capture..." -ForegroundColor Yellow
        Send-TelegramText $msg.capture_start

        $caps = Capture-DualScreens
        $nowStr = (Get-Date).ToString("HH:mm:ss dd/MM/yyyy")

        if ($caps.IsDual) {
            # Photo 1: Left Monitor
            $captionLeft = $msg.caption_left + [System.Environment]::NewLine + "⏰ " + $nowStr
            Send-TelegramPhoto -imagePath $caps.Left -caption $captionLeft

            Start-Sleep -Milliseconds 800

            # Photo 2: Right Monitor with action buttons
            $captionRight = $msg.caption_right + [System.Environment]::NewLine + "⏰ " + $nowStr
            Send-TelegramPhoto -imagePath $caps.Right -caption $captionRight -replyMarkupJson $actionButtonsMarkup
        } else {
            $singleCaption = "🖥️ *ẢNH CHỤP MÀN HÌNH*" + [System.Environment]::NewLine + "⏰ " + $nowStr
            Send-TelegramPhoto -imagePath $caps.Stitched -caption $singleCaption -replyMarkupJson $actionButtonsMarkup
        }

        Write-Host "[+] Successfully delivered dual screen captures to Telegram!" -ForegroundColor Green

    } catch {
        Write-Host "[!] Error during capture: $_" -ForegroundColor Red
        Send-TelegramText ($msg.err + $_)
    } finally {
        Cleanup-Captures
        $script:isProcessing = $false
    }
}

# 7. Startup Message & Telegram Listener Loop
Send-TelegramText $msg.startup $actionButtonsMarkup

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

                # Handle button click (callback queries)
                if ($upd.callback_query) {
                    $cb = $upd.callback_query
                    $cbId = $cb.id
                    $data = $cb.data

                    if ($data -eq "trigger_plan") {
                        Write-Host "[Telegram] Button pressed: Cap nhat lai Plan" -ForegroundColor Yellow
                        Answer-CallbackQuery -callbackQueryId $cbId -toastText $msg.toast
                        Trigger-DailyPlanAnalysis
                    } elseif ($data -eq "trigger_capture") {
                        Write-Host "[Telegram] Button pressed: Chup man hinh" -ForegroundColor Yellow
                        Answer-CallbackQuery -callbackQueryId $cbId -toastText $msg.toast_capture
                        Trigger-ScreenCaptureOnly
                    }
                }

                # Handle text command
                if ($upd.message -and $upd.message.text) {
                    $msgText = $upd.message.text.Trim().ToLower()

                    if ($msgText -in @("/start", "/help")) {
                        Send-TelegramText $msg.welcome $actionButtonsMarkup
                    } elseif ($msgText -eq "/plan") {
                        Write-Host "[Telegram] Received command: /plan" -ForegroundColor Yellow
                        Trigger-DailyPlanAnalysis
                    } elseif ($msgText -eq "/capture") {
                        Write-Host "[Telegram] Received command: /capture" -ForegroundColor Yellow
                        Trigger-ScreenCaptureOnly
                    }
                }
            }
        }
    } catch {
        Start-Sleep -Seconds 2
    }

    Start-Sleep -Milliseconds 500
}
