#!/usr/bin/env python3
"""
Minimal OpenAI-compatible mock server - stdlib only.

Lets you try every script in this repo (and run the smoke tests) without a GPU,
a model, or network access. It implements just enough of the API surface the
scripts touch:

    GET  /v1/models                (three models, one deliberately broken)
    POST /v1/chat/completions      (blocking and stream=true / SSE)
    POST /v1/embeddings            (float and base64 encoding_format)

Any request whose model name looks like "error-404" is answered with that HTTP
status, so the failure paths of the scripts can be tested reproducibly.

Embeddings are deterministic word + character-trigram hashes, L2-normalized, so the
sanity suite in python/embed-test.py behaves like it would against a real
model: identical texts match exactly, paraphrases score higher than unrelated
text, and batch position never changes a vector.

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
BROKEN_MODEL_ID = "error-503"

# Fixed timestamps so /v1/models output is byte-identical on every machine.
# 1735689600 = 2025-01-01T00:00:00Z, 1740787200 = 2025-03-01T00:00:00Z
CATALOG = [
    {"id": MODEL_ID, "object": "model", "created": 1735689600, "owned_by": "mock",
     "max_model_len": 8192},
    {"id": EMBED_MODEL_ID, "object": "model", "created": 1740787200, "owned_by": "mock",
     "max_model_len": 512},
    # Advertised but not usable - so a probe run has a reproducible failure row.
    {"id": BROKEN_MODEL_ID, "object": "model", "owned_by": "mock"},
]
DEFAULT_DIM = 128
REPLY = "Merhaba! Bu bir mock yanittir - Türkçe karakter testi: çğışöüÇĞİŞÖÜ"


# --------------------------------------------------------------------------
# deterministic pseudo-embeddings
# --------------------------------------------------------------------------

def _bucket(feature, dim):
    h = hashlib.sha256(feature.encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big") % dim, (1.0 if h[4] % 2 else -1.0)


def embed_text(text, dim=DEFAULT_DIM, max_chars=8192):
    """Word + character-trigram feature hashing, L2-normalized.

    Words carry most of the weight so that paraphrases sharing vocabulary score
    higher than unrelated text - the property the sanity suite checks for.
    """
    text = text[:max_chars].lower()               # simulate max-model-len truncation
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

    # -- helpers ----------------------------------------------------------
    def _json(self, obj, status=200):
        # Deliberately no charset in Content-Type: this is what trips up
        # PowerShell 5.1, and the scripts here are expected to cope.
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
            self._error(400, "request body is not valid JSON")
            return None

    def _authorized(self):
        if not self.server.require_key:
            return True
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and auth[7:].strip():
            return True
        self._error(401, "missing or malformed Authorization header", "authentication_error")
        return False

    def _maybe_injected_error(self, model):
        """model="error-404" makes the server answer 404 - lets the scripts'
        failure paths be tested with a reproducible, documented status."""
        if not str(model).startswith("error-"):
            return False
        try:
            status = int(str(model).split("-", 1)[1])
        except ValueError:
            status = 500
        self._error(status, "injected error for model %r" % model, "injected_error")
        return True

    # -- routes -----------------------------------------------------------
    def do_GET(self):
        if self.path.rstrip("/").endswith("/v1/models"):
            if not self._authorized():
                return
            self._json({"object": "list", "data": CATALOG})
        else:
            self._error(404, "unknown route %s" % self.path, "not_found")

    def do_POST(self):
        if self.path.endswith("/chat/completions"):
            self._chat()
        elif self.path.endswith("/embeddings"):
            self._embeddings()
        else:
            self._error(404, "unknown route %s (expected /v1/chat/completions "
                             "or /v1/embeddings)" % self.path, "not_found")

    def _chat(self):
        if not self._authorized():
            return
        body = self._read_body()
        if body is None:
            return
        if not body.get("model"):
            self._error(400, "'model' is a required property")
            return
        if self._maybe_injected_error(body["model"]):
            return
        if body["model"] == EMBED_MODEL_ID:
            self._error(400, "this model does not support chat completions",
                        "invalid_request_error")
            return
        messages = body.get("messages") or []
        if not messages:
            self._error(400, "'messages' must contain at least one item")
            return

        prompt_tokens = sum(rough_tokens(str(m.get("content", ""))) for m in messages)

        if body.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            for piece in REPLY.split(" "):
                chunk = {"id": "chatcmpl-mock", "object": "chat.completion.chunk",
                         "model": body["model"],
                         "choices": [{"index": 0, "delta": {"content": piece + " "},
                                      "finish_reason": None}]}
                self.wfile.write(("data: %s\n\n" % json.dumps(chunk, ensure_ascii=False))
                                 .encode("utf-8"))
                self.wfile.flush()
                time.sleep(self.server.delay or 0.02)
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
            self._error(400, "'model' is a required property")
            return
        if self._maybe_injected_error(body["model"]):
            return
        texts = body.get("input")
        if isinstance(texts, str):
            texts = [texts]
        if not texts:
            self._error(400, "'input' must be a string or a non-empty array")
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


def build_server(host="127.0.0.1", port=8899, require_key=True, delay=0.0, verbose=False):
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True
    srv.require_key = require_key
    srv.delay = delay
    srv.verbose = verbose
    return srv


def main():
    p = argparse.ArgumentParser(description="OpenAI-compatible mock server")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8899)
    p.add_argument("--delay", type=float, default=0.0,
                   help="artificial per-response latency in seconds")
    p.add_argument("--no-auth", action="store_true", help="accept requests without a key")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    srv = build_server(args.host, args.port, not args.no_auth, args.delay, args.verbose)
    print("mock OpenAI-compatible server on http://%s:%d/v1  (model: %s, Ctrl-C to stop)"
          % (args.host, args.port, MODEL_ID))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
