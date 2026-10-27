# Máquina de Vídeos

Fluxo que garimpa Shorts virais do nicho (marketing, tecnologia/IA, produção de conteúdo), escolhe os melhores e produz **vídeos curtos verticais originais** com motion design e narração da ElevenLabs, depois agenda no YouTube, no Instagram (Reels) e no TikTok (rascunho).

```
garimpar → transcrever → TRIAGEM (Claude) → pauta → APROVAÇÃO (usuário) → ROTEIRO (Claude) → validar/previa → produzir → REVISÃO (Claude) → publicar
```

## Regras de ouro

1. **Nunca escreva Python avulso para uma etapa.** Tudo passa por `python mv.py <comando>`. Se faltar algo, melhore o módulo certo em `maquina/` (e mantenha o comando funcionando para as próximas vezes), não crie um script solto.
2. **O Claude só escreve JSON**: `analise.json` (triagem) e `roteiro.json` (roteiro). O resto é código determinístico.
3. **Cenas são modelos fixos.** O roteiro escolhe o tipo e preenche os dados; não se desenha animação do zero. Catálogo atual: `python mv.py cenas`. Cena nova = nova classe em `maquina/render/cenas.py`.
4. **Créditos:** a narração é cobrada a cada geração. Sempre `validar` e `previa` antes de `produzir`. Nunca use `--refazer-narracao` sem o usuário pedir.
5. **Texto fiel, visual próprio** (decisão do usuário). A narração reproduz o texto do vídeo original: se for em português, igual; se for em outro idioma, tradução fiel para PT-BR natural, frase por frase, sem resumir, reordenar nem acrescentar ideias. Só o CTA final do criador original é trocado pelo nosso (`marca.cta_padrao`). O visual é nosso, com outra pegada e não um clone, mas pode reaproveitar prints do original (fotos, telas, produtos, logotipos da marca citada) via `python mv.py frames nº`. A descrição sempre credita o vídeo e o canal originais (`creditos` no roteiro.json). Risco conhecido e aceito pelo usuário: denúncia por direitos autorais ou conteúdo reutilizado.
6. **Fatos checados.** Os fatos do original são conferidos na fonte primária. Como o texto é fiel, um fato errado ou não confirmado não é reescrito por conta própria: avise o usuário e só ajuste a frase se ele concordar. As fontes vão em `roteiro.json > fontes_checadas`.
9. **Cada vídeo com cara própria.** Escolha o fundo (`visual.fundo`), combine cenas com imagem (`foto`, `fotos`, `manchete`) e cenas de texto, e não repita a mesma sequência de tipos do vídeo anterior.
7. **Aprovação humana** na pauta (sempre) e no roteiro (até o usuário dizer que pode seguir direto).
8. Comandos que demoram (garimpo via yt-dlp, render em lote) rodam em background.

## Comandos (`python mv.py -h`)

| Etapa | Comando | O que faz |
|---|---|---|
| Ambiente | `checar` | Ferramentas, fontes e conexões |
| 1 | `garimpar [--fonte api\|ytdlp] [--dias N]` | Busca Shorts recentes do nicho, filtra e calcula a nota 0–100 |
| 2 | `transcrever [--top N] [nº ...]` | Baixa a transcrição dos melhores candidatos |
| 3 | `pendentes triagem` | Lista (JSON) o que o Claude precisa triar → skill **triagem** |
| 4 | `pauta` | Registra as triagens e gera `pautas/AAAA-MM-DD.md` |
| 5 | `aprovar nº ...` / `descartar nº ...` | Decisão do usuário |
| 6 | `pendentes roteiro` | Aprovados sem roteiro → skill **roteiro** |
| 6b | `frames nº [--intervalo 1]` | Baixa o vídeo original e extrai quadros em `frames/`, com índice `frames/indice.jpg` (miniaturas com o tempo de cada quadro) |
| 7 | `validar nº` · `previa nº [--video]` | Checa schema, duração e layout; prévia sem gastar créditos |
| 8 | `produzir nº [--provedor google\|elevenlabs]` | Narração + render + `qa.png` + cópia em `saida/` → skill **producao**. Provedor padrão: `narracao.provedor` no config |
| 9 | `publicar nº [--quando "AAAA-MM-DD HH:MM"] [--agora] [--redes youtube,instagram,tiktok]` | Agenda no próximo horário livre nas redes de `publicacao.redes`. YouTube: envia já, com agendamento nativo. Instagram e TikTok: as APIs não agendam, então ficam na fila e saem na hora pelo `despachar`. Rede que deu erro: rode de novo com `--redes <rede>` |
| 9b | `despachar` | Publica o que chegou na hora: Reel no Instagram; no TikTok manda para os **rascunhos** do app e grava a legenda em `saida/<vídeo>.tiktok.txt` (você abre a notificação, cola e publica). Roda a cada 5 min pela tarefa `rotinas/despachar.ps1` |
| — | `conectar youtube\|instagram\|tiktok` · `agenda` | Autoriza a rede uma vez e mostra a conta · lista publicações agendadas, com erro ou a sair |
| — | `status [etapa]` | Contagem por etapa ou lista de uma etapa |
| — | `exportar` · `limpar` | Gera `painel/videos.json` para o painel online · descarta candidatos em idiomas fora do nicho |
| Voz | `vozes` · `usar-voz <nome>` | Amostras de todas as vozes pt-BR do Google em `vozes/index.html`; grava a escolhida como padrão. Vozes Chirp 3 HD (mais naturais) são geradas cena a cena: troca de cena exata, legenda com tempo estimado |

