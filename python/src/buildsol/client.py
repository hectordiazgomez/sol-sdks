from . import _async_resources as asynchronous
from . import _resources as sync
from ._transport import Transport


class Sol:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = "https://api.buildsol.ai",
        timeout: float = 120.0,
        max_retries: int = 2,
        http_client=None,
    ):
        self._transport = Transport(
            api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            http_client=http_client,
        )
        self.speech = sync.Speech(self._transport)
        self.voices = sync.Voices(self._transport)
        self.controls = sync.Controls(self._transport)
        self.dialects = sync.Dialects(self._transport)
        self.balance = sync.BalanceResource(self._transport)
        self.transcriptions = sync.Transcriptions(self._transport)
        self.translations = sync.Translations(self._transport)
        self.live = sync.Live(self._transport)

    def close(self):
        if self._transport.owns_client:
            self._transport.http.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class AsyncSol:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = "https://api.buildsol.ai",
        timeout: float = 120.0,
        max_retries: int = 2,
        http_client=None,
    ):
        self._transport = Transport(
            api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            http_client=http_client,
            asynchronous=True,
        )
        self.speech = asynchronous.Speech(self._transport)
        self.voices = asynchronous.Voices(self._transport)
        self.controls = asynchronous.Controls(self._transport)
        self.dialects = asynchronous.Dialects(self._transport)
        self.balance = asynchronous.BalanceResource(self._transport)
        self.transcriptions = asynchronous.Transcriptions(self._transport)
        self.translations = asynchronous.Translations(self._transport)
        self.live = asynchronous.Live(self._transport)

    async def close(self):
        if self._transport.owns_client:
            await self._transport.http.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()
