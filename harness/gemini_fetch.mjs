// Only the specified Gemini RPCs are forwarded to the operator-owned Unix socket.
import http from 'node:http';
import { Readable } from 'node:stream';
globalThis.fetch = async (input, init) => {
  const request = new Request(input, init);
  const url = new URL(request.url);
  const allowed = /^\/v1beta\/models\/gpt-6\.1-sol:(generateContent|streamGenerateContent|countTokens)$/;
  if (url.origin !== 'http://rax-model.invalid' || !allowed.test(url.pathname) ||
      !['', '?alt=sse'].includes(url.search) || request.method !== 'POST')
    throw new Error('Unsupported model service operation');
  const bytes = Buffer.from(await request.arrayBuffer());
  return new Promise((resolve, reject) => {
    const out = http.request({socketPath: process.env.RAX_MODEL_SOCKET,
      method: 'POST', path: url.pathname+url.search,
      headers: {'content-type':'application/json','content-length':bytes.length}}, res =>
        resolve(new Response(Readable.toWeb(res), {status:res.statusCode,headers:res.headers})));
    const cancel = () => out.destroy(new Error('Gemini request aborted'));
    request.signal.addEventListener('abort',cancel,{once:true});
    out.on('close',()=>request.signal.removeEventListener('abort',cancel));
    out.on('error',reject);
    if (request.signal.aborted) cancel(); else out.end(bytes);
  });
};
