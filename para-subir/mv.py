"""Máquina de Vídeos: linha de comando única do fluxo.

Uso: python mv.py <comando> [opções]     (python mv.py -h lista tudo)
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import traceback
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from maquina import db  # noqa: E402
from maquina.config import CFG, RAIZ, ErroConfig, env, gravar_json, ler_json, pasta_video  # noqa: E402


def _log(msg: str):
    with open(CFG["_dados"] / "logs" / f"{date.today()}.log", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%H:%M:%S} {msg}\n")


def _slug(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:50] or "video"


def _video(con, ref: str):
    v = db.obter(con, ref)
    if not v:
        sys.exit(f"Vídeo '{ref}' não encontrado. Use o nº da pauta ou o ID do YouTube (python mv.py status).")
    return v


def _roteiro_de(ref: str, con) -> tuple[dict, Path, object]:
    caminho = Path(ref)
    if caminho.suffix == ".json" and caminho.exists():
        return ler_json(caminho), caminho.parent, None
    v = _video(con, ref)
    arq = pasta_video(v["id"]) / "roteiro.json"
    if not arq.exists():
        sys.exit(f"Ainda não existe roteiro para o nº {v['n']}: {arq}")
    return ler_json(arq), arq.parent, v


# ---------------- comandos ----------------

def cmd_checar(a):
    ok = True

    def linha(nome, cond, dica=""):
        nonlocal ok
        ok &= bool(cond) or "opcional" in dica
        print(f"  [{'ok' if cond else '--'}] {nome}" + ("" if cond else f"  → {dica}"))

    print("Ambiente")
    linha("Python 3.11+", sys.version_info >= (3, 11))
    for exe in ("ffmpeg", "ffprobe", "deno"):
        linha(exe, shutil.which(exe), "instale com winget e abra um terminal novo")
    try:
        import yt_dlp
        linha(f"yt-dlp {yt_dlp.version.__version__}", True)
    except ImportError:
        linha("yt-dlp", False, "pip install -r requirements.txt")
    try:
        from maquina.render.base import _arquivo_fonte
        for peso in CFG["marca"]["fontes"]:
            linha(f"fonte {peso}: {Path(_arquivo_fonte(peso)).name}", True)
    except ErroConfig as e:
        linha("fontes", False, str(e))
    print("Conexões")
    linha("YOUTUBE_API_KEY", env("YOUTUBE_API_KEY", False), "opcional: sem ela o garimpo usa yt-dlp")
    prov = CFG["narracao"].get("provedor", "elevenlabs")
    linha("ELEVENLABS_API_KEY", env("ELEVENLABS_API_KEY", False),
          ("necessária" if prov == "elevenlabs" else "opcional") + ": narração ElevenLabs")
    linha("GOOGLE_API_KEY (ou a do YouTube)", env("GOOGLE_API_KEY", False) or env("YOUTUBE_API_KEY", False),
          ("necessária" if prov == "google" else "opcional") + ": narração Google (CLAUDE.md > Conexões)")
    print(f"  narração padrão: {prov}")
    cred = RAIZ / "credenciais"
    from maquina import publicar
    redes = CFG["publicacao"].get("redes", ["youtube"])
    for rede, dica in (("youtube", "credenciais/client_secret.json"),
                       ("instagram", "INSTAGRAM_TOKEN no .env, depois python mv.py conectar instagram"),
                       ("tiktok", "TIKTOK_CLIENT_KEY/SECRET no .env, depois python mv.py conectar tiktok")):
        linha(f"publicar no {publicar.NOMES[rede]}", publicar.conectado(rede),
              ("necessário" if rede in redes else "opcional") + f" (publicacao.redes): {dica} (CLAUDE.md > Conexões)")
    print(f"Dados em: {CFG['_dados']}")
    print("Tudo pronto." if ok else "Há itens pendentes acima.")


def cmd_garimpar(a):
    from maquina import garimpo, nota
    if a.dias:
        CFG["garimpo"]["max_idade_dias"] = a.dias
    videos = garimpo.garimpar(a.fonte)
    con = db.conectar()
    novos = 0
    for v in videos:
        v["nota"], v["nota_detalhes"] = nota.calcular(v)
        novos += db.salvar_candidato(con, v)
    _log(f"garimpo: {len(videos)} aprovados no filtro, {novos} novos")
    print(f"{len(videos)} vídeos passaram no filtro ({novos} novos).")
    for v in sorted(videos, key=lambda x: -x["nota"])[:10]:
        print(f"  {v['nota']:5.1f}  {v['views']:>10,} views  {v['titulo'][:60]}")


def cmd_transcrever(a):
    from maquina import legendas
    from maquina.garimpo import ErroBloqueio
    con = db.conectar()
    # Só estas etapas podem (re)ganhar transcrição; as outras já passaram dela.
    transcreviveis = ("candidato", "sem_legenda", "erro")
    if a.refs:
        alvos = []
        for r in a.refs:
            v = _video(con, r)
            if v["status"] in transcreviveis:
                alvos.append(v)
            else:
                print(f"  [pulado] nº {v['n']} já está em '{v['status']}'")
    else:
        n = a.top or CFG["nota"]["top_para_triagem"]
        alvos = [v for v in db.listar(con, "candidato", limite=n) if (v["nota"] or 0) >= CFG["nota"]["nota_minima"]]
    for v in alvos:
        pasta = pasta_video(v["id"])
        gravar_json(pasta / "meta.json", dict(v))
        try:
            texto = legendas.transcrever(v["url"], pasta, v["idioma"])
        except ErroBloqueio:
            # Não marca nada: os vídeos continuam na fila para a próxima tentativa.
            print("  O YouTube bloqueou temporariamente este IP. Parei aqui; tente de novo em algumas horas.")
            break
        except Exception as e:  # um vídeo com problema não para a fila
            db.mudar(con, v["id"], "erro", erro=f"transcrição: {e}")
            print(f"  [erro] nº {v['n']}: {e}")
            continue
        if texto:
            db.mudar(con, v["id"], "transcrito")
            print(f"  [ok] nº {v['n']} ({len(texto.split())} palavras) {v['titulo'][:55]}")
        else:
            db.mudar(con, v["id"], "sem_legenda")
            print(f"  [sem legenda] nº {v['n']} {v['titulo'][:55]}")


def cmd_pendentes(a):
    """Lista o que espera o Claude: triagem (transcritos) ou roteiro (aprovados)."""
    con = db.conectar()
    status = {"triagem": "transcrito", "roteiro": "aprovado"}[a.etapa]
    for v in db.listar(con, status):
        pasta = pasta_video(v["id"])
        if a.etapa == "triagem" and (pasta / "analise.json").exists():
            continue
        print(json.dumps({"n": v["n"], "id": v["id"], "titulo": v["titulo"], "nota": v["nota"],
                          "pasta": str(pasta)}, ensure_ascii=False))


def cmd_pauta(a):
    """Lê as analise.json escritas na triagem e gera a pauta do dia em pautas/."""
    con = db.conectar()
    for v in db.listar(con, "transcrito"):
        arq = pasta_video(v["id"]) / "analise.json"
        if arq.exists():
            an = ler_json(arq)
            ok = an.get("relevante") and an.get("viavel_motion")
            db.mudar(con, v["id"], "triado" if ok else "descartado")
    itens = []
    for v in db.listar(con, "triado"):
        an = ler_json(pasta_video(v["id"]) / "analise.json")
        itens.append((v, an, (v["nota"] or 0) * 0.5 + an.get("nota_conteudo", 0) * 5))
    itens.sort(key=lambda x: -x[2])
    pasta = RAIZ / "pautas"
    pasta.mkdir(exist_ok=True)
    arq = pasta / f"{date.today()}.md"
    linhas = [f"# Pauta {date.today():%d/%m/%Y}", "",
              "Aprovar: `python mv.py aprovar 12 15` · Descartar: `python mv.py descartar 13`", ""]
    for v, an, pts in itens:
        det = json.loads(v["nota_detalhes"] or "{}")
        linhas += [
            f"## nº {v['n']} · {v['titulo']}",
            f"[{v['canal']}]({v['url']}) · {v['views']:,} views · {det.get('idade_dias')} dias · "
            f"nota {v['nota']} · conteúdo {an.get('nota_conteudo')}/10 · prioridade {pts:.0f}",
            "",
            f"- **Fala central:** {an.get('fala_central', '')}",
            f"- **Por que viralizou:** {an.get('por_que_viralizou', '')}",
            f"- **Nosso ângulo:** {an.get('angulo', '')}",
            f"- **Gancho sugerido:** {an.get('gancho_sugerido', '')}",
            "",
        ]
    arq.write_text("\n".join(linhas), encoding="utf-8")
    print(f"Pauta com {len(itens)} itens: {arq}")


def _mudar_varios(refs, status):
    con = db.conectar()
    for r in refs:
        v = _video(con, r)
        db.mudar(con, v["id"], status)
        print(f"  nº {v['n']} → {status}: {v['titulo'][:60]}")


def cmd_aprovar(a):
    _mudar_varios(a.refs, "aprovado")


def cmd_descartar(a):
    _mudar_varios(a.refs, "descartado")


def cmd_cenas(a):
    from maquina.render.motor import _registro
    for tipo, cls in _registro().items():
        print(f"\n## {tipo}\n{cls.descricao}")
        for campo, desc in cls.campos.items():
            print(f"  - {campo.rstrip('*')}{' (obrigatório)' if campo.endswith('*') else ''}: {desc}")
        print(f"  exemplo: {json.dumps(cls.exemplo, ensure_ascii=False)}")


def cmd_validar(a):
    from maquina.roteiro import validar
    con = db.conectar()
    from maquina.roteiro import resolver_imagens
    roteiro, pasta, v = _roteiro_de(a.ref, con)
    erros, avisos = validar(roteiro, pasta)
    roteiro = resolver_imagens(roteiro, pasta)
    if not erros:
        # Testa o layout com tempos estimados: textos que não cabem viram avisos.
        from maquina.render.motor import montar_plano, palavras_estimadas
        avisos += montar_plano(roteiro, palavras_estimadas(roteiro["cenas"]))["avisos"]
    for e in erros:
        print(f"  ERRO  {e}")
    for w in avisos:
        print(f"  aviso {w}")
    if erros:
        sys.exit(1)
    if v is not None and v["status"] in ("aprovado", "roteirizado"):
        db.mudar(con, v["id"], "roteirizado")
    print("Roteiro válido." + (" Revise os avisos." if avisos else ""))


def cmd_previa(a):
    from maquina.render.motor import folha_contato, montar_plano, palavras_estimadas, renderizar
    con = db.conectar()
    from maquina.roteiro import resolver_imagens
    roteiro, pasta, _ = _roteiro_de(a.ref, con)
    roteiro = resolver_imagens(roteiro, pasta)
    plano = montar_plano(roteiro, palavras_estimadas(roteiro["cenas"]))
    for w in plano["avisos"]:
        print(f"  aviso {w}")
    png = folha_contato(plano, pasta / "previa.png")
    print(f"Prévia: {png}")
    if a.video:
        mp4 = renderizar(plano, pasta / "previa.mp4")
        print(f"Vídeo sem som: {mp4} ({plano['duracao']:.1f}s)")


def cmd_produzir(a):
    from maquina import narracao
    from maquina.render.motor import folha_contato, montar_plano, palavras_do_alinhamento, renderizar
    from maquina.roteiro import resolver_imagens, validar
    con = db.conectar()
    v = _video(con, a.ref)
    publicado = v["status"] == "publicado"
    if publicado and not a.forcar:
        sys.exit(f"nº {v['n']} já foi publicado (https://youtu.be/{v['youtube_publicado']}). "
                 "Use --forcar para gerar uma nova versão local; ela não volta para a fila de publicação.")
    pasta = pasta_video(v["id"])
    roteiro = ler_json(pasta / "roteiro.json")
    erros, _ = validar(roteiro, pasta)
    if erros:
        sys.exit("Roteiro com erros. Rode: python mv.py validar " + str(v["n"]))
    mp3, al = pasta / "narracao.mp3", pasta / "narracao.json"
    provedor = a.provedor or CFG["narracao"].get("provedor", "elevenlabs")
    anterior = ler_json(al).get("provedor", "elevenlabs") if al.exists() else None
    if a.refazer_narracao or not mp3.exists() or (a.provedor and a.provedor != anterior):
        print(f"Gerando narração ({provedor})...")
        print(f"  ok, {narracao.narrar(roteiro, mp3, al, provedor)}")
    else:
        print(f"Narração ({anterior}) já existe, reaproveitando (use --refazer-narracao para gerar outra).")
    dados_al = ler_json(al)
    palavras = dados_al.get("palavras") or palavras_do_alinhamento(dados_al.get("alinhamento") or {
        "characters": [], "character_start_times_seconds": [], "character_end_times_seconds": []})
    if not palavras:
        sys.exit("A narração não trouxe o tempo das palavras. Rode de novo com --refazer-narracao.")
    dur_audio = float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp3)]).strip())
    plano = montar_plano(resolver_imagens(roteiro, pasta), palavras,
                         max(dur_audio, palavras[-1]["e"]) + CFG["video"]["cauda_s"])
    for w in plano["avisos"]:
        print(f"  aviso {w}")
    print(f"Renderizando {plano['duracao']:.1f}s...")
    final = renderizar(plano, pasta / "final.mp4", mp3)
    folha_contato(plano, pasta / "qa.png")
    destino = CFG["_saida"] / f"{date.today()}_{v['n']}_{_slug(roteiro['titulo'])}.mp4"
    shutil.copy2(final, destino)
    # Um vídeo já publicado continua "publicado": a nova versão fica só no disco.
    db.mudar(con, v["id"], None if publicado else "produzido", saida=str(destino))
    _log(f"produzido nº {v['n']}: {destino.name}")
    print(f"Pronto: {destino}\nRevisão visual: {pasta / 'qa.png'}")


def cmd_publicar(a):
    from zoneinfo import ZoneInfo
    from maquina import publicar
    con = db.conectar()
    v = _video(con, a.ref)
    if v["status"] not in ("produzido", "publicado"):
        sys.exit(f"nº {v['n']} está '{v['status']}'; só vídeos produzidos podem ser publicados.")
    redes = a.redes.split(",") if a.redes else list(CFG["publicacao"].get("redes", ["youtube"]))
    if invalidas := [r for r in redes if r not in publicar.REDES]:
        sys.exit(f"Rede desconhecida: {', '.join(invalidas)}. Use: {', '.join(publicar.REDES)}.")
    feitas = db.publicacoes(con, v["id"])
    pular = {r: feitas[r]["estado"] for r in redes
             if r in feitas and feitas[r]["estado"] in ("agendado", "enviando", "enviado")}
    if "youtube" in redes and v["youtube_publicado"]:
        pular["youtube"] = "enviado"
    for r, estado in pular.items():
        print(f"  {r}: já {estado}, pulando")
    redes = [r for r in redes if r not in pular]
    if not redes:
        sys.exit(f"Nada a fazer para o nº {v['n']}.")
    if sem := [r for r in redes if not publicar.conectado(r)]:
        sys.exit(f"Sem conexão com {', '.join(sem)}: python mv.py conectar <rede> (CLAUDE.md > Conexões), "
                 f"ou escolha as redes com --redes.")
    fuso = ZoneInfo(CFG["publicacao"]["fuso"])
    agora = datetime.now(fuso)
    if a.agora:
        quando = agora
    elif a.quando:
        quando = datetime.strptime(a.quando, "%Y-%m-%d %H:%M").replace(tzinfo=fuso)
        if not v["agendado_para"]:
            ocupados = db.horarios_ocupados(con)
            if quando.isoformat(timespec="minutes") in ocupados:
                sys.exit(f"Já existe um vídeo agendado para {quando:%d/%m %H:%M}. Escolha outro horário.")
            no_dia = sum(o.startswith(quando.date().isoformat()) for o in ocupados)
            if no_dia >= CFG["publicacao"]["max_por_dia"]:
                sys.exit(f"{quando:%d/%m} já tem {no_dia} vídeos agendados (limite publicacao.max_por_dia).")
    elif v["agendado_para"]:  # já saiu em outra rede: acompanha o mesmo horário (ou agora, se já passou)
        quando = max(datetime.fromisoformat(v["agendado_para"]), agora)
    else:
        quando = publicar.proximo_horario(db.horarios_ocupados(con))
    roteiro = ler_json(pasta_video(v["id"]) / "roteiro.json")
    quando_utc = quando.astimezone(timezone.utc).isoformat(timespec="seconds")
    campos = {} if v["agendado_para"] else {"agendado_para": quando.isoformat(timespec="minutes")}
    if "youtube" in redes:
        yt = publicar.enviar(Path(v["saida"]), roteiro, quando)
        db.registrar_publicacao(con, v["id"], "youtube", quando_utc, "enviado", ref=f"https://youtu.be/{yt}")
        campos["youtube_publicado"] = yt
        _log(f"publicado nº {v['n']} → youtube {yt} em {quando}")
        print(f"YouTube: https://youtu.be/{yt} (agendado para {quando:%d/%m %H:%M})")
    outras = [r for r in redes if r != "youtube"]
    for rede in outras:
        db.registrar_publicacao(con, v["id"], rede, quando_utc, "agendado")
    db.mudar(con, v["id"], "publicado", **campos)
    if not outras:
        return
    if quando <= agora + timedelta(minutes=5):
        if _despachar(con, v["id"]):
            sys.exit(1)
    else:
        print(f"{' e '.join(publicar.NOMES[r] for r in outras)}: agendado para {quando:%d/%m %H:%M}. Sai pelo 'despachar' "
              f"(tarefa rotinas/despachar.ps1; o computador precisa estar ligado nesse horário).")


def _despachar(con, so_video: str | None = None) -> int:
    """Publica no Instagram/TikTok o que já chegou na hora. Devolve quantos deram erro."""
    from maquina import publicar
    erros = 0
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for p in db.publicacoes_vencidas(con, agora):
        if so_video and p["video_id"] != so_video:
            continue
        if not db.reservar_publicacao(con, p["video_id"], p["rede"]):
            continue  # outro despachar já pegou
        try:
            roteiro = ler_json(pasta_video(p["video_id"]) / "roteiro.json")
            ref = publicar.enviar_agora(p["rede"], Path(p["saida"]), roteiro)
        except Exception as e:
            erros += 1
            db.registrar_publicacao(con, p["video_id"], p["rede"], p["quando"], "erro", erro=str(e))
            _log(f"ERRO ao publicar nº {p['n']} no {p['rede']}: {traceback.format_exc()}")
            print(f"{publicar.NOMES[p['rede']]} nº {p['n']}: erro: {e}\n"
                  f"  (para tentar de novo: python mv.py publicar {p['n']} --redes {p['rede']})")
            continue
        db.registrar_publicacao(con, p["video_id"], p["rede"], p["quando"], "enviado", ref=ref)
        _log(f"publicado nº {p['n']} → {p['rede']} {ref}")
        if p["rede"] == "tiktok":
            print(f"TikTok nº {p['n']}: rascunho enviado. Abra a notificação no app do TikTok, cole a legenda de "
                  f"{Path(p['saida']).with_suffix('.tiktok.txt').name} e toque em Publicar.")
        else:
            print(f"{publicar.NOMES[p['rede']]} nº {p['n']}: {ref}")
    return erros


def cmd_despachar(a):
    con = db.conectar()
    if not db.publicacoes_vencidas(con, datetime.now(timezone.utc).isoformat(timespec="seconds")):
        print("Nada para publicar agora.")
        return
    if _despachar(con):
        sys.exit(1)


def cmd_conectar(a):
    if a.rede == "youtube":
        from maquina import publicar
        publicar._servico()
        print("YouTube autorizado.")
    elif a.rede == "instagram":
        from maquina import instagram
        c = instagram.credencial()
        print(f"Instagram conectado: @{c['usuario']} (Página {c['pagina']}).")
    else:
        from maquina import tiktok
        print(f"TikTok conectado: {tiktok.usuario(interativo=True)}.")


def cmd_agenda(a):
    """Publicações por rede: o que está agendado, com erro, e o que já saiu com data futura."""
    from zoneinfo import ZoneInfo
    fuso = ZoneInfo(CFG["publicacao"]["fuso"])
    linhas = db.agenda(db.conectar())
    if not linhas:
        print("Nenhuma publicação pendente.")
    for p in linhas:
        quando = datetime.fromisoformat(p["quando"]).astimezone(fuso)
        extra = p["erro"] if p["estado"] == "erro" else (p["ref"] or "")
        print(f"  {quando:%d/%m %H:%M}  nº {p['n']:<4} {p['rede']:<9} {p['estado']:<9} {extra}"[:160])


def cmd_frames(a):
    """Baixa o vídeo original (uma vez) e extrai quadros + um índice com o tempo de cada um."""
    import yt_dlp
    from PIL import Image, ImageDraw
    from maquina.render.base import fonte
    con = db.conectar()
    v = _video(con, a.ref)
    pasta = pasta_video(v["id"])
    original = pasta / "original.mp4"
    if not original.exists():
        print("Baixando o vídeo original...")
        opts = {"quiet": True, "no_warnings": True, "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080]/b",
                "merge_output_format": "mp4", "outtmpl": str(pasta / "original.%(ext)s")}
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([v["url"]])
    quadros = pasta / "frames"
    if quadros.exists():
        shutil.rmtree(quadros)
    quadros.mkdir()
    subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(original), "-vf", f"fps=1/{a.intervalo}",
                    "-q:v", "2", str(quadros / "f_%04d.jpg")], check=True)
    arquivos = sorted(quadros.glob("f_*.jpg"))
    # Índice: miniaturas com o nome do arquivo e o segundo do vídeo.
    tw, th, col = 200, 356, 6
    linhas = -(-len(arquivos) // col)
    indice = Image.new("RGB", (tw * col, (th + 34) * linhas), (30, 30, 30))
    d = ImageDraw.Draw(indice)
    f = fonte("bold", 22)
    for i, arq in enumerate(arquivos):
        im = Image.open(arq)
        im.thumbnail((tw, th))
        x, y = (i % col) * tw, (i // col) * (th + 34)
        indice.paste(im, (x + (tw - im.width) // 2, y))
        seg = i * a.intervalo
        d.text((x + 6, y + th + 4), f"{arq.name}  {int(seg // 60)}:{int(seg % 60):02d}", font=f, fill=(255, 220, 120))
    indice.save(quadros / "indice.jpg", quality=85)
    print(f"{len(arquivos)} quadros em {quadros}\nÍndice: {quadros / 'indice.jpg'}")


def cmd_limpar(a):
    """Descarta candidatos que declaram um idioma fora de nicho.idiomas (garimpos antigos)."""
    con = db.conectar()
    idiomas = CFG["nicho"]["idiomas"]
    fora = [v for v in db.listar(con, "candidato") if v["idioma"] and v["idioma"] not in idiomas]
    for v in fora:
        db.mudar(con, v["id"], "descartado", erro=f"idioma '{v['idioma']}' fora do nicho")
    print(f"{len(fora)} candidatos descartados por idioma.")


def cmd_exportar(a):
    """Gera painel/videos.json: a lista completa para o painel (artefato) do fluxo."""
    from maquina.nota import idade_dias
    con = db.conectar()
    linhas = []
    for v in db.listar(con, ordem="n"):
        det = json.loads(v["nota_detalhes"] or "{}")
        arq = pasta_video(v["id"]) / "analise.json"
        an = ler_json(arq) if arq.exists() else {}
        linhas.append({
            "n": v["n"], "titulo": v["titulo"], "canal": v["canal"], "url": v["url"],
            "publicado_em": (v["publicado_em"] or "")[:10],
            "idade_dias": round(idade_dias(v["publicado_em"]), 1) if v["publicado_em"] else None,
            "duracao_s": v["duracao_s"], "views": v["views"], "likes": v["likes"],
            "comentarios": v["comentarios"], "inscritos_canal": v["inscritos_canal"],
            "views_por_dia": det.get("views_por_dia"), "outlier": det.get("outlier"),
            "engajamento": det.get("engajamento"), "nota": v["nota"],
            "idioma": v["idioma"], "palavra_chave": v["palavra_chave"], "status": v["status"],
            "nota_conteudo": an.get("nota_conteudo"), "fala_central": an.get("fala_central"),
            "angulo": an.get("angulo"), "agendado_para": v["agendado_para"],
            "youtube_publicado": f"https://youtu.be/{v['youtube_publicado']}" if v["youtube_publicado"] else None,
            "encontrado_em": (v["encontrado_em"] or "")[:10],
        })
    pasta = RAIZ / "painel"
    pasta.mkdir(exist_ok=True)
    gravar_json(pasta / "videos.json", linhas)
    print(f"{len(linhas)} vídeos exportados: {pasta / 'videos.json'}")


AMOSTRA = ("Você ainda gasta quatro horas pra fazer um único vídeo? "
           "Com essas três ferramentas de IA, dá pra fazer em vinte minutos.")


def cmd_vozes(a):
    """Gera uma amostra de cada voz pt-BR do Google e uma página para ouvir e comparar."""
    import base64
    import html
    from maquina import narracao
    vozes = narracao.vozes_google()
    pasta = RAIZ / "vozes"
    pasta.mkdir(exist_ok=True)
    familias = {"Chirp3": "Chirp 3 HD: as mais naturais (legenda com tempo estimado)",
                "Neural2": "Neural2", "Wavenet": "Wavenet", "Standard": "Standard: robóticas"}
    blocos = {f: [] for f in familias}

    def amostra(nome: str):
        dados = narracao._sintetizar({"text": AMOSTRA}, nome)
        (pasta / f"{nome}.mp3").write_bytes(base64.b64decode(dados["audioContent"]))
        print(f"  amostra: {nome}")

    faltando = [v["name"] for v in vozes if not (pasta / f"{v['name']}.mp3").exists()]
    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(amostra, faltando))  # list() propaga o primeiro erro, se houver
    for v in vozes:
        nome = v["name"]
        familia = nome.split("-")[2]
        arq = pasta / f"{nome}.mp3"
        genero = {"MALE": "masculina", "FEMALE": "feminina"}.get(v.get("ssmlGender"), "")
        curto = nome.split("-")[-1] if familia == "Chirp3" else nome.split("-", 2)[2]
        blocos.setdefault(familia, []).append(
            f'<div class="voz"><b>{html.escape(curto)}</b> <span>{genero}</span>'
            f'<audio controls preload="none" src="{html.escape(arq.name)}"></audio>'
            f'<code>python mv.py usar-voz {html.escape(nome)}</code></div>')
    atual = CFG["narracao"]["google"]["voz"]
    corpo = "".join(f"<h2>{familias.get(f, f)}</h2>{''.join(b)}" for f, b in blocos.items() if b)
    (pasta / "index.html").write_text(f"""<!doctype html><meta charset="utf-8"><title>Vozes Google pt-BR</title>
