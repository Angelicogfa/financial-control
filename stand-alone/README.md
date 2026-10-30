# Financial Control — instalação stand-alone

Este diretório roda o Financial Control usando as imagens Docker já publicadas no GitHub Container Registry. Não é preciso clonar o repositório, instalar Python ou Node nem compilar nada: bastam o Docker e os três arquivos daqui.

| Arquivo | Para que serve |
|---|---|
| `docker-compose.yml` | a stack completa: Postgres, Redis, migrations, API, worker e web |
| `.env.sample` | modelo do `.env`, com todas as variáveis e valores padrão |
| `README.md` | este passo a passo |

Imagens usadas:

| Imagem | Serviços |
|---|---|
| `ghcr.io/angelicogfa/finance-controle-api:<versão>` | `migrate`, `api` e `worker` |
| `ghcr.io/angelicogfa/finance-controle-web:<versão>` | `web` |
| `postgres:16-alpine` e `redis:7-alpine` | banco e cache |

Só o `web` fica acessível de fora, na porta `8080`. Banco, cache e API ficam na rede interna do Docker.

## 1. Pré-requisitos

- **Docker** com **Docker Compose v2**: [Docker Desktop](https://docs.docker.com/get-docker/) no Windows ou macOS, ou Docker Engine com o plugin `compose` no Linux. Para conferir:

  ```bash
  docker --version
  docker compose version
  ```

- Máquina **x86-64 (amd64)**. As imagens são publicadas só para `linux/amd64`. Em Macs com Apple Silicon, o Docker Desktop roda essas imagens por emulação (Rosetta), com algum custo de desempenho. Em Raspberry Pi e outras máquinas ARM no Linux, elas não rodam.
- Cerca de 2 GB livres em disco para as imagens e os dados.

## 2. Baixar os arquivos

Crie uma pasta e baixe os dois arquivos da stack:

```bash
mkdir financial-control && cd financial-control
curl -fsSLO https://raw.githubusercontent.com/Angelicogfa/financial-control/main/stand-alone/docker-compose.yml
curl -fsSL https://raw.githubusercontent.com/Angelicogfa/financial-control/main/stand-alone/.env.sample -o .env.sample
```

No Windows, use os mesmos comandos no PowerShell trocando `curl` por `curl.exe`, ou baixe os arquivos pela página do repositório (botão *Raw*). Se você já tem o repositório clonado, basta entrar na pasta `stand-alone/`.

## 3. Criar o `.env`

```bash
cp .env.sample .env
```

No PowerShell: `Copy-Item .env.sample .env`.

### 3.1. Senhas do banco e do cache

Gere duas senhas aleatórias, uma para o Postgres e outra para o Redis:

```bash
openssl rand -hex 24
```

Se não tiver `openssl`, use qualquer gerador de senhas, mas **só com letras e números**, porque as senhas também entram nas URLs de conexão. Coloque as senhas no `.env`:

```dotenv
POSTGRES_PASSWORD=<senha-do-postgres>
REDIS_PASSWORD=<senha-do-redis>
```

Não é preciso escrever `DATABASE_URL` nem `REDIS_URL`: o `docker-compose.yml` monta as duas a partir dessas variáveis.

### 3.2. Versão

Por padrão, `FINCONTROL_VERSION=latest` acompanha a release mais nova. Para atualizar só quando você decidir, fixe uma versão. As versões disponíveis estão em [Releases](https://github.com/Angelicogfa/financial-control/releases):

```dotenv
FINCONTROL_VERSION=v1.0.0
```

### 3.3. Baixar as imagens

```bash
docker compose pull
```

Se aparecer `denied` ou `unauthorized`, veja [Imagens privadas](#imagens-privadas).

### 3.4. Usuário e senha de login

Escolha o usuário em `AUTH_USERNAME` (padrão: `admin`). Depois, gere o hash da senha. O comando pede a senha duas vezes, sem mostrar na tela, e imprime a linha pronta:

```bash
docker compose run --rm --no-deps api python cli.py hash-password
```

Cole a linha `AUTH_PASSWORD_HASH='$argon2id$...'` **inteira, com as aspas simples**, no lugar da linha `AUTH_PASSWORD_HASH=change-me` do `.env`. Sem as aspas, os `$` do hash são interpretados e a tela de login avisa que a autenticação não está configurada.

### 3.5. Segredo do token de sessão

```bash
docker compose run --rm --no-deps api python cli.py new-secret
```

Cole a linha `AUTH_JWT_SECRET=...` impressa no lugar de `AUTH_JWT_SECRET=change-me`.

### 3.6. Ajustes opcionais

| Variável | Quando mudar |
|---|---|
| `BRAPI_TOKEN` | Recomendado. Crie um token gratuito em [brapi.dev](https://brapi.dev/dashboard). Sem ele, a brapi recusa a maioria dos tickers e o Yahoo Finance vira a fonte. |
| `WEB_PORT` | Se a porta `8080` já estiver em uso. |
| `WEB_BIND` | Use `127.0.0.1` para o app abrir só neste computador. Com `0.0.0.0` (padrão), ele fica acessível também pela rede local. |
| `CORS_ORIGINS` | Inclua o endereço usado no navegador se não for `http://localhost:8080`, por exemplo `http://192.168.0.10:8080`. |
| `AUTH_COOKIE_SECURE` | `true` quando o app for servido por HTTPS, atrás de um proxy reverso com certificado. |
| `TZ` | Fuso horário dos agendamentos do worker. |

As demais variáveis já vêm com valores que funcionam e estão comentadas no `.env.sample`.

> O `.env` guarda senhas: não compartilhe e não versione esse arquivo.

## 4. Subir a stack

```bash
docker compose up -d
```

Na primeira vez, o Postgres e o Redis são inicializados, e o serviço `migrate` cria as tabelas do banco antes de a API subir. As próximas subidas aplicam só as migrations novas.

## 5. Conferir e acessar

```bash
docker compose ps -a
```

`postgres`, `redis`, `api` e `web` devem aparecer como `healthy`, `worker` como `Up`, e `migrate` como `Exited (0)`, porque ele só roda uma vez. A primeira subida leva cerca de um minuto.

Abra **http://localhost:8080** (ou a porta definida em `WEB_PORT`) e entre com o usuário e a senha do passo 3.4. A saúde da API pode ser conferida em http://localhost:8080/api/v1/ready.

## 6. Primeiros passos no app

1. **Configuração › Estratégia:** defina as metas ARCA (somando 100%), as bandas e os critérios de elegibilidade.
2. **Configuração › Contas:** cadastre suas corretoras e bancos.
3. **Lançamentos › Importar extrato B3:** na [Área do Investidor da B3](https://www.investidor.b3.com.br), exporte *Extratos › Negociação* e *Extratos › Movimentação* e importe os dois arquivos. Importar o mesmo arquivo de novo não duplica nada.
4. **Carteira › Novo ativo:** cadastre renda fixa e caixa, informando o contrato.
5. **Aportar:** informe o valor, revise a distribuição e confirme as compras.

O worker sincroniza sozinho cotações, séries do Banco Central, catálogo da B3, demonstrativos e comunicados da CVM. O andamento aparece em **Configuração › Dados de mercado**.

Para explorar o app com dados fictícios, num banco **vazio** (o comando se recusa a rodar se já houver ativos):

```bash
docker compose exec worker python -m worker.seed_demo
```

## Operação

### Parar e iniciar

```bash
docker compose stop      # para sem remover nada
docker compose start     # volta a rodar
docker compose down      # remove os containers; os dados continuam nos volumes
```

> **Cuidado:** `docker compose down -v` apaga os volumes, ou seja, **todos os seus dados**.

### Atualizar para uma nova versão

1. Faça um backup (seção abaixo).
2. Se você fixou a versão, troque `FINCONTROL_VERSION` no `.env`. Com `latest`, pule este passo.
3. Baixe as imagens e recrie os containers. As migrations rodam sozinhas:

   ```bash
   docker compose pull
   docker compose up -d
   ```

4. Opcional: remova as imagens antigas com `docker image prune`.

Para voltar a uma versão anterior, restaure o backup feito antes da atualização e fixe a versão antiga em `FINCONTROL_VERSION`. As migrations não são desfeitas automaticamente.

### Backup e restauração

Backup do banco num arquivo `.dump` na pasta atual:

```bash
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > fincontrol_$(date +%Y%m%d_%H%M%S).dump
```

Restaurar um backup:

```bash
docker compose exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' < arquivo.dump
```

No PowerShell, o redirecionamento `>` pode corromper o arquivo binário. Rode esses dois comandos no Git Bash ou no WSL.

### Logs

```bash
docker compose logs -f api worker
```

## Solução de problemas

| Sintoma | Causa provável e correção |
|---|---|
| `denied` ou `unauthorized` no `docker compose pull` | As imagens ainda estão privadas. Veja [Imagens privadas](#imagens-privadas). |
| `manifest unknown` no `pull` | A versão em `FINCONTROL_VERSION` não existe. Confira em [Releases](https://github.com/Angelicogfa/financial-control/releases). |
| `set POSTGRES_PASSWORD in .env` | O `.env` não existe na mesma pasta do `docker-compose.yml`, ou a variável está vazia. |
| A tela de login diz que a autenticação não está configurada | `AUTH_PASSWORD_HASH` ou `AUTH_JWT_SECRET` ainda começa com `change-me`, ou o hash foi colado sem as aspas simples. Corrija e rode `docker compose up -d`. |
| `migrate` termina com erro de autenticação no banco | A senha do Postgres foi trocada depois que o volume foi criado. O banco guarda a senha da primeira subida: volte para ela no `.env`. |
| `port is already allocated` | A porta `8080` está em uso. Troque `WEB_PORT` no `.env`. |
| `502 Bad Gateway` logo após subir | A API ainda está iniciando. Aguarde até ela aparecer como `healthy` em `docker compose ps`. |

### Imagens privadas

Se as imagens ainda não estiverem públicas no GitHub, faça login no registro antes do `pull`. Use um [token clássico do GitHub](https://github.com/settings/tokens) com o escopo `read:packages`:

```bash
docker login ghcr.io -u <seu-usuario-github>
```

Cole o token quando o Docker pedir a senha.

### Rodando junto com o repositório clonado

Esta stack usa os mesmos volumes (`fincontrol_pgdata`, `fincontrol_redisdata`) dos `docker-compose` da raiz do repositório. Por isso, ela enxerga os mesmos dados. Não rode as duas ao mesmo tempo: pare uma (`docker compose down`) antes de subir a outra. Para manter as duas separadas, troque `PGDATA_VOLUME`, `REDISDATA_VOLUME` e `WEB_PORT` no `.env`.

## Licença

Uso pessoal gratuito, uso comercial proibido e citação da fonte obrigatória, nos termos da [PolyForm Noncommercial License 1.0.0](../LICENSE.md). Detalhes no [README do projeto](../README.md#licença).
