"""치이카와 위시 도감 자동 업데이트
- 일본 공식샵(chiikawamarket.jp) / 나가노마켓(치이카와 캐릭터만)에서 도감에 없는 상품을 추가
- 기존 상품의 품절/판매중 상태 갱신
- 품절 상품의 메루카리 판매완료 시세 갱신 (하루 MKT_LIMIT개씩, 오래된 것부터)
- 끝나면 data/bundle.js 를 다시 만듦
사용: python scripts/update.py   (환경변수 MKT_LIMIT=200, SKIP_MERCARI=1, SKIP_SHOP=1)
"""
import datetime,json,os,re,sys,time,statistics,urllib.request,urllib.parse,colorsys,io
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
BRAND=re.compile(r"^(ちいかわぽけっと|ちいかわ|ナガノマーケット|ナガノキャラクターズ|ナガノフレンズ)\s*")
SERIES_JA=re.compile(r'映画「?ちいかわ」?|アニメ『ちいかわ』|『ちいかわ』|(超)?まじかるちいかわ|東京ちいかわ|ちいかわ(?=[ァ-ヴー一-龥]|らんど|ぽけっと|たち|ず|\s?[Bb]aby|×|\s?x\s)|ちいかわ(?=\s*[A-Za-z])')
def detect_chars(nj):
    t=re.sub(r'【[^】]*】','',nj);t=BRAND.sub('',t,1);t=SERIES_JA.sub(' ',t)
    paren=" ".join(re.findall(r'[（(]([^）)]*)[）)]',t))
    for src in (paren,t):
        hits=sorted((src.find(ja),ko) for ja,ko in CH if ja in src)
        if hits: return [k for _,k in hits]
    return []
def chars_of_old(t):
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
        u=img_url.split("?")[0]+("?width=96" if "shopify" in img_url else "")
        raw=urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=30).read()
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
            s=BRAND.sub(lambda m:{"ちいかわ":"치이카와 ","ちいかわぽけっと":"치이카와 포켓 "}.get(m.group(1),"나가노 캐릭터즈 " if "キャラクターズ" in m.group(1) else ""),t)
            for ja,ko in CH: s=s.replace(ja,ko)
            url="https://translate.googleapis.com/translate_a/single?client=gtx&sl=ja&tl=ko&dt=t&q="+urllib.parse.quote(s)
            j=json.load(urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=15))
            out="".join(seg[0] for seg in j[0] if seg and seg[0]).strip()
            out=re.sub(r"\s+"," ",out).replace("（","(").replace("）",")")
            if out and not re.search(r"[぀-ヿ]",out):
                _gt_fail[0]=0;return out,"google"
        except Exception:
            _gt_fail[0]+=1
    core=BRAND.sub("",t);m=BRAND.match(t)
    pre={"ちいかわぽけっと":"치이카와 포켓 ","ナガノキャラクターズ":"나가노 캐릭터즈 "}.get(m.group(1),"") if m else ""
    return (pre+dict_tr(core)).strip() if pre else dict_tr(t),"dict"

# ---------- 공식 한국어 이름 (치이카와샵·나가노마켓 /ko 페이지) ----------
FAN={"라코":"랏코","토끼":"우사기","가르마":"하치와레","하늘다람쥐":"모몽가","헌책방":"후루혼야","밤만쥬":"쿠리만쥬","해달":"랏코","그 녀석":"아노코","갑옷상":"갑옷씨","검은 별":"검은별"}
def ko_clean(t):
    t=re.sub(r"【[^】]*】","",t).strip()
    t=re.sub(r"^\s*(\[(예약|사전 ?주문|추첨 ?판매|予約|재입고|입고 예정)[^\]]*\]\s*)+","",t)
    t=t.replace('영화 "치이카와"',"영화 치이카와").replace("영화 「치이카와」","영화 치이카와")
    t=re.sub(r"^Nagano Characters\s*","나가노 캐릭터즈 ",t)
    t=re.sub(r"^(Nagano Market|나가노 마켓)\s*","",t)
    t=re.sub(r"^치이카와\s+(?=치이카와|영화 치이카와|애니메이션|애니\s)","",t)
    t=re.sub(r"치이카와(레스토랑|파크|클리닉|베이커리|랜드|반점)",r"치이카와 \1",t)
    for a,b in FAN.items(): t=re.sub(r"(?<![가-힣])"+a+r"(?=$|[^가-힣]|의|가|를|은|는|와|과|도|랑)",b,t)
    t=re.sub(r"(?<![가-힣장수])풍뎅이(?=$|[^가-힣]|의)","장수풍뎅이",t)
    return re.sub(r"\s+"," ",t).strip()
