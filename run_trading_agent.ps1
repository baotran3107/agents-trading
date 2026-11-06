<#
.SYNOPSIS
    Order Flow Trading Agent - Windows Native PowerShell Daemon
    Zero Python dependencies. Native Windows dual-screen capture, agy CLI & Telegram integration.
    Pure ASCII source code with UTF-8 runtime decoding to ensure 100% compatibility across all Windows versions.
#>

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# UTF-8 string decoder for internationalized strings
function u([string]$b64) {
    [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($b64))
}

# Pre-encoded UTF-8 strings
$TXT_PROMPT_TPL   = u "QuG6oW4gbMOgIG3hu5l0IGNodXnDqm4gZ2lhIGdpYW8gZOG7i2NoIMSR4buLbmggbMaw4bujbmcgdGhlbyBwaMawxqFuZyBwaMOhcCBPcmRlciBGbG93IHbDoCBBdWN0aW9uIE1hcmtldCBUaGVvcnkgcGjDom4gdMOtY2ggdsOgbmcgKHswfSkuCgpRdWFuIHPDoXQga+G7uSBow6xuaCDhuqNuaCBiaeG7g3UgxJHhu5MgMiBtw6BuIGjDrG5oIHThuqFpOiB7MX0KLSBNw4BOIEjDjE5IIFRSw4FJOiBD4bqldSB0csO6YyBWb2x1bWUgUHJvZmlsZSAoVkFILCBWQUwsIFBPQykgdsOgIGJp4buDdSDEkeG7kyBGb290cHJpbnQgKERlbHRhLCBj4bulbSBo4bqlcCB0aOG7pSwgbeG6pXQgY8OibiBi4bqxbmcgYmlkL2FzaykuCi0gTcOATiBIw4xOSCBQSOG6okk6IEJvb2ttYXAgKELhuqNuIMSR4buTIG5oaeG7h3QgdMaw4budbmcgdGhhbmgga2hv4bqjbiByZXN0aW5nIGxpbWl0IG9yZGVycywgQ1ZELCBib25nIGLDs25nIGto4bubcCBs4buHbmggY2jhu6cgxJHhu5luZykuCgpOR1Xhu5JOIEThu64gTEnhu4ZVOiBDaOG7iSDEkeG7jWMgdsOgIHBow6JuIHTDrWNoIHRy4buxYyB0aeG6v3AgdOG7qyDhuqNuaCBjaOG7pXAgMiBtw6BuIGjDrG5oIHRyw6puLiBUb8OgbiBi4buZIHRoYW5nIGdpw6EsIGPhuqV1IHRyw7pjIFZvbHVtZSBQcm9maWxlIHbDoCB0aGFuaCBraG/huqNuIEJvb2ttYXAgxJHhu4F1IHF1YW4gc8OhdCB0cuG7sWMgdGnhur9wIHThu6sgYmnhu4N1IMSR4buTIChraMO0bmcgZMO5bmcgYuG6pXQga+G7syBk4buvIGxp4buHdSBuw6BvIHThu6sgTVQ1KS4KClFVWSBU4bquQyBC4bquVCBCVeG7mEMgVuG7gCBOR8OUTiBOR+G7riBWw4AgTuG7mEkgRFVORzoKMS4gVE/DgE4gQuG7mCBO4buYSSBEVU5HIE3DlCBU4bqiIFBI4bqiSSDEkMav4buiQyBWSeG6vlQgSE/DgE4gVE/DgE4gQuG6sE5HIFRJ4bq+TkcgVknhu4ZUIChTVFJJQ1RMWSBWSUVUTkFNRVNFKS4KMi4gJ2RhdGUnOiDEkOG7i25oIGThuqFuZyBuZ8OgeSBi4bqvdCBideG7mWMgbMOgIGRkL21tL3l5eXkgKHbDrSBk4bulOiAnezJ9JykuCjMuICdvdmVydmlldyc6IFTDs20gdOG6r3QgYuG7kWkgY+G6o25oIHRo4buLIHRyxrDhu51uZyB0cm9uZyBuZ8OgeSB0aOG6rXQgY8O0IMSR4buNbmcsIFThu5BJIMSQQSAxMDAgS8OdIFThu7AgYuG6sW5nIHRp4bq/bmcgVmnhu4d0Lgo0LiAncGxhbnMnOiBU4bqhbyB04burIDIgxJHhur9uIDMga+G6vyBob+G6oWNoIGdpYW8gZOG7i2NoICgjUGxhbiAxLCAjUGxhbiAyLCAjUGxhbiAzKSwgbeG7l2kgcGxhbiBn4buTbToKICAgLSAncGxhbl9udW1iZXInOiAxLCAyIGhv4bq3YyAzCiAgIC0gJ2JpYXMnOiAnQlVZJyBob+G6t2MgJ1NFTEwnCiAgIC0gJ3dhaXRfem9uZV9sb3cnOiBt4bupYyBnacOhIHRo4bqlcCBj4bunYSB2w7luZyBjaOG7nSBwaOG6o24g4bupbmcKICAgLSAnd2FpdF96b25lX2hpZ2gnOiBt4bupYyBnacOhIGNhbyBj4bunYSB2w7luZyBjaOG7nSBwaOG6o24g4bupbmcKICAgLSAnZW50cnlfY29uZGl0aW9uJzogxJFp4buBdSBraeG7h24ga8OtY2ggaG/huqF0IHbDoG8gbOG7h25oIG5n4bqvbiBn4buNbiBzw7pjIHTDrWNoIHRoZW8gT3JkZXIgRmxvdyAoRm9vdHByaW50LCBCb29rbWFwKSBi4bqxbmcgdGnhur9uZyBWaeG7h3QuCjUuIFRy4bqjIHbhu4EgxJHDum5nIMSR4buLbmggZOG6oW5nIEpTT04gdGhlbyBzY2hlbWEgxJHDoyBjdW5nIGPhuqVwLg=="
$TXT_HEADER_LEFT  = u "TcOATiBIw4xOSCBUUsOBSTogVk9MVU1FIFBST0ZJTEUgVsOAIEZPT1RQUklOVA=="
$TXT_HEADER_RIGHT = u "TcOATiBIw4xOSCBQSOG6okk6IEJPT0tNQVA="
$TXT_STARTUP      = u "8J+agCAqVHJhZGluZyBTaWduYWwgQWdlbnQgKFdpbmRvd3MgTmF0aXZlKSDEkcOjIGto4bufaSDEkeG7mW5nIHbDoCDEkWFuZyBjaOG6oXkgdGjGsOG7nW5nIHRy4buxYy4qCgrwn5OMIELhuqVtIG7DunQgKlvwn5SEIEPhuq1wIG5o4bqtdCBs4bqhaSBQbGFuXSogYsOqbiBkxrDhu5tpIChob+G6t2MgZ+G7rWkgL3BsYW4pIGLhuqV0IGvhu7MgbMO6YyBuw6BvIMSR4buDIGNo4bulcCAyIG3DoG4gaMOsbmggdsOgIHBow6JuIHTDrWNoIGvhur8gaG/huqFjaC4="
$TXT_WELCOME      = u "8J+RiyBYaW4gY2jDoG8hIEjhu4cgdGjhu5FuZyBCb3QgcGjDom4gdMOtY2ggT3JkZXIgRmxvdyDEkWFuZyBob+G6oXQgxJHhu5luZyB0csOqbiBXaW5kb3dzLgoKQuG6pW0gbsO6dCAqW/CflIQgQ+G6rXAgbmjhuq10IGzhuqFpIFBsYW5dKiBiw6puIGTGsOG7m2kgxJHhu4Mga8OtY2ggaG/huqF0IHBow6JuIHTDrWNoLg=="
$TXT_BUSY         = u "4o+zIMSQYW5nIGPDsyBt4buZdCB0aeG6v24gdHLDrG5oIHBow6JuIHTDrWNoIMSRYW5nIGNo4bqheSwgdnVpIGzDsm5nIGNo4budIHRyb25nIGdpw6J5IGzDoXQuLi4="
$TXT_START        = u "8J+UhCBC4bqvdCDEkeG6p3UgY2jhu6VwIDIgbcOgbiBow6xuaCAoVlAvRm9vdHByaW50IHbDoCBCb29rbWFwKSB2w6AgcGjDom4gdMOtY2gga+G6vyBob+G6oWNoLi4u"
$TXT_TOAST        = u "xJBhbmcgY2jhu6VwIDIgbcOgbiBow6xuaCB2w6AgcGjDom4gdMOtY2guLi4="
$TXT_ERR          = u "4pqg77iPIEPDsyBs4buXaSB44bqjeSByYSB0cm9uZyBxdcOhIHRyw6xuaCBwaMOibiB0w61jaDog"
$TXT_BTN_PLAN     = u "8J+UhCBD4bqtcCBuaOG6rXQgbOG6oWkgUGxhbg=="
$TXT_DATE_LBL     = u "8J+ThSBL4bq/IGhv4bqhY2ggbmfDoHkg"
$TXT_OVERVIEW_LBL = u "8J+TnSA="
$TXT_WAIT_LBL     = u "4oCiIFbDuW5nIGNo4budOiA="
$TXT_ENTRY_LBL    = u "4oCiIMSQaeG7gXUga2nhu4duIHbDoG86IA=="

