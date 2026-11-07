from buildsol import Sol

with Sol() as sol:
    with sol.speech.stream(text="Hola, tu pedido llega mañana.", speed=1.0) as audio:
        audio.save("speech.mp3")
        print("Saved speech.mp3", audio.request_id)
