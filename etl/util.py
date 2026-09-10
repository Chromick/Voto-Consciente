"""Utilidades de rede, cache e leitura de CSV. Sem dependencias externas."""

from __future__ import annotations

import csv
import gzip
import http.client
import io
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import zlib
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CACHE = RAIZ / "cache"
DADOS = RAIZ / "dados"

UA = "dignos/1.0 (projeto civico de dados abertos; github.com/Chromick/Voto-Consciente)"
TIMEOUT = 180

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def log(*a):
    print(*a, flush=True)


def nome_cache(url: str) -> str:
    limpo = re.sub(r"[^A-Za-z0-9._-]+", "_", url.split("://", 1)[-1])
    return limpo[-150:]


def baixar(url: str, headers: dict | None = None, ttl_horas: float = 24.0,
           cache: bool = True, dados_post: bytes | None = None,
           timeout: float = TIMEOUT) -> bytes:
    """GET (ou POST) com cache em disco. Devolve bytes crus."""
    CACHE.mkdir(parents=True, exist_ok=True)
    alvo = CACHE / nome_cache(url + ("#post" if dados_post else ""))
    if cache and alvo.exists() and ttl_horas > 0:
        idade = (time.time() - alvo.stat().st_mtime) / 3600
        if idade < ttl_horas:
            return alvo.read_bytes()

    h = {"User-Agent": UA, "Accept-Encoding": "gzip"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=dados_post, headers=h)

    # Os arquivos grandes da Camara as vezes cortam a conexao no meio
    # (IncompleteRead). Lemos em blocos e aproveitamos o que chegou: um CSV
    # truncado ainda serve, so perde as ultimas linhas. Nesse caso nao gravamos
    # no cache, para tentar baixar completo na proxima execucao.
    pedacos = bytearray()
    truncado = False
    with urllib.request.urlopen(req, timeout=timeout) as r:
        gzipado = r.headers.get("Content-Encoding") == "gzip"
        try:
            while True:
                bloco = r.read(1 << 20)
                if not bloco:
                    break
                pedacos += bloco
        except http.client.IncompleteRead as e:
            pedacos += e.partial or b""
            truncado = True
        except (TimeoutError, OSError) as e:
            if not pedacos:
                raise
            log(f"   ! leitura interrompida ({type(e).__name__}), usando {len(pedacos):,} bytes")
            truncado = True

    bruto = bytes(pedacos)
    if gzipado:
        if truncado:
            # zlib aceita fluxo truncado; gzip.decompress nao.
            bruto = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(bruto)
        else:
            bruto = gzip.decompress(bruto)

    if truncado:
        log(f"   ! resposta truncada em {nome_cache(url)[:60]}: seguindo com dado parcial")
    if cache and not truncado:
        alvo.write_bytes(bruto)
    return bruto


def baixar_json(url: str, headers: dict | None = None, ttl_horas: float = 24.0,
                dados_post: bytes | None = None, timeout: float = TIMEOUT):
    h = {"Accept": "application/json"}
    if headers:
        h.update(headers)
    return json.loads(
        baixar(url, h, ttl_horas, dados_post=dados_post, timeout=timeout)
        .decode("utf-8", "replace"))


def tentar(fn, rotulo: str, padrao=None, tentativas: int = 3, espera: float = 3.0):
    """Executa fn com retentativas; nunca derruba o ETL inteiro por uma fonte fora do ar."""
    for i in range(tentativas):
        try:
            return fn()
        except Exception as e:
            codigo = getattr(e, "code", "")
            log(f"   ! {rotulo}: {type(e).__name__} {codigo} {e}")
            if i < tentativas - 1:
                time.sleep(espera * (i + 1))
    log(f"   ! {rotulo}: desistindo, seguindo sem esta fonte")
    return padrao


def ler_csv(bruto: bytes, delim: str = ";"):
    """Le CSV da Camara (UTF-8 com BOM, separado por ponto e virgula) como dicts."""
    texto = bruto.decode("utf-8-sig", "replace")
    return csv.DictReader(io.StringIO(texto, newline=""), delimiter=delim)


def ler_csv_url(url: str, ttl_horas: float = 24.0, delim: str = ";"):
    return ler_csv(baixar(url, ttl_horas=ttl_horas), delim)


def ler_csv_zip(url: str, ttl_horas: float = 24.0, delim: str = ";"):
    bruto = baixar(url, ttl_horas=ttl_horas)
    z = zipfile.ZipFile(io.BytesIO(bruto))
    nome = next(n for n in z.namelist() if n.lower().endswith(".csv"))
    with z.open(nome) as f:
        return ler_csv(f.read(), delim)


def sem_acento(s: str) -> str:
    if not s:
        return ""
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def chave_nome(s: str) -> str:
    """Normaliza nome para casamento entre fontes diferentes."""
    s = sem_acento(s or "").upper()
    s = re.sub(r"\b(DEPUTADO|DEPUTADA|SENADOR|SENADORA|DR|DRA|PROF|PASTOR|DELEGADO|CORONEL|SARGENTO)\b", " ", s)
    s = re.sub(r"[^A-Z ]+", " ", s)
    return " ".join(s.split())


def num(v, padrao: float = 0.0) -> float:
    if v is None:
        return padrao
    t = str(v).strip().replace(",", ".")
    if not t:
        return padrao
    try:
        return float(t)
    except ValueError:
        return padrao


def inteiro(v, padrao: int = 0) -> int:
    return int(num(v, padrao))


def id_da_uri(uri: str) -> str:
    return (uri or "").rstrip("/").rsplit("/", 1)[-1]


def salvar_json(caminho: Path, obj, compacto: bool = True, mostrar: bool = True):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        if compacto:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(obj, f, ensure_ascii=False, indent=1)
    if mostrar:
        kb = caminho.stat().st_size / 1024
        log(f"   -> {caminho.relative_to(RAIZ)}  ({kb:,.0f} KB)")


def percentil(valores: list[float]) -> dict:
    """Mapa valor -> percentil (0..1) usando ordenacao simples."""
    ordenado = sorted(valores)
    n = len(ordenado)
    if n == 0:
        return {}
    saida = {}
    for v in set(ordenado):
        menores = sum(1 for x in ordenado if x < v)
        iguais = sum(1 for x in ordenado if x == v)
        saida[v] = (menores + iguais / 2) / n
    return saida
