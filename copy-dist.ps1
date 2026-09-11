$source = "d:\个人开发\个人工作台\dist"
$dest = "d:\个人开发\个人工作台\dist-output\win-unpacked\resources\app\dist"
Write-Host "Source exists: $(Test-Path $source)"
Write-Host "Dest parent exists: $(Test-Path (Split-Path $dest -Parent))"
Get-ChildItem $source | ForEach-Object { Write-Host "Copying $($_.Name)..." }
Copy-Item -Path "$source\*" -Destination $dest -Recurse -Force
Write-Host "Done"