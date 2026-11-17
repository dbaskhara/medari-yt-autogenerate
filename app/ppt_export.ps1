param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][string]$OutDir)
# Export every slide of a PowerPoint file to slideN.png (1440x1080) and slides.json.
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force $OutDir | Out-Null
$app = New-Object -ComObject PowerPoint.Application
try {
  # ReadOnly, Untitled, WithWindow = false
  $pres = $app.Presentations.Open($Path, $true, $false, $false)
  $ratio = $pres.PageSetup.SlideWidth / $pres.PageSetup.SlideHeight
  $h = 1080; $w = [int][math]::Round($h * $ratio)
  $info = @()
  foreach ($s in $pres.Slides) {
    $file = Join-Path $OutDir ("slide{0}.png" -f $s.SlideIndex)
    $s.Export($file, 'PNG', $w, $h)
    $texts = @(); $pics = 0
    foreach ($sh in $s.Shapes) {
      if ($sh.Type -eq 13) { $pics++ }
      if ($sh.HasTextFrame -and $sh.TextFrame.HasText) { $texts += $sh.TextFrame.TextRange.Text }
    }
    $info += [pscustomobject]@{ index = $s.SlideIndex; pictures = $pics; text = ($texts -join "`n") }
  }
  $pres.Close()
  [pscustomobject]@{ ratio = $ratio; slides = $info } | ConvertTo-Json -Depth 4 | Out-File -Encoding utf8 (Join-Path $OutDir 'slides.json')
} finally {
  if ($app.Presentations.Count -eq 0) { $app.Quit() }
  [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($app)
}
