<#
.SYNOPSIS
    Order Flow Trading Agent - Windows Native PowerShell Daemon
    Zero Python dependencies. Native Windows dual-screen capture, agy CLI & Telegram integration.
#>

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

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

    # Use curl.exe (built-in on Windows 10/11) for reliable multipart/form-data upload
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

    # Sort screens horizontally (left screen has smallest X coordinate)
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
        $gStitched.DrawString("MÀN HÌNH TRÁI: VOLUME PROFILE & FOOTPRINT", $font, $textBrush, 20, 10)
        $gStitched.DrawString("MÀN HÌNH PHẢI: BOOKMAP", $font, $textBrush, ($bmpLeft.Width + 20), 10)

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
        # Single screen fallback
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
        Write-Host "[🧹] Da don dep sach se thu muc data/captures" -ForegroundColor Gray
    } catch {
        Write-Warning "Khong the xoa file anh tam: $_"
    }
}

# 5. Core Trigger Function: Capture -> agy Call -> Telegram Send -> Cleanup
$script:isAnalyzing = $false

function Trigger-DailyPlanAnalysis() {
    if ($script:isAnalyzing) {
        Send-TelegramText "⏳ Đang có một tiến trình phân tích đang chạy, vui lòng chờ trong giây lát..."
        return
    }

    $script:isAnalyzing = $true
    try {
        Write-Host "`n[>>>] KHOI TAO PHAN TICH THEO YEU CAU..." -ForegroundColor Yellow
        Send-TelegramText "🔄 Bắt đầu chụp 2 màn hình (VP/Footprint và Bookmap) và phân tích kế hoạch..."

        # Step 1: Capture dual screens
        $stitchedImage = Capture-DualScreens
        Write-Host "[+] Da chup va ghep anh: $stitchedImage" -ForegroundColor Green

        # Step 2: Prepare JSON schema & prompt for agy
        $schemaJson = @'
{
  "type": "object",
  "properties": {
    "date": { "type": "string" },
    "overview": { "type": "string" },
    "plans": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "plan_number": { "type": "integer" },
          "bias": { "type": "string" },
          "wait_zone_low": { "type": "number" },
          "wait_zone_high": { "type": "number" },
          "entry_condition": { "type": "string" }
        },
        "required": ["plan_number", "bias", "wait_zone_low", "wait_zone_high", "entry_condition"]
      }
    }
  },
  "required": ["date", "overview", "plans"]
}
'@

        $todayStr = (Get-Date).ToString("dd/MM/yyyy")
        $prompt = @"
Bạn là một chuyên gia giao dịch định lượng theo phương pháp Order Flow và Auction Market Theory phân tích vàng ($symbol).

Quan sát kỹ hình ảnh biểu đồ 2 màn hình tại: $stitchedImage
- MÀN HÌNH TRÁI: Cấu trúc Volume Profile (VAH, VAL, POC) và biểu đồ Footprint (Delta, cụm hấp thụ, mất cân bằng bid/ask).
- MÀN HÌNH PHẢI: Bookmap (Bản đồ nhiệt tường thanh khoản resting limit orders, CVD, bong bóng khớp lệnh chủ động).

NGUỒN DỮ LIỆU: Chỉ đọc và phân tích trực tiếp từ ảnh chụp 2 màn hình trên. Toàn bộ thang giá, cấu trúc Volume Profile và thanh khoản Bookmap đều quan sát trực tiếp từ biểu đồ (không dùng bất kỳ dữ liệu nào từ MT5).

