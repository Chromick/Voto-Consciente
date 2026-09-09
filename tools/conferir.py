"""Sanidade dos dados gerados: confere se os numeros batem com a realidade.

    python tools/conferir.py
"""

import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
d = json.load(open(RAIZ / "dados" / "ranking.json", encoding="utf-8"))
ps = d["parlamentares"]

print("POSICAO MEDIA POR PARTIDO")
print("  + = mercado | conservador | ambientalista | flexibilizacao trabalhista")
linhas = [(e.get("costumes", 0), p, e) for p, e in d["partidos"].items() if "costumes" in e]
for _, p, e in sorted(linhas):
    print("  {:14s} eco {:+.2f}  costumes {:+.2f}  ambiente {:+.2f}  trabalho {:+.2f}".format(
        p, e.get("economia", 0), e.get("costumes", 0), e.get("ambiente", 0), e.get("trabalho", 0)))

def media(campo):
    vals = [x["notas"][campo] for x in ps if x["notas"][campo] is not None]
    return sum(vals) / len(vals) if vals else 0

print()
print("Presenca media em sessoes deliberativas: {:.1f}%".format(media("presenca")))
print("Participacao media em votacoes nominais: {:.1f}%".format(media("participacao")))
print("Confianca media do posicionamento: {:.2f}".format(
    sum(x["confianca_eixos"] for x in ps) / len(ps)))

gastos = sorted((x["metricas"]["gasto_mensal"], x["nome"]) for x in ps
                if x["metricas"]["gasto_mensal"])
if gastos:
    print("Cota mensal: menor R$ {:,.0f} ({}) | maior R$ {:,.0f} ({})".format(
        gastos[0][0], gastos[0][1], gastos[-1][0], gastos[-1][1]))

com = [x for x in ps if x["n_sancoes"]]
print("Com sancao oficial cruzada por nome: {}".format(len(com)))
for x in com[:10]:
    print("   - {} ({}-{})".format(x["nome"], x["partido"], x["uf"]))

print()
print("Extremos do eixo costumes (conservador +1 / progressista -1):")
ord_c = sorted((x["eixos"].get("costumes"), x["nome"], x["partido"]) for x in ps
               if x["eixos"].get("costumes") is not None)
for v, n, p in ord_c[:5]:
    print("   {:+.2f}  {} ({})".format(v, n, p))
print("   ...")
for v, n, p in ord_c[-5:]:
    print("   {:+.2f}  {} ({})".format(v, n, p))

faltantes = [x["nome"] for x in ps if not x["eixos"]]
print()
print("Sem posicionamento algum: {}".format(len(faltantes)))