# Load .NET UI assemblies for multi-monitor capture & GDI+ graphics
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# 1. Load configurations from .env
$scriptDir = $PSScriptRoot
if (-not $scriptDir) { $scriptDir = (Get-Location).Path }
$envPath = Join-Path $scriptDir ".env"
$capturesDir = Join-Path $scriptDir "data\captures"

if (-not (Test-Path $capturesDir)) {
    New-Item -ItemType Directory -Path $capturesDir -Force | Out-Null
}

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
    Write-Host "[LOI] Khong tim thay TELEGRAM_BOT_TOKEN hoac TELEGRAM_CHAT_ID trong file .env!" -ForegroundColor Red
    pause
    exit 1
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  ORDER FLOW TRADING AGENT - NATIVE WINDOWS DAEMON" -ForegroundColor Green
Write-Host "  Chat ID: $chatId | Model: $modelName" -ForegroundColor Cyan
Write-Host "  Khong can Python | Tu dong chup 2 man hinh va goi agy" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 2. Telegram Helper Functions
function Send-TelegramText([string]$text, [string]$replyMarkupJson = "") {
    $url = "https://api.telegram.org/bot$botToken/sendMessage"
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
        Write-Warning "Loi gui text Telegram: $_"
    }
}

function Send-TelegramPhotoWithPlan([string]$imagePath, [string]$caption, [string]$replyMarkupJson = "") {
    $url = "https://api.telegram.org/bot$botToken/sendPhoto"
    Write-Host "[*] Dang gui anh va ke hoach sang Telegram..." -ForegroundColor Cyan

    if (Test-Path "$env:SystemRoot\System32\curl.exe") {
        $curlExe = "$env:SystemRoot\System32\curl.exe"
    } else {
        $curlExe = "curl"
    }

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
    $url = "https://api.telegram.org/bot$botToken/answerCallbackQuery"
    try {
        Invoke-RestMethod -Uri $url -Method Post -Body @{
            callback_query_id = $callbackQueryId
            text = $toastText
        } | Out-Null
    } catch {
        Write-Warning "Loi answerCallbackQuery: $_"
    }
}

