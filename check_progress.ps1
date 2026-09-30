# Monitor results directory for growing files
Write-Host "📊 Checking output files..." -ForegroundColor Cyan
 = @(Get-ChildItem -Path "c:\Users\udayr\Downloads\llm project_trailgpt\Agentic-TrailGPT\results" -File 2> | Where-Object {.Extension -eq ".json"})
if (.Count -gt 0) {
     | ForEach-Object {
         = [math]::Round(.Length/1KB, 1)
         = (Get-Content .FullName | Measure-Object -Line).Lines
        Write-Host "✓ " -ForegroundColor Green
        Write-Host "  Size:  KB | Lines: "
    }
} else {
    Write-Host "⏳ Waiting for output files..." -ForegroundColor Yellow
}
