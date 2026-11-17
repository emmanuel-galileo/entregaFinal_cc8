param(
    [string]$PortName = 'COM3',
    [ValidateSet('UTF8','CP1252')][string]$TextEncoding = 'UTF8'
)
$ErrorActionPreference = 'Stop'
$port = [System.IO.Ports.SerialPort]::new($PortName,115200,[System.IO.Ports.Parity]::None,8,[System.IO.Ports.StopBits]::One)
$port.Handshake = [System.IO.Ports.Handshake]::None
$port.Encoding = if ($TextEncoding -eq 'UTF8') { [System.Text.UTF8Encoding]::new($false) } else { [System.Text.Encoding]::GetEncoding(1252) }
$port.DtrEnable = $false
$port.RtsEnable = $false
$surrogate = ''
$keyLengths = [System.Collections.Generic.List[int]]::new()
try {
    $port.Open()
    Write-Host "Terminal: $PortName, 115200 8N1, $TextEncoding. ESC cierra el puerto."
    Write-Host 'Selecciona 1=A o 2=B. Los comandos como /start, /send Hola y /status llevan Enter.'
    Write-Host 'Usa /stop en ambas placas antes de cerrar si quieres apagar los emisores.'
    $port.Write("?`r")
    while ($true) {
        $received = $port.ReadExisting()
        if ($received.Length) { [Console]::Write($received) }
        if ([Console]::KeyAvailable) {
            $key = [Console]::ReadKey($true)
            if ($key.Key -eq [ConsoleKey]::Escape) { break }
            if ($key.Key -eq [ConsoleKey]::Enter) { $port.Write("`r"); $keyLengths.Clear(); [Console]::WriteLine(); continue }
            if ($key.Key -eq [ConsoleKey]::Backspace) {
                if ($keyLengths.Count) {
                    $last = $keyLengths.Count-1
                    $port.Write(([string][char]8)*$keyLengths[$last])
                    $keyLengths.RemoveAt($last)
                    [Console]::Write("`b `b")
                }
                continue
            }
            if ($key.KeyChar -eq [char]0) { continue }
            if ([char]::IsHighSurrogate($key.KeyChar)) { $surrogate = [string]$key.KeyChar; continue }
            $text = $surrogate + [string]$key.KeyChar
            $surrogate = ''
            $port.Write($text)
            $keyLengths.Add($port.Encoding.GetByteCount($text))
            [Console]::Write($text)
        }
        Start-Sleep -Milliseconds 10
    }
} finally {
    if ($port.IsOpen) { $port.Close() }
    $port.Dispose()
}
