$ErrorActionPreference = 'Stop'
$path = (Resolve-Path (Join-Path $PSScriptRoot '..\index.html')).Path
$utf8 = New-Object System.Text.UTF8Encoding $false
$lines = [System.IO.File]::ReadAllLines($path, $utf8)
$head = $lines[0..35]
$tail = $lines[1688..($lines.Length - 1)]
$mid = @(
  '    <div id="app"></div>',
  '',
  '    <!-- 全局浮层：与旧版 DOM id/class 契约一致（AuthUI、FileManager、PlayerUI 等） -->',
  ''
)
$new = $head + $mid + $tail
[System.IO.File]::WriteAllLines($path, $new, $utf8)
Write-Host "OK: spliced index.html -> #app + overlays tail"
