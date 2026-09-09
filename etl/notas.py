"""Consolidacao: transforma dados crus em eixos ideologicos e notas 0-100.

Decisoes que valem ser explicitas (estao todas visiveis na interface):

* O vetor ideologico vem de 4 sinais com pesos diferentes. Votacao nominal
  pesa mais porque e ato praticado, nao discurso.
* A posicao media do PARTIDO nao e curada por ninguem: e calculada como a
  media dos proprios membros. Serve de apoio para quem tem poucos votos
  classificados.
* "Uso da cota" e comparativo (percentil entre pares), nao juizo moral:
  gastar pouco nao e virtude automatica, e sinal a ser olhado.
"""

from __future__ import annotations

from collections import defaultdict

from .temas import EIXOS, derivar_geral
from .util import percentil

PESOS_SINAL = {
    "espectro": 0.50,   # como votou, medido contra bancadas-ancora
    "frentes": 0.22,    # bancadas que assinou
    "autorias": 0.10,   # ementas dos projetos proprios
    "votos_tema": 0.08,  # votos em propostas com tema e direcao explicitos
    "partido": 0.10,    # media empirica do partido (nao curada)
}


def _media_ponderada(pares: list[tuple[float, float]]) -> float | None:
    soma = sum(v * p for v, p in pares)
    peso = sum(p for _, p in pares)
    return soma / peso if peso else None


def posicao_dos_partidos(pessoas: list[dict]) -> dict[str, dict]:
    """Media empirica por partido, a partir do comportamento dos proprios membros."""
    acum = defaultdict(lambda: defaultdict(list))
    for p in pessoas:
        for eixo, v in (p.get("_eixos_espectro") or {}).items():
            acum[p.get("partido") or "?"][eixo].append(v)
    saida = {}
    for partido, eixos in acum.items():
        saida[partido] = {e: round(sum(vs) / len(vs), 3)
                          for e, vs in eixos.items() if len(vs) >= 3}
    return saida


def _referencia_por_casa(pessoas: list[dict]) -> dict[str, dict]:
    """Quanta evidencia EXISTE em cada casa legislativa.

    O Senado faz muito menos votacao nominal que a Camara e nao publica frentes
    parlamentares. Se a confianca fosse medida na mesma regua, todo senador
    ficaria com confianca baixa e - por causa do encolhimento da afinidade -
    seria injustamente rebaixado no ranking. A regua e por casa: mede o quanto
    temos DAQUELA pessoa em relacao ao maximo disponivel entre os colegas dela.
    """
    ref: dict[str, dict] = {}
    for casa in {p["casa"] for p in pessoas}:
        grupo = [p for p in pessoas if p["casa"] == casa]
        ref[casa] = {
            "max_votos": max((max((p.get("_espectro_n") or {}).values(), default=0)
                              for p in grupo), default=0),
            "tem_frentes": any(p.get("_n_frentes_uteis") for p in grupo),
        }
    return ref


def consolidar_eixos(pessoas: list[dict]) -> dict[str, dict]:
    partidos = posicao_dos_partidos(pessoas)
    referencia = _referencia_por_casa(pessoas)
    for p in pessoas:
        espectro = p.get("_eixos_espectro") or {}
        votos_tema = p.get("_eixos_votos") or {}
        frentes = p.get("_eixos_frentes") or {}
        autorias = p.get("_eixos_autorias") or {}
        prior = partidos.get(p.get("partido") or "?", {})

        # frentes acumulam soma bruta; normaliza para -1..1
        maior_frente = max((abs(v) for v in frentes.values()), default=0.0)
        frentes_norm = {e: v / maior_frente for e, v in frentes.items()} if maior_frente else {}

        # o eixo geral nao existe nas frentes/autorias: derivamos dos tematicos
        for fonte in (frentes_norm, autorias):
            if fonte and "geral" not in fonte:
                g = derivar_geral(fonte)
                if g is not None:
                    fonte["geral"] = g

        final = {}
        for eixo in EIXOS:
            pares = []
            if eixo in espectro:
                pares.append((espectro[eixo], PESOS_SINAL["espectro"]))
            if eixo in frentes_norm:
                pares.append((frentes_norm[eixo], PESOS_SINAL["frentes"]))
            if eixo in autorias:
                pares.append((autorias[eixo], PESOS_SINAL["autorias"]))
            if eixo in votos_tema:
                pares.append((votos_tema[eixo], PESOS_SINAL["votos_tema"]))
            if eixo in prior:
                pares.append((prior[eixo], PESOS_SINAL["partido"]))
            m = _media_ponderada(pares)
            if m is not None:
                final[eixo] = round(max(-1.0, min(1.0, m)), 3)

        p["eixos"] = final
        # Confianca: quanto da evidencia disponivel na casa temos desta pessoa.
        n_esp = max((p.get("_espectro_n") or {}).values(), default=0)
        n_frentes = p.get("_n_frentes_uteis", 0)
        ref = referencia[p["casa"]]
        # 60% do maximo da casa ja e considerado historico completo
        base = ref["max_votos"] * 0.6
        parte_votos = min(1.0, n_esp / base) if base else 0.0
        if ref["tem_frentes"]:
            confianca = parte_votos * 0.7 + min(n_frentes, 4) / 4 * 0.3
        else:
            confianca = parte_votos
        p["confianca_eixos"] = round(min(1.0, confianca), 2)
        p["_espectro_votos"] = n_esp
    return partidos


