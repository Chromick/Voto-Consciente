"""Catalogo de eixos politicos, lexico de termos e classificacao tematica.

Este arquivo e a UNICA fonte de verdade sobre ideologia: o ETL o exporta para
`dados/lexico.json`, e o front-end usa o mesmo lexico para interpretar o texto
que a pessoa digita. Assim o que voce le aqui e exatamente o que o site aplica.

Convencao dos eixos: valor vai de -1 a +1.
"""

from __future__ import annotations

import re

from .util import sem_acento

EIXOS = {
    "geral": {
        "rotulo": "Espectro geral",
        "neg": "Esquerda",
        "pos": "Direita",
    },
    "economia": {
        "rotulo": "Economia",
        "neg": "Estado forte / redistribuicao",
        "pos": "Livre mercado / estado enxuto",
    },
    "costumes": {
        "rotulo": "Costumes",
        "neg": "Progressista",
        "pos": "Conservador / religioso",
    },
    "ambiente": {
        "rotulo": "Meio ambiente",
        "neg": "Produtivista / ruralista",
        "pos": "Ambientalista",
    },
    "seguranca": {
        "rotulo": "Seguranca publica",
        "neg": "Garantista / direitos humanos",
        "pos": "Punitivista / armamentista",
    },
    "trabalho": {
        "rotulo": "Trabalho",
        "neg": "Protecao sindical / CLT",
        "pos": "Flexibilizacao / empreendedorismo",
    },
    "instituicoes": {
        "rotulo": "Instituicoes",
        "neg": "Blindagem / sigilo",
        "pos": "Transparencia / controle",
    },
}

# ---------------------------------------------------------------------------
# Lexico: termo -> deslocamento nos eixos.
# Usado para (a) interpretar o texto livre do usuario e (b) classificar ementas.
# ---------------------------------------------------------------------------

