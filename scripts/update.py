"""치이카와 위시 도감 자동 업데이트
- 일본 공식샵(chiikawamarket.jp) / 나가노마켓(치이카와 캐릭터만)에서 도감에 없는 상품을 추가
- 기존 상품의 품절/판매중 상태 갱신
- 품절 상품의 메루카리 판매완료 시세 갱신 (하루 MKT_LIMIT개씩, 오래된 것부터)
- 끝나면 data/bundle.js 를 다시 만듦
사용: python scripts/update.py   (환경변수 MKT_LIMIT=200, SKIP_MERCARI=1, SKIP_SHOP=1)
"""
import json,os,re,sys,time,statistics,urllib.request,urllib.parse,colorsys,io
import concurrent.futures as cf
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0,os.path.join(ROOT,"scripts"))
from jpko import tr as dict_tr
D=lambda *p:os.path.join(ROOT,"data",*p)
TODAY=time.strftime("%Y.%m.%d",time.gmtime(time.time()+9*3600))
UA={"User-Agent":"Mozilla/5.0 (wish-dogam updater)"}

def load(name,default):
    try: return json.load(open(D(name),encoding="utf-8"))
    except Exception: return default
def save(name,obj):
    json.dump(obj,open(D(name),"w",encoding="utf-8"),ensure_ascii=False,separators=(",",":"))
def get_json(url,tries=3):
    for a in range(tries):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=40))
        except Exception as e:
            if a==tries-1: raise
            time.sleep(3+a*4)

# ---------- 캐릭터 / 종류 / 색 ----------
CH=[("黒い星","검은별"),("ちいかわ","치이카와"),("ハチワレ","하치와레"),("うさぎ","우사기"),("モモンガ","모몽가"),("くりまんじゅう","쿠리만쥬"),("ラッコ","랏코"),
    ("シーサー","시사"),("古本屋","후루혼야"),("あのこ","아노코"),("キメラ","키메라"),("でかつよ","데카츠요"),("ゴブリン","고블린"),("むちゃうマン","무챠우맨"),
    ("オデ","오데"),("カブトムシ","장수풍뎅이"),("鎧さん","갑옷씨")]
BRAND=re.compile(r"^(ちいかわ|ナガノマーケット|ナガノキャラクターズ|ナガノフレンズ)\s*")
def chars_of(t):
    core=BRAND.sub("",t)
    paren=" ".join(re.findall(r"[（(]([^）)]*)[）)]",core))
    out=[]
    for src in (paren,core):
        for ja,ko in CH:
            if ja in src and ko not in out: out.append(ko)
        if out: break
    if not out and t.startswith("ちいかわ"): out=["치이카와"]
    return out
TYPE={"マスコット":"마스코트","ぬいぐるみ":"누이","キーホルダー":"키링","ステッカー・マステ":"문구","筆記具":"문구","ファイル":"문구","メモ・ふせん":"문구","カレンダー・手帳・ノート":"문구",
 "ポーチ・ケース":"생활","ハンドタオル":"생활","フェイスタオル":"생활","バス・洗面":"생활","マグカップ・コップ":"생활","充電グッズ":"생활","スマホケース":"생활","ヘアアクセサリー・鏡":"생활","コスメ・美容":"생활","マグネット":"생활","カードホルダー":"생활",
 "バッグ":"의류","Tシャツ・パーカー":"의류","靴下":"의류"}
def cat_of(t,ty):
    if "フィギュア" in t or "ソフビ" in t: return "피규어"
    if ty in TYPE: return TYPE[ty]
    if "マスコット" in t: return "마스코트"
    if "ぬいぐるみ" in t: return "누이"
    if re.search("キーホルダー|キーリング|チャーム|バッジ|缶バッジ",t): return "키링"
    if re.search("ステッカー|シール|ファイル|メモ|ペン|カード|ノート|マステ|テープ|レター",t): return "문구"
    if re.search("バッグ|Tシャツ|ソックス|靴下|パーカー|トート|キャップ|パジャマ|スウェット",t): return "의류"
    if re.search("タオル|ミラー|ポーチ|巾着|マグ|皿|ブランケット|ケース|ボトル|クッション|ヘア",t): return "생활"
    return "기타"
def cname(h,s,v):
    h*=360
    if v<0.25: return "블랙·그레이"
    if s<0.12: return "화이트" if v>0.85 else "블랙·그레이"
    if h>=320 or h<12: return "핑크" if (s<0.6 and v>0.7) else "레드"
    if h<40: return "베이지·브라운" if (s<0.55 or v<0.6) else "오렌지"
    if h<65: return "옐로" if v>0.6 else "베이지·브라운"
    if h<170: return "그린"
    if h<215: return "블루"
    if h<250: return "네이비" if v<0.5 else "블루"
    if h<300: return "퍼플"
    return "핑크"
