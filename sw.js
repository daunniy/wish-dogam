/* 치이카와 위시 도감 — 오프라인 지원
   · 화면·굿즈 목록: 인터넷이 되면 항상 최신을 받고, 안 될 때만 저장해 둔 것을 씀
   · 도감에 들어 있는 사진(img/ sp/ photos/ icons/): 한 번 받으면 저장해 둔 것을 씀
   · 다른 사이트(쇼핑몰 사진, 로그인, 환율)는 건드리지 않음
   ※ img/ sp/ photos/ 의 사진을 같은 파일 이름으로 바꿨다면 아래 숫자를 하나 올려 줘 (폰에 저장된 옛 사진이 지워짐) */
const CACHE="dogam-v2";
self.addEventListener("install",()=>self.skipWaiting());
self.addEventListener("activate",e=>e.waitUntil((async()=>{
  for(const k of await caches.keys())if(k!==CACHE)await caches.delete(k);
  await self.clients.claim();
})()));
self.addEventListener("fetch",e=>{
  const r=e.request,u=new URL(r.url);
  if(r.method!=="GET"||u.origin!==location.origin)return;
  const isImg=/\/(img|sp|photos|icons)\/[^/]+$/.test(u.pathname);
  e.respondWith((async()=>{
    const c=await caches.open(CACHE);
    if(isImg){const hit=await c.match(r);if(hit)return hit}
    try{
      const res=await fetch(r);
      if(res.ok)c.put(r,res.clone()).catch(()=>{});
      return res;
    }catch(err){
      const hit=await c.match(r,{ignoreSearch:r.mode==="navigate"});
      if(hit)return hit;
      throw err;
    }
  })());
});