LEXICO: dict[str, dict[str, float]] = {
    # --- identidades genericas -------------------------------------------------
    "conservador": {"costumes": 0.9, "seguranca": 0.5, "economia": 0.3},
    "conservadora": {"costumes": 0.9, "seguranca": 0.5, "economia": 0.3},
    "conservadorismo": {"costumes": 0.9, "seguranca": 0.5, "economia": 0.3},
    "direita": {"costumes": 0.7, "economia": 0.6, "seguranca": 0.5},
    "extrema direita": {"costumes": 0.9, "economia": 0.5, "seguranca": 0.9},
    "bolsonarista": {"costumes": 0.9, "seguranca": 0.9, "economia": 0.5, "ambiente": -0.5},
    "liberal": {"economia": 0.9, "trabalho": 0.5},
    "liberalismo": {"economia": 0.9, "trabalho": 0.5},
    "libertario": {"economia": 1.0, "trabalho": 0.6, "costumes": -0.2},
    "socialista": {"economia": -0.9, "trabalho": -0.8, "costumes": -0.4},
    "socialismo": {"economia": -0.9, "trabalho": -0.8, "costumes": -0.4},
    "comunista": {"economia": -1.0, "trabalho": -0.9},
    "esquerda": {"economia": -0.7, "costumes": -0.6, "trabalho": -0.6, "ambiente": 0.4},
    "social democrata": {"economia": -0.4, "trabalho": -0.4, "costumes": -0.3},
    "progressista": {"costumes": -0.9, "ambiente": 0.4, "seguranca": -0.4},
    "centro": {},
    "centrista": {},
    "moderado": {},
    "nacionalista": {"economia": -0.3, "costumes": 0.6},
    "lulista": {"economia": -0.7, "trabalho": -0.7, "costumes": -0.4},
    "petista": {"economia": -0.7, "trabalho": -0.7, "costumes": -0.4},

    # --- economia --------------------------------------------------------------
    "privatizacao": {"economia": 0.9},
    "privatizar": {"economia": 0.9},
    "estatal": {"economia": -0.7},
    "estatizacao": {"economia": -0.9},
    "estatizar": {"economia": -0.9},
    "imposto": {"economia": 0.4},
    "menos imposto": {"economia": 0.9},
    "carga tributaria": {"economia": 0.6},
    "reforma tributaria": {"economia": 0.2},
    "livre mercado": {"economia": 1.0},
    "estado minimo": {"economia": 1.0},
    "empreendedor": {"economia": 0.7, "trabalho": 0.6},
    "empreendedorismo": {"economia": 0.7, "trabalho": 0.6},
    "microempresa": {"economia": 0.6, "trabalho": 0.4},
    "agronegocio": {"economia": 0.5, "ambiente": -0.6},
    "banco": {"economia": 0.3},
    "juros": {"economia": 0.3},
    "gasto publico": {"economia": 0.6},
    "teto de gastos": {"economia": 0.8},
    "ajuste fiscal": {"economia": 0.7},
    "austeridade": {"economia": 0.8},
    "bolsa familia": {"economia": -0.7},
    "auxilio": {"economia": -0.5},
    "renda basica": {"economia": -0.8},
    "distribuicao de renda": {"economia": -0.8},
    "desigualdade": {"economia": -0.7},
    "reforma agraria": {"economia": -0.8, "ambiente": 0.2},
    "sus": {"economia": -0.6},
    "saude publica": {"economia": -0.5},
    "escola publica": {"economia": -0.4},
    "universidade publica": {"economia": -0.5},
    "servidor publico": {"economia": -0.4},
    "concurso publico": {"economia": -0.3},
    "petrobras": {"economia": -0.5},
    "soberania": {"economia": -0.3, "costumes": 0.4},

    # --- costumes --------------------------------------------------------------
    "cristao": {"costumes": 0.9},
    "cristã": {"costumes": 0.9},
    "evangelico": {"costumes": 0.9},
    "catolico": {"costumes": 0.7},
    "religioso": {"costumes": 0.8},
    "deus": {"costumes": 0.7},
    "igreja": {"costumes": 0.8},
    "familia tradicional": {"costumes": 1.0},
    "valores familiares": {"costumes": 0.9},
    "pro vida": {"costumes": 1.0},
    "antiaborto": {"costumes": 1.0},
    "aborto": {"costumes": 0.5},
    "legalizacao do aborto": {"costumes": -1.0},
    "lgbt": {"costumes": -0.9},
    "lgbtqia": {"costumes": -0.9},
    "casamento homoafetivo": {"costumes": -0.9},
    "transgenero": {"costumes": -0.8},
    "ideologia de genero": {"costumes": 0.9},
    "escola sem partido": {"costumes": 0.9},
    "homeschooling": {"costumes": 0.8},
    "educacao domiciliar": {"costumes": 0.8},
    "feminismo": {"costumes": -0.8},
    "direitos das mulheres": {"costumes": -0.5},
    "feminicidio": {"costumes": -0.2, "seguranca": 0.4},
    "cotas raciais": {"costumes": -0.8},
    "racismo": {"costumes": -0.7},
    "antirracismo": {"costumes": -0.8},
    "maconha": {"costumes": -0.7},
    "legalizacao das drogas": {"costumes": -0.9, "seguranca": -0.7},
    "descriminalizacao": {"costumes": -0.7, "seguranca": -0.6},
    "jogos de azar": {"costumes": -0.3},
    "cassino": {"costumes": -0.3, "economia": 0.4},
    "laico": {"costumes": -0.7},
    "laicidade": {"costumes": -0.7},

    # --- ambiente --------------------------------------------------------------
    "meio ambiente": {"ambiente": 0.8},
    "ambientalista": {"ambiente": 1.0},
    "clima": {"ambiente": 0.8},
    "mudanca do clima": {"ambiente": 0.9},
    "aquecimento global": {"ambiente": 0.9},
    "sustentabilidade": {"ambiente": 0.8},
    "amazonia": {"ambiente": 0.7},
    "desmatamento": {"ambiente": 0.7},
    "preservacao": {"ambiente": 0.8},
    "energia renovavel": {"ambiente": 0.8},
    "animais": {"ambiente": 0.6},
    "causa animal": {"ambiente": 0.7},
    "indigena": {"ambiente": 0.7, "costumes": -0.5},
    "quilombola": {"ambiente": 0.5, "costumes": -0.6},
    "marco temporal": {"ambiente": -0.7},
    "mineracao": {"ambiente": -0.7, "economia": 0.4},
    "garimpo": {"ambiente": -0.9},
    "licenciamento ambiental": {"ambiente": -0.3},
    "ruralista": {"ambiente": -0.9, "economia": 0.5},
    "agrotoxico": {"ambiente": -0.6},
    "veneno": {"ambiente": -0.4},
    "pecuaria": {"ambiente": -0.5, "economia": 0.4},

    # --- seguranca -------------------------------------------------------------
    "seguranca publica": {"seguranca": 0.7},
    "armas": {"seguranca": 0.9},
    "porte de arma": {"seguranca": 1.0},
    "armamentista": {"seguranca": 1.0},
    "desarmamento": {"seguranca": -0.9},
    "cpc": {"seguranca": 0.3},
    "bandido": {"seguranca": 0.9},
    "pena de morte": {"seguranca": 1.0},
    "prisao perpetua": {"seguranca": 1.0},
    "reducao da maioridade penal": {"seguranca": 0.9},
    "maioridade penal": {"seguranca": 0.8},
    "endurecimento": {"seguranca": 0.8},
    "tolerancia zero": {"seguranca": 1.0},
    "policia": {"seguranca": 0.7},
    "policial": {"seguranca": 0.7},
    "militar": {"seguranca": 0.6, "costumes": 0.4},
    "excludente de ilicitude": {"seguranca": 0.9},
    "faccao": {"seguranca": 0.8},
    "narcotrafico": {"seguranca": 0.8},
    "direitos humanos": {"seguranca": -0.8, "costumes": -0.5},
    "encarceramento": {"seguranca": -0.5},
    "audiencia de custodia": {"seguranca": -0.7},
    "ressocializacao": {"seguranca": -0.7},
    "violencia policial": {"seguranca": -0.8},
    "garantismo": {"seguranca": -0.9},

    # --- trabalho --------------------------------------------------------------
    "clt": {"trabalho": -0.7},
    "sindicato": {"trabalho": -0.9},
    "sindical": {"trabalho": -0.9},
    "greve": {"trabalho": -0.7},
    "trabalhador": {"trabalho": -0.6},
    "reforma trabalhista": {"trabalho": 0.7},
    "flexibilizacao": {"trabalho": 0.8},
    "terceirizacao": {"trabalho": 0.8},
    "aplicativo": {"trabalho": 0.3},
    "motorista de aplicativo": {"trabalho": -0.3},
    "salario minimo": {"trabalho": -0.6, "economia": -0.5},
    "jornada de trabalho": {"trabalho": -0.4},
    "escala 6x1": {"trabalho": -0.7},
    "aposentadoria": {"trabalho": -0.5, "economia": -0.4},
    "previdencia": {"economia": 0.3},
    "reforma da previdencia": {"economia": 0.7, "trabalho": 0.6},
    "mei": {"trabalho": 0.5, "economia": 0.6},
    "autonomo": {"trabalho": 0.5},

    # --- instituicoes ----------------------------------------------------------
    "transparencia": {"instituicoes": 1.0},
    "anticorrupcao": {"instituicoes": 1.0},
    "corrupcao": {"instituicoes": 0.8},
    "combate a corrupcao": {"instituicoes": 1.0},
    "ficha limpa": {"instituicoes": 1.0},
    "prestacao de contas": {"instituicoes": 0.9},
    "controle social": {"instituicoes": 0.8},
    "emenda parlamentar": {"instituicoes": -0.3},
    "orcamento secreto": {"instituicoes": -1.0},
    "emendas secretas": {"instituicoes": -1.0},
    "foro privilegiado": {"instituicoes": -0.8},
    "imunidade parlamentar": {"instituicoes": -0.6},
    "sigilo": {"instituicoes": -0.8},
    "anistia": {"instituicoes": -0.6},
    "impeachment": {"instituicoes": 0.2},
    "democracia": {"instituicoes": 0.7},
    "golpe": {"instituicoes": 0.5},
    "voto impresso": {"instituicoes": 0.1, "costumes": 0.5},
    "reforma politica": {"instituicoes": 0.4},
    "fundo eleitoral": {"instituicoes": -0.4},
    "reeleicao": {"instituicoes": -0.2},
    "nepotismo": {"instituicoes": 0.7},
    "improbidade": {"instituicoes": 0.8},
    "lavagem de dinheiro": {"instituicoes": 0.7},
    "honestidade": {"instituicoes": 0.9},
    "honesto": {"instituicoes": 0.9},
    "digno": {"instituicoes": 0.8},
}