def ko_titles(base):
    m={};page=1
    while True:
        try: d=get_json(f"{base}/ko/products.json?limit=250&page={page}")
        except Exception as e:
            print("한국어 이름 실패",base,e);break
        ps=d.get("products",[])
        if not ps: break
        for x in ps: m[x["handle"]]=ko_clean(x["title"])
        page+=1;time.sleep(.3)
    return m
def apply_official_names(lists,maps):
    n=0
    for L in lists:
        for it in L:
            if it.get("nameSrc")=="user": continue
            pre,_,h=it["id"].partition("-")
            nm=maps.get(pre,{}).get(h)
            if nm and it.get("name")!=nm: it["name"]=nm;it["nameSrc"]="official";n+=1
    print("공식 한국어 이름 적용",n,"개")

# ---------- 쇼핑몰 상품 불러오기 ----------
def all_products(base):
    out=[];page=1
    while True:
        d=get_json(f"{base}/products.json?limit=250&page={page}")
        ps=d.get("products",[])
        if not ps: break
        out+=ps;page+=1;time.sleep(.4)
    return out
POCKET_GQL="https://chiikawa-pocket-goods-store.myshopify.com/api/2024-07/graphql.json"
POCKET_TOKEN="17dcf71ecda80f11e15d3f99380770d2"   # 치이카와 포켓 스토어 웹사이트가 공개로 쓰는 읽기 전용 키
def pocket_products():
    Q="query($c:String){products(first:250,after:$c){edges{node{handle title productType availableForSale publishedAt priceRange{minVariantPrice{amount}} featuredImage{url}}} pageInfo{hasNextPage endCursor}}}"
    out=[];c=None
    while True:
        r=urllib.request.Request(POCKET_GQL,data=json.dumps({"query":Q,"variables":{"c":c}}).encode(),headers={**UA,"Content-Type":"application/json","X-Shopify-Storefront-Access-Token":POCKET_TOKEN})
        d=json.load(urllib.request.urlopen(r,timeout=40))["data"]["products"]
        for e in d["edges"]:
            n=e["node"]
            out.append({"title":n["title"],"handle":n["handle"],"product_type":n.get("productType") or "","published_at":n.get("publishedAt") or "",
                "variants":[{"price":n["priceRange"]["minVariantPrice"]["amount"],"available":n["availableForSale"]}],
                "images":[{"src":n["featuredImage"]["url"]}] if n.get("featuredImage") else []})
        if not d["pageInfo"]["hasNextPage"]: break
        c=d["pageInfo"]["endCursor"]
    return out

def to_item(p,shop,prefix,base):
    t=p["title"];h=p["handle"]
    v=p["variants"][0] if p.get("variants") else {}
    avail=any(x.get("available") for x in p.get("variants",[]))
    img=p["images"][0]["src"] if p.get("images") else ""
    if img: img=img.split("?")[0]+"?width=480"
    pub=(p.get("published_at") or p.get("created_at") or "")[:10]
    chs=detect_chars(t)
    recent=pub and (time.time()-time.mktime(time.strptime(pub,"%Y-%m-%d")))<14*86400
    nm,src=translate(t)
    return {"id":prefix+h,"name":nm,"nameSrc":src,"nameJa":t,"character":chs[0] if chs else ("다른 친구들" if re.search("島二郎|セイレーン|ヒトハ|フタバ|人魚|びんよよ",t) else "모두 함께"),"chars":chs,"series":"",
        "category":cat_of(t,p.get("product_type") or ""),"price":int(float(v.get("price") or 0)),"currency":"JPY","shop":shop,
        "released":pub.replace("-","."),"link":f"{base}/products/{h}","img":img,"colors":[],"memo":"",
        "available":avail,"upcoming":(not avail and bool(recent)),"popRank":9999,"addedAt":TODAY}

