# Odisys — Design System

Odisys é um SaaS de IA (B2B/B2C) que gera carrosséis de alto impacto para redes sociais. Três agentes integrados — **Estrategista**, **Copywriter** e **Diretor de Arte** — transformam um prompt em uma narrativa visual pronta para publicar.

**Público:** criadores de conteúdo, agências de marketing, gestores de tráfego, consultores e empreendedores digitais.

**Nome:** *Odi* (Odisseia — a jornada do criador, slide a slide) + *Sys* (System — a orquestração técnica por trás).

## Fontes deste sistema

- Briefing de identidade visual da Odisys (documento enviado pelo fundador, 2026).
- Referência de cor: captura da interface do produto — violeta `#7C5CF8` sobre `#0C0C0F`. **Esta referência substitui o azul/ciano descrito no briefing original.**
- `Odisys Identidade.dc.html` (neste projeto) — board de identidade onde a marca foi desenhada e aprovada.
- Não houve codebase, Figma ou deck anexado. Componentes e UI kit foram derivados do briefing + board de identidade; onde o produto real divergir, o produto vence.

## A marca

O isotipo aprovado é o **Sequência**: o "O" de Odisys desenhado como paginação de carrossel — arco maior (o percurso feito), arco menor (o próximo slide) e ponto (o destino). Loop sem recorrer ao ∞.

Construção: raio do eixo R = 34u em caixa de 100u; traço 13u (0,38R); vãos iguais à espessura; arcos de 225° / 67° / ponto; terminações `round` sempre.

Ajuste óptico: abaixo de 32px o traço engrossa (15u em 32px, 19u em 16px) e o ponto é absorvido pelo arco menor. Nunca reduza os vãos abaixo da espessura do traço.

**O que evitar:** símbolo de infinito, robô/cérebro, faíscas pastel, gradiente aplicado ao logotipo (o gradiente vive no isotipo; o texto é sólido), sombra, contorno ou rotação na assinatura.

Arquivos em `assets/logo/`.

## Content fundamentals

**Voz:** parceira e técnica. Fala como quem já publicou — objetiva, sem hype de agência. Português do Brasil, tratamento **você**, nunca "nós da Odisys".

- **Casing:** frase natural em títulos e botões (`Gerar carrossel`, não `Gerar Carrossel`). CAIXA ALTA apenas em eyebrows e metadados, sempre com `--tracking-eyebrow`/`--tracking-label`.
- **Verbos primeiro** em ações: *Gerar carrossel*, *Refazer slide*, *Publicar agora*. Nunca "Clique aqui".
- **Frases curtas, sem ponto final** em labels e microcopy. Ponto final só em parágrafos.
- **Números concretos** em vez de adjetivos: "6 slides em 40s", não "rápido demais".
- **Sem emoji.** Em nenhuma superfície do produto ou da marca.
- **Sem exclamação** salvo em confirmação de sucesso rara.
- **Estados vazios** convidam à ação e citam a jornada: *"Sua tela em branco tem prazo. Comece por um ângulo."*
- **Erros** dizem o que houve e o que fazer: *"O estrategista não respondeu. Tente de novo em alguns segundos."* Nunca culpa o usuário, nunca expõe stack.
- **Os agentes têm nome próprio** e são citados como colegas: *"O copywriter reescreveu o slide 3."*

## Visual foundations