def colors_of(img_url):
    try:
        from PIL import Image
        raw=urllib.request.urlopen(urllib.request.Request(img_url.split("?")[0]+"?width=96",headers=UA),timeout=30).read()
        im=Image.open(io.BytesIO(raw)).convert("RGB").resize((48,48))
        cnt={};tot=0
        for r,g,b in list(im.getdata()):
            H,S,V=colorsys.rgb_to_hsv(r/255,g/255,b/255)
            if V>0.92 and S<0.08: continue
            c=cname(H,S,V);cnt[c]=cnt.get(c,0)+1;tot+=1
        out=[]
        for c,k in sorted(cnt.items(),key=lambda x:-x[1]):
            sh=k/tot if tot else 0
            if c=="블랙·그레이" and sh<0.45: continue
            if sh>=0.12: out.append(c)
        return out[:3]
    except Exception:
        return []

# ---------- 번역: 구글 번역(되면) → 안 되면 사전 번역 ----------
_gt_fail=[0]
def translate(t):
    if _gt_fail[0]<5:
        try:
            s=BRAND.sub(lambda m:"치이카와 " if m.group(1)=="ちいかわ" else ("나가노 캐릭터즈 " if "キャラクターズ" in m.group(1) else ""),t)
            for ja,ko in CH: s=s.replace(ja,ko)
            url="https://translate.googleapis.com/translate_a/single?client=gtx&sl=ja&tl=ko&dt=t&q="+urllib.parse.quote(s)
            j=json.load(urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=15))
            out="".join(seg[0] for seg in j[0] if seg and seg[0]).strip()
            out=re.sub(r"\s+"," ",out).replace("（","(").replace("）",")")
            if out and not re.search(r"[぀-ヿ]",out):
                _gt_fail[0]=0;return out
        except Exception:
            _gt_fail[0]+=1
    return dict_tr(t)

# ---------- 쇼핑몰 상품 불러오기 ----------
def all_products(base):
    out=[];page=1
    while True:
        d=get_json(f"{base}/products.json?limit=250&page={page}")
        ps=d.get("products",[])
        if not ps: break
        out+=ps;page+=1;time.sleep(.4)
    return out
def to_item(p,shop,prefix,base):
    t=p["title"];h=p["handle"]
    v=p["variants"][0] if p.get("variants") else {}
    avail=any(x.get("available") for x in p.get("variants",[]))
    img=p["images"][0]["src"] if p.get("images") else ""
    if img: img=img.split("?")[0]+"?width=480"
    pub=(p.get("published_at") or p.get("created_at") or "")[:10]
    chs=chars_of(t)
    recent=pub and (time.time()-time.mktime(time.strptime(pub,"%Y-%m-%d")))<14*86400
    return {"id":prefix+h,"name":translate(t),"nameJa":t,"character":chs[0] if chs else "다른 친구들","chars":chs,"series":"",
        "category":cat_of(t,p.get("product_type") or ""),"price":int(float(v.get("price") or 0)),"currency":"JPY","shop":shop,
        "released":pub.replace("-","."),"link":f"{base}/products/{h}","img":img,"colors":[],"memo":"",
        "available":avail,"upcoming":(not avail and bool(recent)),"popRank":9999,"addedAt":TODAY}

def update_shops(catalog,extra,added):
    have={i["id"] for i in catalog["items"]}|{d["id"] for d in extra}|{i["id"] for i in added}
    status={}
    new=[]
    for base,shop,prefix,only_chiikawa in [("https://chiikawamarket.jp","일본 공식몰","jp-",False),("https://nagano-market.jp","나가노 마켓","ng-",True)]:
        try: ps=all_products(base)
        except Exception as e:
            print("상품 목록 실패",base,e);continue
        print(base,len(ps),"개 상품")
        for p in ps:
            iid=prefix+p["handle"]
            avail=any(x.get("available") for x in p.get("variants",[]))
            status[iid]=avail
            if iid in have: continue
            if only_chiikawa and not any(ja in p["title"] for ja,_ in CH): continue
            if not avail: continue          # 지금 살 수 있는 것만 새로 추가 (품절 옛날 상품 제외)
            if not p.get("images"): continue
            new.append((p,shop,prefix,base))
    print("새로 추가할 상품",len(new))
    with cf.ThreadPoolExecutor(6) as ex:
        items=list(ex.map(lambda a:to_item(*a),new))
    with cf.ThreadPoolExecutor(8) as ex:
        for it,cols in zip(items,ex.map(lambda i:colors_of(i["img"]),items)): it["colors"]=cols
    added+=items
    # 품절/판매중 상태 갱신
    n=0
    for it in catalog["items"]+added:
        if it["id"] in status:
            a=status[it["id"]]
            if it.get("available")!=a:
                it["available"]=a;n+=1
                if a: it["upcoming"]=False
    print("상태 바뀐 상품",n)
    return len(items)