def retranslate(added,limit):
    """사전 번역으로 들어간 이름을 구글 번역으로 다시 다듬기 (되는 날에만)"""
    todo=[i for i in added if i.get("nameSrc")=="dict"][:limit]
    if not todo: return
    nm,src=translate(todo[0]["nameJa"])
    if src!="google": print("구글 번역 불가 → 이름 다듬기 건너뜀");return
    todo[0]["name"]=nm;todo[0]["nameSrc"]=src;n=1
    for it in todo[1:]:
        nm,src=translate(it["nameJa"])
        if src!="google": break
        it["name"]=nm;it["nameSrc"]=src;n+=1;time.sleep(.15)
    print("이름 다듬기",n,"개")

# ---------- 티몰 치이카와 공식몰 (중치마 트래커 www.chiikawatracker.kr 의 공개 목록, 하루 한 번만 읽음) ----------
KO_CH=["치이카와","하치와레","우사기","모몽가","쿠리만쥬","랏코","시사","후루혼야","아노코","검은별","키메라","데카츠요","고블린","오데","장수풍뎅이","갑옷씨"]
JUNK=re.compile(r"(공식\s*)?(순정|정품)|주변기기|주변|공식|생일\s*선물|선물|굿즈|\s{2,}")
def tm_cat(t):
    if re.search("手办|摆件|盲盒|figure",t,re.I): return "피규어"
    if re.search("挂件|挂饰|钥匙扣",t): return "마스코트"
    if re.search("毛绒|玩偶|公仔|抱枕",t): return "누이"
    if re.search("徽章|吧唧|胸针",t): return "키링"
    if re.search("食品|果汁|果冻|糖|零食|饼干|饮料",t): return "기타"
    if re.search("拖鞋|鞋|T恤|卫衣|袜|帽|包|睡衣|衣",t): return "의류"
    if re.search("贴纸|文具|笔|本子|笔记|便签|卡片|卡套|明信片|文件|立牌|亚克力",t): return "문구"
    if re.search("杯|毛巾|手帕|盘|碗|勺|收纳|镜|发|伞|毯|靠垫|保温",t): return "생활"
    return "기타"
def tm_label(o):
    lab=re.sub(r"^.*?/","",o.get("ko") or o.get("name") or "").strip()
    if re.search("블라인드|랜덤|random|随机",lab,re.I): return "랜덤"
    return lab[:28]
def tracker_items(have,status):
    d=get_json("https://www.chiikawatracker.kr/api/items.php")
    out=[]
    for p in d.get("items",[]):
        title=p.get("title","");base=JUNK.sub(" ",p.get("ko") or "").strip(" ,")
        if re.search(r"盲盒|随机|全套|套装|블라인드|랜덤|세트",title+" "+(p.get("ko") or "")): continue
        many=len(p.get("opts",[]))>1
        for o in p.get("opts",[]) or [{"sku":p["id"],"in":True,"ko":"","img":p.get("img")}]:
            iid="tm-"+str(o["sku"]);status[iid]=bool(o.get("in"))
            if iid in have: continue
            lab=tm_label(o) if many else ""
            chs=[c for c in KO_CH if c in lab] or [c for c in KO_CH if c in base] or (["후루혼야"] if "카니" in lab else [])
            nm=("티몰 "+base+(f" ({lab})" if lab else "")).strip()
            out.append({"id":iid,"name":nm,"nameSrc":"tracker","nameZh":title,"character":chs[0] if chs else "치이카와","chars":chs,"series":"",
                "category":tm_cat(title),"price":0,"noPrice":True,"currency":"CNY","shop":"티몰 공식몰",
                "released":"","link":f"https://detail.tmall.com/item.htm?id={p['id']}&skuId={o['sku']}","img":(o.get("img") or p.get("img") or "").replace("http://","https://"),
                "colors":[],"memo":"가격은 티몰에서 확인","available":bool(o.get("in")),"upcoming":False,"popRank":9999,"addedAt":TODAY})
    return out