# ---------------------------------------------------------------------------
# Frentes parlamentares (bancadas): sinal forte e publico de posicionamento.
# ---------------------------------------------------------------------------

FRENTES = [
    (r"evangelic|cristã|cristao|catolic|biblic|religio", {"costumes": 0.8}),
    (r"defesa da vida|pro-vida|pro vida|familia", {"costumes": 0.9}),
    (r"agropecuar|agro|ruralis|agricultura|pecuar", {"ambiente": -0.7, "economia": 0.5}),
    (r"ambientalis|meio ambiente|clima|sustentab|energia renovavel", {"ambiente": 0.9}),
    (r"defesa animal|causa animal|protecao animal", {"ambiente": 0.6}),
    (r"seguranca publica|policial|policia|combate ao crime|pena", {"seguranca": 0.8}),
    (r"armas|tiro|caca|cac\b|colecionador", {"seguranca": 0.9}),
    (r"direitos humanos", {"seguranca": -0.8, "costumes": -0.5}),
    (r"lgbt|diversidade sexual", {"costumes": -0.9}),
    (r"mulher|feminin|genero", {"costumes": -0.4}),
    (r"igualdade racial|negr|afro|quilombol", {"costumes": -0.7}),
    (r"indigen", {"ambiente": 0.7, "costumes": -0.5}),
    (r"sindical|trabalhador|classe trabalhadora", {"trabalho": -0.8}),
    (r"servidor|servico publico|funcionalismo", {"trabalho": -0.5, "economia": -0.4}),
    (r"empreendedor|micro e pequena|livre mercado|desburocratiz|empresa", {"economia": 0.7, "trabalho": 0.5}),
    (r"privatiz|concess|parceria publico", {"economia": 0.8}),
    (r"sus\b|saude publica", {"economia": -0.5}),
    (r"educacao publica|escola publica|universidade", {"economia": -0.4}),
    (r"reforma agraria|agricultura familiar|assentado", {"economia": -0.6, "ambiente": 0.3}),
    (r"transparencia|combate a corrupcao|anticorrupcao|controle", {"instituicoes": 0.9}),
    (r"reforma politica|aperfeiçoamento|aperfeicoamento.*legisla", {"instituicoes": 0.3}),
    (r"mineracao|minerac|petroleo|combustivel", {"ambiente": -0.6, "economia": 0.4}),
    (r"assistencia social|pobreza|fome|seguranca alimentar", {"economia": -0.6}),
    (r"crianca|adolescente|primeira infancia", {}),
    (r"idoso|pessoa com deficiencia|autis", {}),
]

