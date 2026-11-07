"""python live_python.py speech.pcm — raw PCM16LE, 16 kHz, mono (no header)."""

import asyncio
import sys
from pathlib import Path
from buildsol import AsyncSol


async def main():
    data = Path(sys.argv[1]).read_bytes()
    if len(data) % 2:
        raise ValueError("Invalid PCM16 byte count")
    async with AsyncSol() as sol:
        async with sol.live.connect(language="es") as live:

            async def send():
                for offset in range(0, len(data), 3200):
                    chunk = data[offset : offset + 3200]
                    await live.send_audio(chunk)
                    await asyncio.sleep(len(chunk) / 32000)
                await live.stop()

            async def receive():
                async for event in live:
                    print(event)  # replace the cumulative transcript, do not append

            tasks = [asyncio.create_task(send()), asyncio.create_task(receive())]
            try:
                await asyncio.gather(*tasks)
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)


asyncio.run(main())
