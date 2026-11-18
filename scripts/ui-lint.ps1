# UI Design System Linter for Windows PowerShell
Write-Host "Running UI Design System Linter..." -ForegroundColor Cyan

$targetFiles = Get-ChildItem -Path "frontend/app", "frontend/components" -Recurse -Include *.tsx, *.ts, *.jsx, *.js, *.css
$fail = $false

$bannedPatterns = @(
    "gradient",
    "backdrop-blur",
    "shadow-lg",
    "shadow-xl",
    "shadow-2xl",
    "rounded-xl",
    "rounded-2xl",
    "rounded-3xl",
    "animate-bounce",
    "animate-ping",
    "animate-pulse"
)

foreach ($file in $targetFiles) {
    $lines = Get-Content -LiteralPath $file.FullName

    foreach ($pat in $bannedPatterns) {
        for ($i = 0; $i -lt $lines.Count; $i++) {
            if ($lines[$i] -match $pat) {
                Write-Host "ERROR: Banned pattern '$pat' found in $($file.FullName):$($i+1)" -ForegroundColor Red
                Write-Host "  $($lines[$i])"
                $fail = $true
            }
        }
    }

    # Check for hex colors outside globals.css and styleguide
    if ($file.Name -ne "globals.css" -and $file.Name -ne "page.tsx") {
        for ($i = 0; $i -lt $lines.Count; $i++) {
            if ($lines[$i] -match "#[0-9a-fA-F]{3,6}") {
                Write-Host "ERROR: Hex color found outside globals.css in $($file.FullName):$($i+1)" -ForegroundColor Red
                Write-Host "  $($lines[$i])"
                $fail = $true
            }
        }
    }
}

if ($fail) {
    Write-Host "UI Lint Failed: UI violates section 11 design system constraints." -ForegroundColor Red
    exit 1
} else {
    Write-Host "UI Lint Passed cleanly. Zero forbidden design elements found." -ForegroundColor Green
    exit 0
}
