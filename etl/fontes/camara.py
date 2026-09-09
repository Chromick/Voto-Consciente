"""Camara dos Deputados - Dados Abertos.

Estrategia: usar os ARQUIVOS COMPLETOS (CSV) em vez de milhares de chamadas na
API. Sao poucas dezenas de MB e trazem votos nominais, presenca em sessoes,
autoria de proposicoes e frentes parlamentares.

Docs: https://dadosabertos.camara.leg.br/swagger/api.html
"""

from __future__ import annotations

from collections import defaultdict

from ..temas import classificar_ementa, eixos_da_frente
from ..util import baixar_json, id_da_uri, inteiro, ler_csv_url, log, num, tentar

ARQ = "https://dadosabertos.camara.leg.br/arquivos"
API = "https://dadosabertos.camara.leg.br/api/v2"

# Como cada tipo de voto conta para o alinhamento tematico.
PESO_VOTO = {
    "sim": 1.0,
    "nao": -1.0,
    "não": -1.0,
    "obstrucao": -0.7,
    "obstrução": -0.7,
    "abstencao": 0.0,
    "abstenção": 0.0,
}


def legislatura_atual() -> int:
    dados = tentar(lambda: baixar_json(f"{API}/legislaturas?ordem=DESC&ordenarPor=id&itens=1",
                                       ttl_horas=168), "legislatura", None)
    if dados and dados.get("dados"):
        return inteiro(dados["dados"][0]["id"], 57)
    return 57


def deputados(id_legislatura: int) -> dict[str, dict]:
    """Deputados EM EXERCICIO HOJE + dados biograficos do arquivo completo.

    Sem o filtro `idLegislatura` a API devolve exatamente quem esta em exercicio
    agora (513). Passando a legislatura ela devolveria tambem suplentes que
    assumiram por poucos dias, o que polui qualquer ranking.
    """
    saida: dict[str, dict] = {}
    pagina = 1
    while True:
        url = (f"{API}/deputados?ordem=ASC&ordenarPor=nome&itens=100&pagina={pagina}")
        resp = tentar(lambda u=url: baixar_json(u, ttl_horas=12), f"deputados pag {pagina}", None)
        if not resp:
            break
        lote = resp.get("dados", [])
        if not lote:
            break
        for d in lote:
            i = str(d["id"])
            saida[i] = {
                "id": f"dep-{i}",
                "id_fonte": i,
                "casa": "camara",
                "cargo": "Deputado(a) Federal",
                "nome": d.get("nome"),
                "partido": d.get("siglaPartido"),
                "uf": d.get("siglaUf"),
                "foto": d.get("urlFoto"),
                "email": d.get("email"),
                "url_fonte": f"https://www.camara.leg.br/deputados/{i}",
            }
        if not any(l.get("rel") == "next" for l in resp.get("links", [])):
            break
        pagina += 1
    log(f"   deputados em exercicio: {len(saida)}")

    linhas = tentar(lambda: list(ler_csv_url(f"{ARQ}/deputados/csv/deputados.csv", ttl_horas=168)),
                    "deputados.csv", [])
    for l in linhas:
        i = id_da_uri(l.get("uri"))
        if i in saida:
            redes = [u.strip() for u in (l.get("urlRedeSocial") or "").split(",") if u.strip()]
            saida[i].update({
                "nome_civil": l.get("nomeCivil"),
                "sexo": l.get("siglaSexo"),
                "nascimento": l.get("dataNascimento") or None,
                "uf_nascimento": l.get("ufNascimento") or None,
                "municipio_nascimento": l.get("municipioNascimento") or None,
                "site": l.get("urlWebsite") or None,
                "redes": redes,
                "primeira_legislatura": inteiro(l.get("idLegislaturaInicial")),
            })
    return saida


def frentes(deps: dict, id_legislatura: int) -> None:
    """Bancadas informais. Sinal ideologico forte e publico."""
    linhas = tentar(lambda: ler_csv_url(f"{ARQ}/frentesDeputados/csv/frentesDeputados.csv",
                                        ttl_horas=168), "frentesDeputados.csv", [])
    por_dep = defaultdict(list)
    for l in linhas or []:
        if inteiro(l.get("deputado_.idLegislatura")) != id_legislatura:
            continue
        i = str(l.get("deputado_.id") or "")
        if i in deps:
            titulo = (l.get("titulo") or "").strip()
            if titulo:
                por_dep[i].append(titulo)
    for i, d in deps.items():
        titulos = sorted(set(por_dep.get(i, [])))
        d["frentes"] = titulos
        eixos: dict[str, float] = {}
        for t in titulos:
            for eixo, v in eixos_da_frente(t).items():
                eixos[eixo] = eixos.get(eixo, 0.0) + v
        d["_eixos_frentes"] = eixos
        d["_n_frentes_uteis"] = sum(1 for t in titulos if eixos_da_frente(t))
    log(f"   frentes mapeadas para {sum(1 for d in deps.values() if d['frentes'])} deputados")


