$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VendorDir = Join-Path $ProjectRoot 'vendor'
$InstallerPath = Join-Path $VendorDir 'OllamaSetup.exe'
$DownloadUrl = 'https://ollama.com/download/OllamaSetup.exe'

New-Item -ItemType Directory -Force -Path $VendorDir | Out-Null

if (-not (Test-Path -LiteralPath $InstallerPath)) {
    Write-Host 'Downloading the official Ollama Windows installer...'
    $TemporaryPath = "$InstallerPath.download"
    Remove-Item -LiteralPath $TemporaryPath -Force -ErrorAction SilentlyContinue
    try {
        Invoke-WebRequest -Uri $DownloadUrl -OutFile $TemporaryPath -UseBasicParsing
        Move-Item -LiteralPath $TemporaryPath -Destination $InstallerPath -Force
    }
    catch {
        Remove-Item -LiteralPath $TemporaryPath -Force -ErrorAction SilentlyContinue
        throw
    }
}

$file = Get-Item -LiteralPath $InstallerPath
if ($file.Length -lt 10MB) {
    Remove-Item -LiteralPath $InstallerPath -Force
    throw 'The downloaded Ollama installer is unexpectedly small; refusing to bundle it.'
}

$signature = Get-AuthenticodeSignature -FilePath $InstallerPath
if ($signature.Status -ne 'Valid') {
    Remove-Item -LiteralPath $InstallerPath -Force
    throw "Ollama installer signature is not valid (status: $($signature.Status))."
}

# Match the organization identity used by Ollama's own Windows install script.
if ($signature.SignerCertificate.Subject -notmatch '(^|, )O=Ollama Inc\.(,|$)') {
    $subject = $signature.SignerCertificate.Subject
    Remove-Item -LiteralPath $InstallerPath -Force
    throw "Unexpected Ollama installer publisher: $subject"
}

Write-Host "Verified official signed Ollama installer: $([math]::Round($file.Length / 1MB, 1)) MB"
Write-Host "Publisher: $($signature.SignerCertificate.Subject)"
