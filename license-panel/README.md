# Painel de licenças

Controla quem pode usar o Boa Safra Acesso Remoto. Cada computador precisa de um
**serial** ativado; o serial fica preso àquele computador e vale **1 ano** (ou o
prazo que você definir). Sem licença válida, o aplicativo abre, mas não aceita
nem faz conexões remotas.

O painel também guarda a **marca de cada cliente** (nome, empresa, logos) e gera,
pelo GitHub Actions, um instalador do Windows inteiro com a marca dele.

## Como funciona

```
 cliente (app)                         painel                       GitHub Actions
 ─────────────                         ──────                       ──────────────
 digita o serial ──── /api/v1/activate ──▶ vincula ao computador,
                                          começa a contar 1 ano
                 ◀── status assinado ───  (Ed25519)
 guarda o status
 a cada 1 hora  ──── /api/v1/validate ──▶ ativa? vencida? revogada?
                 ◀── status assinado ───
                                          Marcas → Gerar instalador ──▶ baixa o pacote da marca,
                                                                        troca nomes e ícones,
                                                                        publica MSI + EXE
```

- **Validação somente online.** O serviço do app pergunta ao painel a cada hora.
  Se o painel ficar inacessível, a última resposta vale por até **24 horas**;
  depois disso o computador fica bloqueado até conseguir verificar de novo.
- **Respostas assinadas.** O painel assina cada resposta com a sua chave
  Ed25519, e o app só aceita as que conferem com a chave pública embutida no
  build e citam aquele serial e aquele computador. Copiar a configuração de uma
  máquina para outra não funciona, e um servidor falso não libera nada.
- **Bloqueio.** Sem licença, o computador recusa quem tenta acessá-lo
  ("o computador remoto não tem uma licença válida") e não inicia conexões.
  O aviso de vencimento aparece 30 dias antes.

## Instalação

Requer Docker e um domínio com HTTPS, porque os clientes e o GitHub Actions
acessam o painel pela internet.

```bash
cd license-panel
cp .env.example .env      # preencha senha, domínio e (opcional) GitHub
docker compose --profile https up -d --build
```

O perfil `https` sobe um Caddy que emite o certificado sozinho; para isso o DNS de
`PANEL_DOMAIN` precisa apontar para o servidor e as portas 80/443 precisam estar
abertas. Se você já tem Nginx/Traefik, suba só o painel (`docker compose up -d`)
e encaminhe para `127.0.0.1:8000`, ajustando `PANEL_TRUSTED_PROXIES`.

Pode rodar no mesmo servidor do `hbbs`/`hbbr`.

### Primeiro acesso

1. Entre em `https://seu-dominio` com `PANEL_ADMIN_USER` / `PANEL_ADMIN_PASSWORD`
   e troque a senha em **Configurações**.
2. Em **Configurações**, copie a **chave pública** e o endereço do painel.
3. Coloque os dois no build padrão, por um destes caminhos:
   - nas **variáveis do repositório** no GitHub (*Settings → Secrets and variables
     → Actions → Variables*): `BOASAFRA_LICENSE_PUBLIC_KEY` e
     `BOASAFRA_LICENSE_SERVER` (recomendado: não precisa de commit);
   - ou em `src/branding.rs`, nas constantes `LICENSE_PUBLIC_KEY` e
     `LICENSE_SERVER`.
4. Gere um novo instalador. **Um build sem a chave bloqueia tudo** e mostra
   "Esta versão não tem servidor de licenças configurado".

> A chave privada fica em `/data/license_signing_key`, no volume
> `license-data`. **Faça backup do volume.** Se a chave se perder, todos os
> clientes precisam ser recompilados e reinstalados com a chave nova.

## Uso no dia a dia

| Tarefa | Onde |
| --- | --- |
| Cadastrar cliente | **Clientes** → Novo cliente |
| Gerar seriais | página do cliente → *Gerar seriais* (quantidade, validade, início na ativação ou hoje) |
| Ver vencimentos | **Início** mostra as que vencem em 30 dias e as vencidas |
| Renovar | página da licença → *Renovar* (soma 365 dias ao vencimento atual) |
| Mudar a data | página da licença → *Definir vencimento* |
| Bloquear um computador | página da licença → *Revogar* (vale na próxima verificação, até 1 hora) |
| Trocar o computador do cliente | página da licença → *Trocar de computador*: o antigo é bloqueado e o serial pode ser ativado no novo |
| Exportar | **Licenças** → Exportar CSV (abre no Excel) |
| Auditoria | **Eventos**, e o histórico na página de cada licença |