def _catalogo_votacoes(anos: list[int]) -> dict[str, dict]:
    """idVotacao -> metadados + classificacao tematica."""
    cat: dict[str, dict] = {}
    for ano in anos:
        linhas = tentar(lambda a=ano: list(ler_csv_url(f"{ARQ}/votacoes/csv/votacoes-{a}.csv")),
                        f"votacoes-{ano}.csv", [])
        for l in linhas:
            cat[l["id"]] = {
                "id": l["id"],
                "data": l.get("data"),
                "orgao": l.get("siglaOrgao"),
                "descricao": (l.get("descricao") or "").strip(),
                "aprovacao": inteiro(l.get("aprovacao")),
                "sim": inteiro(l.get("votosSim")),
                "nao": inteiro(l.get("votosNao")),
                "ementa": "",
                "proposicao": "",
            }
        for arquivo in ("votacoesProposicoes", "votacoesObjetos"):
            linhas = tentar(
                lambda a=ano, f=arquivo: list(ler_csv_url(f"{ARQ}/{f}/csv/{f}-{a}.csv")),
                f"{arquivo}-{ano}.csv", [])
            for l in linhas:
                v = cat.get(l.get("idVotacao"))
                if not v:
                    continue
                if not v["ementa"]:
                    v["ementa"] = (l.get("proposicao_ementa") or "").strip()
                if not v["proposicao"]:
                    v["proposicao"] = (l.get("proposicao_titulo") or "").strip()

    classificadas = 0
    for v in cat.values():
        eixos, conf = classificar_ementa(f"{v['ementa']} {v['descricao']}")
        v["eixos"], v["conf"] = eixos, conf
        if conf >= 0.6:
            classificadas += 1
    log(f"   votacoes no periodo: {len(cat)} (com direcao tematica clara: {classificadas})")
    return cat


def votos(deps: dict, anos: list[int]) -> dict:
    """Participacao em votacoes nominais + matriz de votos para o espectro.

    Cuidado importante: a maioria das votacoes registradas e SIMBOLICA (nao tem
    voto individual). Se elas entrassem no denominador, todo mundo apareceria
    com 8% de participacao. So contam votacoes de plenario que efetivamente
    tiveram voto nominal registrado.
    """
    cat = _catalogo_votacoes(anos)
    plen = {i for i, v in cat.items() if v["orgao"] == "PLEN"}

    registrados = defaultdict(set)          # dep -> ids de votacoes de plenario
    plen_com_voto: set[str] = set()         # denominador honesto
    matriz: dict[str, dict[str, float]] = {}  # idVotacao -> {dep: +1/-1}
    eixos_dep = defaultdict(lambda: defaultdict(float))
    peso_dep = defaultdict(lambda: defaultdict(float))
    exemplos = defaultdict(list)

    for ano in anos:
        linhas = tentar(lambda a=ano: ler_csv_url(f"{ARQ}/votacoesVotos/csv/votacoesVotos-{a}.csv"),
                        f"votacoesVotos-{ano}.csv", [])
        n = 0
        for l in linhas or []:
            dep = str(l.get("deputado_id") or "")
            if dep not in deps:
                continue
            n += 1
            idv = l.get("idVotacao")
            sinal_bruto = PESO_VOTO.get((l.get("voto") or "").strip().lower())
            if idv in plen:
                plen_com_voto.add(idv)
                registrados[dep].add(idv)
                if sinal_bruto is not None and abs(sinal_bruto) > 0.5:
                    matriz.setdefault(idv, {})[dep] = 1.0 if sinal_bruto > 0 else -1.0
            v = cat.get(idv)
            if not v or not v["eixos"] or v["conf"] < 0.6:
                continue
            sinal = PESO_VOTO.get((l.get("voto") or "").strip().lower())
            if not sinal:
                continue
            for eixo, direcao in v["eixos"].items():
                eixos_dep[dep][eixo] += sinal * direcao * v["conf"]
                peso_dep[dep][eixo] += abs(direcao) * v["conf"]
            if len(exemplos[dep]) < 12 and abs(sinal) == 1.0:
                exemplos[dep].append({
                    "votacao": idv,
                    "data": v["data"],
                    "proposicao": v["proposicao"] or v["descricao"][:90],
                    "ementa": v["ementa"][:220],
                    "voto": (l.get("voto") or "").strip(),
                    "eixos": v["eixos"],
                })
        log(f"   votos {ano}: {n:,} registros de deputados em exercicio")

    total_plen = len(plen_com_voto)
    log(f"   votacoes nominais de plenario (denominador): {total_plen}")
    for i, d in deps.items():
        vistas = len(registrados[i])
        d["_votos_plenario"] = vistas
        d["_votos_plenario_total"] = total_plen
        d["_participacao_pct"] = round(100 * vistas / total_plen, 1) if total_plen else None
        vet, base = {}, 0
        for eixo, soma in eixos_dep[i].items():
            p = peso_dep[i][eixo]
            if p > 0:
                vet[eixo] = round(soma / p, 3)
                base += 1
        d["_eixos_votos"] = vet
        d["_eixos_votos_n"] = base
        d["_votos_exemplo"] = exemplos[i]
    return {"total_plenario": total_plen, "catalogo": len(cat), "matriz": matriz}