# 3. Dual Monitor Screen Capture & Stitching Function
function Capture-DualScreens() {
    $timestamp = (Get-Date).ToString("yyyyMMdd_HHmmss")
    $leftPath = Join-Path $capturesDir "chart_left_$timestamp.png"
    $rightPath = Join-Path $capturesDir "chart_right_$timestamp.png"
    $stitchedPath = Join-Path $capturesDir "chart_stitched_$timestamp.png"

    $allScreens = [System.Windows.Forms.Screen]::AllScreens | Sort-Object { $_.Bounds.X }

    if ($allScreens.Count -ge 2) {
        $leftMon = $allScreens[0]
        $rightMon = $allScreens[1]
        Write-Host "[*] Phat hien 2 man hinh:" -ForegroundColor Green
        Write-Host "    - Trai (VP & Footprint): $($leftMon.Bounds.Width)x$($leftMon.Bounds.Height) tai ($($leftMon.Bounds.X),$($leftMon.Bounds.Y))"
        Write-Host "    - Phai (Bookmap):        $($rightMon.Bounds.Width)x$($rightMon.Bounds.Height) tai ($($rightMon.Bounds.X),$($rightMon.Bounds.Y))"

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

        # 3. Stitch side-by-side with header banner
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
        $gStitched.DrawString($TXT_HEADER_LEFT, $font, $textBrush, 20, 10)
        $gStitched.DrawString($TXT_HEADER_RIGHT, $font, $textBrush, ($bmpLeft.Width + 20), 10)

        $stitchedBmp.Save($stitchedPath, [System.Drawing.Imaging.ImageFormat]::Png)

        # Release resources
        $font.Dispose()
        $textBrush.Dispose()
        $bgBrush.Dispose()
        $gStitched.Dispose()
        $bmpLeft.Dispose()
        $bmpRight.Dispose()
        $stitchedBmp.Dispose()
    } else {
        $mon = $allScreens[0]
        Write-Host "[*] Phat hien 1 man hinh: $($mon.Bounds.Width)x$($mon.Bounds.Height)" -ForegroundColor Yellow
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
        Write-Host "[*] Da don dep sach se thu muc data/captures" -ForegroundColor Gray
    } catch {
        Write-Warning "Khong the xoa file anh tam: $_"
    }
}

