# LP Odisys — guia do projeto e dos ambientes

Leia este arquivo antes de aplicar qualquer modificação. Ele descreve a diferença entre
**produção** e **staging** e as regras que evitam que uma mudança de staging vaze para produção
(ou o contrário).

## O projeto

Landing page **estática de página única**. Sem framework, sem build, sem dependências —
o que está no repositório é exatamente o que vai para o ar.

```
index.html          a LP inteira (head com SEO/GTM + todo o conteúdo)
css/styles.css      estilos
js/main.js          interações
assets/             logo, OG images, favicons
robots.txt          robots de PRODUÇÃO
robots.staging.txt  robots de STAGING (servido via rewrite por host)
sitemap.xml         sitemap de produção
vercel.json         config de deploy (idêntico em todas as branches)
tools/              scripts auxiliares de geração de assets (não vão para o ar)
```

Deploy pela **Vercel**, projeto `lp-odisys`, team `danilodsjs-projects`, plano **Hobby**.

## Ambientes

| Branch    | Ambiente Vercel | Domínio                              | Indexável | `RegEx - environment` (GTM) |
|-----------|-----------------|--------------------------------------|-----------|-----------------------------|
| `main`    | Production      | `odisys.com.br`, `www.odisys.com.br` | **Sim**   | `production`               |
| `staging` | Preview         | `lpstaging.odisys.com.br`            | Não       | `staging`                  |
| outras    | Preview         | `*-danilodsjs-projects.vercel.app`   | Não       | `staging`                  |

`lpstaging.odisys.com.br` é um **preview deployment** com domínio customizado atribuído à branch
`staging` (Vercel → Settings → Domains → Git Branch). Ele fica atrás da **Vercel Authentication**:
só quem está logado na conta Vercel acessa. Para mostrar a terceiros, use o link compartilhável
da página do deployment.

## Fluxo de trabalho

```
feature branch  →  PR para `staging`  →  validar em lpstaging.odisys.com.br  →  PR para `main`
```

Nunca commite direto em `main`. Nada vai para produção sem ter passado pelo staging.

## Regras ao editar

1. **URLs absolutas sempre apontam para produção.** Canonical, `og:url`, `og:image`,
   `twitter:image` e o JSON-LD no `index.html`, mais o `sitemap.xml`, usam
   `https://odisys.com.br` — **inclusive na branch `staging`**. Não troque por URL de staging:
   quem impede a indexação do staging é o header `X-Robots-Tag` do `vercel.json`, não a canonical.

2. **Dois arquivos de robots, propósitos diferentes.** `robots.txt` é o de produção (`Allow: /`);
   `robots.staging.txt` é o de staging (`Disallow: /`). Editar um não implica editar o outro.

3. **`vercel.json` é idêntico em todas as branches.** As regras específicas de staging são
   condicionadas por host:

   ```json
   "has": [{ "type": "host", "value": "lpstaging.odisys.com.br" }]
   ```

   Isso mantém o arquivo igual em `main` e `staging`, então merges entre elas nunca conflitam nem
   vazam regra de um ambiente para o outro. Ao adicionar uma regra nova, decida explicitamente se
   ela vale para os dois ambientes (sem `has`) ou só para o staging (com `has`).

4. **GTM: a lógica de ambiente mora no GTM, não no código.** O container `GTM-TQBQ5R4G` e a
   propriedade GA4 `G-FYRYEM4QCM` servem **esta LP e o app** (`app.odisys.com.br`, repo
   `saas-carrossel`), nos dois ambientes. Quem classifica o ambiente é a variável
   `RegEx - environment` no GTM, a partir do `Page Hostname`:

   | Host | Ambiente |
   |---|---|
   | `odisys.com.br`, `www.odisys.com.br` | produção (LP) |
   | `app.odisys.com.br` | produção (app) |
   | `lpstaging.odisys.com.br` | staging (LP) |
   | `staging.odisys.com.br` | staging (app) |
   | `*.vercel.app` | staging (previews dos dois projetos) |
   | `localhost`, `127.0.0.1` | staging (dev) |

   A tabela enumera só os hosts **não-produtivos**; o valor padrão é `production`. Essa direção é
   deliberada: esquecer um host de produção faria o GA4 descartar tráfego real de forma silenciosa
   e permanente, enquanto esquecer um host de staging apenas suja o relatório — visível e
   reversível. Um domínio de produção novo não exige nada; um host de staging que não termine em
   `staging.odisys.com.br` nem em `.vercel.app` precisa de uma linha nova na tabela do GTM.

   **Não reintroduza um push de `environment` no dataLayer.** A LP já teve esse bloco e ele foi
   removido: com dois projetos publicando no mesmo container, uma segunda fonte de verdade volta a
   permitir mapas divergentes entre os repositórios — que foi exatamente o bug que motivou a
   mudança (o regex da LP não conhecia `app.odisys.com.br`). O hostname é a única fonte.

   A jusante disso, no GTM: `Lookup - traffic_type` traduz `staging` → `internal` e **não tem valor
   padrão** (é o que impede produção de enviar `traffic_type`), e o acionador `Bloqueio - Staging`
   usa a mesma variável como exceção nas tags de conversão — o filtro do GA4 protege só o GA4,
   não o Google Ads nem a Meta. No GA4, o filtro `Internal Traffic` descarta `traffic_type =
   internal` na entrada; **ativá-lo é irreversível e não é retroativo**.

5. **Não crie Custom Environments.** `vercel deploy --target=staging` e os Custom Environments da
   Vercel são recursos Pro+; a conta é Hobby. O staging é branch + domínio, como descrito acima.

## Como verificar uma mudança

```bash
# staging protegido (deslogado) → 401 da Vercel Authentication
curl -sI https://lpstaging.odisys.com.br | head -1

# produção NÃO pode ter noindex nem o robots de staging
curl -sI https://odisys.com.br | grep -i x-robots-tag   # não deve retornar nada
curl -s  https://odisys.com.br/robots.txt | head -5     # deve continuar com "Allow: /"
```

No navegador, logado em `https://lpstaging.odisys.com.br`:

- DevTools → Network → documento: header `x-robots-tag: noindex, nofollow`
- `https://lpstaging.odisys.com.br/robots.txt` mostra `Disallow: /`
Para o ambiente visto pelo GTM, use o Preview do Tag Assistant e olhe a aba **Variáveis**:
`RegEx - environment` deve dar `staging` nos hosts de staging e `production` em
`odisys.com.br`/`www.odisys.com.br` e `app.odisys.com.br`, com `Lookup - traffic_type` em
`undefined` nesses três.

## Fora do repositório

Domínio, DNS, Vercel Authentication e a configuração do container GTM são feitos nos painéis da
Vercel e do Google Tag Manager. Nenhum commit altera essas configurações — se algo ali precisa
mudar, avise em vez de tentar resolver no código.
