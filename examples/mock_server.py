#!/usr/bin/env python3
"""
Minimal OpenAI uyumlu sahte (mock) sunucu - sadece standart kütüphane.

GPU, model ya da ağ erişimi olmadan bu depodaki her betiği denemenizi (ve smoke
testlerini çalıştırmanızı) sağlar. Betiklerin dokunduğu API yüzeyinin yalnızca
gerekli kadarını uygular:

    GET  /v1/models                (dört model, biri bilerek bozuk)
    POST /v1/chat/completions      (bloklayan ve stream=true / SSE)
    POST /v1/embeddings            (float ve base64 encoding_format)
    POST /v1/rerank                (Cohere/Jina biçimi: results[].relevance_score)

Model adı "error-404" gibi olan her istek o HTTP status'u ile yanıtlanır; böylece
betiklerin hata yolları tekrarlanabilir şekilde test edilebilir.

Embedding'ler deterministik kelime + karakter-trigram hash'leridir ve
L2-normalize edilir. Böylece python/embed-test.py içindeki sağlık paketi gerçek
bir modeldeki gibi davranır: aynı metinler birebir eşleşir, paraphrase alakasız
metinden yüksek skor alır ve batch pozisyonu vektörü değiştirmez.

Not: gerçek sunucular hata mesajlarını İngilizce döndürür; buradaki Türkçe
mesajlar yalnızca bu deponun diline uyması içindir - yapı (error.message /
error.type) gerçek API ile aynıdır.

    python3 examples/mock_server.py --port 8899
    LLM_ENDPOINT=http://127.0.0.1:8899 LLM_API_KEY=sk-mock LLM_MODEL=mock-model \
        bash/llm-prompt.sh "Merhaba"
"""

import argparse
import base64
import hashlib
import json
import math
import struct
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL_ID = "mock-model"
EMBED_MODEL_ID = "mock-embed"
RERANK_MODEL_ID = "mock-rerank"
BROKEN_MODEL_ID = "error-503"

# Sabit timestamp: /v1/models çıktısı her makinede byte-byte aynı olsun.
# 1735689600 = 2025-01-01T00:00:00Z, 1740787200 = 2025-03-01T00:00:00Z
CATALOG = [
    {"id": MODEL_ID, "object": "model", "created": 1735689600, "owned_by": "mock",
     "max_model_len": 8192},
    {"id": EMBED_MODEL_ID, "object": "model", "created": 1740787200, "owned_by": "mock",
     "max_model_len": 512},
    {"id": RERANK_MODEL_ID, "object": "model", "created": 1740787200, "owned_by": "mock",
     "max_model_len": 512},
    # Listede var ama çalışmıyor - probe çıktısında tekrarlanabilir bir hata satırı.
    {"id": BROKEN_MODEL_ID, "object": "model", "owned_by": "mock"},
]
DEFAULT_DIM = 128
REPLY = "Merhaba! Bu bir mock yanittir - Türkçe karakter testi: çğışöüÇĞİŞÖÜ"


# --------------------------------------------------------------------------
# deterministik sahte embedding'ler
# --------------------------------------------------------------------------

def _bucket(feature, dim):
    h = hashlib.sha256(feature.encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big") % dim, (1.0 if h[4] % 2 else -1.0)


def embed_text(text, dim=DEFAULT_DIM, max_chars=8192):
    """Kelime + karakter-trigram feature hashing, L2-normalize.

    Ağırlığın çoğunu kelimeler taşır; böylece ortak kelime içeren paraphrase
    metinler alakasız metinden yüksek skor alır - sağlık paketinin aradığı
    özellik budur.
    """
    text = text[:max_chars].lower()               # max-model-len truncation simülasyonu
    vec = [0.0] * dim

    words = "".join(c if c.isalnum() else " " for c in text).split()
    for word in words:
        bucket, sign = _bucket("w:" + word, dim)
        vec[bucket] += sign * 3.0

    padded = "  %s  " % text
    for i in range(len(padded) - 2):
        bucket, sign = _bucket("g:" + padded[i:i + 3], dim)
        vec[bucket] += sign * 0.5

    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        vec[0] = 1.0
        return vec
    return [x / norm for x in vec]


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b))


def to_base64(vec):
    return base64.b64encode(struct.pack("<%df" % len(vec), *vec)).decode("ascii")