# 5. Core Trigger Function: Capture -> agy Call -> Telegram Send -> Cleanup
$script:isAnalyzing = $false

function Trigger-DailyPlanAnalysis() {
    if ($script:isAnalyzing) {
        Send-TelegramText $TXT_BUSY
        return
    }

    $script:isAnalyzing = $true
    try {
        Write-Host "`n[>>>] KHOI TAO PHAN TICH THEO YEU CAU..." -ForegroundColor Yellow
        Send-TelegramText $TXT_START

        # Step 1: Capture dual screens
        $stitchedImage = Capture-DualScreens
        Write-Host "[+] Da chup va ghep anh: $stitchedImage" -ForegroundColor Green

        # Step 2: Prepare JSON schema & prompt for agy
        $schemaJson = '{"type":"object","properties":{"date":{"type":"string"},"overview":{"type":"string"},"plans":{"type":"array","items":{"type":"object","properties":{"plan_number":{"type":"integer"},"bias":{"type":"string"},"wait_zone_low":{"type":"number"},"wait_zone_high":{"type":"number"},"entry_condition":{"type":"string"}},"required":["plan_number","bias","wait_zone_low","wait_zone_high","entry_condition"]}}},"required":["date","overview","plans"]}'

        $todayStr = (Get-Date).ToString("dd/MM/yyyy")
        $prompt = [string]::Format($TXT_PROMPT_TPL, $symbol, $stitchedImage, $todayStr)

        Write-Host "[*] Dang goi agy ($modelName) phan tich..." -ForegroundColor Cyan
        $agyOutput = & agy -p $prompt --model $modelName --disable-slash-commands --output-format json --json-schema $schemaJson

        if (-not $agyOutput) {
            throw "CLI agy khong tra ve ket qua!"
        }

        # Parse JSON output from agy (support array of lines from PowerShell 5.1 CLI output)
        $rawJsonText = if ($agyOutput -is [array]) { $agyOutput -join "`n" } else { [string]$agyOutput }
        $parsedOutput = $rawJsonText | ConvertFrom-Json
        $planData = $null

        if ($parsedOutput.structured_output) {
            $planData = $parsedOutput.structured_output
        } elseif ($parsedOutput.response) {
            if ($parsedOutput.response -is [string]) {
                $rawStr = $parsedOutput.response.Trim()
                if ($rawStr.StartsWith("```")) {
                    $rawStr = ($rawStr -replace "(?s)^```(?:json)?\s*", "") -replace "(?s)\s*```$", ""
                }
                $planData = $rawStr | ConvertFrom-Json
            } else {
                $planData = $parsedOutput.response
            }
        }

        if (-not $planData) {
            throw "Khong the trich xuat cau truc DailyPlan tu output cua agy!"
        }

        # Format plan text according to content.md strictly
        $captionLines = @(
            ($TXT_DATE_LBL + $planData.date),
            ($TXT_OVERVIEW_LBL + $planData.overview),
            ""
        )

        foreach ($p in $planData.plans) {
            $captionLines += ("#Plan " + $p.plan_number + ": " + $p.bias)
            $captionLines += ($TXT_WAIT_LBL + $p.wait_zone_low + " - " + $p.wait_zone_high)
            $captionLines += ($TXT_ENTRY_LBL + $p.entry_condition)
            $captionLines += ""
        }

        $finalCaption = ($captionLines -join "`n").Trim()
        Write-Host "`n$finalCaption`n" -ForegroundColor Green

        # Inline button for next update
        $markupObj = @{
            inline_keyboard = @(
                @(
                    @{
                        text = $TXT_BTN_PLAN
                        callback_data = "trigger_plan"
                    }
                )
            )
        }
        $planButtonMarkup = ($markupObj | ConvertTo-Json -Compress)

        # Step 3: Send to Telegram
        Send-TelegramPhotoWithPlan -imagePath $stitchedImage -caption $finalCaption -replyMarkupJson $planButtonMarkup
        Write-Host "[+] Da gui ket qua thanh cong sang Telegram!" -ForegroundColor Green

    } catch {
        Write-Host "[!] Loi trong qua trinh phan tich: $_" -ForegroundColor Red
        Send-TelegramText ($TXT_ERR + $_)
    } finally {
        # Step 4: Always clean up captures immediately
        Cleanup-Captures
        $script:isAnalyzing = $false
    }
}

