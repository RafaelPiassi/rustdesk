<#
.SYNOPSIS
  Baixa o instalador mais recente do GitHub para a pasta compartilhada.

.DESCRIPTION
  Rode no PC servidor depois que o build terminar:
      powershell -ExecutionPolicy Bypass -File .\baixar-instalador.ps1
#>
param(
    [string]$PastaInstaladores = "C:\BoaSafra\Instaladores",
    [string]$Release = "boasafra-windows",
    [string]$Repo = "RafaelPiassi/rustdesk"
)
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$info = Invoke-RestMethod "https://api.github.com/repos/$Repo/releases/tags/$Release" -Headers @{ "User-Agent" = "boasafra" }
$arquivos = $info.assets | Where-Object { $_.name -match "x86_64\.(msi|exe)$" }
if (-not $arquivos) { throw "Nenhum instalador x86_64 na release $Release ainda." }

New-Item -ItemType Directory -Force $PastaInstaladores | Out-Null
Get-ChildItem $PastaInstaladores -Filter "*x86_64.*" | Remove-Item -Force
foreach ($a in $arquivos) {
    Write-Host "Baixando $($a.name) ($([math]::Round($a.size / 1MB, 1)) MB)"
    Invoke-WebRequest $a.browser_download_url -OutFile (Join-Path $PastaInstaladores $a.name) -UseBasicParsing
}
Copy-Item -Force (Join-Path $PSScriptRoot "instalar-cliente.cmd") $PastaInstaladores
Write-Host "`nPronto. Em cada PC, abra \\$env:COMPUTERNAME\Instaladores e execute instalar-cliente.cmd como administrador." -ForegroundColor Green
