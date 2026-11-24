# Servidor na rede local (Windows)

Sobe, num PC Windows da rede, tudo o que os clientes Boa Safra precisam:

| Serviço | Porta | Para quê |
| --- | --- | --- |
| `hbbs` | 21115–21116 (TCP/UDP), 21118 | servidor de ID |
| `hbbr` | 21117, 21119 | relay |
| `licencas` | 8000 | painel de licenças (`http://IP:8000`) |

## 1. Servidor

1. Instale o [Docker Desktop](https://www.docker.com/products/docker-desktop/) e
   deixe marcado "iniciar com o Windows".
2. Reserve um IP fixo para este PC no roteador.
3. Baixe o projeto e rode o script como administrador:

```powershell
cd $env:USERPROFILE
Invoke-WebRequest https://github.com/RafaelPiassi/rustdesk/archive/refs/heads/claude/boasafra-license-panel.zip -OutFile boasafra.zip
Expand-Archive boasafra.zip -DestinationPath . -Force
cd .\rustdesk-claude-boasafra-license-panel\deploy\rede-local
powershell -ExecutionPolicy Bypass -File .\instalar-servidor.ps1
```

O script pede a senha do painel, libera as portas no firewall, sobe os
containers, cria o compartilhamento `\\SERVIDOR\Instaladores` e grava em
`chaves.txt` os quatro valores que o build do instalador precisa.

## 2. Instalador

Os valores de `chaves.txt` (são todos públicos) viram variáveis do repositório
no GitHub: *Settings → Secrets and variables → Actions → Variables*.
Depois, um push para uma branch `build/...` gera o MSI e o EXE na release
`boasafra-windows`. Para trazê-los para a pasta compartilhada:

```powershell
powershell -ExecutionPolicy Bypass -File .\baixar-instalador.ps1
```

## 3. Clientes

Em cada PC, abra `\\SERVIDOR\Instaladores`, clique com o botão direito em
`instalar-cliente.cmd` → *Executar como administrador*. Para já ativar a
licença, rode pelo prompt: `instalar-cliente.cmd XXXX-XXXX-XXXX-XXXX-XXXX`.

Os seriais são gerados no painel: `http://IP-DO-SERVIDOR:8000` → Clientes →
Gerar seriais.

## Backup

A pasta `dados\` guarda a chave do servidor de ID, a chave de assinatura das
licenças e o banco do painel. Se ela se perder, todos os clientes precisam de um
instalador novo. Copie-a para outro lugar regularmente.