def presenca(deps: dict, anos: list[int]) -> None:
    """Faltas: presenca em sessoes deliberativas do plenario."""
    for i, d in deps.items():
        d.setdefault("_sessoes_presente", 0)
        d.setdefault("_sessoes_total", 0)

    presentes = defaultdict(set)
    sessoes_validas: set[str] = set()

    for ano in anos:
        eventos = tentar(lambda a=ano: list(ler_csv_url(f"{ARQ}/eventos/csv/eventos-{a}.csv")),
                         f"eventos-{ano}.csv", [])
        # "Sessao Deliberativa" = plenario (o que conta como falta).
        # "Reuniao Deliberativa" = comissao, e cada deputado so integra algumas,
        # por isso nao pode entrar no denominador.
        validos = {str(e.get("id")) for e in eventos
                   if (e.get("descricaoTipo") or "").strip().lower().startswith("sessão delibera")
                   or (e.get("descricaoTipo") or "").strip().lower().startswith("sessao delibera")}
        sessoes_validas |= validos

        linhas = tentar(
            lambda a=ano: ler_csv_url(f"{ARQ}/eventosPresencaDeputados/csv/eventosPresencaDeputados-{a}.csv"),
            f"eventosPresencaDeputados-{ano}.csv", [])
        for l in linhas or []:
            ev = str(l.get("idEvento") or "")
            dep = str(l.get("idDeputado") or "")
            if ev in validos and dep in deps:
                presentes[dep].add(ev)

    total = len(sessoes_validas)
    for i, d in deps.items():
        p = len(presentes[i])
        d["_sessoes_presente"] = p
        d["_sessoes_total"] = total
        d["_presenca_pct"] = round(100 * p / total, 1) if total else None
    log(f"   sessoes deliberativas no periodo: {total}")


def autorias(deps: dict, anos: list[int]) -> None:
    """Producao legislativa: proposicoes de autoria e quantas viraram norma."""
    for d in deps.values():
        d["_autorias"] = 0
        d["_autorias_aprovadas"] = 0
        d["_autorias_exemplo"] = []
        d["_eixos_autorias"] = {}

    for ano in anos:
        props = {}
        linhas = tentar(lambda a=ano: ler_csv_url(f"{ARQ}/proposicoes/csv/proposicoes-{a}.csv"),
                        f"proposicoes-{ano}.csv", [])
        for l in linhas or []:
            tipo = (l.get("siglaTipo") or "").upper()
            if tipo not in ("PL", "PLP", "PEC", "PDL", "MPV", "PLV"):
                continue  # ignora requerimentos e afins
            props[str(l.get("id"))] = {
                "titulo": f"{tipo} {l.get('numero')}/{l.get('ano')}",
                "ementa": (l.get("ementa") or "").strip(),
                "situacao": (l.get("ultimoStatus_descricaoSituacao") or "").strip(),
            }

        autores = tentar(lambda a=ano: ler_csv_url(f"{ARQ}/proposicoesAutores/csv/proposicoesAutores-{a}.csv"),
                         f"proposicoesAutores-{ano}.csv", [])
        acumula = defaultdict(lambda: defaultdict(float))
        pesos = defaultdict(lambda: defaultdict(float))
        for l in autores or []:
            if str(l.get("proponente") or "") != "1":
                continue
            dep = str(l.get("idDeputadoAutor") or "")
            p = props.get(str(l.get("idProposicao") or ""))
            if dep not in deps or not p:
                continue
            d = deps[dep]
            d["_autorias"] += 1
            virou_norma = "transformad" in p["situacao"].lower()
            if virou_norma:
                d["_autorias_aprovadas"] += 1
            if len(d["_autorias_exemplo"]) < 8:
                d["_autorias_exemplo"].append({
                    "titulo": p["titulo"], "ementa": p["ementa"][:220],
                    "situacao": p["situacao"], "virou_norma": virou_norma,
                })
            eixos, conf = classificar_ementa(p["ementa"])
            if conf >= 0.6:
                for eixo, direcao in eixos.items():
                    acumula[dep][eixo] += direcao * conf
                    pesos[dep][eixo] += abs(direcao) * conf
        for dep, eixos in acumula.items():
            atual = deps[dep]["_eixos_autorias"]
            for eixo, soma in eixos.items():
                p = pesos[dep][eixo]
                if p:
                    atual[eixo] = round((atual.get(eixo, 0.0) + soma / p) / (2 if eixo in atual else 1), 3)
        log(f"   autorias {ano}: {sum(1 for d in deps.values() if d['_autorias'])} deputados com proposicoes")