def _nota_percentil(pessoas: list[dict], campo: str, invertido: bool = False) -> None:
    valores = [p[campo] for p in pessoas if isinstance(p.get(campo), (int, float))]
    if not valores:
        for p in pessoas:
            p[f"pct_{campo}"] = None
        return
    tabela = percentil(valores)
    for p in pessoas:
        v = p.get(campo)
        if not isinstance(v, (int, float)):
            p[f"pct_{campo}"] = None
        else:
            q = tabela[v]
            p[f"pct_{campo}"] = round(100 * (1 - q if invertido else q), 1)


def calcular_notas(pessoas: list[dict]) -> None:
    for p in pessoas:
        p["_producao"] = (p.get("_autorias") or 0) + 5 * (p.get("_autorias_aprovadas") or 0)

    # comparacoes justas acontecem dentro da mesma casa legislativa
    for casa in ("camara", "senado"):
        grupo = [p for p in pessoas if p["casa"] == casa]
        if not grupo:
            continue
        _nota_percentil(grupo, "_producao")
        _nota_percentil(grupo, "_gasto_mensal", invertido=True)

    for p in pessoas:
        presenca = p.get("_presenca_pct")
        participacao = p.get("_participacao_pct")
        producao = p.get("pct__producao")
        economia = p.get("pct__gasto_mensal")

        sancoes = len(p.get("_sancoes") or [])
        nota_integridade = 100.0 if sancoes == 0 else max(0.0, 100.0 - 55.0 * sancoes)

        alertas = []
        if isinstance(p.get("_gasto_concentracao"), float) and p["_gasto_concentracao"] >= 0.5:
            alertas.append("Mais da metade da cota foi para um unico fornecedor")
        if isinstance(economia, (int, float)) and economia <= 10:
            alertas.append("Esta entre os que mais gastam a cota por mes")
        if isinstance(presenca, (int, float)) and presenca < 60:
            alertas.append("Presenca abaixo de 60% nas sessoes deliberativas")
        if isinstance(participacao, (int, float)) and participacao < 50:
            alertas.append("Registrou voto em menos da metade das votacoes nominais")
        if sancoes:
            alertas.append(f"{sancoes} registro(s) oficial(is) de sancao encontrados por nome")

        p["notas"] = {
            "presenca": round(presenca, 1) if isinstance(presenca, (int, float)) else None,
            "participacao": round(participacao, 1) if isinstance(participacao, (int, float)) else None,
            "producao": producao,
            "economia": economia,
            "integridade": round(nota_integridade, 1),
        }
        p["alertas"] = alertas


def limpar(pessoas: list[dict]) -> list[dict]:
    """Monta o registro publico (campos internos com _ ficam de fora)."""
    saida = []
    for p in pessoas:
        saida.append({
            "id": p["id"],
            "casa": p["casa"],
            "cargo": p["cargo"],
            "nome": p.get("nome"),
            "nome_civil": p.get("nome_civil"),
            "partido": p.get("partido"),
            "uf": p.get("uf"),
            "foto": p.get("foto"),
            "nascimento": p.get("nascimento"),
            "site": p.get("site"),
            "redes": p.get("redes") or [],
            "url_fonte": p.get("url_fonte"),
            "eixos": p.get("eixos") or {},
            "confianca_eixos": p.get("confianca_eixos", 0),
            "notas": p["notas"],
            "alertas": p.get("alertas") or [],
            "metricas": {
                "presenca_pct": p.get("_presenca_pct"),
                "sessoes_presente": p.get("_sessoes_presente"),
                "sessoes_total": p.get("_sessoes_total"),
                "participacao_pct": p.get("_participacao_pct"),
                "votos_plenario": p.get("_votos_plenario"),
                "votos_plenario_total": p.get("_votos_plenario_total"),
                "autorias": p.get("_autorias"),
                "autorias_aprovadas": p.get("_autorias_aprovadas"),
                "gasto_total": p.get("_gasto_total"),
                "gasto_mensal": p.get("_gasto_mensal"),
                "gasto_meses": p.get("_gasto_meses"),
                "gasto_concentracao": p.get("_gasto_concentracao"),
                "votacoes_classificadas": p.get("_eixos_votos_n", 0),
                "espectro_votos": p.get("_espectro_votos", 0),
                "frentes_n": len(p.get("frentes") or []),
            },
            "frentes": p.get("frentes") or [],
            "gasto_categorias": p.get("_gasto_categorias") or [],
            "gasto_fornecedores": p.get("_gasto_fornecedores") or [],
            "gasto_maior": p.get("_gasto_maior"),
            "votos_exemplo": p.get("_votos_exemplo") or [],
            "autorias_exemplo": p.get("_autorias_exemplo") or [],
            "sancoes": p.get("_sancoes") or [],
            "mencoes": p.get("_mencoes") or [],
        })
    return saida