# 6. Startup Message & Telegram Event Listener Loop
$initMarkupObj = @{
    inline_keyboard = @(
        @(
            @{
                text = $TXT_BTN_PLAN
                callback_data = "trigger_plan"
            }
        )
    )
}
$initMarkup = ($initMarkupObj | ConvertTo-Json -Compress)

Send-TelegramText $TXT_STARTUP $initMarkup

Write-Host "`n[+] Server da san sang va dang lang nghe su kien tu Telegram..." -ForegroundColor Green
Write-Host "    Nhan Ctrl+C de dung server.`n" -ForegroundColor Gray

$lastUpdateId = 0

while ($true) {
    try {
        $updateUrl = "https://api.telegram.org/bot$botToken/getUpdates?offset=$($lastUpdateId + 1)&timeout=3"
        $response = Invoke-RestMethod -Uri $updateUrl -Method Get -TimeoutSec 10 -ErrorAction Stop

        if ($response.ok -and $response.result) {
            foreach ($upd in $response.result) {
                $lastUpdateId = [int64]$upd.update_id

                # Handle Button Click (Callback Query)
                if ($upd.callback_query) {
                    $cb = $upd.callback_query
                    $cbId = $cb.id
                    $data = $cb.data

                    if ($data -eq "trigger_plan") {
                        Write-Host "[Telegram] Nguoi dung bam nut: Cap nhat lai Plan" -ForegroundColor Yellow
                        Answer-CallbackQuery -callbackQueryId $cbId -toastText $TXT_TOAST
                        Trigger-DailyPlanAnalysis
                    }
                }

                # Handle Text Messages
                if ($upd.message -and $upd.message.text) {
                    $msgText = $upd.message.text.Trim().ToLower()

                    if ($msgText -in @("/start", "/help")) {
                        Send-TelegramText $TXT_WELCOME $initMarkup
                    } elseif ($msgText -eq "/plan") {
                        Write-Host "[Telegram] Nhan lenh: /plan" -ForegroundColor Yellow
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