SETJ=re.compile(r"全\s*\d+\s*種|コンプ|ランダム|アソート|ブラインド|シークレット含")
GROUPJ=re.compile(r"みんな|集合|大集合|トリオ|なかまたち|仲間たち|ファミリー")
def is_set_or_group(title):
    t=re.sub(r"【[^】]*】","",title or "")
    if SETJ.search(t): return True
    par=re.findall(r"[（(]([^）)]*)[）)]",t)
    if par and not GROUPJ.search(par[-1]):
        try:
            if len(detect_chars(par[-1]))==1: return False
        except Exception: pass
    if GROUPJ.search(t): return True
    try: return len(detect_chars(t))>=2 and not re.search(r"(になった|なりきり|な)[ぁ-んァ-ン一-龥]*(ちいかわ|ハチワレ|うさぎ|モモンガ)",t)
    except Exception: return False

def update_shops(catalog,extra,added):
    have={i["id"] for i in catalog["items"]}|{d["id"] for d in extra}|{i["id"] for i in added}|set(load("hidden.json",[]))
    def _nj(t): return re.sub(r"\s+","",re.sub(r"【[^】]*】","",t or ""))
    have_names={(i.get("shop"),_nj(i.get("nameJa"))) for i in catalog["items"]+extra+added if i.get("nameJa")}
    status={}
    new=[]
    for base,shop,prefix,only_chiikawa,all_items in [("https://chiikawamarket.jp","일본 공식몰","jp-",False,True),("https://nagano-market.jp","나가노 마켓","ng-",True,False),("https://chiikawa-pocket-goods-store.com","치이카와 포켓 스토어","pk-",False,True)]:
        try: ps=pocket_products() if prefix=="pk-" else all_products(base)
        except Exception as e:
            print("상품 목록 실패",base,e);continue
        print(base,len(ps),"개 상품")
        for p in ps:
            iid=prefix+p["handle"]
            avail=any(x.get("available") for x in p.get("variants",[]))
            status[iid]=avail
            if iid in have or (shop,_nj(p["title"])) in have_names: continue
            if only_chiikawa and not any(ja in p["title"] for ja,_ in CH): continue
            if is_set_or_group(p["title"]): continue   # 세트·랜덤·단체 상품은 넣지 않음 (캐릭터별 단품만)
            if not avail and not all_items: continue   # 나가노마켓은 판매중인 것만, 치이카와샵은 전 상품
            if not p.get("images"): continue
            new.append((p,shop,prefix,base))
    try:
        tm=tracker_items(have,status);print("티몰 새 상품",len(tm))
        with cf.ThreadPoolExecutor(8) as ex:
            for it,cols in zip(tm,ex.map(lambda i:colors_of(i["img"]) if i["img"] else [],tm)): it["colors"]=cols
        added+=tm
    except Exception as e: print("티몰 목록 실패",e)
    print("새로 추가할 상품",len(new))
    with cf.ThreadPoolExecutor(4) as ex:
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

# ---------- 치이카와샵 시리즈(컬렉션) → 시리즈 이름 ----------
SERIES_COLL=[("chiikawaclinic","치이카와 클리닉"),("ana","치이카와×ANA"),("suppaiman","치이카와×슷파이만"),("go-ikebukuro-goods","Go!IKEBUKURO"),
 ("tokyochiikawa","도쿄 치이카와"),("goharajuku","Go!HARAJUKU"),("chiikawababy","Chiikawa Baby"),("tenshitoakuma","천사♡악마"),("parallelworld","치이카와 평행 세계!?"),
 ("chiikawabakery","치이카와 베이커리"),("chiikawa-sushi","치이카와 스시"),("shisamatsuri","시사 축제 & 시사 기념품"),("ramenbuta","치이카와 라멘 부타"),
 ("magicalchiikawa","매지컬 치이카와"),("chiikawarestaurant","치이카와 레스토랑"),("suizokukan","치이카와 수족관"),("sanriocharacters","치이카와×산리오"),
 ("wakuwakuyuenchi","두근두근 유원지"),("chiikawahanten","치이카와 반점"),("chiikawaland","치이카와 랜드"),("chiikawamovie","인어섬의 비밀 (영화)"),
 ("chiikawapark","치이카와 파크"),("anime-chiikawa","애니 치이카와"),("tokyomiyage","치이카와 도쿄 기념품")]
