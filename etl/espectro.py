"""Estimativa de posicao ideologica a partir do comportamento real de voto.

Problema: classificar o tema de uma votacao pela ementa funciona em poucos
casos (a maioria das ementas e do tipo "Altera a Lei n. X"). Isso deixaria o
calculo apoiado quase so em frentes parlamentares.

Solucao (projecao supervisionada, prima da tecnica de ideal points usada em
ciencia politica): em vez de perguntar "de que assunto e esta votacao?",
perguntamos "esta votacao SEPAROU quem e reconhecidamente de um lado de quem e
do outro?".

  1. Para cada eixo, montamos dois grupos-ancora a partir de fato publico e
     verificavel: as frentes parlamentares que a pessoa assinou (ex.: bancada
     evangelica no polo conservador de costumes; frente de direitos humanos no
     polo oposto).
  2. Uma votacao e "discriminante" para aquele eixo se os dois grupos votaram
     de forma claramente diferente.
  3. A posicao de cada parlamentar e o quanto ela votou com um polo ou com o
     outro no conjunto dessas votacoes discriminantes.

Assim usamos TODAS as votacoes nominais, e a nota vira comportamento
observado, nao rotulo atribuido por alguem.
"""

from __future__ import annotations

from .temas import EIXOS
from .util import log

TAMANHO_ANCORA = 55       # quantos parlamentares por polo
MIN_POR_ANCORA = 8        # tamanho minimo de cada grupo-ancora
MIN_ANCORA_NA_VOTACAO = 5  # ancoras presentes para a votacao valer
MIN_DIVERGENCIA = 0.25    # quanto os polos precisam divergir
MIN_VOTOS_PESSOA = 10     # abaixo disso nao publicamos o eixo
MARGEM_ESPECIFICA = 0.15  # quanto uma votacao precisa ser MAIS de um eixo que dos outros

# Para montar o eixo geral (esquerda-direita) a partir dos eixos tematicos.
SINAL_GERAL = {"economia": 1, "costumes": 1, "ambiente": -1,
               "seguranca": 1, "trabalho": 1, "instituicoes": 0}


def ancoras_por_frentes(pessoas: dict[str, dict]) -> dict[str, dict[str, set]]:
    """Escolhe os polos por RANKING, nao por corte relativo ao maximo.

    Bancadas grandes (agro, seguranca) somam valores muito altos e, num corte
    proporcional ao maximo, apagariam bancadas pequenas mas nitidas (frente
    ambientalista, direitos humanos). Pegar os N mais extremos de cada lado
    garante os dois polos sempre que existir sinal nos dois sentidos.
    """
    grupos: dict[str, dict[str, set]] = {}
    for eixo in EIXOS:
        valores = [(i, (p.get("_eixos_frentes") or {}).get(eixo))
                   for i, p in pessoas.items()]
        valores = [(i, v) for i, v in valores if v]
        if not valores:
            log(f"   ancora {eixo}: sem sinal de frentes")
            continue
        valores.sort(key=lambda kv: kv[1], reverse=True)
        pos = {i for i, v in valores[:TAMANHO_ANCORA] if v > 0}
        neg = {i for i, v in valores[-TAMANHO_ANCORA:] if v < 0}
        if len(pos) >= MIN_POR_ANCORA and len(neg) >= MIN_POR_ANCORA:
            grupos[eixo] = {"pos": pos, "neg": neg}
            log(f"   ancora {eixo}: {len(pos)} de um polo, {len(neg)} do outro")
        else:
            log(f"   ancora {eixo}: insuficiente ({len(pos)}/{len(neg)}) - eixo virá de frentes e autorias")
    return grupos


def ancoras_por_partido(pessoas: dict[str, dict], posicao_partidos: dict[str, dict]) -> dict[str, dict[str, set]]:
    """Para o Senado (que nao tem frentes na API), ancora pela media do partido
    calculada na Camara."""
    grupos: dict[str, dict[str, set]] = {}
    for eixo in EIXOS:
        pos, neg = set(), set()
        for i, p in pessoas.items():
            v = (posicao_partidos.get(p.get("partido") or "?") or {}).get(eixo)
            if v is None:
                continue
            if v >= 0.35:
                pos.add(i)
            elif v <= -0.35:
                neg.add(i)
        if len(pos) >= 5 and len(neg) >= 5:
            grupos[eixo] = {"pos": pos, "neg": neg}
    return grupos


def _divergencia(votos: dict[str, float], g: dict[str, set]) -> float | None:
    vp = [v for i, v in votos.items() if i in g["pos"]]
    vn = [v for i, v in votos.items() if i in g["neg"]]
    if len(vp) < MIN_ANCORA_NA_VOTACAO or len(vn) < MIN_ANCORA_NA_VOTACAO:
        return None
    return (sum(vp) / len(vp) - sum(vn) / len(vn)) / 2


