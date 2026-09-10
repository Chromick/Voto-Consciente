"""Pipeline completo: baixa dados publicos -> gera os JSON estaticos do site.

Uso:
    python -m etl.build                      # ano corrente, Camara + Senado
    python -m etl.build --anos 2023 2026     # legislatura inteira
    python -m etl.build --casas camara       # so a Camara (mais rapido)
    python -m etl.build --noticias --limite-noticias 40
    python -m etl.build --sem-cache          # ignora o cache local

Saida em dados/: ranking.json, p/<id>.json, lexico.json, meta.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import shutil

from . import espectro, notas
from .fontes import camara, cota, integridade, senado, tse
from .temas import exportar_lexico
from .util import DADOS, RAIZ, log, salvar_json

FONTES_CREDITO = [
    {"nome": "Camara dos Deputados - Dados Abertos",
     "url": "https://dadosabertos.camara.leg.br/",
     "usado": "deputados, votos nominais, presenca em sessoes, autoria de proposicoes, frentes"},
    {"nome": "Camara dos Deputados - Cota Parlamentar (CEAP)",
     "url": "https://www.camara.leg.br/transparencia/gastos-parlamentares",
     "usado": "cada despesa reembolsada com dinheiro publico"},
    {"nome": "Senado Federal - Dados Abertos",
     "url": "https://legis.senado.leg.br/dadosabertos/",
     "usado": "senadores, votacoes nominais, licencas, autorias"},
    {"nome": "TSE - Divulgacao de Candidaturas e Contas Eleitorais",
     "url": "https://divulgacandcontas.tse.jus.br/divulga/",
     "usado": "candidaturas de 2026 em todos os cargos: situacao do registro, "
              "patrimonio declarado, ocupacao, escolaridade e coligacao"},
    {"nome": "TCU - Inabilitados",
     "url": "https://contas.tcu.gov.br/ords/f?p=1660:3",
     "usado": "sancao oficial por contas julgadas irregulares"},
    {"nome": "CGU - CEIS/CNEP (Portal da Transparencia)",
     "url": "https://portaldatransparencia.gov.br/sancoes",
     "usado": "sancoes administrativas (opcional, exige chave gratuita)"},
    {"nome": "GDELT Project",
     "url": "https://www.gdeltproject.org/",
     "usado": "mencoes em noticias (apenas informativo, nunca entra na nota)"},
]


def main() -> None:
    ap = argparse.ArgumentParser(description="Coleta dados publicos e gera os JSON do site")
    ap.add_argument("--anos", nargs="+", type=int,
                    default=[dt.date.today().year],
                    help="anos a considerar (ex: 2023 2024 2025 2026)")
    ap.add_argument("--casas", default="camara,senado")
    ap.add_argument("--noticias", action="store_true",
                    help="busca mencoes na imprensa (lento: ~5s por pessoa)")
    ap.add_argument("--limite-noticias", type=int, default=None)
    ap.add_argument("--sem-cache", action="store_true")
    args = ap.parse_args()

    if args.sem_cache:
        shutil.rmtree(RAIZ / "cache", ignore_errors=True)

    anos = sorted(set(args.anos))
    casas = {c.strip() for c in args.casas.split(",") if c.strip()}
    log(f"== Dignos | anos={anos} casas={sorted(casas)}")

    pessoas: dict[str, dict] = {}
    posicao_partidos: dict[str, dict] = {}

    if "camara" in casas:
        log("\n[1/6] Camara dos Deputados")
        leg = camara.legislatura_atual()
        deps = camara.deputados(leg)
        camara.frentes(deps, leg)
        resultado = camara.votos(deps, anos)
        camara.presenca(deps, anos)
        camara.autorias(deps, anos)
        log("   espectro ideologico a partir das votacoes nominais")
        espectro.estimar(deps, resultado.get("matriz") or {},
                         espectro.ancoras_por_frentes(deps))
        posicao_partidos = notas.posicao_dos_partidos(list(deps.values()))
        log("\n[2/6] Cota parlamentar (dinheiro publico)")
        cota.carregar(deps, anos)
        pessoas.update({d["id"]: d for d in deps.values()})

    if "senado" in casas:
        log("\n[3/6] Senado Federal")
        sens = senado.senadores()
        resultado = senado.votos(sens, anos)
        senado.licencas_e_autorias(sens, anos)
        if posicao_partidos:
            # o Senado nao publica frentes na API: ancoramos pela posicao que o
            # partido demonstrou nas votacoes da Camara
            espectro.estimar(sens, resultado.get("matriz") or {},
                             espectro.ancoras_por_partido(sens, posicao_partidos))
        pessoas.update({s["id"]: s for s in sens.values()})

    log("\n[4/6] Integridade (sancoes oficiais)")
    integridade.aplicar(pessoas, com_noticias=args.noticias,
                        limite_noticias=args.limite_noticias)

    log("\n[5/6] Consolidando eixos e notas")
    lista = list(pessoas.values())
    partidos = notas.consolidar_eixos(lista)
    notas.calcular_notas(lista)
    publico = notas.limpar(lista)
    publico.sort(key=lambda p: (p["nome"] or "").upper())

    # ranking leve (carrega rapido) + detalhe por pessoa (carrega ao clicar)
    resumo = [{
        "id": p["id"], "nome": p["nome"], "casa": p["casa"], "cargo": p["cargo"],
        "partido": p["partido"], "uf": p["uf"], "foto": p["foto"],
        "eixos": p["eixos"], "confianca_eixos": p["confianca_eixos"],
        "notas": p["notas"], "n_alertas": len(p["alertas"]),
        "n_sancoes": len(p["sancoes"]), "n_mencoes": len(p["mencoes"]),
        "metricas": {k: p["metricas"][k] for k in
                     ("presenca_pct", "participacao_pct", "autorias", "autorias_aprovadas",
                      "gasto_total", "gasto_mensal", "espectro_votos", "frentes_n")},
    } for p in publico]

    shutil.rmtree(DADOS / "p", ignore_errors=True)
    for p in publico:
        salvar_json(DADOS / "p" / f"{p['id']}.json", p, mostrar=False)
    log(f"   -> dados/p/*.json ({len(publico)} arquivos de detalhe)")

    salvar_json(DADOS / "ranking.json", {
        "gerado_em": dt.datetime.now().isoformat(timespec="seconds"),
        "anos": anos,
        "total": len(resumo),
        "partidos": partidos,
        "parlamentares": resumo,
    })
    log("\n[6/6] Cedula de 2026 (TSE)")
    resultado_tse = tse.carregar(publico)
    if resultado_tse:
        shutil.rmtree(DADOS / "cedula", ignore_errors=True)
        contagem = {}
        for chave, bloco in resultado_tse["cedula"].items():
            salvar_json(DADOS / "cedula" / f"{chave}.json", bloco, mostrar=False)
            contagem[chave] = len(bloco["candidatos"])
        salvar_json(DADOS / "cedula" / "indice.json", {
            "gerado_em": dt.datetime.now().isoformat(timespec="seconds"),
            "ano": 2026,
            "total": resultado_tse["total"],
            "com_mandato": resultado_tse["casados"],
            "cargos": tse.CARGOS_URNA,
            "vinculados": tse.VINCULADOS,
            "contagem": contagem,
        }, compacto=False)
        log(f"   -> dados/cedula/*.json ({len(contagem)} arquivos)")

    salvar_json(DADOS / "lexico.json", exportar_lexico())
    salvar_json(DADOS / "meta.json", {
        "gerado_em": dt.datetime.now().isoformat(timespec="seconds"),
        "anos": anos,
        "casas": sorted(casas),
        "total_parlamentares": len(publico),
        "com_noticias": bool(args.noticias),
        "fontes": FONTES_CREDITO,
    }, compacto=False)

    log(f"\nOK: {len(publico)} parlamentares. Rode `python servir.py` e abra http://localhost:8000")


if __name__ == "__main__":
    main()
