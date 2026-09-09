"""Cota para Exercicio da Atividade Parlamentar (CEAP) - "uso do dinheiro".

Arquivo diario da Camara: https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip
Cada linha e uma despesa reembolsada com dinheiro publico.
"""

from __future__ import annotations

from collections import defaultdict

from ..util import chave_nome, ler_csv_zip, log, num, tentar

URL = "https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip"


def carregar(deps: dict, anos: list[int]) -> None:
    por_chave = {chave_nome(d["nome"]): i for i, d in deps.items()}
    por_civil = {chave_nome(d.get("nome_civil") or ""): i for i, d in deps.items()}

    total = defaultdict(float)
    por_categoria = defaultdict(lambda: defaultdict(float))
    por_fornecedor = defaultdict(lambda: defaultdict(float))
    meses = defaultdict(set)
    docs = defaultdict(int)
    maior = defaultdict(lambda: {"valor": 0.0})
    sem_dono = 0

    for ano in anos:
        linhas = tentar(lambda a=ano: ler_csv_zip(URL.format(ano=a), ttl_horas=24),
                        f"cota {ano}", None)
        if linhas is None:
            continue
        n = 0
        for l in linhas:
            dep = str(l.get("ideCadastro") or "").strip()
            if dep not in deps:
                k = chave_nome(l.get("txNomeParlamentar") or "")
                dep = por_chave.get(k) or por_civil.get(k)
                if not dep:
                    sem_dono += 1
                    continue
            valor = num(l.get("vlrLiquido"))
            if valor <= 0:
                continue
            n += 1
            total[dep] += valor
            cat = (l.get("txtDescricao") or "OUTROS").strip()
            por_categoria[dep][cat] += valor
            forn = (l.get("txtFornecedor") or "").strip()
            if forn:
                por_fornecedor[dep][forn] += valor
            meses[dep].add(f"{l.get('numAno')}-{str(l.get('numMes')).zfill(2)}")
            docs[dep] += 1
            if valor > maior[dep]["valor"]:
                maior[dep] = {
                    "valor": round(valor, 2),
                    "descricao": cat,
                    "fornecedor": forn,
                    "data": (l.get("datEmissao") or "")[:10],
                    "documento": l.get("urlDocumento") or None,
                }
        log(f"   cota {ano}: {n:,} despesas atribuidas")
    if sem_dono:
        log(f"   cota: {sem_dono:,} linhas de liderancas/ex-deputados ignoradas")

    for i, d in deps.items():
        t = round(total[i], 2)
        m = len(meses[i]) or 1
        cats = sorted(por_categoria[i].items(), key=lambda kv: -kv[1])[:6]
        forns = sorted(por_fornecedor[i].items(), key=lambda kv: -kv[1])[:5]
        concentracao = (forns[0][1] / t) if (forns and t) else 0.0
        d["_gasto_total"] = t
        d["_gasto_mensal"] = round(t / m, 2)
        d["_gasto_meses"] = m
        d["_gasto_docs"] = docs[i]
        d["_gasto_categorias"] = [{"nome": c, "valor": round(v, 2)} for c, v in cats]
        d["_gasto_fornecedores"] = [{"nome": f, "valor": round(v, 2)} for f, v in forns]
        d["_gasto_maior"] = maior[i] if maior[i]["valor"] else None
        d["_gasto_concentracao"] = round(concentracao, 3)
