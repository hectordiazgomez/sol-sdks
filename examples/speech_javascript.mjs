import { Sol } from "buildsol";
const sol = new Sol();
const audio = await sol.speech.stream({ text: "Hola, tu pedido llega mañana.", speed: 1.0 });
await audio.save("speech.mp3");
console.log("Saved speech.mp3", audio.requestId);