def rough_tokens(text):
    return max(1, len(text) // 4)


# --------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    delay = 0.0

    def log_message(self, fmt, *args):
        if self.server.verbose:
            sys.stderr.write("[mock] %s - %s\n" % (self.address_string(), fmt % args))

    # -- yardımcılar ------------------------------------------------------
    def _json(self, obj, status=200):
        # Content-Type'ta bilerek charset yok: PowerShell 5.1'i tökezleten şey
        # tam olarak bu ve buradaki betiklerin bununla başa çıkması bekleniyor.
        payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _error(self, status, message, code="invalid_request_error"):
        self._json({"error": {"message": message, "type": code, "code": None}}, status)

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:
            self._error(400, "istek gövdesi geçerli JSON değil")
            return None

    def _authorized(self):
        if not self.server.require_key:
            return True
        auth = self.headers.get("Authorization", "")
        token = auth[7:].strip() if auth.startswith("Bearer ") else ""
        if token and (self.server.key is None or token == self.server.key):
            return True
        self._error(401, "Authorization başlığı eksik ya da hatalı", "authentication_error")
        return False

    def _maybe_injected_error(self, model):
        """model="error-404" sunucuyu 404 döndürmeye zorlar - betiklerin hata
        yolları böylece tekrarlanabilir ve belgelenmiş bir status ile test edilir."""
        if not str(model).startswith("error-"):
            return False
        try:
            status = int(str(model).split("-", 1)[1])
        except ValueError:
            status = 500
        self._error(status, "%r modeli için enjekte edilmiş hata" % model, "injected_error")
        return True

    # -- rotalar ----------------------------------------------------------
    def do_GET(self):
        if self.path.rstrip("/").endswith("/v1/models"):
            if not self._authorized():
                return
            self._json({"object": "list", "data": CATALOG})
        else:
            self._error(404, "bilinmeyen rota %s" % self.path, "not_found")

    def do_POST(self):
        if self.path.endswith("/chat/completions"):
            self._chat()
        elif self.path.endswith("/embeddings"):
            self._embeddings()
        elif self.path.endswith("/rerank"):
            self._rerank()
        else:
            self._error(404, "bilinmeyen rota %s (/v1/chat/completions, /v1/embeddings "
                             "ya da /v1/rerank bekleniyordu)" % self.path, "not_found")

    def _chat(self):
        if not self._authorized():
            return
        body = self._read_body()
        if body is None:
            return
        if not body.get("model"):
            self._error(400, "'model' zorunlu bir alan")
            return
        if self._maybe_injected_error(body["model"]):
            return
        if body["model"] in (EMBED_MODEL_ID, RERANK_MODEL_ID):
            self._error(400, "bu model chat completions desteklemiyor",
                        "invalid_request_error")
            return
        messages = body.get("messages") or []
        if not messages:
            self._error(400, "'messages' en az bir eleman içermeli")
            return

        prompt_tokens = sum(rough_tokens(str(m.get("content", ""))) for m in messages)

        if body.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            # Prefill simülasyonu: ilk token'dan önce üç chunk gecikmesi kadar
            # bekle; böylece TTFT ile ITL ayrı ve doğrulanabilir sayılar olur.
            chunk_delay = self.server.delay or 0.02
            time.sleep(chunk_delay * 3)
            for piece in REPLY.split(" "):
                chunk = {"id": "chatcmpl-mock", "object": "chat.completion.chunk",
                         "model": body["model"],
                         "choices": [{"index": 0, "delta": {"content": piece + " "},
                                      "finish_reason": None}]}
                self.wfile.write(("data: %s\n\n" % json.dumps(chunk, ensure_ascii=False))
                                 .encode("utf-8"))
                self.wfile.flush()
                time.sleep(chunk_delay)
            done = {"id": "chatcmpl-mock", "object": "chat.completion.chunk",
                    "model": body["model"],
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
            self.wfile.write(("data: %s\n\ndata: [DONE]\n\n"
                              % json.dumps(done)).encode("utf-8"))
            self.wfile.flush()
            self.close_connection = True
            return

        time.sleep(self.server.delay)
        self._json({
            "id": "chatcmpl-mock", "object": "chat.completion",
            "created": 0, "model": body["model"],
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": REPLY}}],
            "usage": {"prompt_tokens": prompt_tokens,
                      "completion_tokens": rough_tokens(REPLY),
                      "total_tokens": prompt_tokens + rough_tokens(REPLY)},
        })

    def _embeddings(self):
        if not self._authorized():
            return
        body = self._read_body()
        if body is None:
            return
        if not body.get("model"):
            self._error(400, "'model' zorunlu bir alan")
            return
        if self._maybe_injected_error(body["model"]):
            return
        texts = body.get("input")
        if isinstance(texts, str):
            texts = [texts]
        if not texts:
            self._error(400, "'input' bir string ya da boş olmayan bir dizi olmalı")
            return

        dim = int(body.get("dimensions") or DEFAULT_DIM)
        fmt = body.get("encoding_format", "float")
        time.sleep(self.server.delay)

        data = []
        for i, text in enumerate(texts):
            vec = embed_text(str(text), dim)
            data.append({"object": "embedding", "index": i,
                         "embedding": to_base64(vec) if fmt == "base64" else vec})
        tokens = sum(rough_tokens(str(t)) for t in texts)
        self._json({"object": "list", "model": body["model"], "data": data,
                    "usage": {"prompt_tokens": tokens, "total_tokens": tokens}})


    def _rerank(self):
        if not self._authorized():
            return
        body = self._read_body()
        if body is None:
            return
        if not body.get("model"):
            self._error(400, "'model' zorunlu bir alan")
            return
        if self._maybe_injected_error(body["model"]):
            return
        query = body.get("query")
        if not query:
            self._error(400, "'query' zorunlu bir alan")
            return
        docs = body.get("documents")
        if isinstance(docs, str):
            docs = [docs]
        if not docs:
            self._error(400, "'documents' boş olmayan bir dizi olmalı")
            return

        time.sleep(self.server.delay)
        qv = embed_text(str(query))
        puanlar = []
        for i, d in enumerate(docs):
            metin = d if isinstance(d, str) else str((d or {}).get("text", ""))
            # cosine [-1,1] -> relevance_score [0,1]
            puanlar.append((i, (cosine(qv, embed_text(metin)) + 1.0) / 2.0, metin))
        # Yüksek puan önce; eşitlikte istek sırası korunur (kararlı sıralama).
        puanlar.sort(key=lambda t: -t[1])

        top_n = body.get("top_n")
        if isinstance(top_n, int) and top_n > 0:
            puanlar = puanlar[:top_n]

        sonuclar = []
        for i, puan, metin in puanlar:
            kayit = {"index": i, "relevance_score": puan}
            if body.get("return_documents"):
                kayit["document"] = {"text": metin}
            sonuclar.append(kayit)

        tokens = rough_tokens(str(query)) + sum(rough_tokens(str(d)) for d in docs)
        self._json({"id": "rerank-mock", "model": body["model"], "results": sonuclar,
                    "usage": {"prompt_tokens": tokens, "total_tokens": tokens}})


class MockServer(ThreadingHTTPServer):
    """İstemcinin bağlantıyı erken kapatması normaldir (stream'i yarıda bırakmak,
    `head` ile kesmek gibi); bunun için traceback basmıyoruz."""

    def handle_error(self, request, client_address):
        hata = sys.exc_info()[1]
        if isinstance(hata, (ConnectionResetError, BrokenPipeError)):
            return
        ThreadingHTTPServer.handle_error(self, request, client_address)


def build_server(host="127.0.0.1", port=8899, require_key=True, delay=0.0,
                 verbose=False, key=None):
    srv = MockServer((host, port), Handler)
    srv.daemon_threads = True
    srv.require_key = require_key
    srv.key = key            # None: herhangi bir boş olmayan token kabul edilir
    srv.delay = delay
    srv.verbose = verbose
    return srv


def main():
    p = argparse.ArgumentParser(description="OpenAI uyumlu sahte sunucu")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8899)
    p.add_argument("--delay", type=float, default=0.0,
                   help="yanıt başına yapay gecikme (saniye)")
    p.add_argument("--no-auth", action="store_true", help="anahtarsız istekleri kabul et")
    p.add_argument("--key", help="yalnızca bu bearer token'ı kabul et (401 yolunu test etmek için)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    srv = build_server(args.host, args.port, not args.no_auth, args.delay,
                       args.verbose, args.key)
    print("OpenAI uyumlu sahte sunucu: http://%s:%d/v1  (model: %s, durdurmak için Ctrl-C)"
          % (args.host, args.port, MODEL_ID))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\ngörüşürüz")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
