import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {mkdtemp,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {WebSocketServer} from 'ws';
import {Sol, AuthenticationError, APIError, AbortError, TimeoutError, ProtocolError, LiveConnection} from '../dist/index.js';
const json=(body,status=200,headers={})=>new Response(JSON.stringify(body),{status,headers});
const client=(fetch,extra={})=>new Sol({apiKey:'test-key',fetch,...extra});

test('ESM and CommonJS exports',()=>{assert.equal(typeof createRequire(import.meta.url)('../dist/index.cjs').Sol,'function');});
test('stream yields first chunk before response completion and closes on break',async()=>{
 let cancelled=false;let sent=false;
 const sol=client(async(url,request)=>{assert.equal(request.headers.Authorization,'Bearer test-key');assert.equal(JSON.parse(request.body).text,'Hola');return new Response(new ReadableStream({pull(c){if(!sent){sent=true;c.enqueue(new Uint8Array([1,2]));}},cancel(){cancelled=true;}}),{headers:{'x-request-id':'r1'}});});
 const audio=await sol.speech.stream({text:'Hola'});assert.equal(audio.requestId,'r1');
 for await(const chunk of audio){assert.deepEqual([...chunk],[1,2]);break;}
 assert.ok(cancelled);
});
test('audio create/save preserves bytes',async()=>{
 const folder=await mkdtemp(join(tmpdir(),'sol-sdk-'));
 try{const audio=await client(async()=>new Response(new Uint8Array([0,255]))).speech.create({text:'Hola'});await audio.save(join(folder,'audio.wav'));assert.deepEqual([...await readFile(join(folder,'audio.wav'))],[0,255]);}finally{await rm(folder,{recursive:true});}
});
test('all public routes and multipart fields',async()=>{
 const seen=[];const sol=client(async(url,req)=>{seen.push({url,req});return json({ok:true});});
 await sol.voices.list({country:'PE',gender:'female'});assert.ok(seen.at(-1).url.endsWith('/v1/voices?country=PE&gender=female'));
 await sol.voices.get('a/# ?');assert.ok(seen.at(-1).url.endsWith('/v1/voices/a%2F%23%20%3F'));
 await sol.voices.create({name:'Mi voz',audio:{data:new Uint8Array([1,2]),filename:'sample.mp3'},consent:true});
 assert.equal(seen.at(-1).req.body.get('consent'),'true');assert.equal(seen.at(-1).req.body.get('audio').name,'sample.mp3');
 await sol.voices.delete('abc');assert.equal(seen.at(-1).req.method,'DELETE');
 await sol.balance.get();await sol.controls.get();await sol.dialects.list();
 await sol.transcriptions.create({file:new Uint8Array([1,2]),language:'es',diarize:true},{idempotencyKey:'file-1'});
 assert.equal(seen.at(-1).req.headers['Idempotency-Key'],'file-1');assert.equal(seen.at(-1).req.body.get('diarize'),'true');
 await sol.translations.create({text:'Hola',source_language:'es',target_language:'pt'},{idempotencyKey:'text-1'});
 assert.equal(JSON.parse(seen.at(-1).req.body).target_language,'pt');
 await sol.live.createSession({language:'es'});assert.ok(seen.at(-1).url.endsWith('/v1/audio/transcription-sessions'));
});
test('reference audio multipart',async()=>{
 await client(async(url,req)=>{assert.equal(req.body.get('text'),'Hola');assert.equal(req.body.get('reference_audio').name,'ref.wav');return new Response('audio');}).speech.create({text:'Hola',referenceFile:{data:new Uint8Array([1,2]),filename:'ref.wav'}});
});
test('GET retries 429; billable POST never retries',async()=>{
 let calls=0;const sol=client(async()=>++calls===1?json({error:{message:'wait'}},429,{'retry-after':'0'}):json({characters_remaining:10}));
 assert.equal((await sol.balance.get()).characters_remaining,10);assert.equal(calls,2);
 calls=0;await assert.rejects(()=>client(async()=>{calls++;return json({error:{message:'busy'}},503);}).speech.create({text:'Hola'}),APIError);assert.equal(calls,1);
});
test('idempotent uploads can retry with identical key/data',async()=>{
 const seen=[];await client(async(url,req)=>{seen.push(req);return seen.length===1?json({},503,{'retry-after':'0'}):json({text:'ok'});}).transcriptions.create({file:{data:new Uint8Array([1,2]),filename:'a.wav'}},{idempotencyKey:'same'});
 assert.equal(seen.length,2);assert.ok(seen.every(x=>x.headers['Idempotency-Key']==='same'&&x.body.get('file').size===2));
});
test('typed errors retain status, details, request ID; redirects never followed',async()=>{
 await assert.rejects(()=>client(async(url,req)=>{assert.equal(req.redirect,'manual');return json({error:{message:'No',code:'invalid_key',details:{a:1}}},401,{'x-request-id':'r'});}).balance.get(),e=>e instanceof AuthenticationError&&e.status===401&&e.requestId==='r'&&e.details.a===1);
 await assert.rejects(()=>client(async()=>new Response('',{status:307,headers:{location:'https://elsewhere.invalid'}})).balance.get(),APIError);
});
test('cancellation and timeout',async()=>{
 const fetch=async(url,{signal})=>new Promise((resolve,reject)=>{signal.addEventListener('abort',()=>reject(signal.reason),{once:true});});
 const c=new AbortController();const promise=client(fetch).speech.create({text:'Hola'},{signal:c.signal});c.abort();await assert.rejects(()=>promise,AbortError);
 await assert.rejects(()=>client(fetch,{timeoutMs:5,maxRetries:0}).balance.get(),TimeoutError);
});
test('SSE handles split Unicode and CRLF; errors surface',async()=>{
 const bytes=new TextEncoder().encode('data: {"type":"segment","text":"áé"}\r\n\r\ndata: {"type":"completed","text":"áé"}\n\n');
 const sol=client(async()=>new Response(new ReadableStream({start(c){for(let i=0;i<bytes.length;i++)c.enqueue(bytes.slice(i,i+1));c.close();}})));
 const events=await sol.transcriptions.stream({file:new Uint8Array([1,2])});const found=[];for await(const e of events)found.push(e.text);assert.deepEqual(found,['áé','áé']);
 const broken=await client(async()=>new Response('data: {"type":"error","error":{"message":"No","status":401}}\n\n')).transcriptions.stream({file:new Uint8Array([1,2])});
 await assert.rejects(async()=>{for await(const e of broken){}},AuthenticationError);
});
test('invalid JSON becomes ProtocolError',async()=>{await assert.rejects(()=>client(async()=>new Response('invalid')).balance.get(),ProtocolError);});
test('live websocket waits ready, sends PCM, stops and reads completion',async()=>{
 const server=new WebSocketServer({port:0,host:'127.0.0.1'});await new Promise(r=>server.once('listening',r));let pcm;
 server.on('connection',ws=>{let n=0;ws.on('message',(data,binary)=>{if(n++===0){assert.deepEqual(JSON.parse(data),{type:'start',token:'single-use'});ws.send('{"type":"ready"}');}else if(binary){pcm=Buffer.from(data);ws.send('{"type":"transcript","text":"Hola"}');}else{assert.equal(JSON.parse(data).type,'stop');ws.send('{"type":"completed","text":"Hola"}');ws.close();}});});
 try{const live=await LiveConnection.connect({url:`ws://127.0.0.1:${server.address().port}`,token:'single-use'},{timeoutMs:1000});assert.equal(live.ready.type,'ready');await assert.rejects(()=>live.sendAudio(new Uint8Array([1])));await live.sendAudio(new Uint8Array([1,2]));await live.stop();const types=[];for await(const e of live)types.push(e.type);assert.deepEqual(types,['transcript','completed']);assert.deepEqual([...pcm],[1,2]);}finally{await new Promise(r=>server.close(r));}
});

test('truncated SSE never claims completion',async()=>{
 const stream=await client(async()=>new Response('data: {"type":"segment","text":"partial"}\n\n')).transcriptions.stream({file:new Uint8Array([1,2])});
 await assert.rejects(async()=>{for await(const event of stream){}},/without a completed/);
});
test('partial audio failures are surfaced without retry',async()=>{
 let calls=0;let reads=0;
 const sol=client(async()=>{calls++;return new Response(new ReadableStream({pull(c){if(reads++===0)c.enqueue(new Uint8Array([1,2]));else c.error(new Error('broken'));}}));});
 await assert.rejects(()=>sol.speech.create({text:'Hola'}),/interrupted/);assert.equal(calls,1);
});
test('live disconnect before completion fails',async()=>{
 const server=new WebSocketServer({port:0,host:'127.0.0.1'});await new Promise(r=>server.once('listening',r));
 server.on('connection',ws=>ws.once('message',()=>{ws.send('{"type":"ready"}');setTimeout(()=>ws.close(),5);}));
 try{const live=await LiveConnection.connect({url:`ws://127.0.0.1:${server.address().port}`,token:'x'},{timeoutMs:1000});await assert.rejects(async()=>{for await(const event of live){}},/before completion/);}finally{await new Promise(r=>server.close(r));}
});
