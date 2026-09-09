# Voto Consciente

Sua **cédula da eleição de 2026** montada só com dado público oficial. Você
escolhe o estado e vê, cargo por cargo, quem pediu registro — presidente,
governador, senador, deputado federal e deputado estadual/distrital — ordenado
por quanto cada um combina com o que você escreveu e por como trabalhou de fato:
como votou, quanto gastou de dinheiro público, quantas sessões faltou, quantos
projetos apresentou e o que a Justiça Eleitoral registra sobre a candidatura.

Você escreve com suas palavras o que defende ("sou conservador e cristão", "sou
socialista, defendo o SUS", "quero acima de tudo transparência") e o site ordena
os candidatos de cada cargo.

**A regra mais importante do projeto:** a maior parte dos 20.911 candidatos
nunca teve mandato federal, então não existe voto, presença nem cota para
avaliar. Nesses casos o site escreve **"sem nota"**, separa essas pessoas num
bloco à parte e mostra só o que o TSE informa. Ele nunca finge saber.

Custo para rodar e publicar: **zero**. Nenhum servidor para pagar e nenhuma
chave de API obrigatória.

---

## Rodar na sua máquina

Precisa apenas de Python 3.10 ou mais novo.

```bash
python -m etl.build --anos 2025 2026   # baixa e processa (~3 min na 1a vez)
python servir.py                       # abre http://localhost:8000
```

O primeiro comando gera os arquivos em `dados/`. O segundo sobe um servidor
local. Os downloads ficam em `cache/`, então rodar de novo é rápido.

Opções úteis:

```bash
python -m etl.build --casas camara            # só a Câmara (mais rápido)
python -m etl.build --anos 2023 2024 2025 2026  # legislatura inteira
python -m etl.build --noticias --limite-noticias 50  # busca menções na imprensa
python -m etl.build --sem-cache               # ignora o cache e rebaixa tudo
python tools/conferir.py                      # sanidade dos números gerados
```

### Atualizar as candidaturas de 2026

A cédula já vem versionada em `dados/cedula/`, então o comando acima funciona
sem instalar nada. Para rebaixar do TSE você precisa de um navegador de
verdade — o site do TSE devolve **403 para qualquer cliente que não seja
navegador** (a checagem é pela impressão digital do TLS, não pelo User-Agent:
nem `curl` com todos os cabeçalhos do Chrome passa):

```bash
python -m pip install playwright
python -m playwright install chromium
python tools/coletar_tse.py            # cédula inteira, ~20 min
python tools/coletar_tse.py --cargos 1 3 5   # só presidente/governador/senador
```

Isso grava `dados/tse/` (bruto, fora do git) e o `etl.build` seguinte
transforma em `dados/cedula/`. Detalhe que custou tempo: o headless **antigo**
do Chromium é barrado pelo WAF; é preciso `channel="chromium"` (headless novo).

## Publicar de graça na internet

O site é estático: HTML + JS + JSON. Não existe backend.

1. Crie um repositório **público** no GitHub e envie este projeto.
2. Em **Settings → Pages**, escolha `Source: GitHub Actions`.
3. Pronto. O workflow `.github/workflows/atualizar-dados.yml` roda toda segunda,
   recoleta os dados e republica o site.

O que isso consome do plano gratuito: cerca de 10 minutos de GitHub Actions por
semana (o limite é 2.000/mês, e é ilimitado em repositório público) e
hospedagem estática no GitHub Pages. Nada disso é cobrado.

Se quiser incluir as sanções da CGU (CEIS/CNEP), pegue a
[chave gratuita do Portal da Transparência](https://portaldatransparencia.gov.br/api-de-dados/cadastrar-email)
e salve em **Settings → Secrets → Actions** com o nome
`PORTAL_TRANSPARENCIA_KEY`. Sem ela o resto funciona igual.

---

## De onde vem cada número

| Fonte | O que traz | Precisa de chave? |
|---|---|---|
| [Câmara — Dados Abertos](https://dadosabertos.camara.leg.br/) | deputados, votos nominais, presença em sessões, autoria de proposições, frentes parlamentares | não |
| [Câmara — Cota Parlamentar](https://www.camara.leg.br/transparencia/gastos-parlamentares) | cada despesa reembolsada, com fornecedor e nota fiscal | não |
| [Senado — Dados Abertos](https://legis.senado.leg.br/dadosabertos/) | senadores, votações nominais de plenário, licenças, autorias | não |
| [TCU — Inabilitados](https://contas.tcu.gov.br/ords/f?p=1660:3) | quem foi inabilitado por contas julgadas irregulares | não |
| [CGU — CEIS/CNEP](https://portaldatransparencia.gov.br/sancoes) | sanções administrativas | sim (gratuita) |
| [GDELT](https://www.gdeltproject.org/) | menções em notícias (apenas informativo) | não |
| [TSE — Divulgação de Candidaturas](https://divulgacandcontas.tse.jus.br/divulga/) | as 20.911 candidaturas de 2026: situação do registro, Ficha Limpa, cassação, patrimônio, ocupação, escolaridade, coligação | não, mas exige navegador |

Em vez de milhares de chamadas de API, o ETL usa os **arquivos completos** que a
Câmara publica diariamente. São poucas dezenas de MB e trazem voto por voto.

## Como o ranking é calculado

**Quem entra no ranking com nota.** Só candidatos com mandato federal em
exercício, porque só deles existe registro de atuação. Os outros aparecem sem
nota, num bloco separado, com a ficha do TSE. O vínculo candidato ↔ mandato é
por nome, com regra conservadora: nome de urna só casa dentro do mesmo estado
(sem isso, o senador Eduardo Gomes, do Tocantins, casava com xarás candidatos a
deputado estadual no Acre e no Paraná); e se dois candidatos casam com o mesmo
mandato, ninguém leva o histórico.

**Presença e votações** são medidas a partir da chegada da pessoa, não do início
do período. Sem isso, ministro que deixou o cargo para disputar a eleição
aparecia com 8% de presença como se fosse faltoso — André Fufuca ia a 20%,
quando o número correto sobre o período em que esteve na Câmara é 79%.

**Qualificação** (cada item vira nota 0–100, comparando com os colegas da mesma casa):

- **presença** — sessões deliberativas de plenário com registro de presença;
- **votações** — em quantas votações nominais registrou voto;
- **projetos** — proposições de autoria própria, com peso 5x para as que viraram norma;
- **uso da cota** — percentil do gasto mensal. Gastar pouco não é virtude
  automática: é sinal para olhar;
- **integridade** — 100 sem registro de sanção; cai forte a cada sanção oficial.

**Posição ideológica** — a parte difícil, explicada em detalhe em `etl/espectro.py`.
Resumo: classificar votação por ementa quase não funciona (a maioria diz só
"altera a Lei nº X"). Então invertemos a pergunta: montamos dois grupos-âncora a
partir das frentes parlamentares que cada um assinou e verificamos quais votações
**separaram** esses grupos. A posição de cada parlamentar é o quanto ele votou com
um polo ou com o outro. Isso usa todas as votações nominais e mede comportamento,
não discurso.

Validação: as médias por partido saem na ordem que qualquer observador
reconhece (PT/PSOL/PCdoB/REDE num extremo, PL/NOVO no outro, centrão no meio),
sem que ninguém tenha rotulado partido nenhum — ver `python tools/conferir.py`.

## O que este projeto NÃO faz

- **Não trata acusação como condenação.** Só entra na nota o registro oficial de
  punição. Menção em notícia aparece como link e **não altera nota nenhuma**.
- **Não esconde incerteza.** O cruzamento de sanções é por nome e pode pegar
  homônimo: todo achado vem com aviso e link para a fonte. Cada perfil mostra a
  confiança do posicionamento, e a afinidade encolhe quando há pouco dado.
- **Não diz em quem votar.** Os pesos do ranking são seus, ajustáveis na tela.
- **Não dá nota a quem não tem histórico.** Candidato estreante aparece na
  cédula com a ficha do TSE e o rótulo "sem nota". Inventar um número ali seria
  pior do que não ter número.
- **Não avalia o trabalho de deputado estadual.** As 27 assembleias publicam
  dados de formas diferentes e não existe fonte nacional. Eles aparecem na
  cédula, mas só com o registro de candidatura.
- **Não sabe o resultado de eleições anteriores.** O TSE devolve o cargo e o
  resultado das candidaturas passadas com campos inconsistentes; por isso
  guardamos apenas os anos em que a pessoa concorreu, e o resto fica no link
  para a fonte.

## Estrutura

```
etl/
  build.py       orquestra tudo e gera os JSON
  espectro.py    posição ideológica a partir das votações
  temas.py       eixos, dicionário de termos e classificação de ementas
  notas.py       consolidação dos eixos e cálculo das notas
  util.py        rede com cache, leitura de CSV, download tolerante a falha
  fontes/        um módulo por fonte: camara, cota, senado, integridade, tse
web/             site estático (HTML, CSS, JS puro)
dados/
  ranking.json   quem está no cargo hoje
  cedula/        candidaturas de 2026, um arquivo por UF e cargo (versionado)
  p/             detalhe de cada parlamentar
  tse/           bruto do TSE (fora do git; refaz com tools/coletar_tse.py)
tools/coletar_tse.py  coleta as candidaturas (único passo que exige navegador)
tools/conferir.py     checagem de sanidade dos dados
```

Licença: MIT. Os dados são públicos e pertencem a quem paga por eles.
