"""Sinais de integridade.

REGRA ETICA DO PROJETO: nunca misturar condenacao com acusacao.

  - "sancoes" = registro OFICIAL de punicao (TCU: inabilitados por contas
    irregulares; CGU: CEIS/CNEP). Isso pesa na nota.
  - "mencoes" = aparicoes em noticias/diarios oficiais junto a palavras como
    "investigacao" ou "denuncia". Isso NAO pesa na nota; entra apenas como
    link para a pessoa ler e julgar. Cita fonte sempre.

Casamento e feito por nome normalizado, o que pode gerar homonimo: por isso
todo achado carrega `confianca` e um aviso na interface.
"""

from __future__ import annotations

import os
import time
import urllib.parse
from collections import defaultdict

from ..util import baixar_json, chave_nome, log, tentar

TCU = "https://contas.tcu.gov.br/ords/condenacao/consulta/inabilitados"
CEIS = "https://api.portaldatransparencia.gov.br/api-de-dados/ceis"
CNEP = "https://api.portaldatransparencia.gov.br/api-de-dados/cnep"
GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"
QUERIDO = "https://queridodiario.ok.org.br/api/gazettes"

TERMOS_SUSPEITA = ("investigacao", "denuncia", "improbidade", "corrupcao",
                   "operacao", "indiciado", "reu", "condenado", "escandalo")


def tcu_inabilitados() -> dict[str, list[dict]]:
    """Pessoas inabilitadas pelo TCU (contas julgadas irregulares)."""
    achados: dict[str, list[dict]] = defaultdict(list)
    # API ORDS: paginacao e por offset/limit (inicio/quantidade sao ignorados e
    # devolvem so 25 registros).
    inicio, pagina, lote = 0, 0, 500
    while True:
        url = f"{TCU}?offset={inicio}&limit={lote}"
        resp = tentar(lambda u=url: baixar_json(u, ttl_horas=72), f"TCU inabilitados {inicio}", None)
        itens = (resp or {}).get("items") or []
        for it in itens:
            achados[chave_nome(it.get("nome") or "")].append({
                "fonte": "TCU - inabilitados",
                "tipo": "sancao",
                "descricao": "Inabilitado para cargo em comissao/funcao de confianca (contas irregulares)",
                "processo": it.get("processo"),
                "deliberacao": it.get("deliberacao"),
                "data": (it.get("data_acordao") or "")[:10],
                "vigencia_ate": (it.get("data_final") or "")[:10],
                "uf": it.get("uf"),
                "municipio": it.get("municipio"),
                "url": "https://contas.tcu.gov.br/ords/f?p=1660:3",
            })
        pagina += 1
        if not (resp or {}).get("hasMore") or pagina > 80:
            break
        inicio += lote
    log(f"   TCU: {sum(len(v) for v in achados.values()):,} registros de inabilitacao")
    return achados


def cgu_sancoes() -> dict[str, list[dict]]:
    """CEIS/CNEP da CGU. Precisa de chave gratuita em PORTAL_TRANSPARENCIA_KEY."""
    chave = os.environ.get("PORTAL_TRANSPARENCIA_KEY", "").strip()
    achados: dict[str, list[dict]] = defaultdict(list)
    if not chave:
        log("   CGU: sem PORTAL_TRANSPARENCIA_KEY, pulando CEIS/CNEP (opcional)")
        return achados
    for nome, base in (("CEIS", CEIS), ("CNEP", CNEP)):
        for pagina in range(1, 40):
            url = f"{base}?pagina={pagina}"
            resp = tentar(lambda u=url: baixar_json(u, {"chave-api-dados": chave}, ttl_horas=72),
                          f"{nome} pag {pagina}", None)
            if not resp:
                break
            for it in resp:
                pessoa = (it.get("sancionado") or {}).get("nome") or ""
                if not pessoa:
                    continue
                achados[chave_nome(pessoa)].append({
                    "fonte": f"CGU - {nome}",
                    "tipo": "sancao",
                    "descricao": (it.get("tipoSancao") or {}).get("descricaoResumida") or nome,
                    "data": it.get("dataInicioSancao"),
                    "url": "https://portaldatransparencia.gov.br/sancoes",
                })
            if len(resp) < 15:
                break
    log(f"   CGU: {sum(len(v) for v in achados.values()):,} registros")
    return achados


def noticias(pessoas: list[dict], limite: int | None = None) -> dict[str, list[dict]]:
    """Mencoes na imprensa (GDELT). Rate limit oficial: 1 chamada / 5s."""
    saida: dict[str, list[dict]] = {}
    alvo = pessoas[:limite] if limite else pessoas
    for n, p in enumerate(alvo, 1):
        consulta = f'"{p["nome"]}" (denuncia OR investigacao OR corrupcao) sourcelang:portuguese'
        url = (f"{GDELT}?query={urllib.parse.quote(consulta)}"
               f"&mode=artlist&maxrecords=8&format=json&timespan=24months")
        resp = tentar(lambda u=url: baixar_json(u, ttl_horas=168), f"GDELT {p['nome']}", None,
                      tentativas=2, espera=6)
        artigos = (resp or {}).get("articles") or []
        itens = []
        for a in artigos:
            titulo = a.get("title") or ""
            if not any(t in chave_nome(titulo).lower() for t in TERMOS_SUSPEITA):
                continue
            itens.append({
                "fonte": a.get("domain"),
                "tipo": "mencao",
                "titulo": titulo[:180],
                "data": (a.get("seendate") or "")[:8],
                "url": a.get("url"),
            })
        if itens:
            saida[p["id"]] = itens[:6]
        if n % 25 == 0:
            log(f"   noticias: {n}/{len(alvo)}")
        time.sleep(5.2)  # respeita o limite do GDELT
    log(f"   noticias: {len(saida)} pessoas com mencoes filtradas")
    return saida


def aplicar(deps: dict, com_noticias: bool = False, limite_noticias: int | None = None) -> None:
    sancoes = tcu_inabilitados()
    for k, v in cgu_sancoes().items():
        sancoes.setdefault(k, []).extend(v)

    for d in deps.values():
        chaves = {chave_nome(d.get("nome_civil") or ""), chave_nome(d.get("nome") or "")}
        chaves.discard("")
        encontrados = []
        for k in chaves:
            for s in sancoes.get(k, []):
                item = dict(s)
                item["confianca"] = "alta" if k == chave_nome(d.get("nome_civil") or "") else "media"
                item["aviso"] = "Casamento por nome; confirme se e a mesma pessoa."
                encontrados.append(item)
        d["_sancoes"] = encontrados
        d["_mencoes"] = []

    if com_noticias:
        pessoas = sorted(deps.values(), key=lambda d: d.get("nome") or "")
        achados = noticias(pessoas, limite_noticias)
        for d in deps.values():
            d["_mencoes"] = achados.get(d["id"], [])
