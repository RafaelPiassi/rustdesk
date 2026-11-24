<#
.SYNOPSIS
  Sobe o servidor Boa Safra na rede local: ID/relay (hbbs/hbbr) e painel de licenças.

.DESCRIPTION
  Rode no PC servidor, como administrador, dentro desta pasta:
      powershell -ExecutionPolicy Bypass -File .\instalar-servidor.ps1
  Requer o Docker Desktop instalado e aberto. Pode ser executado de novo sem
  problema: só cria o que ainda não existe.

.PARAMETER Ip
  Endereço deste PC na rede. Sem ele, o script tenta descobrir sozinho.
#>
param(
    [string]$Ip,
    [string]$PastaInstaladores = "C:\BoaSafra\Instaladores"
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Passo($texto) { Write-Host "`n==> $texto" -ForegroundColor Green }

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { throw "Abra o PowerShell como administrador e rode de novo." }

Passo "Verificando o Docker"
docker version --format "{{.Server.Version}}" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Docker não encontrado ou parado. Instale o Docker Desktop (https://www.docker.com/products/docker-desktop/), abra-o e rode de novo."
}

Passo "Descobrindo o endereço deste PC na rede"
if (-not $Ip) {
    $Ip = Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" -and
                       $_.InterfaceAlias -notmatch "vEthernet|WSL|Docker|Loopback|VirtualBox|VMware" } |
        Sort-Object -Property @{ Expression = { $_.PrefixOrigin -eq "Dhcp" } } |
        Select-Object -First 1 -ExpandProperty IPAddress
}
if (-not $Ip) { throw "Não consegui descobrir o IP. Rode de novo com -Ip 192.168.x.x" }
Write-Host "IP: $Ip  (reserve este IP no roteador para ele não mudar)"

if (-not (Test-Path .env)) {
    Passo "Criando a configuração do painel de licenças"
    $senha = Read-Host "Senha do usuário admin do painel (mínimo 10 caracteres)" -AsSecureString
    $texto = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($senha))
    if ($texto.Length -lt 10) { throw "A senha precisa ter pelo menos 10 caracteres." }
    @(
        "PANEL_ADMIN_USER=admin"
        "PANEL_ADMIN_PASSWORD=$texto"
        "PANEL_PUBLIC_URL=http://${Ip}:8000"
        "PANEL_VALIDITY_DAYS=365"
        "PANEL_TZ=America/Sao_Paulo"
    ) | Set-Content -Encoding ascii .env
}

Passo "Liberando as portas no Firewall do Windows"
$regras = @(
    @{ Nome = "BoaSafra TCP"; Protocolo = "TCP"; Portas = @("21115-21119", "8000") },
    @{ Nome = "BoaSafra UDP"; Protocolo = "UDP"; Portas = @("21116") }
)
foreach ($r in $regras) {
    if (-not (Get-NetFirewallRule -DisplayName $r.Nome -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName $r.Nome -Direction Inbound -Action Allow `
            -Protocol $r.Protocolo -LocalPort $r.Portas -Profile Domain,Private | Out-Null
    }
}

Passo "Subindo os containers (a primeira vez demora alguns minutos)"
New-Item -ItemType Directory -Force dados\rustdesk, dados\licencas | Out-Null
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw "docker compose falhou; veja as mensagens acima." }

Passo "Aguardando as chaves"
$chaveHbbs = "dados\rustdesk\id_ed25519.pub"
for ($i = 0; $i -lt 60 -and -not (Test-Path $chaveHbbs); $i++) { Start-Sleep 2 }
if (-not (Test-Path $chaveHbbs)) { throw "O hbbs não gerou a chave. Veja: docker compose logs hbbs" }
$rsKey = (Get-Content $chaveHbbs -Raw).Trim()

$licKey = $null
for ($i = 0; $i -lt 60 -and -not $licKey; $i++) {
    $licKey = docker compose exec -T licencas python -c "import base64,nacl.signing as s;print(base64.b64encode(bytes(s.SigningKey(base64.b64decode(open('/data/license_signing_key').read())).verify_key)).decode())" 2>$null
    if (-not $licKey) { Start-Sleep 2 }
}
if (-not $licKey) { throw "O painel não subiu. Veja: docker compose logs licencas" }

Passo "Criando a pasta compartilhada de instaladores"
New-Item -ItemType Directory -Force $PastaInstaladores | Out-Null
Copy-Item -Force instalar-cliente.cmd $PastaInstaladores
if (-not (Get-SmbShare -Name Instaladores -ErrorAction SilentlyContinue)) {
    New-SmbShare -Name Instaladores -Path $PastaInstaladores -ReadAccess "Todos" -ErrorAction SilentlyContinue | Out-Null
    if (-not $?) { New-SmbShare -Name Instaladores -Path $PastaInstaladores -ReadAccess "Everyone" | Out-Null }
}

$resumo = @"
Servidor Boa Safra
==================
Painel de licenças : http://${Ip}:8000   (usuário admin)
Pasta de instaladores: \\$env:COMPUTERNAME\Instaladores  ($PastaInstaladores)

Valores para o build do instalador (variáveis do repositório no GitHub):
BOASAFRA_RENDEZVOUS_SERVER  = $Ip
BOASAFRA_RS_PUB_KEY         = $rsKey
BOASAFRA_LICENSE_SERVER     = http://${Ip}:8000
BOASAFRA_LICENSE_PUBLIC_KEY = $licKey

Faça backup da pasta $PSScriptRoot\dados : ela guarda as chaves e o banco de licenças.
"@
$resumo | Set-Content -Encoding utf8 chaves.txt
Write-Host "`n$resumo" -ForegroundColor Cyan
Write-Host "Resumo salvo em $PSScriptRoot\chaves.txt"