`nº` é o número da pauta (também aceita o ID do YouTube).

## Identidade visual

Estilo fixo de todos os vídeos: **colagem retrô tátil** (`video.estilo: colagem`, código em `maquina/render/colagem.py`).
- **Base:** papel envelhecido (tons de pedra quente, sépia), manchas, fibras, vinheta, granulado de filme em todo o quadro; pontos de meio-tom nos cantos; faixa de papel kraft rasgado na base (área da interface do Shorts).
- **Elementos:** tudo é recorte de papel com borda branca irregular e sombra suave de camada: títulos em palavras recortadas (letras de revista), etiquetas, bandeiras, pílulas, carimbos, fichas datilografadas, nota rasgada, fita zebrada de alerta. Texto nunca solto: sempre dentro de um recorte.
- **Marca Odisys por cima da colagem** (guia em `assets/odisys/`, de github.com/danilodsj/idvisual-odisys): a colagem continua sendo o estilo; a Odisys entra na paleta, nas fontes e na assinatura. Do guia da Odisys, ignoramos de propósito "sem grão" e "uma cor só", porque o Vox Style manda.
- **Tipografia:** Manrope ExtraBold (títulos e botões, marca Odisys), IBM Plex Mono (etiquetas datilografadas, legenda, chips e eyebrows em CAIXA ALTA). Escrita à mão (Segoe Print) em polaroids; Bodoni e Old English só no recorte de jornal. Linha de base irregular e tinta levemente falhada. Fontes em `assets/fontes/`.
- **Cores:** neutros de papel + violeta Odisys `#7C5CF8` (`menta`, destaque principal), violeta profundo `#4A25D6` (`violeta`), violeta claro `#A78BFF` (`magenta`, só sobre fundo escuro), mostarda como marca-texto (`ambar`), carmim para negativo/alerta (`vermelho`), tinta `#0C0C0F`.
- **Assinatura:** isotipo Odisys em gradiente no canto superior direito (`marca.logo`), botão de CTA com o gradiente da marca (135°, `#4A25D6 → #7C5CF8 → #A78BFF`). O gradiente nunca vai em texto. Fundo `grafite` = o escuro nativo da Odisys.
- **Movimento:** stop-motion a 12 fps, leve tremor e balanço rotacional; entradas como cartões deslizando ou "pulando" na mesa; cortes secos entre cenas.
- **Evitar:** degradês corporativos, vetor brilhante, 3D realista, flat minimalista.
- Teste visual de todas as cenas: `python mv.py previa modelos/roteiro_todas_cenas.json --video`.
- Estilos anteriores ainda disponíveis: `cidade_noturna`, `liso`.

## Painel online (Radar de Shorts)

