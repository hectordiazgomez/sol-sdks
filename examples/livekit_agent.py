"""LiveKit voice agent: install livekit-plugins-silero and set cloud + Sol keys."""

import os

from buildsol_livekit import TTS
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, cli, inference
from livekit.plugins import silero

server = AgentServer()


@server.rtc_session()
async def entrypoint(ctx: JobContext):
    session = AgentSession(
        stt=inference.STT(model="deepgram/nova-3", language="es"),
        llm=inference.LLM(model="openai/gpt-4.1-mini"),
        tts=TTS(voice_id=os.getenv("SOL_VOICE_ID")),
        vad=silero.VAD.load(),
    )
    await session.start(
        room=ctx.room,
        agent=Agent(instructions="Responde en español, con frases breves y naturales."),
    )
    await session.say("Hola, soy Sol. Estoy hablando desde LiveKit.")


if __name__ == "__main__":
    cli.run_app(server)