def update_series(lists):
    m={}
    for coll,name in SERIES_COLL:
        try:
            p=1
            while True:
                d=get_json(f"https://chiikawamarket.jp/collections/{coll}/products.json?limit=250&page={p}").get("products",[])
                if not d: break
                for x in d: m.setdefault("jp-"+x["handle"],name)
                p+=1;time.sleep(.3)
        except Exception as e: print("시리즈 실패",coll,e)
    n=0
    for L in lists:
        for it in L:
            nm=m.get(it["id"])
            if nm and it.get("series")!=nm: it["series"]=nm;n+=1
    print("시리즈 지정",n,"개")

def update_restock(all_items,days=30):
    """치이카와샵(일본) 재입고 컬렉션 → data/restock.json"""
    ids={i["id"] for i in all_items}
    R=load("restock.json",{"items":[]});by={x["pid"]:x for x in R.get("items",[])}
    for page in range(1,5):
        try: d=get_json(f"https://chiikawamarket.jp/ko/collections/restock/products.json?limit=250&page={page}").get("products",[])
        except Exception as e: print("재입고 불러오기 실패",e);break
        if not d: break
        for x in d:
            at=(x.get("published_at") or "")[:16]
            m=[]
            for v in x.get("variants",[]):
                k=f"jp-{v.get('sku')}"
                if k in ids: m.append(k)
                else: m+=[i for i in ids if i.startswith(k+"~")]
            img=(x.get("images") or [{}])[0].get("src","")
            e={"pid":x["id"],"handle":x.get("handle",""),"title":ko_clean(x.get("title","")),"at":at,"avail":any(v.get("available") for v in x.get("variants",[])),"ids":sorted(set(m)),"img":img}
            old=by.get(x["id"])
            if old and old.get("at")==at: old.update(avail=e["avail"],ids=e["ids"] or old.get("ids",[]),title=e["title"])
            else: by[x["id"]]=e
    cut=(datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))-datetime.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M")
    items=sorted([x for x in by.values() if x.get("at","")>=cut],key=lambda x:x["at"],reverse=True)
    save("restock.json",{"updated":datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M"),"items":items})
    print("재입고",len(items),"개 (최근",days,"일)")

def bundle():
    catalog=load("catalog.json",{"items":[]});added=load("added.json",[])
    c=dict(catalog);c["items"]=catalog["items"]+added
    data={"catalog":c,"market":load("market.json",{}),"extra":load("extra.json",[]),"restock":load("restock.json",{"items":[]}),"updated":load("sync.json",{}).get("lastRun","")}
    open(D("bundle.js"),"w",encoding="utf-8").write("window.DOGAM_DATA="+json.dumps(data,ensure_ascii=False,separators=(",",":"))+";\n")
    print("bundle.js 작성",os.path.getsize(D("bundle.js"))//1024,"KB")

def main():
    if "--bundle-only" in sys.argv: return bundle()
    catalog=load("catalog.json",{"items":[]});extra=load("extra.json",[]);added=load("added.json",[]);market=load("market.json",{})
    if "--restock" in sys.argv:
        update_restock(catalog["items"]+added+extra);return bundle()
    n=0
    if not os.environ.get("SKIP_SHOP"):
        n=update_shops(catalog,extra,added)
        retranslate(added,int(os.environ.get("RETRANSLATE_LIMIT","1500")))
        maps={"jp":ko_titles("https://chiikawamarket.jp"),"ng":ko_titles("https://nagano-market.jp")}
        apply_official_names([catalog["items"],added,extra],maps)
        update_series([catalog["items"],added,extra]);save("extra.json",extra)
        save("catalog.json",catalog);save("added.json",added)
    if not os.environ.get("SKIP_MERCARI"):
        try: update_market(catalog,added,market,int(os.environ.get("MKT_LIMIT","400")))
        except Exception as e: print("메루카리 갱신 실패",e)
        save("market.json",market)
    try: update_restock(catalog["items"]+added+extra)
    except Exception as e: print("재입고 갱신 실패",e)
    save("sync.json",{"lastRun":TODAY,"added":n})
    bundle()

if __name__=="__main__": main()