Artefato: https://claude.ai/artifact/5wcCCE2sLEkgZTbxWxizmZ (tipo Dashboard). Lê `painel/videos.json`, que é uma exportação do banco local.
**Atualize sempre que o banco mudar** (depois de `garimpar`, `pauta`, `aprovar`/`descartar`, `produzir`, `publicar` ou `limpar`):
1. `python mv.py exportar`
2. Artifact `publish` com `url` do painel, `file_path` = `painel/videos.json`, `asset: true` → anote o novo `/_blob/<id>`.
3. ArtifactData `update` em `datasets/videos`: `source.url` novo, `source.name` "videos.json", `updated: {at: <agora ISO>, by: "Claude (python mv.py exportar)"}` (leia o documento antes para pegar a `version`). Depois apague o arquivo anterior com Artifact `delete` (`path` = id antigo).
A página em si fica em `painel/index.html` (documento `files/index.html` do painel); só reescreva se o usuário pedir mudança visual.

## Etapas (status no banco)

`candidato → transcrito → triado → aprovado → roteirizado → produzido → publicado`
Fora da linha: `descartado`, `sem_legenda`, `erro` (mensagem em `status erro`).

Arquivos de cada vídeo ficam em `<dados>/videos/<id>/`: `meta.json`, `transcricao.txt`, `analise.json`, `roteiro.json`, `previa.png`, `narracao.mp3`, `narracao.json`, `final.mp4`, `qa.png`.
`<dados>` = `caminhos.dados` no config (fora do OneDrive). Finais copiados para `saida/`.

## Formatos que o Claude escreve

**analise.json** (triagem):
```json
{
  "relevante": true,
  "viavel_motion": true,
  "nota_conteudo": 8,
  "fala_central": "a ideia que gerou o engajamento, em uma frase",
  "por_que_viralizou": "gancho, tensão, utilidade, polêmica...",
  "angulo": "como NÓS vamos tratar o tema de forma original",
  "gancho_sugerido": "primeira frase do nosso vídeo",
  "fatos_a_checar": ["afirmação 1", "afirmação 2"]
}
```
`relevante` = está no nicho. `viavel_motion` = a ideia funciona só com narração + animação (descarte o que depende de rosto, humor visual, demonstração física ou trend de áudio). `nota_conteudo` 0–10 = força e utilidade da ideia.

**roteiro.json**: modelo completo em `modelos/roteiro_exemplo.json`.
- `titulo` (≤ 100 caracteres, palavra-chave no começo), `descricao`, `hashtags`, `referencia` (URL original), `creditos` (ex.: "Vídeo original: Ben On Brands"), `fontes_checadas`, `cenas`.
- `modo: "fiel"`: a soma das falas é o texto original (traduzido, se preciso); a duração acompanha o original.
- `visual: {"fundo": "papel" | "kraft" | "quadro" | "papelao" | "grafite"}`: a base do vídeo.
- Imagens nas cenas: caminho relativo à pasta do vídeo (ex.: `frames/f_0012.jpg`), com `recorte` opcional `[x0, y0, x1, y1]` em frações (0–1) para cortar o print.
- Cada cena: `tipo` (do catálogo), `fala` (o que a voz diz), `dados` (o que aparece na tela).
- A tela **resume** a fala, não repete. `*palavra*` = destaque em cor. Marcações de tom na fala: `[animado]`, `[sério]`, `[sussurrando]`.
- 4–10 cenas, termina com `cta`. Fora do modo fiel: 25–45 s (≈ 65–115 palavras), começando com `gancho`/`palavra`/`numero`.
- Números por extenso na fala ("cinco vezes"), em algarismos na tela ("5x").

## Conexões

