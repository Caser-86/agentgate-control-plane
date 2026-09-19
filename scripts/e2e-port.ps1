Set-StrictMode -Version Latest

function Test-FreeLoopbackPort {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateRange(1, 65535)]
        [int]$Port
    )

    $listener = $null
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
        $listener.Start()
        return $true
    } catch [System.Net.Sockets.SocketException] {
        return $false
    } finally {
        if ($null -ne $listener) {
            $listener.Stop()
        }
    }
}

function Get-FreeLoopbackPortRange {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateRange(1, 65535)]
        [int]$StartPort,
        [ValidateRange(1, 100)]
        [int]$Count = 3,
        [ValidateRange(1, 5000)]
        [int]$SearchLimit = 1000
    )

    $lastStart = [Math]::Min(65535 - $Count + 1, $StartPort + $SearchLimit)
    for ($candidate = $StartPort; $candidate -le $lastStart; $candidate++) {
        $available = $true
        for ($offset = 0; $offset -lt $Count; $offset++) {
            if (-not (Test-FreeLoopbackPort -Port ($candidate + $offset))) {
                $available = $false
                break
            }
        }
        if ($available) {
            return $candidate
        }
    }

    throw "无法在 127.0.0.1:$StartPort 起始范围内找到 $Count 个连续空闲端口。"
}
