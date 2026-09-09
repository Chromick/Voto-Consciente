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
  $("#ranking").scrollIntoView({ behavior: "smooth", block: "start" });
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
  } catch (e) {
    $("#top10").innerHTML =
      `<p class="carregando">Não achei os dados. Rode <code>python -m etl.build</code> e recarregue.</p>`;
    return;
  }

  montarPesos();
  montarFiltros();
  montarFontes();
  renderizar();

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
