// node live_javascript.mjs speech.pcm — PCM16LE, 16 kHz mono, no WAV header.
import { readFile } from "node:fs/promises";
import { setTimeout as sleep } from "node:timers/promises";
import { Sol } from "buildsol";
const data = await readFile(process.argv[2]);
if (data.length % 2) throw new Error("Invalid PCM16 byte count");
const controller = new AbortController();
const live = await new Sol().live.connect({ language: "es", signal: controller.signal });
const sender = (async () => {
  for (let i = 0; i < data.length; i += 3200) {
    const chunk = data.subarray(i, i + 3200);
    await live.sendAudio(chunk);
    await sleep(chunk.length / 32, undefined, { signal: controller.signal });
  }
  await live.stop();
})();
const receiver = (async () => {
  for await (const event of live) console.log(event); // cumulative text replaces previous text
})();
try { await Promise.all([sender, receiver]); }
finally { controller.abort(); await live.close(); await Promise.allSettled([sender, receiver]); }
