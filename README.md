# Voto Consciente

Ranking de deputados e senadores brasileiros construído **só com dado público
oficial**: como votaram, quanto gastaram de dinheiro público, quantas sessões
faltaram, quantos projetos apresentaram e se têm sanção registrada.

Você escreve com suas palavras o que defende ("sou conservador e cristão", "sou
socialista, defendo o SUS", "quero acima de tudo transparência") e o site mostra
o Top 10 de quem **combina com você** e ao mesmo tempo **trabalha bem**.

Custo para rodar e publicar: **zero**. Nenhuma dependência para instalar, nenhum
servidor para pagar, nenhuma chave de API obrigatória.

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

Em vez de milhares de chamadas de API, o ETL usa os **arquivos completos** que a
Câmara publica diariamente. São poucas dezenas de MB e trazem voto por voto.

## Como o ranking é calculado

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
- **Não cobre candidatos estreantes.** Quem nunca teve mandato não tem votação,
  presença nem cota para analisar. O foco é quem já exerce o cargo — que é
  justamente quem se apresenta à reeleição.

## Estrutura

```
etl/
  build.py       orquestra tudo e gera os JSON
  espectro.py    posição ideológica a partir das votações
  temas.py       eixos, dicionário de termos e classificação de ementas
  notas.py       consolidação dos eixos e cálculo das notas
  util.py        rede com cache, leitura de CSV, download tolerante a falha
  fontes/        um módulo por fonte: camara, cota, senado, integridade
web/             site estático (HTML, CSS, JS puro)
dados/           saída do ETL, versionada
tools/conferir.py  checagem de sanidade dos dados
```

Licença: MIT. Os dados são públicos e pertencem a quem paga por eles.