- **Modo nativo é escuro.** `--bg-app: #0C0C0F`. O modo claro existe (`[data-theme="light"]`) mas é secundário.
- **Uma cor de marca.** Violeta `#7C5CF8`, com ramp do `#4A25D6` ao `#A78BFF`. Nenhuma segunda cor decorativa — semânticas (`--success`, `--warning`, `--danger`) só comunicam estado.
- **Um gradiente só:** `--gradient-odisys`, 135°. Vive no isotipo, no botão primário, no app icon e no slide de capa. Nunca em texto, nunca em fundo de página inteira.
- **Fundos:** chapados. Superfícies se separam por hairline (`1px solid var(--border-default)`), não por sombra. O único brilho permitido é o `--glow-violet` radial atrás do hero — sutil, ≤22% de opacidade.
- **Sem sombras projetadas na UI.** Profundidade = hairline + mudança de superfície (`--surface-1` → `--surface-2`). Sombra apenas em overlays (`--shadow-overlay`) e no CTA primário (`--shadow-accent`).
- **Raios:** 4px em chips minúsculos, 8px em inputs e botões, 12px em cards de conteúdo, 16px em painéis, 22px em app icon. Nada de pill exceto dots de paginação.
- **Tipografia:** Manrope para tudo que é marca e interface; IBM Plex Mono para metadados, hex, IDs e código. Títulos em 600 com `--tracking-tight`; eyebrows em mono 11-12px CAIXA ALTA com tracking generoso — é a assinatura tipográfica do sistema.
- **Animação:** discreta e rápida. `--dur-fast` em hover, `--dur-base` em entrada, `--ease-enter` para aparecer, `--ease-standard` para mover. Sem bounce, sem spring. O único loop é o isotipo girando como spinner (`odisys-orbit`, 1400ms linear) durante geração.
- **Hover:** clareia (violeta sobe um degrau; superfícies ganham `--border-strong`). Nunca escurece, nunca muda escala.
- **Press:** escurece um degrau (`--accent-press`), sem `transform`.
- **Foco:** `--ring-focus` — anel violeta de 2px afastado por 2px do fundo. Sempre visível, nunca `outline: none` sem substituto.
- **Transparência e blur:** só em overlays de modal (`rgba(8,8,10,.72)` + `blur(8px)`) e na barra fixa do editor. Em nenhum card.
- **Imagens:** frias, alto contraste, com dominante violeta. Sem grão, sem foto stock sorridente. A maior parte da superfície é tipografia sobre chapado — o produto gera as imagens, o sistema não as decora.
- **Layout:** canvas de 1440px, padding lateral de 100px em páginas de marca e 26px em telas de app. Seções separadas por 88px com um hairline + eyebrow numerada (01, 02, 03…).
- **Cards:** `--surface-1`, hairline, raio 16px, padding 34px, sem sombra. No hover de card clicável a borda vira `--border-strong`.

## Iconography

- **Não existe icon font ou sprite proprietário.** O sistema usa **Lucide** (`lucide-static` via CDN), stroke 1.5–2px, cantos arredondados — casa com as terminações `round` do isotipo. **Isto é uma substituição:** se a Odisys já usa outro set no produto, troque e me avise.
- Ícones herdam `currentColor` e nunca são coloridos com o gradiente.
- Tamanhos: 14px inline em labels, 16px em botões, 20px em navegação, 24px em estados vazios.
- **Sem emoji** como ícone, em nenhuma hipótese. Sem caracteres unicode decorativos (▲, ✦, →) fora de setas funcionais.
- O isotipo **não é um ícone**: não use dentro de botões nem em listas. Ele aparece no header, no favicon, no avatar e como spinner.

## Intentional additions

Nenhuma fonte definia um inventário de componentes, então o conjunto padrão foi autorado a partir do briefing e do board: Button, IconButton, Input, Textarea, Select, Checkbox, Switch, Card, Badge, Tag, Tabs, Dialog, Tooltip, Logo, SlideCard, AgentPill.
`Logo`, `SlideCard` e `AgentPill` são específicos da Odisys — a marca e o objeto central do produto (o slide) precisavam de primitivas próprias.

## Index

- `styles.css` — ponto de entrada; importa tudo em `tokens/`.
- `tokens/` — `fonts`, `colors`, `typography`, `spacing`, `shape`, `motion`.
- `assets/logo/` — isotipo (gradiente, sólido, branco, preto, currentColor), lockups horizontal e vertical, app icon.
- `assets/logo/favicon.svg` + `assets/logo/favicon/` — set completo de favicon (16/32/48 PNG transparente, apple-touch 180, PWA 192/512/1024, `app-icon.svg`, `favicon-mono.svg`) e `README.md` com o snippet de `<head>`. Manifest em `site.webmanifest` na raiz.
- `guidelines/` — cards de especificação (cores, tipografia, espaçamento, marca, movimento).
- `components/brand/` — Logo, AgentPill, SlideCard.
- `components/core/` — Button, IconButton, Card, Badge, Tag.
- `components/forms/` — Input, Textarea, Select, Checkbox, Switch.
- `components/overlay/` — Dialog, Tooltip, Tabs.
- `ui_kits/odisys-app/` — recriação clicável do produto (login → prompt → editor de carrossel → biblioteca).
- `SKILL.md` — wrapper para uso como Agent Skill.
