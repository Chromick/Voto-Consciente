/* Voto Consciente - toda a interacao roda no navegador, lendo JSON estatico. */

const ESTADO = {
  lexico: null,
  eixos: null,
  dados: null,
  meta: null,
  perfil: null,
  termos: [],
  pesos: {
    afinidade: 40, presenca: 15, participacao: 15,
    producao: 10, economia: 10, integridade: 10,
  },
};

const ROTULO_PESO = {
  afinidade: "Combinar comigo",
  presenca: "Presença",
  participacao: "Vota nas sessões",
  producao: "Projetos próprios",
  economia: "Gasta pouco da cota",
  integridade: "Ficha sem sanção",
};

const $ = (s) => document.querySelector(s);
const criar = (tag, cls, html) => {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  if (html !== undefined) el.innerHTML = html;
  return el;
};
const dinheiro = (v) =>
  v == null ? "—" : v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
const pct = (v) => (v == null ? "—" : `${Math.round(v)}%`);

/* ------------------------------------------------------------------ *
 * Leitura do texto do usuario (mesmo lexico usado no ETL)
 * ------------------------------------------------------------------ */
function semAcento(s) {
  return s.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

function vetorDeTexto(texto) {
  const t = semAcento((texto || "").toLowerCase()).replace(/\s+/g, " ");
  const acumulado = {}, peso = {}, achados = [];
  const termos = Object.keys(ESTADO.lexico).sort((a, b) => b.length - a.length);
  for (const termo of termos) {
    if (!termo) continue;
    const escapado = termo.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    if (new RegExp(`(^|[^a-z])${escapado}([^a-z]|$)`).test(t)) {
      achados.push(termo);
      for (const [eixo, v] of Object.entries(ESTADO.lexico[termo])) {
        acumulado[eixo] = (acumulado[eixo] || 0) + v;
        peso[eixo] = (peso[eixo] || 0) + Math.abs(v);
      }
    }
  }
  const vetor = {};
  for (const eixo of Object.keys(ESTADO.eixos)) {
    if (eixo === "geral") continue;
    vetor[eixo] = peso[eixo] ? +(acumulado[eixo] / peso[eixo]).toFixed(3) : null;
  }
  vetor.geral = derivarGeral(vetor);
  return { vetor, achados };
}

/* O eixo geral (esquerda-direita) e derivado dos tematicos, com a mesma
   formula usada no ETL (dados/lexico.json traz os sinais). */
function derivarGeral(vetor) {
  let soma = 0, peso = 0;
  for (const [eixo, sinal] of Object.entries(ESTADO.sinalGeral || {})) {
    const v = vetor[eixo];
    if (!sinal || v == null || v === 0) continue;
    soma += sinal * v * Math.abs(v);
    peso += Math.abs(v);
  }
  return peso ? +(soma / peso).toFixed(3) : null;
}

/* Afinidade: media ponderada da proximidade em cada eixo que a pessoa expressou.
   Peso = intensidade com que ela expressou aquele eixo.

   Dois cuidados que evitam resultado enganoso:
   - exige pelo menos 2 eixos comparaveis (1 eixo isolado dava "100% combina"
     para quem quase nao tem dado);
   - encolhe o resultado na direcao de 50% quando a confianca no perfil do
     parlamentar e baixa. Pouco dado nao pode virar certeza. */
function afinidade(perfil, candidato) {
  if (!perfil) return null;
  let soma = 0, peso = 0;
  const contribuicoes = [];
  for (const [eixo, u] of Object.entries(perfil)) {
    if (u == null || Math.abs(u) < 0.08) continue;
    const c = candidato.eixos ? candidato.eixos[eixo] : undefined;
    if (c == null) continue;
    const prox = 1 - Math.abs(u - c) / 2;   // 0..1
    const w = Math.abs(u);
    soma += prox * w;
    peso += w;
    contribuicoes.push({ eixo, usuario: u, candidato: c, prox });
  }
  if (!peso || contribuicoes.length < 2) return null;
  const bruto = (soma / peso) * 100;
  const conf = Math.max(0.15, Math.min(1, candidato.confianca_eixos ?? 0));
  return {
    valor: Math.round(50 + (bruto - 50) * conf),
    bruto: Math.round(bruto),
    confianca: conf,
    contribuicoes,
    eixosUsados: contribuicoes.length,
  };
}

function notaGeral(p, af) {
  const partes = [];
  const add = (chave, valor) => {
    const w = ESTADO.pesos[chave];
    if (w > 0 && valor != null) partes.push([valor, w]);
  };
  add("afinidade", af ? af.valor : null);
  add("presenca", p.notas.presenca);
  add("participacao", p.notas.participacao);
  add("producao", p.notas.producao);
  add("economia", p.notas.economia);
  add("integridade", p.notas.integridade);
  if (!partes.length) return 0;
  const soma = partes.reduce((s, [v, w]) => s + v * w, 0);
  const peso = partes.reduce((s, [, w]) => s + w, 0);
  return soma / peso;
}

/* ------------------------------------------------------------------ *
 * Ranking
 * ------------------------------------------------------------------ */
function filtrar(lista) {
  const casa = $("#f-casa").value;
  const uf = $("#f-uf").value;
  const partido = $("#f-partido").value;
  const limpo = $("#f-limpo").checked;
  const robusto = $("#f-confianca").checked;
  const busca = semAcento($("#f-busca").value.toLowerCase().trim());
  return lista.filter((p) => {
    if (casa && p.casa !== casa) return false;
    if (uf && p.uf !== uf) return false;
    if (partido && p.partido !== partido) return false;
    if (limpo && p.n_sancoes > 0) return false;
    if (robusto && (p.confianca_eixos || 0) < 0.5) return false;
    if (busca && !semAcento(p.nome.toLowerCase()).includes(busca)) return false;
    return true;
  });
}

function calcularRanking() {
  const lista = filtrar(ESTADO.dados.parlamentares).map((p) => {
    const af = afinidade(ESTADO.perfil, p);
    return { p, af, geral: notaGeral(p, af) };
  });
  lista.sort((a, b) => b.geral - a.geral);
  return lista;
}

function cardParlamentar(item, posicao) {
  const { p, af, geral } = item;
  const card = criar("div", `card${posicao <= 3 ? " ouro" : ""}`);
  card.appendChild(criar("div", "pos", String(posicao)));

  const cabeca = criar("div", "cabeca");
  const img = criar("img");
  img.src = p.foto || "";
  img.alt = p.nome;
  img.loading = "lazy";
  img.onerror = () => { img.style.visibility = "hidden"; };
  cabeca.appendChild(img);
  cabeca.appendChild(criar("div", null,
    `<div class="nome">${p.nome}</div>
     <div class="meta">${p.partido || "sem partido"} · ${p.uf} · ${p.casa === "senado" ? "Senado" : "Câmara"}</div>`));
  card.appendChild(cabeca);

  card.appendChild(criar("div", "selo-geral", `${Math.round(geral)}<small>NOTA GERAL</small>`));
  if (af) {
    const selo = criar("div", "selo-afinidade", `${af.valor}% combina com você`);
    selo.title = `Proximidade bruta ${af.bruto}% em ${af.eixosUsados} eixos, ` +
      `ajustada pela confiança dos dados (${Math.round(af.confianca * 100)}%).`;
    card.appendChild(selo);
  } else if (ESTADO.perfil) {
    card.appendChild(criar("div", "badge info", "sem dado suficiente para comparar ideologia"));
  }

  const notas = criar("div", "notas-mini");
  const linhas = [
    ["Presença", p.notas.presenca],
    ["Votações", p.notas.participacao],
    ["Projetos", p.notas.producao],
    ["Uso da cota", p.notas.economia],
  ];
  for (const [rotulo, valor] of linhas) {
    const l = criar("div", "nota-mini");
    l.appendChild(criar("span", null, rotulo));
    const barra = criar("div", "barra");
    barra.appendChild(criar("span", null, "")).style.width = `${valor == null ? 0 : valor}%`;
    l.appendChild(barra);
    l.appendChild(criar("b", null, valor == null ? "—" : Math.round(valor)));
    notas.appendChild(l);
  }
  card.appendChild(notas);

  const badges = criar("div", "badges");
  if (p.n_sancoes > 0) {
    badges.appendChild(criar("span", "badge grave", `${p.n_sancoes} sanção oficial`));
  } else {
    badges.appendChild(criar("span", "badge ok", "sem sanção encontrada"));
  }
  if (p.n_mencoes > 0) badges.appendChild(criar("span", "badge", `${p.n_mencoes} menção na imprensa`));
  if (p.n_alertas > 0) badges.appendChild(criar("span", "badge", `${p.n_alertas} ponto de atenção`));
  if ((p.confianca_eixos || 0) < 0.5) {
    badges.appendChild(criar("span", "badge info", "pouco histórico para posicionar"));
  }
  card.appendChild(badges);

  card.onclick = () => abrirDetalhe(p.id);
  return card;
}

function renderizar() {
  const lista = calcularRanking();
  const topo = $("#top10");
  topo.innerHTML = "";
  lista.slice(0, 10).forEach((item, i) => topo.appendChild(cardParlamentar(item, i + 1)));
  if (!lista.length) topo.appendChild(criar("p", "carregando", "Nenhum parlamentar com esses filtros."));

  $("#contagem").textContent = `${lista.length} parlamentares no cálculo`;
  $("#rotulo-contexto").textContent = ESTADO.perfil
    ? "para o seu perfil"
    : "por qualificação (escreva sua posição acima para personalizar)";

  const corpo = $("#tabela tbody");
  corpo.innerHTML = "";
  lista.forEach((item, i) => {
    const { p, af, geral } = item;
    const tr = criar("tr");
    tr.innerHTML = `
      <td>${i + 1}</td>
      <td><strong>${p.nome}</strong><br><small>${p.partido || "—"} · ${p.uf}</small></td>
      <td>${af ? af.valor + "%" : "—"}</td>
      <td><strong>${Math.round(geral)}</strong></td>
      <td>${pct(p.notas.presenca)}</td>
      <td>${pct(p.notas.participacao)}</td>
      <td>${p.metricas.autorias ?? 0}${p.metricas.autorias_aprovadas ? ` (${p.metricas.autorias_aprovadas} lei)` : ""}</td>
      <td>${dinheiro(p.metricas.gasto_mensal)}</td>
      <td>${p.n_sancoes ? `<span class="badge grave">sanção</span>` : (p.n_alertas || "—")}</td>`;
    tr.onclick = () => abrirDetalhe(p.id);
    corpo.appendChild(tr);
  });
}

/* ------------------------------------------------------------------ *
 * Cedula de 2026: todos os cargos que o eleitor escolhe na urna
 *
 * Aqui a populacao e diferente do ranking de mandato: a maioria dos
 * candidatos NUNCA teve mandato federal, entao nao existe voto, presenca nem
 * cota para avaliar. Em vez de fingir uma nota, mostramos o que existe e
 * dizemos em que ela se baseia.
 * ------------------------------------------------------------------ */
const CACHE_CEDULA = new Map();

const NOME_UF = {
  AC: "Acre", AL: "Alagoas", AM: "Amazonas", AP: "Amapá", BA: "Bahia",
  CE: "Ceará", DF: "Distrito Federal", ES: "Espírito Santo", GO: "Goiás",
  MA: "Maranhão", MG: "Minas Gerais", MS: "Mato Grosso do Sul", MT: "Mato Grosso",
  PA: "Pará", PB: "Paraíba", PE: "Pernambuco", PI: "Piauí", PR: "Paraná",
  RJ: "Rio de Janeiro", RN: "Rio Grande do Norte", RO: "Rondônia", RR: "Roraima",
  RS: "Rio Grande do Sul", SC: "Santa Catarina", SE: "Sergipe", SP: "São Paulo",
  TO: "Tocantins",
};

/* Ordem real da urna em 2026. Senado elege duas vagas (renovação de 2/3);
   governador e presidente levam o vice na mesma chapa. */
const SLOTS_URNA = [
  { id: "dep-fed", cargo: 6, titulo: "Deputado Federal", curto: "Dep. federal" },
  { id: "dep-est", cargo: "estadual", titulo: "Deputado Estadual", tituloDF: "Deputado Distrital", curto: "Dep. estadual" },
  { id: "sen-1", cargo: 5, titulo: "Senador — 1ª vaga", curto: "Senador 1", senadoSlot: 0 },
  { id: "sen-2", cargo: 5, titulo: "Senador — 2ª vaga", curto: "Senador 2", senadoSlot: 1 },
  { id: "gov", cargo: 3, titulo: "Governador e vice-governador", curto: "Governador", vice: 4 },
  { id: "pres", cargo: 1, titulo: "Presidente e vice-presidente", curto: "Presidente", vice: 2, ufFixa: "BR" },
];

async function carregarCedula(uf, cargo) {
  const chave = `${uf}-${cargo}`;
  if (CACHE_CEDULA.has(chave)) return CACHE_CEDULA.get(chave);
  let dado = { candidatos: [] };
  try {
    const r = await fetch(`dados/cedula/${chave}.json`);
    if (r.ok) {
      dado = await r.json();
      // o cargo fica no cabecalho do arquivo; o card precisa dele no item
      for (const c of dado.candidatos) { c.cargo = dado.cargo; c.uf = dado.uf; }
    }
  } catch (e) { /* cargo inexistente naquela UF (ex.: distrital fora do DF) */ }
  CACHE_CEDULA.set(chave, dado);
  return dado;
}

/* Quanto do candidato conseguimos de fato verificar. Vira selo no card:
   o eleitor precisa saber se a nota vem de registro publico de atuacao ou
   apenas da ficha de candidatura. */
function baseDeAvaliacao(c) {
  if (c.mandato) return { nivel: "completo", texto: "mandato atual verificado" };
  const anteriores = (c.anteriores_anos || []).length;
  if (anteriores > 1) {
    return { nivel: "parcial", texto: `${anteriores} candidaturas anteriores` };
  }
  return { nivel: "minimo", texto: "sem histórico parlamentar federal" };
}

/* A foto do TSE tem endereco previsivel; o JSON guarda so um booleano. */
function fotoCandidato(c) {
  if (c.foto) return c.foto;              // veio do mandato (Camara/Senado)
  if (!c.tem_foto) return "";
  const el = (ESTADO.cedula || {}).id_eleicao || "20322002026";
  return `https://divulgacandcontas.tse.jus.br/divulga/rest/arquivo/img/${el}/${c.id}/${c.uf}`;
}

/* So existe "nota geral" para quem tem atuacao registrada para avaliar.
   Quem nunca teve mandato federal nao tem presenca, voto, projeto nem cota:
   o unico numero disponivel seria a situacao do registro, e ai TODO candidato
   com registro deferido apareceria com 100 - um desconhecido empatado com um
   parlamentar de otima folha. Nesse caso devolvemos null e a interface diz,
   com todas as letras, que nao ha o que avaliar. */
function notaCandidato(c, af) {
  if (!c.mandato) return null;
  const partes = [];
  const add = (chave, valor) => {
    const w = ESTADO.pesos[chave];
    if (w > 0 && valor != null) partes.push([valor, w]);
  };
  add("afinidade", af ? af.valor : null);
  const n = c.notas || {};
  add("presenca", n.presenca);
  add("participacao", n.participacao);
  add("producao", n.producao);
  add("economia", n.economia);
  // integridade: junta a sancao administrativa com a situacao do registro
  const integridade = n.integridade == null
    ? c.nota_registro
    : Math.min(n.integridade, c.nota_registro);
  add("integridade", integridade);
  if (!partes.length) return null;
  const soma = partes.reduce((s, [v, w]) => s + v * w, 0);
  const peso = partes.reduce((s, [, w]) => s + w, 0);
  return soma / peso;
}

/* Sem mandato nao ha voto para medir ideologia; sobra a media do partido.
   E um sinal fraco de proposito - por isso entra com confianca baixa, o que
   puxa a afinidade para perto de 50%. */
function afinidadeCandidato(c) {
  if (!ESTADO.perfil) return null;
  if (c.eixos && Object.keys(c.eixos).length) return afinidade(ESTADO.perfil, c);
  const doPartido = (ESTADO.dados.partidos || {})[c.partido];
  if (!doPartido) return null;
  const af = afinidade(ESTADO.perfil, { eixos: doPartido, confianca_eixos: 0.3 });
  if (af) af.viaPartido = true;
  return af;
}

/* Devolve dois grupos, deliberadamente separados: quem da para avaliar pelo
   que fez, e quem so tem ficha de candidatura. Misturar os dois numa lista
   unica daria a impressao de que sao comparaveis - e nao sao. */
function rankearCedula(lista) {
  const soHistorico = $("#c-so-historico").checked;
  const soAptos = $("#c-so-aptos").checked;
  const busca = semAcento($("#c-busca").value.toLowerCase().trim());
  const filtrados = lista.filter((c) => {
    if (soHistorico && !c.mandato) return false;
    if (soAptos && (c.alertas_tse || []).some((a) => a.tipo === "registro" || a.tipo === "inapto")) return false;
    if (busca) {
      const alvo = semAcento(`${c.urna || ""} ${c.nome || ""}`.toLowerCase());
      if (!alvo.includes(busca)) return false;
    }
    return true;
  }).map((c) => {
    const af = afinidadeCandidato(c);
    return { c, af, geral: notaCandidato(c, af) };
  });

  const avaliaveis = filtrados.filter((x) => x.geral != null)
    .sort((a, b) => b.geral - a.geral);
  // sem nota: ordena pela afinidade estimada do partido e, sem perfil, por nome
  const demais = filtrados.filter((x) => x.geral == null)
    .sort((a, b) => (b.af ? b.af.valor : -1) - (a.af ? a.af.valor : -1)
      || ((b.c.anteriores_anos || []).length - (a.c.anteriores_anos || []).length)
      || (a.c.urna || "").localeCompare(b.c.urna || ""));
  return { avaliaveis, demais };
}

function cargoEstadual(uf) {
  return uf === "DF" ? 8 : 7;
}

function parDaChapa(titular, lista) {
  if (!titular || !lista || !lista.length) return null;
  const n = titular.numero;
  const mesmos = lista.filter((c) => c.numero === n && c.id !== titular.id);
  const semRenuncia = mesmos.filter((c) =>
    !(c.alertas_tse || []).some((a) => /ren[uú]ncia/i.test(a.texto)));
  const validos = semRenuncia.filter((c) =>
    !(c.alertas_tse || []).some((a) => a.tipo === "inapto" || a.tipo === "registro"));
  return validos[0] || semRenuncia[0] || mesmos[0] || null;
}

function filaDoCargo(lista) {
  const { avaliaveis, demais } = rankearCedula(lista);
  return [...avaliaveis, ...demais];
}

/* A urna e uma sugestao de VOTO, nao um ranking de "quem trabalha melhor".
   Ter mandato ajuda a ter certeza, mas nao pode fazer um candidato de 8% de
   afinidade passar na frente de um de 65% so porque o segundo nunca foi
   deputado. A lista de "todos os candidatos" continua separada (rankearCedula). */
function pontuacaoUrna(item) {
  const af = item.af ? item.af.valor : null;
  const nota = item.geral;
  const registro = item.c.nota_registro ?? 70;
  if (ESTADO.perfil) {
    const afin = af == null ? 50 : af;
    if (nota != null) return afin * 0.72 + nota * 0.28;
    return afin * 0.88 + registro * 0.12;
  }
  if (nota != null) return nota;
  return ((item.c.anteriores_anos || []).length) * 8 + registro * 0.2;
}

function filaUrna(lista) {
  const { avaliaveis, demais } = rankearCedula(lista);
  return [...avaliaveis, ...demais].sort((a, b) => pontuacaoUrna(b) - pontuacaoUrna(a));
}

function porqueSugestao(item) {
  if (!item) return "Nenhum candidato válido com os filtros atuais.";
  const partes = [];
  if (item.c.mandato) partes.push("tem mandato federal para conferir");
  if (item.af && !item.af.viaPartido) {
    partes.push(`${item.af.valor}% de afinidade com o que você escreveu`);
  } else if (item.af && item.af.viaPartido) {
    partes.push(`afinidade estimada pelo partido ${item.c.partido} (${item.af.valor}%) — sem votos individuais`);
  }
  if (item.geral != null) partes.push(`nota ${Math.round(item.geral)} no que dá para medir`);
  if (!partes.length) {
    partes.push("melhor ficha de registro entre os candidatos válidos — sem mandato federal para avaliar o trabalho");
  }
  return partes.join(" · ");
}

function abrirSugestao(item) {
  if (!item) return;
  if (item.c.mandato) abrirDetalhe(item.c.mandato.id);
  else abrirCandidato(item.c);
}

function linhaChapa(rotulo, pessoa) {
  if (!pessoa) return "";
  return `<div>${rotulo}: <strong>${pessoa.urna || pessoa.nome}</strong> (${pessoa.partido || "—"}${pessoa.mandato ? " · mandato verificado" : ""})</div>`;
}

function montarSlot(def, item, extras) {
  const slot = criar("article", `slot-urna${item ? " clickavel" : ""}`);
  const numero = item && item.c.numero != null ? String(item.c.numero) : "—";
  slot.appendChild(criar("div", "numero-voto", numero));
  const corpo = criar("div");
  const titulo = def.tituloDF && $("#c-uf").value === "DF" ? def.tituloDF : def.titulo;
  corpo.appendChild(criar("p", "cargo-slot", titulo));
  if (!item) {
    corpo.appendChild(criar("h3", null, "Sem sugestão"));
    corpo.appendChild(criar("p", "porque", porqueSugestao(null)));
    slot.appendChild(corpo);
    return slot;
  }
  const nomeVice = extras.vice ? ` / ${extras.vice.urna || extras.vice.nome}` : "";
  corpo.appendChild(criar("h3", null, `${item.c.urna || item.c.nome}${nomeVice}`));
  const chapa = criar("div", "chapa");
  chapa.innerHTML = [
    `${item.c.partido || "sem partido"} · ${item.c.uf} · nº ${item.c.numero ?? "—"}`,
    extras.vice ? linhaChapa("Vice", extras.vice) : "",
    extras.sup1 ? linhaChapa("1º suplente", extras.sup1) : "",
    extras.sup2 ? linhaChapa("2º suplente", extras.sup2) : "",
  ].filter(Boolean).join("");
  corpo.appendChild(chapa);
  corpo.appendChild(criar("p", "porque", porqueSugestao(item)));
  if (extras.alts && extras.alts.length) {
    const ul = criar("ul", "alts");
    extras.alts.forEach((alt, i) => {
      ul.appendChild(criar("li", null,
        `Outra opção: ${alt.c.urna || alt.c.nome} (${alt.c.numero ?? "—"}${alt.af ? ` · ${alt.af.valor}% afinidade` : ""})`));
    });
    corpo.appendChild(ul);
  }
  const base = baseDeAvaliacao(item.c);
  corpo.appendChild(criar("span", "selo-base", base.texto));
  slot.appendChild(corpo);
  slot.onclick = () => abrirSugestao(item);
  return slot;
}

async function renderizarUrna() {
  const alvo = $("#slots-urna");
  const faixa = $("#numeros-urna");
  const uf = $("#c-uf") && $("#c-uf").value;
  if (!alvo || !uf || !ESTADO.cedula) return;
  alvo.innerHTML = "<p class='carregando'>Montando a urna do seu estado...</p>";
  faixa.hidden = true;

  const depEst = cargoEstadual(uf);
  const [fed, est, sen, gov, viceGov, pres, vicePres, sup1, sup2] = await Promise.all([
    carregarCedula(uf, 6),
    carregarCedula(uf, depEst),
    carregarCedula(uf, 5),
    carregarCedula(uf, 3),
    carregarCedula(uf, 4),
    carregarCedula("BR", 1),
    carregarCedula("BR", 2),
    carregarCedula(uf, 9),
    carregarCedula(uf, 10),
  ]);

  const senado = filaUrna(sen.candidatos || []);
  const escolhidos = {};
  const extras = {};

  for (const def of SLOTS_URNA) {
    if (def.senadoSlot != null) {
      const item = senado[def.senadoSlot] || null;
      escolhidos[def.id] = item;
      extras[def.id] = item ? {
        sup1: parDaChapa(item.c, sup1.candidatos || []),
        sup2: parDaChapa(item.c, sup2.candidatos || []),
        alts: senado.filter((x, i) => i !== def.senadoSlot && i < 4).slice(0, 2),
      } : { alts: [] };
      continue;
    }
    const cargo = def.cargo === "estadual" ? depEst : def.cargo;
    const bloco = cargo === 6 ? fed : cargo === depEst ? est : cargo === 3 ? gov : pres;
    const fila = filaUrna(bloco.candidatos || []);
    const item = fila[0] || null;
    escolhidos[def.id] = item;
    const viceLista = def.vice === 4 ? (viceGov.candidatos || []) : def.vice === 2 ? (vicePres.candidatos || []) : [];
    extras[def.id] = {
      vice: item ? parDaChapa(item.c, viceLista) : null,
      alts: fila.slice(1, 3),
    };
  }

  alvo.innerHTML = "";
  faixa.innerHTML = "";
  faixa.hidden = false;
  for (const def of SLOTS_URNA) {
    const item = escolhidos[def.id];
    const titulo = def.tituloDF && uf === "DF" && def.id === "dep-est" ? "Dep. distrital" : def.curto;
    const dig = criar("div", "digito",
      `<small>${titulo}</small><b>${item && item.c.numero != null ? item.c.numero : "—"}</b>`);
    faixa.appendChild(dig);
    alvo.appendChild(montarSlot(def, item, extras[def.id]));
  }

  const comHistorico = Object.values(escolhidos).filter((x) => x && x.c.mandato).length;
  $("#urna-contagem").textContent =
    `${uf} · ${SLOTS_URNA.length} cargos · ${comHistorico} sugestões com mandato federal verificado`;
  if (!ESTADO.perfil) {
    const aviso = criar("p", "dica");
    aviso.textContent = "Sem o seu texto, a ordem usa só quem já trabalha no cargo e a ficha do TSE. Escreva sua posição para personalizar.";
    alvo.prepend(aviso);
  }
}

function cardCandidato(item, posicao) {
  const { c, af, geral } = item;
  const base = baseDeAvaliacao(c);
  const card = criar("div", `card${posicao <= 3 ? " ouro" : ""} base-${base.nivel}`);
  card.appendChild(criar("div", "pos", String(posicao)));

  const cabeca = criar("div", "cabeca");
  const img = criar("img");
  img.src = fotoCandidato(c);
  img.alt = c.urna || "";
  img.loading = "lazy";
  img.onerror = () => { img.style.visibility = "hidden"; };
  cabeca.appendChild(img);
  cabeca.appendChild(criar("div", null,
    `<div class="nome">${c.urna || c.nome}</div>
     <div class="meta">${c.numero ?? "—"} · ${c.partido || "sem partido"} · ${c.uf}</div>`));
  card.appendChild(cabeca);

  if (geral != null) {
    card.appendChild(criar("div", "selo-geral", `${Math.round(geral)}<small>NOTA GERAL</small>`));
  } else {
    const s = criar("div", "selo-geral sem-nota", `—<small>SEM NOTA</small>`);
    s.title = "Não há mandato federal para avaliar: sem votos, presença, projetos ou cota.";
    card.appendChild(s);
  }
  if (af) {
    const selo = criar("div", "selo-afinidade", `${af.valor}% combina com você`);
    selo.title = af.viaPartido
      ? "Estimado pela média do partido — não há votos deste candidato para medir."
      : `Proximidade bruta ${af.bruto}% em ${af.eixosUsados} eixos.`;
    if (af.viaPartido) selo.classList.add("fraco");
    card.appendChild(selo);
  }

  if (c.mandato) {
    const n = c.notas || {};
    const notas = criar("div", "notas-mini");
    for (const [rotulo, valor] of [["Presença", n.presenca], ["Votações", n.participacao],
                                   ["Projetos", n.producao], ["Uso da cota", n.economia]]) {
      const l = criar("div", "nota-mini");
      l.appendChild(criar("span", null, rotulo));
      const barra = criar("div", "barra");
      barra.appendChild(criar("span", null, "")).style.width = `${valor == null ? 0 : valor}%`;
      l.appendChild(barra);
      l.appendChild(criar("b", null, valor == null ? "—" : Math.round(valor)));
      notas.appendChild(l);
    }
    card.appendChild(notas);
  } else {
    const ficha = criar("div", "ficha-tse");
    const linhas = [];
    if (c.ocupacao) linhas.push(["Ocupação", c.ocupacao]);
    if (c.instrucao) linhas.push(["Escolaridade", c.instrucao]);
    if (c.bens != null) linhas.push(["Patrimônio declarado", dinheiro(c.bens)]);
    if ((c.anteriores_anos || []).length) linhas.push(["Já concorreu", `${c.anteriores_anos.length}x`]);
    ficha.innerHTML = linhas.map(([k, v]) => `<div><span>${k}</span><b>${v}</b></div>`).join("");
    card.appendChild(ficha);
  }

  const badges = criar("div", "badges");
  badges.appendChild(criar("span", `badge ${base.nivel === "completo" ? "ok" : "info"}`, base.texto));
  for (const a of (c.alertas_tse || [])) {
    badges.appendChild(criar("span", "badge grave", a.texto));
  }
  if (!(c.alertas_tse || []).length && c.situacao) {
    badges.appendChild(criar("span", "badge ok", `registro ${c.situacao.toLowerCase()}`));
  }
  if (c.reeleicao) badges.appendChild(criar("span", "badge", "tenta reeleição"));
  card.appendChild(badges);

  card.onclick = () => (c.mandato ? abrirDetalhe(c.mandato.id) : abrirCandidato(c));
  return card;
}

function abrirCandidato(c) {
  const el = $("#modal-conteudo");
  // o TSE so devolve o ANO das candidaturas anteriores de forma confiavel
  const anos = c.anteriores_anos || [];
  const alertas = (c.alertas_tse || []).map((a) => `<li>${a.texto}</li>`).join("");
  el.innerHTML = `
    <div class="detalhe-topo">
      ${fotoCandidato(c) ? `<img src="${fotoCandidato(c)}" alt="">` : ""}
      <div>
        <h2>${c.urna || c.nome}</h2>
        <p class="meta">${ESTADO.cedula.cargos[c.cargo] || ""} · ${c.uf} · ${c.partido || "sem partido"} · nº ${c.numero ?? "—"}</p>
        <p class="meta">Nome completo: ${c.nome || "—"}</p>
        ${c.coligacao_composicao ? `<p class="meta">Coligação: ${c.coligacao_composicao}</p>` : ""}
      </div>
    </div>
    <div class="cartoes">
      <div class="cartao"><span>SITUAÇÃO DO REGISTRO</span><strong>${c.situacao || "—"}</strong>
        <small>${c.apto ? "candidatura apta" : "verifique a situação"}</small></div>
      <div class="cartao"><span>PATRIMÔNIO DECLARADO</span><strong>${dinheiro(c.bens)}</strong>
        <small>declarado ao TSE em 2026</small></div>
      <div class="cartao"><span>OCUPAÇÃO</span><strong>${c.ocupacao || "—"}</strong>
        <small>${c.instrucao || ""}</small></div>
    </div>
    <p class="aviso-modal">Este candidato não tem mandato federal em exercício, então
      não há votos, presença nem cota parlamentar para avaliar. O que aparece aqui é o
      que consta no registro de candidatura do TSE.</p>
    ${alertas ? `<h3>Pontos de atenção no registro</h3><ul class="lista-alertas">${alertas}</ul>` : ""}
    ${anos.length ? `<h3>Já concorreu antes</h3>
      <p class="meta">Pediu registro em ${anos.join(", ")}. O resultado de cada
      uma está na página do TSE, no link abaixo.</p>` : ""}
    ${c.sites && c.sites.length ? `<h3>Links declarados</h3><ul class="lista-alertas">${
      c.sites.map((s) => `<li><a href="${s}" target="_blank" rel="noopener">${s}</a></li>`).join("")}</ul>` : ""}
    <p class="fonte-link"><a href="https://divulgacandcontas.tse.jus.br/divulga/#/candidato/2026/20322002026/${c.uf}/${c.id}"
       target="_blank" rel="noopener">Ver a candidatura completa no TSE →</a></p>`;
  $("#modal").classList.remove("oculto");
}

let LIMITE_CEDULA = 12;

/* Presidente e nacional: o arquivo fica em BR, nao na UF do eleitor. */
function ufDoCargo(cargo) {
  const c = (ESTADO.cedula || {}).contagem || {};
  return c[`BR-${cargo}`] ? "BR" : $("#c-uf").value;
}

async function renderizarCedula() {
  const cargo = ESTADO.cargoAtivo;
  const uf = ufDoCargo(cargo);
  if (!uf || !cargo) return;
  const alvo = $("#lista-cedula");
  alvo.innerHTML = "<p class='carregando'>Carregando candidatos...</p>";
  const dado = await carregarCedula(uf, cargo);
  const { avaliaveis, demais } = rankearCedula(dado.candidatos || []);
  alvo.innerHTML = "";

  // Com os dois grupos na tela, "#1" seria lido como "o melhor de todos".
  // O titulo diz de que lista aquele primeiro lugar e.
  if (avaliaveis.length && demais.length) {
    const cabeca = criar("div", "divisor-grupo forte");
    cabeca.innerHTML = `<h3>Dá para avaliar pelo que já fez (${avaliaveis.length})</h3>
      <p>Exercem mandato federal hoje, então há voto, presença, projetos e uso da
      cota para conferir. A ordem abaixo usa esses números e o seu perfil.</p>`;
    alvo.appendChild(cabeca);
  }
  avaliaveis.forEach((item, i) => alvo.appendChild(cardCandidato(item, i + 1)));

  if (demais.length) {
    const aviso = criar("div", "divisor-grupo");
    aviso.innerHTML = `<h3>Sem histórico federal para avaliar (${demais.length})</h3>
      <p>Estes candidatos não têm voto, presença nem cota parlamentar registrados —
      não é possível dar nota ao trabalho deles. Aparece o que a Justiça Eleitoral
      informa: situação do registro, patrimônio declarado e candidaturas anteriores.
      ${ESTADO.perfil ? "A afinidade mostrada é estimada pela média do partido." : ""}</p>`;
    alvo.appendChild(aviso);
    demais.slice(0, LIMITE_CEDULA).forEach((item, i) =>
      alvo.appendChild(cardCandidato(item, i + 1)));
  }

  if (!avaliaveis.length && !demais.length) {
    alvo.appendChild(criar("p", "carregando", "Nenhum candidato com esses filtros."));
  }
  $("#c-mais").classList.toggle("oculto", demais.length <= LIMITE_CEDULA);
  $("#cedula-contagem").textContent =
    `${avaliaveis.length + demais.length} candidatos · ${avaliaveis.length} com mandato para conferir`;
}

function montarCedula() {
  const indice = ESTADO.cedula;
  if (!indice) return;
  const seletor = $("#c-uf");
  const ufs = [...new Set(Object.keys(indice.contagem).map((k) => k.split("-")[0]))]
    .filter((u) => u !== "BR").sort();
  seletor.innerHTML = ufs.map((u) =>
    `<option value="${u}">${u} — ${NOME_UF[u] || u}</option>`).join("");
  seletor.value = localStorage.getItem("uf") || "SP";

  const ordemAbas = ["6", "7", "8", "5", "3", "1"];
  const abas = $("#abas-cargo");
  const desenharAbas = () => {
    const uf = seletor.value;
    abas.innerHTML = "";
    const disponiveis = ordemAbas
      .filter((cod) => indice.cargos[cod] && (indice.contagem[`${uf}-${cod}`] || indice.contagem[`BR-${cod}`]))
      .map((cod) => [cod, indice.cargos[cod]]);
    for (const [cod, nome] of disponiveis) {
      const rotulo = cod === "8" ? "Deputado Distrital" : nome;
      const b = criar("button", `aba${String(ESTADO.cargoAtivo) === String(cod) ? " ativa" : ""}`, rotulo);
      b.onclick = () => {
        ESTADO.cargoAtivo = cod;
        LIMITE_CEDULA = 12;
        desenharAbas();
        renderizarCedula();
      };
      abas.appendChild(b);
    }
    if (!disponiveis.some(([cod]) => String(cod) === String(ESTADO.cargoAtivo))) {
      ESTADO.cargoAtivo = disponiveis.length ? disponiveis[0][0] : null;
      desenharAbas();
    }
  };

  seletor.onchange = () => {
    localStorage.setItem("uf", seletor.value);
    LIMITE_CEDULA = 12;
    desenharAbas();
    renderizarCedula();
    renderizarUrna();
  };
  for (const id of ["#c-so-historico", "#c-so-aptos"]) {
    $(id).onchange = () => { LIMITE_CEDULA = 12; renderizarCedula(); renderizarUrna(); };
  }
  $("#c-busca").oninput = () => { LIMITE_CEDULA = 12; renderizarCedula(); };
  $("#c-mais").onclick = () => { LIMITE_CEDULA += 24; renderizarCedula(); };

  ESTADO.cargoAtivo = "6";
  desenharAbas();
  renderizarCedula();
  renderizarUrna();
}

/* ------------------------------------------------------------------ *
 * Eixos visuais
 * ------------------------------------------------------------------ */
function linhaEixo(eixo, valorCandidato, valorUsuario) {
  const info = ESTADO.eixos[eixo];
  const l = criar("div", "eixo");
  l.appendChild(criar("span", "polo", info.neg));
  const trilha = criar("div", "trilha");
  if (valorCandidato != null) {
    const pino = criar("div", "pino");
    pino.style.left = `${((valorCandidato + 1) / 2) * 100}%`;
    pino.title = `posição do parlamentar: ${valorCandidato}`;
    trilha.appendChild(pino);
  }
  if (valorUsuario != null) {
    const pino = criar("div", "pino usuario");
    pino.style.left = `${((valorUsuario + 1) / 2) * 100}%`;
    pino.title = `sua posição: ${valorUsuario}`;
    trilha.appendChild(pino);
  }
  l.appendChild(trilha);
  l.appendChild(criar("span", "polo dir", info.pos));
  return l;
}

function mostrarPerfil() {
  const alvo = $("#perfil-eixos");
  alvo.innerHTML = "";
  let algum = false;
  for (const [eixo, valor] of Object.entries(ESTADO.perfil || {})) {
    if (valor == null) continue;
    algum = true;
    const bloco = criar("div");
    bloco.appendChild(criar("div", "dica", `<strong>${ESTADO.eixos[eixo].rotulo}</strong>`));
    bloco.appendChild(linhaEixo(eixo, null, valor));
    alvo.appendChild(bloco);
  }
  $("#perfil").classList.toggle("oculto", !algum);
  $("#perfil-termos").innerHTML = ESTADO.termos.length
    ? `Termos reconhecidos no seu texto: ${ESTADO.termos.map((t) => `<b>${t}</b>`).join(", ")}.`
    : "Nenhum termo do dicionário foi reconhecido — tente palavras como conservador, liberal, socialista, SUS, porte de arma, meio ambiente, transparência.";
  if (!algum) {
    $("#perfil").classList.remove("oculto");
    $("#perfil-eixos").innerHTML = `<p class="dica">Não consegui identificar posição no seu texto. Use os atalhos acima como ponto de partida.</p>`;
  }
}

/* ------------------------------------------------------------------ *
 * Detalhe
 * ------------------------------------------------------------------ */
async function abrirDetalhe(id) {
  const modal = $("#modal");
  const box = $("#modal-conteudo");
  box.innerHTML = `<p class="carregando">Carregando dados oficiais...</p>`;
  modal.classList.remove("oculto");
  document.body.style.overflow = "hidden";

  let p;
  try {
    p = await (await fetch(`dados/p/${id}.json`)).json();
  } catch (e) {
    box.innerHTML = `<p class="carregando">Não foi possível carregar o detalhe.</p>`;
    return;
  }

  const af = afinidade(ESTADO.perfil, p);
  const m = p.metricas;
  const html = [];

  html.push(`<div class="perfil-topo">
      <img src="${p.foto || ""}" alt="${p.nome}" onerror="this.style.visibility='hidden'">
      <div>
        <h2>${p.nome}</h2>
        <div class="dica">${p.cargo} · ${p.partido || "sem partido"} · ${p.uf}
          ${p.nome_civil ? `<br>Nome civil: ${p.nome_civil}` : ""}</div>
        ${af ? `<div class="selo-afinidade">${af.valor}% combina com você</div>` : ""}
      </div>
    </div>`);

  html.push(`<div class="blocos">
    <div class="bloco"><div class="rotulo">Presença em sessões</div>
      <div class="valor-grande">${pct(m.presenca_pct)}</div>
      <div class="detalhe">${m.sessoes_presente ?? "—"} de ${m.sessoes_total ?? "—"} sessões deliberativas</div></div>
    <div class="bloco"><div class="rotulo">Votações nominais</div>
      <div class="valor-grande">${pct(m.participacao_pct)}</div>
      <div class="detalhe">votou em ${m.votos_plenario ?? "—"} de ${m.votos_plenario_total ?? "—"}</div></div>
    <div class="bloco"><div class="rotulo">Cota parlamentar</div>
      <div class="valor-grande">${dinheiro(m.gasto_total)}</div>
      <div class="detalhe">${dinheiro(m.gasto_mensal)} por mês${m.gasto_meses ? ` · ${m.gasto_meses} meses` : ""}</div></div>
    <div class="bloco"><div class="rotulo">Projetos de autoria</div>
      <div class="valor-grande">${m.autorias ?? 0}</div>
      <div class="detalhe">${m.autorias_aprovadas ?? 0} viraram norma</div></div>
  </div>`);

  // eixos
  html.push(`<div class="secao-modal"><h3>Posição política observada nos atos</h3>
    <p class="dica">Azul = parlamentar. Verde = você. Confiança do cálculo:
      ${Math.round((p.confianca_eixos || 0) * 100)}% — baseada em
      ${m.espectro_votos || 0} votações que separaram os polos e
      ${m.frentes_n || 0} frentes parlamentares assinadas.</p>
    <div class="eixos-lista" id="eixos-detalhe"></div></div>`);

  if (p.alertas && p.alertas.length) {
    html.push(`<div class="secao-modal"><h3>Pontos de atenção</h3>
      <div class="badges">${p.alertas.map((a) => `<span class="badge">${a}</span>`).join("")}</div></div>`);
  }

  if (p.sancoes && p.sancoes.length) {
    html.push(`<div class="secao-modal"><h3>Sanções oficiais encontradas</h3>
      ${p.sancoes.map((s) => `<div class="item nao">
        <div class="topo-item"><span>${s.fonte}</span><span class="voto-tag nao">${s.confianca === "alta" ? "nome civil confere" : "confirmar"}</span></div>
        <div class="ementa">${s.descricao}${s.processo ? ` · processo ${s.processo}` : ""}${s.data ? ` · ${s.data}` : ""}
          <br>${s.aviso} <a href="${s.url}" target="_blank" rel="noopener">ver na fonte</a></div></div>`).join("")}</div>`);
  } else {
    html.push(`<div class="secao-modal"><h3>Sanções oficiais</h3>
      <p class="dica">Nenhum registro localizado nas bases consultadas (TCU inabilitados, CEIS/CNEP).
      Ausência de registro não é atestado de idoneidade — é só ausência de registro nessas bases.</p></div>`);
  }

  if (p.mencoes && p.mencoes.length) {
    html.push(`<div class="secao-modal"><h3>Menções na imprensa <span class="badge">não entra na nota</span></h3>
      ${p.mencoes.map((n) => `<div class="item">
        <div class="topo-item"><a href="${n.url}" target="_blank" rel="noopener">${n.titulo}</a></div>
        <div class="ementa">${n.fonte || ""} ${n.data || ""}</div></div>`).join("")}</div>`);
  }

  if (p.votos_exemplo && p.votos_exemplo.length) {
    html.push(`<div class="secao-modal"><h3>Como votou (amostra classificada por tema)</h3>
      ${p.votos_exemplo.map((v) => {
        const cls = v.voto.toLowerCase().startsWith("s") ? "sim" : "nao";
        return `<div class="item ${cls}">
          <div class="topo-item"><span>${v.proposicao || "votação"}</span>
            <span class="voto-tag ${cls}">${v.voto}</span></div>
          <div class="ementa">${v.ementa || ""} <em>${v.data || ""}</em></div></div>`;
      }).join("")}</div>`);
  }

  if (p.autorias_exemplo && p.autorias_exemplo.length) {
    html.push(`<div class="secao-modal"><h3>Projetos que apresentou</h3>
      ${p.autorias_exemplo.map((a) => `<div class="item ${a.virou_norma ? "sim" : ""}">
        <div class="topo-item"><span>${a.titulo}</span>
          ${a.virou_norma ? `<span class="voto-tag sim">virou norma</span>` : ""}</div>
        <div class="ementa">${a.ementa || ""}${a.situacao ? ` · ${a.situacao}` : ""}</div></div>`).join("")}</div>`);
  }

  if (p.gasto_categorias && p.gasto_categorias.length) {
    html.push(`<div class="secao-modal"><h3>Onde gastou a cota</h3>
      ${p.gasto_categorias.map((c) => `<div class="nota-mini" style="grid-template-columns:230px 1fr 90px">
        <span>${c.nome}</span>
        <div class="barra"><span style="width:${Math.min(100, (c.valor / p.gasto_categorias[0].valor) * 100)}%"></span></div>
        <b>${dinheiro(c.valor)}</b></div>`).join("")}
      ${p.gasto_maior ? `<p class="dica">Maior despesa individual: ${dinheiro(p.gasto_maior.valor)}
        em ${p.gasto_maior.descricao} (${p.gasto_maior.fornecedor || "fornecedor não informado"})
        ${p.gasto_maior.documento ? `· <a href="${p.gasto_maior.documento}" target="_blank" rel="noopener">nota fiscal</a>` : ""}</p>` : ""}
      ${p.gasto_fornecedores && p.gasto_fornecedores.length ? `<p class="dica">Principais fornecedores:
        ${p.gasto_fornecedores.map((f) => `${f.nome} (${dinheiro(f.valor)})`).join(" · ")}</p>` : ""}
    </div>`);
  }

  if (p.frentes && p.frentes.length) {
    html.push(`<div class="secao-modal"><h3>Frentes parlamentares que assinou (${p.frentes.length})</h3>
      <div class="lista-simples">${p.frentes.map((f) => `<span>${f}</span>`).join("")}</div></div>`);
  }

  html.push(`<div class="secao-modal"><h3>Confira você mesmo</h3>
    <p class="dica"><a href="${p.url_fonte}" target="_blank" rel="noopener">Página oficial do parlamentar</a>
    ${p.site ? ` · <a href="${p.site}" target="_blank" rel="noopener">site pessoal</a>` : ""}
    ${(p.redes || []).map((r) => ` · <a href="${r}" target="_blank" rel="noopener">rede social</a>`).join("")}</p></div>`);

  box.innerHTML = html.join("");

  const alvo = box.querySelector("#eixos-detalhe");
  for (const eixo of Object.keys(ESTADO.eixos)) {
    const c = p.eixos ? p.eixos[eixo] : null;
    const u = ESTADO.perfil ? ESTADO.perfil[eixo] : null;
    if (c == null && u == null) continue;
    const bloco = criar("div");
    bloco.appendChild(criar("div", "dica", `<strong>${ESTADO.eixos[eixo].rotulo}</strong>`));
    bloco.appendChild(linhaEixo(eixo, c, u));
    alvo.appendChild(bloco);
  }
}

function fecharModal() {
  $("#modal").classList.add("oculto");
  document.body.style.overflow = "";
}

/* ------------------------------------------------------------------ *
 * Boot
 * ------------------------------------------------------------------ */
function montarPesos() {
  const alvo = $("#pesos");
  alvo.innerHTML = "";
  for (const [chave, valor] of Object.entries(ESTADO.pesos)) {
    const linha = criar("div", "peso");
    linha.appendChild(criar("span", null, ROTULO_PESO[chave]));
    const input = criar("input");
    input.type = "range";
    input.min = 0; input.max = 100; input.step = 5; input.value = valor;
    const saida = criar("span", "valor", `${valor}`);
    input.oninput = () => {
      ESTADO.pesos[chave] = +input.value;
      saida.textContent = input.value;
      renderizar();
      if (ESTADO.cedula) {
        renderizarCedula();
        renderizarUrna();
      }
    };
    linha.appendChild(input);
    linha.appendChild(saida);
    alvo.appendChild(linha);
  }
}

function montarFiltros() {
  const ufs = [...new Set(ESTADO.dados.parlamentares.map((p) => p.uf).filter(Boolean))].sort();
  const partidos = [...new Set(ESTADO.dados.parlamentares.map((p) => p.partido).filter(Boolean))].sort();
  for (const uf of ufs) $("#f-uf").appendChild(criar("option", null, uf)).value = uf;
  for (const pt of partidos) $("#f-partido").appendChild(criar("option", null, pt)).value = pt;
  ["#f-casa", "#f-uf", "#f-partido", "#f-limpo", "#f-confianca"].forEach((s) => { $(s).onchange = renderizar; });
  let timer;
  $("#f-busca").oninput = () => { clearTimeout(timer); timer = setTimeout(renderizar, 200); };
}

function montarFontes() {
  const alvo = $("#lista-fontes");
  for (const f of ESTADO.meta.fontes || []) {
    alvo.appendChild(criar("div", "fonte",
      `<strong>${f.nome}</strong><small>${f.usado}</small><br>
       <a href="${f.url}" target="_blank" rel="noopener">${f.url}</a>`));
  }
  $("#gerado").textContent =
    `Dados coletados em ${new Date(ESTADO.meta.gerado_em).toLocaleString("pt-BR")} · ` +
    `período analisado: ${(ESTADO.meta.anos || []).join(", ")} · ` +
    `${ESTADO.meta.total_parlamentares} parlamentares.`;
}

function aplicarTexto() {
  const { vetor, achados } = vetorDeTexto($("#texto").value);
  ESTADO.perfil = vetor;
  ESTADO.termos = achados;
  mostrarPerfil();
  renderizar();
  if (ESTADO.cedula) {
    renderizarCedula();
    renderizarUrna();
  }
  $("#urna").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function iniciar() {
  try {
    const [lexico, dados, meta] = await Promise.all([
      fetch("dados/lexico.json").then((r) => r.json()),
      fetch("dados/ranking.json").then((r) => r.json()),
      fetch("dados/meta.json").then((r) => r.json()),
    ]);
    ESTADO.lexico = lexico.lexico;
    ESTADO.eixos = lexico.eixos;
    ESTADO.sinalGeral = lexico.sinal_geral;
    ESTADO.dados = dados;
    ESTADO.meta = meta;
    // a cedula e opcional: sem ela o site ainda funciona como ranking de mandato
    ESTADO.cedula = await fetch("dados/cedula/indice.json")
      .then((r) => (r.ok ? r.json() : null)).catch(() => null);
  } catch (e) {
    $("#top10").innerHTML =
      `<p class="carregando">Não achei os dados. Rode <code>python -m etl.build</code> e recarregue.</p>`;
    return;
  }

  montarPesos();
  montarFiltros();
  montarFontes();
  renderizar();
  if (ESTADO.cedula) montarCedula();
  else {
    $("#cedula").classList.add("oculto");
    $("#urna").classList.add("oculto");
  }

  $("#calcular").onclick = aplicarTexto;
  $("#texto").onkeydown = (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) aplicarTexto(); };
  document.querySelectorAll(".chip").forEach((c) => {
    c.onclick = () => { $("#texto").value = c.dataset.exemplo; aplicarTexto(); };
  });
  $("#fechar").onclick = fecharModal;
  $("#modal").onclick = (e) => { if (e.target.id === "modal") fecharModal(); };
  document.onkeydown = (e) => { if (e.key === "Escape") fecharModal(); };
}

iniciar();
