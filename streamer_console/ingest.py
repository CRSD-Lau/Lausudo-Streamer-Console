"""Loopback-only HTTP ingestion for Social Stream Ninja messages."""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from queue import Empty, Full, Queue
import socket
import threading
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

from .config import IngestSettings
from .normalizer import MessageNormalizer, NormalizedMessage


LOGGER = logging.getLogger(__name__)
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class _LoopbackThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class _IPv6LoopbackThreadingHTTPServer(_LoopbackThreadingHTTPServer):
    address_family = socket.AF_INET6


class BoundedMessageQueue:
    """Qt-safe producer/consumer queue which keeps the newest messages."""

    def __init__(self, maxsize: int = 1_000) -> None:
        self._queue: Queue[NormalizedMessage] = Queue(maxsize=max(1, int(maxsize)))

    def put(self, message: NormalizedMessage) -> None:
        try:
            self._queue.put_nowait(message)
            return
        except Full:
            pass
        try:
            self._queue.get_nowait()
        except Empty:
            pass
        try:
            self._queue.put_nowait(message)
        except Full:  # another producer won the slot; dropping one is bounded/safe
            LOGGER.warning("Social Stream delivery queue saturated; one message dropped")

    def drain(self, max_items: int = 200) -> list[NormalizedMessage]:
        items: list[NormalizedMessage] = []
        for _ in range(max(0, int(max_items))):
            try:
                items.append(self._queue.get_nowait())
            except Empty:
                break
        return items

    def qsize(self) -> int:
        return self._queue.qsize()


class SocialStreamIngestServer:
    """A small, dependency-free loopback webhook receiver.

    Handler threads only normalize and enqueue.  The Qt GUI should call
    :meth:`drain` from a ``QTimer`` on the GUI thread; no Qt object is touched
    by HTTP worker threads.
    """

    def __init__(
        self,
        normalizer: MessageNormalizer | None = None,
        settings: IngestSettings | None = None,
        *,
        output_queue: BoundedMessageQueue | None = None,
    ) -> None:
        self.settings = settings or IngestSettings()
        host = self.settings.host.strip().lower()
        if host not in _LOOPBACK_HOSTS:
            raise ValueError("Social Stream ingestion must bind to a loopback host")
        if not self.settings.path.startswith("/"):
            raise ValueError("ingest path must start with '/'")
        self.normalizer = normalizer or MessageNormalizer()
        self.messages = output_queue or BoundedMessageQueue(self.settings.queue_size)
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        # A handler owns this lock from normalization through queue insertion.
        # That makes receipt sequence the single total order seen by the GUI,
        # even when ThreadingHTTPServer processes simultaneous POST requests.
        self._receipt_lock = threading.Lock()

    @property
    def address(self) -> tuple[str, int]:
        server = self._server
        if server is None:
            return self.settings.host, self.settings.port
        host, port = server.server_address[:2]
        return str(host), int(port)

    @property
    def endpoint(self) -> str:
        host, port = self.address
        return f"http://{host}:{port}{self.settings.path}"

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> tuple[str, int]:
        with self._lock:
            if self.is_running:
                return self.address
            owner = self

            class Handler(BaseHTTPRequestHandler):
                server_version = "StreamerConsoleIngest/1"
                sys_version = ""

                def log_message(self, format: str, *args: object) -> None:
                    # Never log bodies, headers, cookies, query strings, or tokens.
                    LOGGER.debug("Social Stream HTTP request completed")

                def _headers(self, status: HTTPStatus, length: int) -> None:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(length))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.end_headers()

                def _json(self, status: HTTPStatus, payload: Mapping[str, Any]) -> None:
                    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
                    self._headers(status, len(encoded))
                    self.wfile.write(encoded)

                def do_OPTIONS(self) -> None:  # noqa: N802 - stdlib handler API
                    if urlsplit(self.path).path != owner.settings.path:
                        self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                        return
                    self.send_response(HTTPStatus.NO_CONTENT)
                    self.send_header("Content-Length", "0")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
                    self.send_header("Access-Control-Allow-Headers", "Content-Type")
                    self.send_header("Access-Control-Max-Age", "600")
                    self.end_headers()

                def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
                    if urlsplit(self.path).path != owner.settings.path:
                        self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                        return
                    content_length = self.headers.get("Content-Length")
                    if content_length is None:
                        self._json(HTTPStatus.LENGTH_REQUIRED, {"error": "length_required"})
                        return
                    try:
                        length = int(content_length)
                    except ValueError:
                        self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_length"})
                        return
                    if length < 1:
                        self._json(HTTPStatus.BAD_REQUEST, {"error": "empty_body"})
                        return
                    if length > owner.settings.max_body_bytes:
                        self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "body_too_large"})
                        return
                    content_type = self.headers.get_content_type()
                    if content_type not in {"application/json", "text/json", "text/plain"}:
                        self._json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "json_required"})
                        return
                    try:
                        body = self.rfile.read(length)
                        payload = json.loads(body.decode("utf-8-sig"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
                        return
                    candidates: Iterable[Any]
                    if isinstance(payload, list):
                        candidates = payload
                    elif isinstance(payload, Mapping):
                        # Some forwarding tools wrap a batch in {"messages": [...]}.
                        batch = payload.get("messages")
                        candidates = batch if isinstance(batch, list) else (payload,)
                    else:
                        self._json(HTTPStatus.BAD_REQUEST, {"error": "object_required"})
                        return
                    accepted, ignored = owner._normalize_and_enqueue(candidates)
                    # Social Stream Ninja treats HTTP 200 as its explicit
                    # delivery-success signal. Processing is synchronous here,
                    # so OK is also the accurate status for accepted batches.
                    self._json(
                        HTTPStatus.OK,
                        {"accepted": accepted, "ignored": ignored},
                    )
                    LOGGER.debug(
                        "Social Stream batch accepted=%d ignored=%d", accepted, ignored
                    )

            server_class = (
                _IPv6LoopbackThreadingHTTPServer
                if self.settings.host.strip().lower() == "::1"
                else _LoopbackThreadingHTTPServer
            )
            self._server = server_class(
                (self.settings.host, self.settings.port), Handler
            )
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                name="social-stream-ingest",
                daemon=True,
            )
            self._thread.start()
            LOGGER.info("Social Stream ingestion listening on loopback port %d", self.address[1])
            return self.address

    def drain(self, max_items: int = 200) -> list[NormalizedMessage]:
        return self.messages.drain(max_items)

    def _normalize_and_enqueue(self, candidates: Iterable[Any]) -> tuple[int, int]:
        accepted = 0
        ignored = 0
        with self._receipt_lock:
            for candidate in candidates:
                if not isinstance(candidate, Mapping):
                    ignored += 1
                    continue
                message = self.normalizer.normalize(candidate)
                if message is None:
                    ignored += 1
                    continue
                self.messages.put(message)
                accepted += 1
        return accepted, ignored

    def stop(self, timeout: float = 3.0) -> None:
        with self._lock:
            server = self._server
            thread = self._thread
            self._server = None
            self._thread = None
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(0.0, timeout))
        LOGGER.info("Social Stream ingestion stopped")

    def __enter__(self) -> "SocialStreamIngestServer":
        self.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.stop()
