"""Senado Federal - Dados Abertos Legislativos.

OpenAPI: https://legis.senado.leg.br/dadosabertos/v3/api-docs
O JSON do Senado e um XML convertido: campos podem vir como objeto unico ou
lista, por isso o helper `lista()` em tudo.
"""

from __future__ import annotations

import calendar
import datetime as dt
from collections import defaultdict

from ..temas import classificar_ementa
from ..util import baixar_json, inteiro, log, num, tentar

BASE = "https://legis.senado.leg.br/dadosabertos"

PESO_VOTO = {"sim": 1.0, "não": -1.0, "nao": -1.0, "abstenção": 0.0, "abstencao": 0.0}
VOTOS_VALIDOS = {"sim", "não", "nao", "abstenção", "abstencao"}


def lista(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def senadores() -> dict[str, dict]:
    resp = tentar(lambda: baixar_json(f"{BASE}/senador/lista/atual", ttl_horas=12),
                  "senadores em exercicio", None)
    saida: dict[str, dict] = {}
    if not resp:
        return saida
    raiz = resp.get("ListaParlamentarEmExercicio", {}).get("Parlamentares", {})
    for p in lista(raiz.get("Parlamentar")):
        ident = p.get("IdentificacaoParlamentar", {}) or {}
        mandato = p.get("Mandato", {}) or {}
        cod = str(ident.get("CodigoParlamentar") or "")
        if not cod:
            continue
        primeira = (lista(((mandato.get("PrimeiraLegislaturaDoMandato") or {}) or {}).get("NumeroLegislatura")) or [None])[0]
        saida[cod] = {
            "id": f"sen-{cod}",
            "id_fonte": cod,
            "casa": "senado",
            "cargo": "Senador(a)",
            "nome": ident.get("NomeParlamentar"),
            "nome_civil": ident.get("NomeCompletoParlamentar"),
            "sexo": "F" if (ident.get("SexoParlamentar") == "Feminino") else "M",
            "partido": (ident.get("SiglaPartidoParlamentar") or "").strip(),
            "uf": ident.get("UfParlamentar"),
            "foto": ident.get("UrlFotoParlamentar"),
            "email": ident.get("EmailParlamentar"),
            "site": ident.get("UrlPaginaParlamentar"),
            "redes": [],
            "url_fonte": ident.get("UrlPaginaParlamentar") or f"https://www25.senado.leg.br/web/senadores/senador/-/perfil/{cod}",
            "primeira_legislatura": inteiro(primeira),
            "frentes": [],
            "_eixos_frentes": {},
            "_n_frentes_uteis": 0,
        }
    log(f"   senadores em exercicio: {len(saida)}")
    return saida


def _ementas_por_votacao(anos: list[int]) -> dict[str, str]:
    """Servico novo /votacao traz a ementa; casa por codigoSessaoVotacao."""
    mapa: dict[str, str] = {}
    for ano in anos:
        resp = tentar(lambda a=ano: baixar_json(f"{BASE}/votacao?ano={a}", ttl_horas=24),
                      f"senado /votacao {ano}", None)
        for v in lista(resp):
            cod = str(v.get("codigoSessaoVotacao") or "")
            if cod:
                mapa[cod] = (v.get("ementa") or "") + " " + (v.get("descricaoVotacao") or "")
    return mapa


def votos(sens: dict, anos: list[int]) -> dict:
    ementas = _ementas_por_votacao(anos)

    registrados = defaultdict(set)
    matriz: dict[str, dict[str, float]] = {}
    eixos_sen = defaultdict(lambda: defaultdict(float))
    peso_sen = defaultdict(lambda: defaultdict(float))
    exemplos = defaultdict(list)
    total_votacoes = 0

    # Buscamos MES A MES. O endpoint anual devolve um JSON de megabytes que o
    # servidor corta no meio, e JSON truncado nao da para aproveitar.
    hoje = dt.date.today()
    periodos = []
    for ano in anos:
        for mes in range(1, 13):
            if dt.date(ano, mes, 1) > hoje:
                break
            ultimo = calendar.monthrange(ano, mes)[1]
            periodos.append((f"{ano}{mes:02d}01", f"{ano}{mes:02d}{ultimo:02d}"))

    for ini, fim in periodos:
        resp = tentar(lambda i=ini, f=fim: baixar_json(
            f"{BASE}/plenario/lista/votacao/{i}/{f}", ttl_horas=24, timeout=40),
            f"senado votacoes {ini[:6]}", None, tentativas=2, espera=2)
        if not resp:
            continue
        raiz = resp.get("ListaVotacoes", {}).get("Votacoes", {})
        for v in lista(raiz.get("Votacao")):
            if (v.get("Secreta") or "N") == "S":
                continue
            cod = str(v.get("CodigoSessaoVotacao") or "")
            texto = ementas.get(cod, "") or (v.get("DescricaoVotacao") or "")
            eixos, conf = classificar_ementa(texto)
            total_votacoes += 1
            materia = v.get("DescricaoIdentificacaoMateria") or ""
            for vp in lista((v.get("Votos") or {}).get("VotoParlamentar")):
                cs = str(vp.get("CodigoParlamentar") or "")
                if cs not in sens:
                    continue
                voto = (vp.get("Voto") or "").strip()
                if voto.lower() in VOTOS_VALIDOS:
                    registrados[cs].add(cod)
                    s = PESO_VOTO.get(voto.lower())
                    if s is not None and abs(s) > 0.5:
                        matriz.setdefault(cod, {})[cs] = 1.0 if s > 0 else -1.0
                if not eixos or conf < 0.6:
                    continue
                sinal = PESO_VOTO.get(voto.lower())
                if not sinal:
                    continue
                for eixo, direcao in eixos.items():
                    eixos_sen[cs][eixo] += sinal * direcao * conf
                    peso_sen[cs][eixo] += abs(direcao) * conf
                if len(exemplos[cs]) < 12:
                    exemplos[cs].append({
                        "votacao": cod,
                        "data": v.get("DataSessao"),
                        "proposicao": materia,
                        "ementa": texto.strip()[:220],
                        "voto": voto,
                        "eixos": eixos,
                    })
    log(f"   senado: {total_votacoes} votacoes nominais de plenario no periodo")

    for cs, s in sens.items():
        vistas = len(registrados[cs])
        s["_votos_plenario"] = vistas
        s["_votos_plenario_total"] = total_votacoes
        s["_participacao_pct"] = round(100 * vistas / total_votacoes, 1) if total_votacoes else None
        vet, base = {}, 0
        for eixo, soma in eixos_sen[cs].items():
            p = peso_sen[cs][eixo]
            if p:
                vet[eixo] = round(soma / p, 3)
                base += 1
        s["_eixos_votos"] = vet
        s["_eixos_votos_n"] = base
        s["_votos_exemplo"] = exemplos[cs]
    return {"total_votacoes": total_votacoes, "matriz": matriz}


def licencas_e_autorias(sens: dict, anos: list[int]) -> None:
    """Afastamentos (proxy de falta) e producao legislativa."""
    for n, (cs, s) in enumerate(sens.items(), 1):
        if n % 20 == 0:
            log(f"   senado: {n}/{len(sens)} senadores detalhados")
        # timeout curto: sao respostas pequenas e o servico as vezes engasga.
        resp = tentar(lambda c=cs: baixar_json(f"{BASE}/senador/{c}/licencas",
                                               ttl_horas=72, timeout=20),
                      f"licencas {cs}", None, tentativas=2, espera=1)
        dias = 0
        if resp:
            raiz = (resp.get("LicencaParlamentar", {}).get("Parlamentar", {}) or {}).get("Licencas", {}) or {}
            for lic in lista(raiz.get("Licenca")):
                if (lic.get("DataInicio") or "")[:4] in {str(a) for a in anos}:
                    dias += 1
        s["_dias_licenca"] = dias
        # A presenca em sessao nao vem na API do Senado; usamos participacao em
        # votacao nominal como metrica principal e deixamos isso explicito.
        s["_sessoes_presente"] = s.get("_votos_plenario", 0)
        s["_sessoes_total"] = s.get("_votos_plenario_total", 0)
        s["_presenca_pct"] = s.get("_participacao_pct")

        s["_autorias"] = 0
        s["_autorias_aprovadas"] = 0
        s["_autorias_exemplo"] = []
        s["_eixos_autorias"] = {}
        acumula, pesos = defaultdict(float), defaultdict(float)
        for ano in anos:
            resp = tentar(lambda c=cs, a=ano: baixar_json(
                f"{BASE}/senador/{c}/autorias?ano={a}", ttl_horas=72, timeout=20),
                f"autorias {cs}/{ano}", None, tentativas=2, espera=1)
            if not resp:
                continue
            raiz = (resp.get("MateriasAutoriaParlamentar", {}).get("Parlamentar", {}) or {}).get("Autorias", {}) or {}
            for a in lista(raiz.get("Autoria")):
                if (a.get("IndicadorAutorPrincipal") or "") != "Sim":
                    continue
                m = a.get("Materia", {}) or {}
                sigla = (m.get("Sigla") or "").upper()
                if sigla not in ("PL", "PLP", "PEC", "PDL", "PLS", "MPV"):
                    continue
                s["_autorias"] += 1
                ementa = (m.get("Ementa") or "").strip()
                if len(s["_autorias_exemplo"]) < 8:
                    s["_autorias_exemplo"].append({
                        "titulo": m.get("DescricaoIdentificacao") or f"{sigla} {m.get('Numero')}/{m.get('Ano')}",
                        "ementa": ementa[:220], "situacao": "", "virou_norma": False,
                    })
                eixos, conf = classificar_ementa(ementa)
                if conf >= 0.6:
                    for eixo, direcao in eixos.items():
                        acumula[eixo] += direcao * conf
                        pesos[eixo] += abs(direcao) * conf
        s["_eixos_autorias"] = {e: round(v / pesos[e], 3) for e, v in acumula.items() if pesos[e]}
        # Senado nao tem cota comparavel a CEAP da Camara neste momento.
        s.setdefault("_gasto_total", None)
        s.setdefault("_gasto_mensal", None)
        s.setdefault("_gasto_categorias", [])
        s.setdefault("_gasto_fornecedores", [])
        s.setdefault("_gasto_maior", None)
        s.setdefault("_gasto_concentracao", None)
    log(f"   senado: licencas e autorias coletadas para {len(sens)} senadores")