| Conexão | Para quê | Como configurar |
|---|---|---|
| `YOUTUBE_API_KEY` (opcional) | Garimpo rápido e barato | Google Cloud → ativar *YouTube Data API v3* → Credenciais → Chave de API → colar no `.env` |
| `ELEVENLABS_API_KEY` | Narração (provedor `elevenlabs`) | elevenlabs.io → Developers → API Keys → colar no `.env` |
| `GOOGLE_API_KEY` (ou a mesma do YouTube) | Narração (provedor `google`) | Google Cloud, mesmo projeto da chave do YouTube → APIs e serviços → Biblioteca → ativar *Cloud Text-to-Speech API* (exige faturamento ativo no projeto; 1 milhão de caracteres/mês grátis em Neural2/Wavenet). Se a chave tiver restrição de API, inclua a Text-to-Speech. Sem `GOOGLE_API_KEY`, usa a `YOUTUBE_API_KEY`. |
| `credenciais/client_secret.json` | Publicar no YouTube | Google Cloud → Tela de consentimento OAuth (adicione seu e-mail como testador) → Credenciais → ID do cliente OAuth tipo *App para computador* → baixar JSON. No 1º `publicar` o navegador abre para autorizar o canal. |
| `META_APP_ID`, `META_APP_SECRET`, `INSTAGRAM_TOKEN` | Publicar Reels no Instagram | Pré-requisito: Instagram **profissional** (Empresa ou Criador) ligado a uma **Página do Facebook**. Usamos o login do Facebook porque é o único que aceita enviar o arquivo direto; o login só do Instagram exige o vídeo num link público. 1) developers.facebook.com → Criar app → tipo *Empresa*; o app pode ficar em modo desenvolvimento, com você como administrador. 2) Adicione o produto *Instagram* (opção login do Facebook) → copie ID e Chave secreta do app (Configurações → Básico) para o `.env`. 3) *Explorador da Graph API* → escolha o app → token de usuário com `instagram_basic`, `instagram_content_publish`, `pages_show_list`, `pages_read_engagement` (e `business_management` se a Página estiver num Gerenciador de Negócios) → marque a Página → copie o token para `INSTAGRAM_TOKEN`. 4) `python mv.py conectar instagram`: troca o token por um token da Página que não expira (`credenciais/instagram.json`). Limite: 100 posts/24 h. |
| `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET` | Mandar para os rascunhos do TikTok | 1) developers.tiktok.com → Manage apps → Connect an app; plataforma *Desktop*. 2) Produtos: *Login Kit* e *Content Posting API*; escopos `user.info.basic` e `video.upload` (não precisa de Direct Post). 3) Redirect URI: `http://localhost:8765/callback/` (porta em `publicacao.tiktok.porta`). 4) Use o **Sandbox** (até 10 contas suas, sem revisão do app): Sandbox settings → Target users → adicione sua conta. 5) Client key/secret do sandbox no `.env`. 6) `python mv.py conectar tiktok`: o navegador abre para autorizar; o token renova sozinho por 1 ano. Limite: 5 rascunhos pendentes por 24 h. Publicar direto pela API exige auditoria, que o TikTok não concede para uso próprio (sem ela tudo sai privado). |

Cota padrão da API do YouTube: 10.000 unidades/dia. Busca = 100, envio ≈ 1.600 (~6 envios/dia). Para mais, pedir aumento ao Google.

## Rotina diária

1. **Automático (manhã)**: `rotinas/manha.ps1` → garimpar, transcrever, triagem pelo Claude, pauta.
2. **Usuário**: lê `pautas/<hoje>.md` e aprova (`aprovar`).
3. **Claude**: para cada aprovado → skill **roteiro** → (aprovação) → skill **producao** → `publicar`.
4. **Automático (a cada 5 min)**: `rotinas/despachar.ps1` → publica no Instagram e manda para os rascunhos do TikTok o que chegou na hora. O computador precisa estar ligado no horário; se estiver desligado, sai na próxima vez que a tarefa rodar.

## Problemas comuns

- `HTTP 429` no YouTube: espere alguns minutos; o `transcrever` já espaça os pedidos.
- "Sign in to confirm you're not a bot": o modo `ytdlp` abriu vídeos demais e o YouTube pausou o IP por algumas horas. Não insista; use a `YOUTUBE_API_KEY` (o modo `api` não sofre esse bloqueio) ou reduza `garimpo.max_detalhes_ytdlp`.
- Publicação com erro no Instagram/TikTok: `python mv.py agenda` mostra a mensagem; corrija e rode `python mv.py publicar nº --redes <rede>`. "TikTok sem autorização válida" ou "Instagram não conectado": `python mv.py conectar <rede>`. `spam_risk_too_many_pending_share` no TikTok: há 5 rascunhos esperando no app; publique ou apague alguns.
- Erro de extração do yt-dlp: `pip install -U "yt-dlp[default]"`.
- `aviso ... não coube`: encurte o texto daquela cena no roteiro e rode `previa` de novo.
- ffmpeg/deno não encontrados: abra um terminal novo (PATH).
- Detalhes de qualquer erro: `<dados>/logs/AAAA-MM-DD.log`.