# Verbos que indicam a DIRECAO da proposta (usados para dar sinal a uma votacao).
CUE_AMPLIA = r"\b(autoriz\w+|permit\w+|amplia\w*|flexibiliz\w+|libera\w*|desregulament\w+|reduz\w+ a exigencia|facilita\w*|isenta\w*|desonera\w*)\b"
CUE_RESTRINGE = r"\b(proib\w+|veda\w*|criminaliz\w+|restring\w+|endurec\w+|aumenta\w* a pena|revoga\w*|limita\w*|obriga\w*)\b"


# O eixo "geral" (esquerda-direita) nao tem termos proprios: e derivado dos
# tematicos. No eixo ambiente o polo positivo (ambientalista) puxa para a
# esquerda, por isso o sinal negativo.
SINAL_GERAL = {"economia": 1, "costumes": 1, "ambiente": -1,
               "seguranca": 1, "trabalho": 1, "instituicoes": 0}


def derivar_geral(vetor: dict[str, float | None]) -> float | None:
    soma = peso = 0.0
    for eixo, sinal in SINAL_GERAL.items():
        v = vetor.get(eixo)
        if not sinal or v is None or v == 0:
            continue
        soma += sinal * v * abs(v)
        peso += abs(v)
    return round(soma / peso, 3) if peso else None