<style>body{{font:15px system-ui;max-width:900px;margin:24px auto;padding:0 16px;background:#f4eee0;color:#26211d}}
.voz{{display:grid;grid-template-columns:150px 90px 1fr;gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid #d6c9ae}}
.voz code{{grid-column:1/-1;font-size:12px;color:#8a7e70}}span{{color:#8a7e70}}audio{{width:100%}}</style>
<h1>Vozes do Google em pt-BR</h1><p>Frase: "{html.escape(AMOSTRA)}"<br>Voz atual: <b>{html.escape(atual)}</b>.
Para trocar, rode o comando que aparece embaixo da voz.</p>{corpo}""", encoding="utf-8")
    print(f"{len(vozes)} vozes. Abra para ouvir: {pasta / 'index.html'}")


def cmd_usar_voz(a):
    """Grava a voz escolhida como padrão em config.yaml (e o provedor correspondente)."""
    arq = RAIZ / "config.yaml"
    texto = arq.read_text(encoding="utf-8")
    if a.voz.startswith("pt-") or a.voz.startswith("en-"):
        novo = re.sub(r"(\n    voz: )\S+", rf"\g<1>{a.voz}", texto, count=1)
        novo = re.sub(r"(\n  provedor: )\S+", r"\g<1>google", novo, count=1)
    else:
        novo = re.sub(r"(\n    voice_id: )\S+", rf"\g<1>{a.voz}", texto, count=1)
        novo = re.sub(r"(\n  provedor: )\S+", r"\g<1>elevenlabs", novo, count=1)
    arq.write_text(novo, encoding="utf-8")
    print(f"Voz padrão agora: {a.voz}. Para refazer a narração de um vídeo: "
          f"python mv.py produzir <nº> --refazer-narracao")


def cmd_status(a):
    con = db.conectar()
    if not a.status:
        for s in db.STATUS:
            q = con.execute("SELECT COUNT(*) FROM videos WHERE status=?", (s,)).fetchone()[0]
            if q:
                print(f"  {s:<12} {q}")
        return
    for v in db.listar(con, a.status, limite=a.limite):
        extra = f"  erro: {v['erro']}" if v["erro"] else ""
        print(f"  nº {v['n']:<4} {v['nota'] or 0:5.1f}  {v['titulo'][:60]}{extra}")


def main():
    p = argparse.ArgumentParser(prog="mv.py", description="Máquina de Vídeos: garimpo → triagem → roteiro → produção → publicação")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("checar", help="confere ferramentas, fontes e conexões")
    s = sub.add_parser("garimpar", help="busca Shorts virais do nicho e calcula a nota")
    s.add_argument("--fonte", choices=["auto", "api", "ytdlp"], default=CFG["garimpo"]["fonte"])
    s.add_argument("--dias", type=int)
    s = sub.add_parser("transcrever", help="baixa as transcrições dos melhores candidatos")
    s.add_argument("refs", nargs="*")
    s.add_argument("--top", type=int)
    s = sub.add_parser("pendentes", help="lista o que espera o Claude (JSON por linha)")
    s.add_argument("etapa", choices=["triagem", "roteiro"])
    sub.add_parser("pauta", help="registra as triagens e gera a pauta do dia")
    for nome in ("aprovar", "descartar"):
        s = sub.add_parser(nome)
        s.add_argument("refs", nargs="+")
    sub.add_parser("cenas", help="catálogo de cenas disponíveis para o roteiro")
    s = sub.add_parser("validar", help="valida o roteiro.json e o layout")
    s.add_argument("ref")
    s = sub.add_parser("previa", help="folha de prévia sem gastar narração (nº ou caminho de .json)")
    s.add_argument("ref")
    s.add_argument("--video", action="store_true", help="também gera um MP4 sem som")
    s = sub.add_parser("produzir", help="narração + render + revisão")
    s.add_argument("ref")
    s.add_argument("--refazer-narracao", action="store_true")
    s.add_argument("--provedor", choices=["elevenlabs", "google"], help="padrão: narracao.provedor do config")
    s.add_argument("--forcar", action="store_true", help="refaz um vídeo já publicado (só a cópia local)")
    s = sub.add_parser("publicar", help="agenda no YouTube, Instagram e TikTok (publicacao.redes)")
    s.add_argument("ref")
    s.add_argument("--quando", help='"AAAA-MM-DD HH:MM"; padrão: próximo horário livre')
    s.add_argument("--agora", action="store_true", help="publica já, sem esperar horário")
    s.add_argument("--redes", help="ex.: instagram,tiktok; padrão: publicacao.redes do config")
    sub.add_parser("despachar", help="publica no Instagram/TikTok o que chegou na hora (tarefa agendada)")
    s = sub.add_parser("conectar", help="autoriza uma rede uma vez e mostra a conta")
    s.add_argument("rede", choices=["youtube", "instagram", "tiktok"])
    sub.add_parser("agenda", help="publicações agendadas, com erro ou a sair, por rede")
    s = sub.add_parser("frames", help="baixa o original e extrai quadros para usar como imagem")
    s.add_argument("ref")
    s.add_argument("--intervalo", type=float, default=1.0, help="segundos entre quadros")
    sub.add_parser("limpar", help="descarta candidatos em idiomas fora do nicho")
    sub.add_parser("exportar", help="gera painel/videos.json para o painel online")
    sub.add_parser("vozes", help="gera amostras das vozes do Google e uma página para ouvir")
    s = sub.add_parser("usar-voz", help="define a voz padrão (nome do Google ou voice_id da ElevenLabs)")
    s.add_argument("voz")
    s = sub.add_parser("status")
    s.add_argument("status", nargs="?", choices=db.STATUS)
    s.add_argument("--limite", type=int, default=30)
    a = p.parse_args()
    try:
        globals()[f"cmd_{a.cmd.replace('-', '_')}"](a)
    except ErroConfig as e:
        sys.exit(f"Configuração: {e}")
    except Exception as e:
        _log(f"ERRO em {a.cmd}: {traceback.format_exc()}")
        sys.exit(f"Erro em '{a.cmd}': {e}\n(detalhes em {CFG['_dados'] / 'logs'})")


if __name__ == "__main__":
    main()
