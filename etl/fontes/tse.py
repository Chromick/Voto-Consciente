"""Candidaturas de 2026 (TSE) e o cruzamento com quem ja tem mandato.

A coleta em si NAO acontece aqui: o TSE bloqueia clientes que nao sejam
navegador, entao quem baixa e `tools/coletar_tse.py` (Playwright), e o
resultado fica versionado em dados/tse/. Este modulo apenas le esse material,
normaliza e cruza com os parlamentares em exercicio.

O cruzamento e a parte que da valor: um candidato a governador que hoje e
deputado ou senador tem voto registrado, presenca e cota - da para julgar pelo
que fez. Quem nunca teve mandato federal aparece com o que o TSE fornece
(situacao do registro, ficha limpa, patrimonio, historico de candidaturas) e
com o aviso de que nao ha historico para avaliar.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..util import DADOS, chave_nome, log

ENTRADA = DADOS / "tse"

# Cargos que o eleitor escolhe na urna, na ordem em que a urna pede.
CARGOS_URNA = {
    6: "Deputado Federal",
    7: "Deputado Estadual",
    8: "Deputado Distrital",
    5: "Senador",
    3: "Governador",
    1: "Presidente",
}
# Chapa: quem e votado junto com o titular (nao aparece como escolha separada).
VINCULADOS = {2: 1, 4: 3, 9: 5, 10: 5}

# Situacoes que significam "esta valendo, pode receber voto".
SITUACOES_OK = {"deferido", "deferido com recurso", "aguardando julgamento"}


def _apelidos(pessoa: dict) -> set[str]:
    """Nomes pelos quais um parlamentar pode ser reconhecido."""
    saida = set()
    for campo in ("nome", "nome_civil"):
        v = pessoa.get(campo)
        if v:
            saida.add(chave_nome(v))
    return {s for s in saida if s}


def _indexar_mandatos(pessoas: list[dict]) -> dict[str, list[dict]]:
    indice: dict[str, list[dict]] = {}
    for p in pessoas:
        for chave in _apelidos(p):
            indice.setdefault(chave, []).append(p)
    return indice


def _casar(cand: dict, indice: dict[str, list[dict]]) -> tuple[dict | None, int]:
    """Liga a candidatura a um mandato atual.

    Atribuir o historico de votacao de alguem a um xara e o pior erro possivel
    aqui, entao a regra e deliberadamente conservadora:

    * nome COMPLETO igual (3+ palavras) vale mesmo entre estados diferentes -
      "JOAO PAULO FERREIRA LIMA" repetir e improvavel;
    * nome de urna ("EDUARDO GOMES") so vale dentro da MESMA UF - sem isso o
      senador do Tocantins virava candidato a deputado estadual no Acre;
    * empate sem desempate por UF: desiste. Melhor nao mostrar historico do
      que mostrar o historico de outra pessoa.

    Devolve (mandato, forca): forca 2 = nome completo, 1 = nome de urna. A
    forca serve para desempatar quando dois candidatos diferentes casam com o
    mesmo mandato (ver `carregar`).
    """
    completo = chave_nome(cand.get("nome") or "")
    if completo and len(completo.split()) >= 3:
        achados = indice.get(completo) or []
        if len(achados) == 1:
            return achados[0], 2
        mesma_uf = [p for p in achados if p.get("uf") == cand.get("uf")]
        if len(mesma_uf) == 1:
            return mesma_uf[0], 2

    for campo in ("nome", "urna"):
        chave = chave_nome(cand.get(campo) or "")
        if not chave:
            continue
        mesma_uf = [p for p in (indice.get(chave) or [])
                    if p.get("uf") == cand.get("uf")]
        if len(mesma_uf) == 1:
            return mesma_uf[0], 1
    return None, 0


def _alertas_do_tse(c: dict) -> list[dict]:
    """Sinais oficiais da Justica Eleitoral sobre a candidatura.

    Diferente de noticia: aqui e registro do proprio TSE. Ainda assim usamos
    linguagem exata - "registro indeferido" nao e o mesmo que "condenado".
    """
    saida = []
    sit = (c.get("situacao") or "").strip()
    if sit and sit.lower() not in SITUACOES_OK:
        saida.append({"tipo": "registro", "texto": f"Registro: {sit}",
                      "peso": "alto"})
    if c.get("apto") is False or c.get("inapto") is True:
        saida.append({"tipo": "inapto",
                      "texto": "TSE marca a candidatura como inapta",
                      "peso": "alto"})
    motivos = [
        ("motivo_ficha_limpa", "Lei da Ficha Limpa citada no indeferimento"),
        ("motivo_abuso_poder", "Abuso de poder citado no indeferimento"),
        ("motivo_compra_voto", "Compra de voto citada no indeferimento"),
        ("motivo_conduta_vedada", "Conduta vedada citada no indeferimento"),
        ("motivo_gasto_ilicito", "Gasto ilicito citado no indeferimento"),
    ]
    for campo, texto in motivos:
        if c.get(campo) in (True, "S", "s", 1):
            saida.append({"tipo": "motivo", "texto": texto, "peso": "alto"})
    if (c.get("cassacao") or 0) > 0:
        saida.append({"tipo": "cassacao",
                      "texto": f"{c['cassacao']} processo(s) de cassacao registrado(s)",
                      "peso": "alto"})
    return saida


def _nota_registro(c: dict, alertas: list[dict]) -> int:
    """0-100 para a situacao junto a Justica Eleitoral."""
    if not alertas:
        return 100
    graves = sum(1 for a in alertas if a["peso"] == "alto")
    return max(0, 100 - 45 * graves)


def _enxuto(d: dict) -> dict:
    """Tira campo vazio do JSON.

    Com 21 mil candidaturas, guardar `"foto":null` em cada uma custa megabytes
    - e o site ja trata campo ausente e campo nulo do mesmo jeito.
    """
    return {k: v for k, v in d.items()
            if v is not None and v != "" and v != [] and v != {}}


def carregar(pessoas: list[dict]) -> dict:
    """Le dados/tse/, cruza com os mandatos e devolve a cedula por UF e cargo."""
    if not ENTRADA.exists():
        log("   ! dados/tse/ nao existe - rode tools/coletar_tse.py")
        return {}

    indice = _indexar_mandatos(pessoas)
    por_mandato = {}
    cedula: dict[str, dict] = {}
    total = casados = 0

    arquivos = sorted(ENTRADA.glob("*-*.json"))
    for arq in arquivos:
        dado = json.loads(arq.read_text(encoding="utf-8"))
        cargo = dado["cargo"]
        uf = dado["uf"]
        saida = []
        for c in dado.get("candidatos", []):
            c["uf"] = uf
            alertas = _alertas_do_tse(c)
            item = {
                "id": c["id"],
                "urna": c.get("urna"),
                "nome": c.get("nome"),
                "numero": c.get("numero"),
                "partido": c.get("partido"),
                "coligacao": c.get("coligacao"),
                "coligacao_composicao": c.get("coligacao_composicao"),
                "uf": uf,
                "situacao": c.get("situacao"),
                "apto": c.get("apto"),
                "reeleicao": c.get("reeleicao"),
                # a URL da foto e sempre .../img/<idEleicao>/<idCandidato>/<UF>,
                # entao o site remonta a partir do id - guardar 90 caracteres
                # iguais em 21 mil candidatos custaria megabytes a toa
                "tem_foto": bool(c.get("foto")),
                "bens": c.get("bens"),
                "instrucao": c.get("instrucao"),
                "ocupacao": c.get("ocupacao"),
                "nascimento": c.get("nascimento"),
                "sexo": c.get("sexo"),
                "cor": c.get("cor"),
                # O TSE devolve o cargo e o resultado das eleicoes anteriores
                # com chaves que nao batem com a listagem (vem nulo, e a UF vem
                # como codigo de municipio). Enquanto isso nao for reconferido,
                # guardamos so o que e confiavel: os anos em que concorreu.
                "anteriores_anos": sorted({a.get("ano") for a in (c.get("anteriores") or [])
                                           if a.get("ano") and a.get("ano") != 2026},
                                          reverse=True)[:8],
                "plano_governo": c.get("plano_governo"),
                "sites": (c.get("sites") or [])[:2],
                "alertas_tse": alertas,
                "nota_registro": _nota_registro(c, alertas),
            }
            item = _enxuto(item)
            m, forca = _casar(c, indice)
            if m:
                item["_mandato_obj"] = m
                item["_forca"] = forca
                por_mandato.setdefault(m["id"], []).append(item)
            total += 1
            saida.append(item)

        if saida:
            cedula[f"{uf}-{cargo}"] = {
                "uf": uf, "cargo": cargo, "cargo_nome": dado.get("cargo_nome"),
                "candidatos": saida,
            }

    # Um mandato so pode virar UMA candidatura. Quando dois candidatos
    # diferentes casam com a mesma pessoa (xara na mesma UF), fica com o
    # casamento mais forte; se houver empate, ninguem leva o historico.
    ambiguos = 0
    for id_mandato, itens in por_mandato.items():
        if len(itens) > 1:
            melhor = max(i["_forca"] for i in itens)
            vencedores = [i for i in itens if i["_forca"] == melhor]
            itens = vencedores if len(vencedores) == 1 else []
            ambiguos += 1
        for item in itens:
            m = item.pop("_mandato_obj")
            item["mandato"] = {
                "id": m["id"], "casa": m["casa"], "cargo_atual": m.get("cargo"),
                "partido": m.get("partido"), "uf": m.get("uf"),
            }
            item["eixos"] = m.get("eixos") or {}
            item["confianca_eixos"] = m.get("confianca_eixos", 0)
            item["notas"] = m.get("notas") or {}
            item["n_sancoes"] = len(m.get("sancoes") or [])
            if not item.get("foto"):
                item["foto"] = m.get("foto")
            casados += 1

    for bloco in cedula.values():
        for item in bloco["candidatos"]:
            item.pop("_mandato_obj", None)
            item.pop("_forca", None)

    log(f"   {total:,} candidaturas lidas de dados/tse/")
    log(f"   {casados:,} vinculadas a um mandato atual (tem voto, presenca e cota)")
    if ambiguos:
        log(f"   {ambiguos} nomes ambiguos (xara na mesma UF) resolvidos com cautela")
    return {"cedula": cedula, "por_mandato": por_mandato,
            "total": total, "casados": casados}