# ---------- 메루카리 시세 ----------
SETW=re.compile(r"セット|まとめ|\d+点|\d+体|\d+個|全種|コンプ|\d+種|セット売り|おまとめ|＋|\+")
CHJ=[ja for ja,_ in CH]
def norm(s): return re.sub(r"[\s　・/／&＆×()（）【】「」!！?？~～]+","",s)
def mkt_job(it):
    from mercari import search
    ja=re.sub(r"【[^】]*】","",it["nameJa"]).strip()
    base=re.sub(r"[（(][^）)]*[）)]\s*$","",ja).strip()
    paren=re.findall(r"[（(]([^）)]*)[）)]\s*$",ja)
    chs=[c for c in CHJ if paren and c in paren[0]]
    core=BRAND.sub("",base)
    toks=[t for t in re.split(r"\s+",core) if len(t)>=2]
    key=max(toks,key=len) if toks else core
    kw="ちいかわ "+core+(" "+paren[0] if paren else "")
    d=None
    for a in range(3):
        try: d=search(kw[:80]);break
        except Exception: time.sleep(3+a*5)
    if d is None: return it["id"],None
    pr=[]
    for x in d.get("items",[]):
        nm=x.get("name","")
        if SETW.search(nm) or norm(key) not in norm(nm): continue
        if chs and not any(c in nm for c in chs): continue
        if paren and not chs and norm(paren[0])[:6] not in norm(nm): continue
        try: pr.append(int(x["price"]))
        except Exception: pass
    if len(pr)<3: return it["id"],{"n":len(pr),"at":TODAY}
    pr.sort();q1=pr[len(pr)//4];q3=pr[(3*len(pr))//4];iq=q3-q1
    f=[p for p in pr if q1-1.5*iq<=p<=q3+1.5*iq] or pr
    return it["id"],{"p":int(statistics.median(f)),"lo":f[len(f)//4],"hi":f[(3*len(f))//4],"n":len(f),"at":TODAY}

def update_market(catalog,added,market,limit):
    pool=[i for i in catalog["items"]+added if i.get("nameJa") and i.get("available") is False and not i.get("upcoming")]
    key=lambda i:(market.get(i["id"]) or {}).get("at","0000")
    pool.sort(key=key)
    todo=[i for i in pool if key(i)!=TODAY][:limit]
    print("메루카리 시세 조회",len(todo),"개")
    ok=fail=0
    with cf.ThreadPoolExecutor(3) as ex:
        for iid,r in ex.map(mkt_job,todo):
            if r is None: fail+=1;continue
            old=market.get(iid) or {}
            if r.get("p") or not old.get("p"): market[iid]=r
            else: old["at"]=TODAY;market[iid]=old
            ok+=1
    print("시세 성공",ok,"실패",fail)
    if todo and fail==len(todo): print("※ 메루카리 조회가 전부 실패했어요 (차단됐을 수 있음)")

def bundle():
    catalog=load("catalog.json",{"items":[]});added=load("added.json",[])
    c=dict(catalog);c["items"]=catalog["items"]+added
    data={"catalog":c,"market":load("market.json",{}),"extra":load("extra.json",[]),"updated":load("sync.json",{}).get("lastRun","")}
    open(D("bundle.js"),"w",encoding="utf-8").write("window.DOGAM_DATA="+json.dumps(data,ensure_ascii=False,separators=(",",":"))+";\n")
    print("bundle.js 작성",os.path.getsize(D("bundle.js"))//1024,"KB")

def main():
    if "--bundle-only" in sys.argv: return bundle()
    catalog=load("catalog.json",{"items":[]});extra=load("extra.json",[]);added=load("added.json",[]);market=load("market.json",{})
    n=0
    if not os.environ.get("SKIP_SHOP"):
        n=update_shops(catalog,extra,added)
        save("catalog.json",catalog);save("added.json",added)
    if not os.environ.get("SKIP_MERCARI"):
        try: update_market(catalog,added,market,int(os.environ.get("MKT_LIMIT","200")))
        except Exception as e: print("메루카리 갱신 실패",e)
        save("market.json",market)
    save("sync.json",{"lastRun":TODAY,"added":n})
    bundle()

if __name__=="__main__": main()
