import asyncio
import json
import threading
from pathlib import Path
import httpx
import pytest
from websockets.sync.server import serve
from buildsol import (
    Sol,
    AsyncSol,
    AuthenticationError,
    RateLimitError,
    ConnectionError,
    ProtocolError,
    LiveConnection,
    AsyncLiveConnection,
)


class Chunks(httpx.SyncByteStream):
    def __init__(self, chunks):
        self.chunks, self.closed = chunks, False

    def __iter__(self):
        yield from self.chunks

    def close(self):
        self.closed = True


class AsyncChunks(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks, self.closed = chunks, False

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk

    async def aclose(self):
        self.closed = True


def client(handler, **kw):
    return Sol(
        "test-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        **kw,
    )


def test_speech_stream_preserves_first_chunk_and_closes():
    body = Chunks([b"first", b"last"])

    def handle(req):
        assert req.headers["authorization"] == "Bearer test-key"
        assert json.loads(req.content) == {
            "text": "Hola",
            "speed": 1,
            "output_format": "pcm",
        }
        return httpx.Response(200, stream=body, headers={"x-request-id": "req1"})

    with client(handle).speech.stream(
        text="Hola", speed=1, output_format="pcm"
    ) as stream:
        assert next(iter(stream)) == b"first"
        assert stream.request_id == "req1"
    assert body.closed


def test_generate_and_save(tmp_path):
    sol = client(lambda _: httpx.Response(200, content=b"\x00\x01"))
    audio = sol.speech.create(text="Hola")
    audio.save(tmp_path / "out.wav")
    assert (tmp_path / "out.wav").read_bytes() == b"\x00\x01"


@pytest.mark.parametrize(
    "operation,path",
    [
        ("balance", "/v1/balance"),
        ("controls", "/v1/tts/controls"),
        ("dialects", "/v1/dialects"),
    ],
)
def test_catalogs(operation, path):
    def handle(req):
        assert req.url.path == path
        return httpx.Response(200, json={"ok": True})

    resource = getattr(client(handle), operation)
    assert (resource.list() if operation == "dialects" else resource.get()) == {
        "ok": True
    }


def test_voice_filters_ids_and_clone():
    seen = []

    def handle(req):
        seen.append(req)
        return httpx.Response(200, json={"voice": {"id": "abc"}})

    sol = client(handle)
    sol.voices.list(country="PE", gender="female", age="young", category="story")
    assert dict(seen[-1].url.params) == dict(
        country="PE", gender="female", age="young", category="story"
    )
    sol.voices.get("abc/# ?")
    assert seen[-1].url.raw_path == b"/v1/voices/abc%2F%23%20%3F"
    sol.voices.create(
        name="Mi voz", audio=("voice.wav", b"RIFF"), consent=True, gender="female"
    )
    body = seen[-1].content
    assert b'name="consent"\r\n\r\ntrue' in body and b'filename="voice.wav"' in body
    sol.voices.delete("abc")
    assert seen[-1].method == "DELETE"


def test_multipart_reference(tmp_path):
    p = tmp_path / "sample.wav"
    p.write_bytes(b"RIFF")

    def handle(req):
        assert b'name="reference_audio"' in req.content
        assert b'name="text"\r\n\r\nHola' in req.content
        return httpx.Response(200, content=b"audio")

    assert (
        client(handle).speech.create(text="Hola", reference_file=p).content == b"audio"
    )


def test_file_transcription_and_translation_idempotency():
    seen = []

    def handle(req):
        seen.append(req)
        return httpx.Response(200, json={"text": "Hola", "translation": "Olá"})

    sol = client(handle)
    sol.transcriptions.create(
        file=("sample.mp3", b"MP3"),
        language="es",
        diarize=True,
        idempotency_key="unique-file-1",
    )
    assert seen[-1].headers["idempotency-key"] == "unique-file-1"
    assert b'name="diarize"\r\n\r\ntrue' in seen[-1].content
    sol.translations.create(
        text="Hola",
        source_language="es",
        target_language="pt",
        idempotency_key="unique-text-1",
    )
    assert json.loads(seen[-1].content)["source_language"] == "es"
    with pytest.raises(ValueError):
        sol.transcriptions.create(file=b"a", idempotency_key="spaces are invalid")


def test_get_retry_honors_retry_after():
    count = 0

    def handle(req):
        nonlocal count
        count += 1
        return (
            httpx.Response(
                429,
                headers={"retry-after": "0"},
                json={"error": {"code": "rate_limit", "message": "wait"}},
            )
            if count == 1
            else httpx.Response(200, json={"characters_remaining": 10})
        )

    assert client(handle).balance.get()["characters_remaining"] == 10
    assert count == 2


def test_no_billable_retry():
    count = 0

    def handle(req):
        nonlocal count
        count += 1
        return httpx.Response(503, json={"error": {"message": "busy"}})

    with pytest.raises(Exception):
        client(handle).speech.create(text="Hola")
    assert count == 1


def test_idempotent_retry_replays_same_upload_and_key():
    requests = []

    def handle(req):
        requests.append(req)
        return (
            httpx.Response(503, headers={"retry-after": "0"})
            if len(requests) == 1
            else httpx.Response(200, json={"text": "ok"})
        )

    assert (
        client(handle).transcriptions.create(
            file=("x.wav", b"RIFF"), idempotency_key="same"
        )["text"]
        == "ok"
    )
    assert len(requests) == 2
    assert all(
        r.headers["idempotency-key"] == "same" and b"RIFF" in r.content
        for r in requests
    )


@pytest.mark.parametrize(
    "status,cls", [(401, AuthenticationError), (429, RateLimitError)]
)
def test_api_errors(status, cls):
    with pytest.raises(cls) as exc:
        client(
            lambda _: httpx.Response(
                status,
                headers={"x-request-id": "r"},
                json={"error": {"code": "bad", "message": "No", "details": {"a": 1}}},
            ),
            max_retries=0,
        ).balance.get()
    assert (
        exc.value.code == "bad"
        and exc.value.request_id == "r"
        and exc.value.details == {"a": 1}
    )


def test_redirect_does_not_forward_api_key():
    seen = []

    def handle(req):
        seen.append(req)
        return httpx.Response(307, headers={"location": "https://evil.invalid"})

    with pytest.raises(Exception):
        client(handle).balance.get()
    assert len(seen) == 1


def test_invalid_json():
    with pytest.raises(ProtocolError):
        client(lambda _: httpx.Response(200, content=b"not-json")).balance.get()


def test_sse_unicode_and_error():
    content = (
        "data: "
        + json.dumps({"type": "segment", "text": "áé"}, ensure_ascii=False)
        + '\r\n\r\ndata: {"type":"completed","text":"áé"}\n\n'
    ).encode()
    with client(
        lambda _: httpx.Response(
            200, stream=Chunks([content[:27], content[27:28], content[28:]])
        )
    ).transcriptions.stream(file=b"RIFF") as events:
        assert [x["text"] for x in events] == ["áé", "áé"]
    with client(
        lambda _: httpx.Response(
            200,
            content=b'data: {"type":"error","error":{"code":"failed","message":"No","status":401}}\n\n',
        )
    ).transcriptions.stream(file=b"RIFF") as events:
        with pytest.raises(AuthenticationError):
            list(events)


async def test_async_resources_stream_and_close(tmp_path):
    seen = []
    body = AsyncChunks([b"a", b"b"])

    async def handle(req):
        seen.append(req)
        if req.url.path == "/v1/text-to-speech":
            return httpx.Response(200, stream=body)
        return httpx.Response(200, json={"ok": True})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    async with AsyncSol("test", http_client=http) as sol:
        async with sol.speech.stream(text="Hola") as stream:
            await stream.save(tmp_path / "a.mp3")
        assert body.closed and (tmp_path / "a.mp3").read_bytes() == b"ab"
        assert await sol.balance.get() == {"ok": True}
        await sol.voices.list(country="PE")
        await sol.voices.get("a/b")
        await sol.controls.get()
        await sol.dialects.list()
        await sol.transcriptions.create(file=b"wav", idempotency_key="f")
        await sol.translations.create(
            text="Hola", source_language="es", target_language="pt"
        )
        await sol.live.create_session(language="es")
    assert not http.is_closed  # caller owns injected transport
    await http.aclose()


async def test_async_sse():
    body = AsyncChunks([b'data: {"type":"completed","text":"ok"}\n', b"\n"])
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=body))
    ) as http:
        async with AsyncSol("test", http_client=http).transcriptions.stream(
            file=b"wav"
        ) as events:
            assert [event async for event in events] == [
                {"type": "completed", "text": "ok"}
            ]
    assert body.closed