def _projetar(pessoas: dict[str, dict], matriz: dict, discriminantes: list,
              minimo: int) -> dict[str, tuple[float, int]]:
    saida = {}
    for i in pessoas:
        soma = peso = 0.0
        n = 0
        for idv, d in discriminantes:
            v = matriz[idv].get(i)
            if v is None:
                continue
            soma += v * (1.0 if d > 0 else -1.0) * abs(d)
            peso += abs(d)
            n += 1
        if peso and n >= minimo:
            saida[i] = (round(max(-1.0, min(1.0, soma / peso)), 3), n)
    return saida


def _ancora_geral(grupos: dict[str, dict[str, set]]) -> dict[str, set] | None:
    """Junta os eixos tematicos num unico polo esquerda/direita.

    Cada pessoa e contada como "direita" ou "esquerda" conforme o lado em que
    aparece nos eixos, respeitando o sinal de SINAL_GERAL (no eixo ambiente o
    polo positivo e ambientalista, que vai para a esquerda).
    """
    placar: dict[str, int] = {}
    for eixo, g in grupos.items():
        s = SINAL_GERAL.get(eixo, 0)
        if not s:
            continue
        for i in g["pos"]:
            placar[i] = placar.get(i, 0) + s
        for i in g["neg"]:
            placar[i] = placar.get(i, 0) - s
    pos = {i for i, v in placar.items() if v > 0}
    neg = {i for i, v in placar.items() if v < 0}
    if len(pos) < MIN_POR_ANCORA or len(neg) < MIN_POR_ANCORA:
        return None
    return {"pos": pos, "neg": neg}


def estimar(pessoas: dict[str, dict], matriz: dict[str, dict[str, float]],
            grupos: dict[str, dict[str, set]]) -> None:
    """Calcula o eixo geral e os eixos tematicos.

    Na pratica brasileira quase toda votacao nominal divide o plenario na MESMA
    linha (governo x oposicao). Se cada eixo usar todas as votacoes que o
    discriminam, os seis eixos saem praticamente iguais - o que daria a falsa
    impressao de seis medidas independentes.

    Por isso separamos:
      * eixo geral: usa todas as votacoes que separam os polos, e e onde mora
        de fato a maior parte do sinal;
      * eixos tematicos: usam apenas as votacoes que dividem MAIS naquele tema
        do que na media dos outros. Sao menos votacoes, mas ai a diferenca
        entre economia, costumes e ambiente e real.
    """
    for p in pessoas.values():
        p.setdefault("_eixos_espectro", {})
        p.setdefault("_espectro_n", {})

    if not matriz:
        log("   espectro: sem matriz de votos, pulando")
        return

    # divergencia de cada votacao em cada eixo
    div: dict[str, dict[str, float]] = {}
    for idv, votos in matriz.items():
        for eixo, g in grupos.items():
            d = _divergencia(votos, g)
            if d is not None:
                div.setdefault(idv, {})[eixo] = d

    geral = _ancora_geral(grupos)
    if geral:
        disc = []
        for idv, votos in matriz.items():
            d = _divergencia(votos, geral)
            if d is not None and abs(d) >= MIN_DIVERGENCIA:
                disc.append((idv, d))
        if disc:
            minimo = max(4, min(MIN_VOTOS_PESSOA, len(disc) // 2))
            resultado = _projetar(pessoas, matriz, disc, minimo)
            for i, (valor, n) in resultado.items():
                pessoas[i]["_eixos_espectro"]["geral"] = valor
                pessoas[i]["_espectro_n"]["geral"] = n
            log(f"   espectro geral: {len(disc)} votacoes, {len(resultado)} posicionados")

    for eixo in grupos:
        especificas = []
        for idv, porEixo in div.items():
            d = porEixo.get(eixo)
            if d is None or abs(d) < MIN_DIVERGENCIA:
                continue
            outros = [abs(v) for e, v in porEixo.items() if e != eixo]
            media_outros = sum(outros) / len(outros) if outros else 0.0
            if abs(d) - media_outros >= MARGEM_ESPECIFICA:
                especificas.append((idv, d))
        if not especificas:
            log(f"   espectro {eixo}: nenhuma votacao especifica do tema "
                f"(virá de frentes e autorias)")
            continue
        minimo = max(4, min(MIN_VOTOS_PESSOA, len(especificas) // 2))
        resultado = _projetar(pessoas, matriz, especificas, minimo)
        for i, (valor, n) in resultado.items():
            pessoas[i]["_eixos_espectro"][eixo] = valor
            pessoas[i]["_espectro_n"][eixo] = n
        log(f"   espectro {eixo}: {len(especificas)} votacoes especificas, "
            f"{len(resultado)} posicionados")