def normaliza_texto(t: str) -> str:
    return re.sub(r"\s+", " ", sem_acento(t or "").lower())


def vetor_de_texto(texto: str) -> tuple[dict[str, float], list[str]]:
    """Converte texto livre em vetor de eixos. Devolve (vetor, termos_encontrados)."""
    t = normaliza_texto(texto)
    acumulado = {e: 0.0 for e in EIXOS}
    peso = {e: 0.0 for e in EIXOS}
    achados = []
    # termos maiores primeiro para "porte de arma" ganhar de "armas"
    for termo in sorted(LEXICO, key=len, reverse=True):
        alvo = normaliza_texto(termo)
        if not alvo:
            continue
        if re.search(r"(?<![a-z])" + re.escape(alvo) + r"(?![a-z])", t):
            achados.append(termo)
            for eixo, v in LEXICO[termo].items():
                acumulado[eixo] += v
                peso[eixo] += abs(v)
    vetor = {}
    for e in EIXOS:
        if e == "geral":
            continue
        vetor[e] = round(acumulado[e] / peso[e], 3) if peso[e] else 0.0
    vetor["geral"] = derivar_geral(vetor) or 0.0
    return vetor, achados


def eixos_da_frente(titulo: str) -> dict[str, float]:
    t = normaliza_texto(titulo)
    saida: dict[str, float] = {}
    for padrao, eixos in FRENTES:
        if re.search(padrao, t):
            for eixo, v in eixos.items():
                saida[eixo] = saida.get(eixo, 0.0) + v
    return saida


def classificar_ementa(texto: str) -> tuple[dict[str, float], float]:
    """Classifica uma ementa/descricao de proposta.

    Devolve (eixos, confianca). Os eixos indicam para onde a politica publica
    anda SE a proposta for aprovada. So retorna confianca alta quando ha um
    verbo de direcao explicito no texto, para nao inventar sinal.
    """
    t = normaliza_texto(texto)
    if not t:
        return {}, 0.0
    bruto, achados = {}, []
    for termo in sorted(LEXICO, key=len, reverse=True):
        alvo = normaliza_texto(termo)
        if len(alvo) < 4:
            continue
        if re.search(r"(?<![a-z])" + re.escape(alvo) + r"(?![a-z])", t):
            achados.append(termo)
            for eixo, v in LEXICO[termo].items():
                bruto[eixo] = bruto.get(eixo, 0.0) + v
    if not bruto:
        return {}, 0.0

    amplia = bool(re.search(CUE_AMPLIA, t))
    restringe = bool(re.search(CUE_RESTRINGE, t))
    if amplia and not restringe:
        sinal, conf = 1.0, 0.8
    elif restringe and not amplia:
        sinal, conf = -1.0, 0.8
    else:
        sinal, conf = 1.0, 0.25  # tema identificado, direcao incerta

    maior = max(abs(v) for v in bruto.values()) or 1.0
    eixos = {e: round(sinal * v / maior, 3) for e, v in bruto.items()}
    return eixos, conf


def exportar_lexico() -> dict:
    """Payload consumido pelo front-end (mesmo lexico, mesma matematica)."""
    return {
        "eixos": EIXOS,
        "sinal_geral": SINAL_GERAL,
        "lexico": {normaliza_texto(k): v for k, v in LEXICO.items()},
    }