QUY TẮC BẮT BUỘC VỀ NGÔN NGỮ VÀ NỘI DUNG:
1. TOÀN BỘ NỘI DUNG MÔ TẢ PHẢI ĐƯỢC VIẾT HOÀN TOÀN BẰNG TIẾNG VIỆT (STRICTLY VIETNAMESE).
2. 'date': Định dạng ngày bắt buộc là dd/mm/yyyy (ví dụ: '$todayStr').
3. 'overview': Tóm tắt bối cảnh thị trường trong ngày thật cô đọng, TỐI ĐA 100 KÝ TỰ bằng tiếng Việt.
4. 'plans': Tạo từ 2 đến 3 kế hoạch giao dịch (#Plan 1, #Plan 2, #Plan 3), mỗi plan gồm:
   - 'plan_number': 1, 2 hoặc 3
   - 'bias': 'BUY' hoặc 'SELL'
   - 'wait_zone_low': mức giá thấp của vùng chờ phản ứng
   - 'wait_zone_high': mức giá cao của vùng chờ phản ứng
   - 'entry_condition': điều kiện kích hoạt vào lệnh ngắn gọn súc tích theo Order Flow (Footprint, Bookmap) bằng tiếng Việt.
5. Trả về đúng định dạng JSON theo schema đã cung cấp.
"@

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
                if ($rawStr.StartsWith('```')) {
                    $rawStr = ($rawStr -replace '(?s)^```(?:json)?\s*', '') -replace '(?s)\s*```$', ''
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
            "📅 Kế hoạch ngày $($planData.date)",
            "📝 $($planData.overview)",
            ""
        )

        foreach ($p in $planData.plans) {
            $captionLines += "#Plan $($p.plan_number): $($p.bias)"
            $captionLines += "• Vùng chờ: $($p.wait_zone_low) - $($p.wait_zone_high)"
            $captionLines += "• Điều kiện vào: $($p.entry_condition)"
            $captionLines += ""
        }

        $finalCaption = ($captionLines -join "`n").Trim()
        Write-Host "`n$finalCaption`n" -ForegroundColor Green

        # Inline button for next update
        $planButtonMarkup = '{"inline_keyboard":[[{"text":"🔄 Cập nhật lại Plan","callback_data":"trigger_plan"}]]}'

        # Step 3: Send to Telegram
        Send-TelegramPhotoWithPlan -imagePath $stitchedImage -caption $finalCaption -replyMarkupJson $planButtonMarkup
        Write-Host "[✓] Da gui ket qua thanh cong sang Telegram!" -ForegroundColor Green

    } catch {
        Write-Host "[!] Loi trong qua trinh phan tich: $_" -ForegroundColor Red
        Send-TelegramText "⚠️ Có lỗi xảy ra trong quá trình phân tích: $_"
    } finally {
        # Step 4: Always clean up captures immediately
        Cleanup-Captures
        $script:isAnalyzing = $false
    }
}

# 6. Startup Message & Telegram Event Listener Loop
$initMarkup = '{"inline_keyboard":[[{"text":"🔄 Cập nhật lại Plan","callback_data":"trigger_plan"}]]}'
Send-TelegramText "🚀 *Trading Signal Agent (Windows Native) đã khởi động và đang chạy thường trực.*`n`n📌 Bấm nút *[🔄 Cập nhật lại Plan]* bên dưới (hoặc gửi `/plan`) bất kỳ lúc nào để chụp 2 màn hình và phân tích kế hoạch." $initMarkup

Write-Host "`n[✓] Server da san sang va dang lang nghe su kien tu Telegram..." -ForegroundColor Green
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
                        Write-Host "[Telegram] Nguoi dung bam nut: 🔄 Cap nhat lai Plan" -ForegroundColor Yellow
                        Answer-CallbackQuery -callbackQueryId $cbId -toastText "Đang chụp 2 màn hình và phân tích..."
                        Trigger-DailyPlanAnalysis
                    }
                }

                # Handle Text Messages
                if ($upd.message -and $upd.message.text) {
                    $msgText = $upd.message.text.Trim().ToLower()

                    if ($msgText -in @("/start", "/help")) {
                        Send-TelegramText "👋 Xin chào! Hệ thống Bot phân tích Order Flow đang hoạt động trên Windows.`n`nBấm nút *[🔄 Cập nhật lại Plan]* bên dưới để kích hoạt phân tích." $initMarkup
                    } elseif ($msgText -eq "/plan") {
                        Write-Host "[Telegram] Nhan lenh: /plan" -ForegroundColor Yellow
                        Trigger-DailyPlanAnalysis
                    }
                }
            }
        }
    } catch {
        # Network jitter / timeout retry
        Start-Sleep -Seconds 2
    }

    Start-Sleep -Milliseconds 500
}