@pytest.fixture
def live_server():
    received = []

    def handler(socket):
        start = json.loads(socket.recv())
        assert start == {"type": "start", "token": "single-use"}
        socket.send('{"type":"ready","id":"live-1"}')
        data = socket.recv()
        received.append(data)
        socket.send('{"type":"transcript","text":"Hola"}')
        assert json.loads(socket.recv()) == {"type": "stop"}
        socket.send('{"type":"completed","text":"Hola"}')

    server = serve(handler, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield (
        {
            "url": f"ws://127.0.0.1:{server.socket.getsockname()[1]}",
            "token": "single-use",
        },
        received,
    )
    server.shutdown()
    thread.join(timeout=3)


def test_live_sync(live_server):
    session, received = live_server
    with LiveConnection(session, timeout=3) as live:
        assert live.ready["type"] == "ready"
        with pytest.raises(ValueError):
            live.send_audio(b"x")
        live.send_audio(b"\x00\x01")
        live.stop()
        assert [e["type"] for e in live] == ["transcript", "completed"]
        with pytest.raises(ProtocolError):
            live.send_audio(b"\x00\x01")
    assert received == [b"\x00\x01"]


async def test_live_async(live_server):
    session, received = live_server
    async with AsyncLiveConnection(session, timeout=3) as live:
        await live.send_audio(b"\x00\x01")
        await live.stop()
        assert [e["type"] async for e in live] == ["transcript", "completed"]
    assert received == [b"\x00\x01"]


def test_sse_without_completion_is_not_success():
    with client(
        lambda _: httpx.Response(
            200, content=b'data: {"type":"segment","text":"partial"}\n\n'
        )
    ).transcriptions.stream(file=b"RIFF") as events:
        with pytest.raises(ProtocolError, match="without a completed"):
            list(events)


def test_interrupted_audio_is_not_retried():
    class Broken(httpx.SyncByteStream):
        def __iter__(self):
            yield b"partial"
            raise httpx.ReadError("broken")

    calls = []

    def handle(req):
        calls.append(req)
        return httpx.Response(200, stream=Broken())

    with pytest.raises(ConnectionError):
        client(handle).speech.create(text="Hola")
    assert len(calls) == 1


async def test_async_cancel_closes_response():
    closed = []

    class Waiting(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"first"
            await asyncio.sleep(60)

        async def aclose(self):
            closed.append(True)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=Waiting()))
    ) as http:
        sol = AsyncSol("test", http_client=http)

        async def read():
            async with sol.speech.stream(text="Hola") as audio:
                async for chunk in audio:
                    await asyncio.sleep(60)

        task = asyncio.create_task(read())
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert closed
