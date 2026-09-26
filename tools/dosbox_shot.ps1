# Run a DOS program in DOSBox Staging, wait, screenshot its window, close it.
# usage: dosbox_shot.ps1 -Dir <dir> -Program <file> -Out <png> [-Seconds 8] [-Keys "..."]
param(
    [Parameter(Mandatory)] [string] $Dir,
    [Parameter(Mandatory)] [string] $Program,
    [Parameter(Mandatory)] [string] $Out,
    [double] $Seconds = 8,
    [string] $Keys = ""
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing, System.Windows.Forms
Add-Type @'
using System; using System.Runtime.InteropServices;
public static class W32 {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
'@
[W32]::SetProcessDPIAware() | Out-Null
$exe = 'C:\Program Files\DOSBox Staging\dosbox.exe'
$conf = Join-Path $env:TEMP ("vlakshot_" + [guid]::NewGuid() + ".conf")
@"
[sdl]
window_size = 960x600
[dosbox]
machine = ega
[cpu]
cpu_cycles = 3000
[autoexec]
mount c "$Dir"
c:
$Program
"@ | Set-Content -Encoding ascii $conf
$args = "-noprimaryconf -nolocalconf -conf `"$conf`""
$p = Start-Process -FilePath $exe -ArgumentList $args -PassThru
try {
    for ($i = 0; $i -lt 100 -and $p.MainWindowHandle -eq 0; $i++) { Start-Sleep -Milliseconds 100; $p.Refresh() }
    Start-Sleep -Seconds $Seconds
    [W32]::SetForegroundWindow($p.MainWindowHandle) | Out-Null
    if ($Keys) {
        foreach ($k in $Keys.Split('|')) { [System.Windows.Forms.SendKeys]::SendWait($k); Start-Sleep -Milliseconds 700 }
        Start-Sleep -Seconds 1
    }
    $r = New-Object W32+RECT
    [W32]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
    $bmp = New-Object System.Drawing.Bitmap ($r.R - $r.L), ($r.B - $r.T)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($r.L, $r.T, 0, 0, $bmp.Size)
    $bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
} finally {
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
}