No computador do cliente: na tela inicial aparece o quadro **Licença**; clique em
**Ativar licença** e digite o serial. No Android, fica em *Configurações →
Licença*.

## Marcas por cliente (white-label)

1. **Marcas → Nova marca**: identificador (uma palavra, ex. `AcmeRemoto`), nome
   exibido (`Acme Acesso Remoto`), empresa, cor e os logos para fundo claro e
   escuro (SVG ou PNG). O ícone quadrado é opcional: sem ele, o ícone é recortado
   do logo, a parte à esquerda do maior espaço vazio entre símbolo e texto.
2. Na página do cliente, escolha a marca em **Marca do instalador**.
3. Na página da marca, **Gerar instalador**. O painel dispara o workflow
   `brand-build.yml` no GitHub; em cerca de 1 hora o MSI e o EXE aparecem em
   *Releases*, e a página da marca mostra o link.

O que muda no instalador de marca: nome do executável (`acmeremoto.exe`), do
serviço do Windows, da pasta de configuração e do link `acmeremoto://`, nome
exibido no atalho, na janela e em *Adicionar/remover programas*, fabricante,
ícones e as imagens do instalador. Ele já sai apontando para este painel e com a
chave pública dele.

Para isso o painel precisa de:

- `PANEL_PUBLIC_URL` com `https://` (o GitHub baixa o pacote da marca dali);
- `GITHUB_REPO` e `GITHUB_TOKEN`: um token *fine-grained* com acesso só ao
  repositório e permissão **Actions: Read and write**.

Atenção: o repositório é **público**, então as execuções e as releases (com os
instaladores e logos de cada marca) ficam visíveis para qualquer pessoa. Se isso
for um problema, torne o fork privado antes de gerar instaladores de marca.

Hoje o build de marca gera o instalador do **Windows** (x64 e ARM64). As demais
plataformas continuam com a marca padrão.

O mesmo rebrand pode ser feito à mão, num clone descartável:

```bash
pip install cairosvg pillow numpy
python3 res/branding/apply_brand.py pacote-da-marca.zip   # ou uma pasta com brand.json + logos
```

## Configuração

| Variável | Para quê |
| --- | --- |
| `PANEL_ADMIN_USER`, `PANEL_ADMIN_PASSWORD` | usuário criado no primeiro início |
| `PANEL_PUBLIC_URL` | endereço público, embutido nos instaladores de marca |
| `PANEL_DOMAIN` | domínio do Caddy (perfil `https`) |
| `PANEL_TRUSTED_PROXIES` | quantos proxies reversos estão na frente (para o IP real nos logs e limites) |
| `PANEL_VALIDITY_DAYS` | validade padrão dos seriais (365) |
| `PANEL_TZ` | fuso das datas na tela (`America/Sao_Paulo`) |
| `GITHUB_REPO`, `GITHUB_TOKEN`, `GITHUB_REF`, `GITHUB_WORKFLOW` | builds de marca |
| `PANEL_SECURE_COOKIES` | `0` só para testar sem HTTPS |
| `PANEL_SECRET_KEY`, `PANEL_SIGNING_KEY` | opcionais; por padrão gerados e guardados em `/data` |

## API

Os clientes chamam, com JSON
`{"serial", "machine", "id", "hostname", "platform", "version", "app"}`:

- `POST /api/v1/activate`: vincula o serial ao computador, se ainda estiver livre;
- `POST /api/v1/validate`: só confere;
- `GET /api/v1/health`.

A resposta é `{"state", "token"}`, em que `token` é o base64 de
`assinatura || JSON` com `serial`, `machine`, `state` (`active`, `expired`,
`revoked`, `bound_elsewhere`, `invalid`), `customer`, `expires_at` e
`checked_at`. `machine` é o SHA-256 do identificador da máquina com o nome do
app, não o identificador em si. Limite: 30 requisições por minuto por IP.

## Desenvolvimento

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
PANEL_DATA_DIR=./data PANEL_ADMIN_PASSWORD=dev PANEL_SECURE_COOKIES=0 flask --app wsgi run
```
