"""Coleta as candidaturas de 2026 no TSE.

Por que este script existe separado do ETL
------------------------------------------
O TSE serve os dados de candidatura em https://divulgacandcontas.tse.jus.br,
protegido por um WAF que bloqueia qualquer cliente que nao seja um navegador
de verdade - Python, curl e ate um curl com todos os cabecalhos do Chrome
levam 403. Nao e o User-Agent: o bloqueio e pela impressao digital do TLS.
O CDN de dados abertos (cdn.tse.jus.br) bloqueia do mesmo jeito, inclusive
para os arquivos de anos anteriores.

A saida deste script fica versionada em dados/tse/, entao quem for so rodar
o ETL ou o site NAO precisa de navegador nem de nenhuma dependencia: o
`python -m etl.build` continua funcionando com a biblioteca padrao.

Uso:
    python -m pip install playwright && python -m playwright install chromium
    python tools/coletar_tse.py            # cedula inteira (~21 mil candidatos)
    python tools/coletar_tse.py --cargos 1 3 5   # so os majoritarios
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "dados" / "tse"

BASE = "https://divulgacandcontas.tse.jus.br/divulga"
ID_ELEICAO = "20322002026"
ANO = 2026

UFS = ["AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS",
       "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC",
       "SE", "SP", "TO"]

# codigo do cargo no TSE -> (nome, escopo)
CARGOS = {
    1: ("Presidente", "BR"),
    2: ("Vice-presidente", "BR"),
    3: ("Governador", "UF"),
    4: ("Vice-governador", "UF"),
    5: ("Senador", "UF"),
    6: ("Deputado Federal", "UF"),
    7: ("Deputado Estadual", "UF"),
    8: ("Deputado Distrital", "UF"),
    9: ("1º Suplente", "UF"),
    10: ("2º Suplente", "UF"),
}

# Roda dentro da pagina do TSE (mesma origem, WAF ja resolvido pelo navegador).
# Devolve so os campos que usamos - o payload cru tem ~70 campos por candidato.
JS_LISTAR = """
async ([base, ano, idEleicao, uf, cargo]) => {
  const r = await fetch(
    `${base}/rest/v1/candidatura/listar/${ano}/${uf}/${idEleicao}/${cargo}/candidatos`,
    { headers: { Accept: 'application/json' } });
  if (!r.ok) return { erro: r.status };
  const j = await r.json();
  return { candidatos: (j.candidatos || []).map(c => ({
    id: c.id, urna: c.nomeUrna, nome: c.nomeCompleto, numero: c.numero,
    partido: c.partido && c.partido.sigla, coligacao: c.nomeColigacao,
    situacao: c.descricaoSituacao, totalizacao: c.descricaoTotalizacao,
    apto: c.candidatoApto, reeleicao: c.st_REELEICAO,
    titulo: c.tituloEleitor, superior: c.idCandidatoSuperior,
  })) };
}
"""

JS_DETALHAR = """
async ([base, ano, idEleicao, uf, ids]) => {
  const saida = {}; const fila = [...ids];
  const trabalhador = async () => {
    while (fila.length) {
      const id = fila.shift();
      try {
        const r = await fetch(
          `${base}/rest/v1/candidatura/buscar/${ano}/${uf}/${idEleicao}/candidato/${id}`,
          { headers: { Accept: 'application/json' } });
        if (!r.ok) continue;
        const j = await r.json();
        saida[id] = {
          cpf: j.cpf, nascimento: j.dataDeNascimento, sexo: j.descricaoSexo,
          cor: j.descricaoCorRaca, instrucao: j.grauInstrucao, ocupacao: j.ocupacao,
          estado_civil: j.descricaoEstadoCivil,
          naturalidade: j.nomeMunicipioNascimento, uf_nascimento: j.sgUfNascimento,
          bens: j.totalDeBens, n_bens: (j.bens || []).length,
          bens_lista: (j.bens || []).map(b => ({
            tipo: b.descricaoDeTipoDeBem, valor: b.valor })).slice(0, 40),
          foto: j.fotoUrlPublicavel ? j.fotoUrl : null,
          coligacao_composicao: j.composicaoColigacao,
          sites: (j.sites || []).slice(0, 3),
          plano_governo: (j.arquivos || []).map(a => a.idArquivo)[0] || null,
          anteriores: (j.eleicoesAnteriores || []).map(e => ({
            ano: e.nrAno, cargo: e.cargo && e.cargo.nome,
            uf: e.sgUe || e.ufCandidatura,
            situacao: e.descricaoTotalizacao || e.descricaoSituacao })),
          cassacao: (j.processosCassacao || []).length,
          desconstituicao: (j.processosDesconstituicao || []).length,
          motivo_ficha_limpa: j.st_MOTIVO_FICHA_LIMPA,
          motivo_abuso_poder: j.st_MOTIVO_ABUSO_PODER,
          motivo_compra_voto: j.st_MOTIVO_COMPRA_VOTO,
          motivo_conduta_vedada: j.st_MOTIVO_CONDUTA_VEDADA,
          motivo_gasto_ilicito: j.st_MOTIVO_GASTO_ILICITO,
          motivo_outros: j.ds_MOTIVO_OUTROS,
          motivo_situacao: j.motivoSituacao,
          situacao_candidato: j.descricaoSituacaoCandidato,
          gasto_campanha: j.gastoCampanha1T,
        };
      } catch (e) { /* segue para o proximo */ }
    }
  };
  await Promise.all([...Array(8)].map(trabalhador));
  return saida;
}
"""


def log(msg: str):
    print(msg, flush=True)


def coletar(cargos: list[int], com_detalhe: bool, limite_detalhe: int | None):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("playwright nao instalado. Rode:\n"
                 "  python -m pip install playwright\n"
                 "  python -m playwright install chromium")

    SAIDA.mkdir(parents=True, exist_ok=True)
    inicio = time.time()
    total_geral = 0

    with sync_playwright() as p:
        # O headless ANTIGO do Chromium e barrado pelo WAF (403); o headless
        # novo (channel="chromium") passa. Manter esse channel e obrigatorio.
        navegador = p.chromium.launch(
            headless=True, channel="chromium",
            args=["--disable-blink-features=AutomationControlled"])
        contexto = navegador.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/141.0.0.0 Safari/537.36"),
            locale="pt-BR", viewport={"width": 1366, "height": 768})
        pagina = contexto.new_page()
        pagina.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        log("abrindo o TSE (resolve o WAF)...")
        pagina.goto(f"{BASE}/", wait_until="domcontentloaded", timeout=90_000)
        pagina.wait_for_timeout(3000)

        # confere que a API responde antes de rodar tudo
        teste = pagina.evaluate(JS_LISTAR, [BASE, ANO, ID_ELEICAO, "BR", 1])
        if teste.get("erro"):
            navegador.close()
            sys.exit(f"o TSE respondeu {teste['erro']} - WAF nao liberou")
        log(f"   ok, a API respondeu ({len(teste['candidatos'])} candidatos a presidente)")

        for cargo in cargos:
            nome_cargo, escopo = CARGOS[cargo]
            ufs = ["BR"] if escopo == "BR" else UFS
            for uf in ufs:
                r = pagina.evaluate(JS_LISTAR, [BASE, ANO, ID_ELEICAO, uf, cargo])
                if r.get("erro"):
                    log(f"   ! {nome_cargo}/{uf}: HTTP {r['erro']}")
                    continue
                candidatos = r["candidatos"]
                if not candidatos:
                    continue

                if com_detalhe:
                    ids = [c["id"] for c in candidatos]
                    if limite_detalhe:
                        ids = ids[:limite_detalhe]
                    detalhes = {}
                    # em blocos, para nao segurar uma unica chamada longa demais
                    for i in range(0, len(ids), 300):
                        detalhes.update(pagina.evaluate(
                            JS_DETALHAR,
                            [BASE, ANO, ID_ELEICAO, uf, ids[i:i + 300]]))
                    for c in candidatos:
                        d = detalhes.get(str(c["id"])) or detalhes.get(c["id"])
                        if d:
                            c.update(d)

                alvo = SAIDA / f"{uf}-{cargo}.json"
                alvo.write_text(json.dumps(
                    {"uf": uf, "cargo": cargo, "cargo_nome": nome_cargo,
                     "ano": ANO, "candidatos": candidatos},
                    ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
                total_geral += len(candidatos)
                log(f"   {nome_cargo:18} {uf}  {len(candidatos):5} candidatos"
                    f"   ({time.time() - inicio:.0f}s)")

        navegador.close()

    indice = {"ano": ANO, "id_eleicao": ID_ELEICAO, "total": total_geral,
              "cargos": {str(c): CARGOS[c][0] for c in cargos},
              "ufs": UFS, "coletado_em": time.strftime("%Y-%m-%dT%H:%M:%S")}
    (SAIDA / "indice.json").write_text(
        json.dumps(indice, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"\nOK: {total_geral:,} candidaturas em {time.time() - inicio:.0f}s -> dados/tse/")


def main():
    ap = argparse.ArgumentParser(description="Coleta candidaturas 2026 do TSE")
    ap.add_argument("--cargos", nargs="*", type=int, default=list(CARGOS),
                    help="codigos de cargo (1 presidente ... 10 2o suplente)")
    ap.add_argument("--sem-detalhe", action="store_true",
                    help="so a listagem, sem bens/ficha limpa")
    ap.add_argument("--limite-detalhe", type=int, default=None,
                    help="detalhar no maximo N por cargo/UF (para testar rapido)")
    a = ap.parse_args()
    coletar(a.cargos, not a.sem_detalhe, a.limite_detalhe)


if __name__ == "__main__":
    main()
