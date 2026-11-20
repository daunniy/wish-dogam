"""치이카와 위시 도감 자동 업데이트
- 일본 공식샵(chiikawamarket.jp) / 나가노마켓(치이카와 캐릭터만) / 반다이 가챠(gashapon.jp)에서 도감에 없는 상품을 추가
- 기존 상품의 품절/판매중 상태 갱신
- 외부 사이트 사진을 쓰는 상품 중 공식몰에 같은 상품이 있으면 공식몰 사진으로
- 품절 상품의 메루카리 시세 갱신: 공식몰(없으면 다른 공식) 일본어 이름, 9090·쿠지는 규칙으로 만든 검색어로 검색, 가장 최근 팔린 3개의 중간값 (하루 MKT_LIMIT개씩, 오래된 것부터)
- 끝나면 data/bundle.js 를 다시 만듦
사용: python scripts/update.py   (환경변수 MKT_LIMIT=200(기본), SKIP_MERCARI=1, SKIP_SHOP=1)
"""
import unicodedata,datetime,html,json,os,re,sys,time,statistics,urllib.request,urllib.parse,colorsys,io
import concurrent.futures as cf
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0,os.path.join(ROOT,"scripts"))
from jpko import tr as dict_tr
D=lambda *p:os.path.join(ROOT,"data",*p)
TODAY=time.strftime("%Y.%m.%d",time.gmtime(time.time()+9*3600))
UA={"User-Agent":"Mozilla/5.0 (wish-dogam updater)"}

def load(name,default):
    """파일이 없으면 default. 파일이 있는데 깨져 있으면 멈춤 (빈 목록으로 덮어쓰는 사고 방지)"""
    if not os.path.exists(D(name)): return default
    try:
        with open(D(name),encoding="utf-8") as f: return json.load(f)
    except Exception as e:
        sys.exit(f"※ data/{name} 파일이 깨져 있어서 멈췄어요 ({e}). 이전 커밋으로 되돌린 뒤 다시 실행해 주세요.")
def _count(obj):
    if isinstance(obj,dict) and isinstance(obj.get("items"),list): return len(obj["items"])
    return len(obj) if isinstance(obj,(list,dict)) else 0
GUARD={"catalog.json","added.json","extra.json","market.json"}   # 갑자기 확 줄면 저장하지 않는 파일
def save(name,obj):
    if name in GUARD and os.path.exists(D(name)) and not os.environ.get("ALLOW_SHRINK"):
        try:
            with open(D(name),encoding="utf-8") as f: old=_count(json.load(f))
        except Exception: old=0
        if old>=50 and _count(obj)<old*0.9:
            sys.exit(f"※ data/{name} 이 {old}개 → {_count(obj)}개로 갑자기 줄어서 저장하지 않고 멈췄어요. (일부러 줄인 거면 ALLOW_SHRINK=1)")
    tmp=D(name)+".tmp"
    with open(tmp,"w",encoding="utf-8") as f: json.dump(obj,f,ensure_ascii=False,separators=(",",":"))
    os.replace(tmp,D(name))
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
            if nm: nm=re.sub(r"\s*\[[^\]]*(발송|예정|구매|배송|예약|취소|동시|지정|순차)[^\]]*\]","",nm).strip()
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

# ---------- 반다이 가챠 (gashapon.jp 공식 사이트의 'ちいかわ' 검색 결과) ----------
GP_BASE="https://gashapon.jp/products/"
def get_html(url,tries=3):
    for a in range(tries):
        try: return urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=40).read().decode("utf-8","replace")
        except Exception:
            if a==tries-1: raise
            time.sleep(3+a*4)
def _gp_text(s): return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]+>"," ",s or ""))).strip()
# 가챠 시리즈 이름은 번역기가 엉뚱하게 바꾸는 게 많아서 먼저 한국어로 바꿔 둠
GP_KO=[("はさむんです。","하사문데스 "),("ならぶんです。","나라분데스 "),("つまんでつなげてますこっと","츠만데 츠나게테 마스코트"),("めじるしアクセサリー","메지루시 액세서리"),
    ("みんなでもぐもぐパーティ","모두 함께 모구모구 파티"),("もぐもぐ","모구모구"),("ますこっと","마스코트"),("マスコット","마스코트"),("チャーム","참"),("スヤスヤ","새근새근 "),
    ("びっくらたまご","빗쿠라타마고 "),("ヴィネットふれんず","비네트 프렌즈"),("ハグコット","허그코트 "),("カプセリウム","캡슐리움 "),("カプキャラ","캡캐라 "),
    ("ジェムリーズ","젬리즈"),("わっか","고리 "),("8の字","8자 "),("でらっくす","디럭스"),("フラットガシャポン","플랫 가샤폰"),("ガシャポン","가샤폰"),("おふろ","목욕"),("ラバーマグネット","러버 마그넷"),("ラバーコースター","러버 코스터")]
def _gp_tr(t):
    for ja,ko in GP_KO: t=t.replace(ja,ko)
    if not re.search(r"[぀-ヿ一-龥]",re.sub("|".join(j for j,_ in CH),"",t)):   # 남은 일본어가 캐릭터 이름뿐이면 번역기 없이
        for ja,ko in CH: t=t.replace(ja,ko)
        return re.sub(r"\s+"," ",t).strip(),"dict"
    return translate(t)
def _gp_chars(t):
    """가챠 한 종의 이름에 나온 캐릭터 (앞에 나온 순서)"""
    return [ko for _,ko in sorted((t.find(ja),ko) for ja,ko in CH if ja in t)]
def _gp_ko(t):
    return _gp_tr(t)[0]
def gashapon_items(have):
    """반다이 가챠: 라인업 하나를 캐릭터(한 종)별 상품으로 나눠서 넣음
       id = gp-<JAN>~<번호>  · 상세 페이지 사진 title 이 그 종의 이름 (ちいかわ / ハチワレ …)"""
    h=get_html(GP_BASE+"result.php?free="+urllib.parse.quote("ちいかわ"))
    cards=re.findall(r'href="detail\.php\?jan_code=(\d+)".*?<img[^>]*src="([^"]+)".*?c-card__name">(.*?)</p>.*?c-card__price--main">([\d,]+)<',h,re.S)
    out=[];seen=set()
    for jan,thumb,name,price in cards:
        name=_gp_text(name);base="gp-"+jan
        if base in seen or "ちいかわ" not in name or "箱売" in name: continue   # 박스 판매는 같은 라인업 묶음이라 뺌
        seen.add(base)
        if base in have or any(x.startswith(base+"~") for x in have): continue
        try: d=get_html(GP_BASE+"detail.php?jan_code="+jan)
        except Exception as e:
            print("가챠 상세 실패",jan,e);continue
        txt=_gp_text(re.sub(r"<script.*?</script>|<style.*?</style>","",d,flags=re.S))
        rel=re.search(r"発売時期\s*(\d{4})年\s*(\d{1,2})月",txt)
        kinds=re.search(r"種類数\s*全\s*(\d+)\s*種",txt)
        released=f"{rel.group(1)}.{int(rel.group(2)):02d}" if rel else ""
        upcoming=bool(released) and released>TODAY[:7]
        # 한 종씩: 사진 title 이 있는 것만 (첫 장은 단체 사진이라 title 이 비어 있음)
        vars_=[];vs=set()
        for src,ttl in re.findall(r'<img[^>]*src="(https://[^"]*/img/model/xl/[^"]+_(?:\d+)\.jpg)"[^>]*title="([^"]*)"',d):
            ttl=html.unescape(ttl).strip()
            if ttl and not re.search("イメージ|パッケージ",ttl) and src not in vs: vs.add(src);vars_.append((src,ttl))
        og=re.search(r'og:image" content="([^"]+)"',d)
        lineup_ko,src_=_gp_tr(name)
        cat="키링" if "めじるし" in name else cat_of(name,"")
        n=kinds.group(1) if kinds else str(len(vars_) or "")
        common={"series":lineup_ko,"category":cat,"price":int(price.replace(",","")),"currency":"JPY","shop":"가챠","released":released,
            "link":GP_BASE+"detail.php?jan_code="+jan,"colors":[],"available":not upcoming,"upcoming":upcoming,"popRank":9999,"addedAt":TODAY}
        if not vars_:   # 종류별 사진이 없으면 라인업 하나로
            chs=detect_chars(name)
            out.append({"id":base,"name":lineup_ko,"nameSrc":src_,"nameJa":name,"character":chs[0] if len(chs)==1 else "모두 함께","chars":chs,
                "img":og.group(1) if og else thumb,"memo":(f"전 {n}종 랜덤 · " if n else "")+"가챠 1회 가격",**common})
        for k,(img,ttl) in enumerate(vars_,1):
            chs=_gp_chars(ttl)
            ch=chs[0] if len(chs)==1 else "모두 함께"   # 여러 캐릭터 또는 장면 이름(캐릭터를 모름)이면 '모두 함께'
            out.append({"id":f"{base}~{k}","name":f"{lineup_ko} ({_gp_ko(ttl)})","nameSrc":src_,"nameJa":f"{name}（{ttl}）",
                "character":ch,"chars":chs,"img":img,"memo":f"전 {n}종 중 1종 · 가챠 1회 가격",**common})
        time.sleep(.5)
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
    official={}   # 공식몰 상품 원본: id → 일본어 이름·사진·가격·링크 (사진 교체·메루카리 검색 이름에 씀)
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
            img=(p.get("images") or [{}])[0].get("src","")
            official[iid]={"ja":p["title"],"img":img.split("?")[0]+"?width=480" if img else "",
                "price":int(float(((p.get("variants") or [{}])[0]).get("price") or 0)),"link":f"{base}/products/{p['handle']}"}
            if iid in have or (shop,_nj(p["title"])) in have_names: continue
            if only_chiikawa and not any(ja in p["title"] for ja,_ in CH): continue
            if is_set_or_group(p["title"]): continue   # 세트·랜덤·단체 상품은 넣지 않음 (캐릭터별 단품만)
            if not avail and not all_items: continue   # 나가노마켓은 판매중인 것만, 치이카와샵은 전 상품
            if not p.get("images"): continue
            new.append((p,shop,prefix,base))
            have.add(iid);have_names.add((shop,_nj(p["title"])))   # 같은 실행 안에서 두 번 들어가지 않게
    # 이미 있는 공식몰 상품: 일본어 이름은 항상 공식몰 기준으로, 사진이 외부 사이트면 공식몰 사진으로
    for it in catalog["items"]+added+extra:
        o=official.get(it["id"])
        if not o: continue
        if o["ja"] and it.get("nameJa")!=o["ja"]: it["nameJa"]=o["ja"]
        if o["img"] and is_external_img(it.get("img")): it["img"]=o["img"]
    try:
        tm=tracker_items(have,status);print("티몰 새 상품",len(tm))
        with cf.ThreadPoolExecutor(8) as ex:
            for it,cols in zip(tm,ex.map(lambda i:colors_of(i["img"]) if i["img"] else [],tm)): it["colors"]=cols
        added+=tm
    except Exception as e: print("티몰 목록 실패",e)
    try:
        gp=gashapon_items(have);print("반다이 가챠 새 상품",len(gp))
        with cf.ThreadPoolExecutor(8) as ex:
            for it,cols in zip(gp,ex.map(lambda i:colors_of(i["img"]) if i["img"] else [],gp)): it["colors"]=cols
        added+=gp
    except Exception as e: print("반다이 가챠 목록 실패",e)
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
    return len(items),official

# ---------- 공식몰 사진: 외부 사이트 사진을 공식몰 사진으로 ----------
OFF_ID=re.compile(r"^(jp|ng|pk)-[^~]+$")   # 공식몰 상품 id (옵션별로 쪼갠 jp-xxx~ 는 제외)
def is_external_img(u):
    """공식몰(shopify)·도감 안 사진이 아닌, 다른 사이트에서 빌려 온 사진인지"""
    u=u or ""
    return u.startswith("http") and "cdn.shopify.com" not in u
def _nk(t):
    t=re.sub(r"\[[^\]]*\]|【[^】]*】","",t or "")
    return re.sub(r"[^0-9A-Za-z가-힣ぁ-ヿ一-龥Ⅰ-ↈ①-⑳]","",t).lower()
def link_official(catalog,added,extra,official,ko_maps):
    """공식몰에 같은 이름·같은 가격의 상품이 있으면
       - 그 공식 상품이 이미 도감에 있으면 → 중복이니 합침 (dup.json, 내 기록은 공식 상품으로 옮겨짐)
       - 없으면 → 사진·링크·일본어 이름을 공식몰 것으로"""
    idx={}
    def put(key,oid,o):
        if len(key)<4: return
        if key in idx:
            if idx[key] and idx[key][0]!=oid: idx[key]=None   # 같은 이름의 공식 상품이 여럿 → 애매해서 안 씀
        else: idx[key]=(oid,o)
    in_data={}
    for i in catalog["items"]+added:
        if OFF_ID.match(i["id"]) and "cdn.shopify.com" in (i.get("img") or ""):
            in_data[i["id"]]=i
            o={"ja":i.get("nameJa",""),"img":i["img"],"price":i.get("price") or 0,"link":i.get("link","")}
            put(_nk(i.get("name")),i["id"],o);put(_nk(i.get("nameJa")),i["id"],o)
    for oid,o in official.items():
        if not o.get("img"): continue
        pre,_,h=oid.partition("-")
        put(_nk((ko_maps.get(pre) or {}).get(h)),oid,o);put(_nk(o["ja"]),oid,o)
    dup=load("dup.json",{});merged=photo=0
    for L,can_merge in ((catalog["items"],True),(added,True),(extra,False)):
        keep=[]
        for it in L:
            hit=None
            if not OFF_ID.match(it["id"]) and is_external_img(it.get("img")) and it.get("currency","JPY")=="JPY":
                hit=idx.get(_nk(it.get("name"))) or idx.get(_nk(it.get("nameJa")))
            if hit:
                oid,o=hit;a=float(it.get("price") or 0);b=float(o.get("price") or 0)
                if a and b and abs(a-b)>max(10,b*0.02): hit=None   # 가격이 다르면 다른 상품으로 봄
            if not hit: keep.append(it);continue
            if can_merge and oid in in_data and oid!=it["id"]:
                dup[it["id"]]=oid;merged+=1;continue
            it["img"]=o["img"];photo+=1
            if not it.get("link"): it["link"]=o["link"]
            if o.get("ja"): it["nameJa"]=o["ja"];it["jaSrc"]="official"
            keep.append(it)
        L[:]=keep
    save("dup.json",dup)
    print("공식몰 사진으로 교체",photo,"개 · 공식 상품과 합침",merged,"개")

# ---------- 메루카리 시세 (공식몰 일본어 이름으로 검색 · 가장 최근 팔린 3개 기준) ----------
SETW=re.compile(r"セット|まとめ|\d+点|\d+体|\d+個|全種|コンプ|\d+種|セット売り|おまとめ|＋|\+")
# 시세를 낮게 끌어내리는 매물: 하자·부속만·묶음 흥정·비공식(핸드메이드 등)
JUNK_MK=re.compile(r"ジャンク|難あり|難有|訳あり|訳有|汚れ|破損|傷あり|キズあり|タグ(なし|無し|切|カット)|のみ|空箱|外箱|台紙|同梱|専用|おまけ|ハンドメイド|類似|パロディ|非公式")
CHJ=[ja for ja,_ in CH]
MKT_FLOOR=0.4   # 정가의 40% 미만으로 팔린 건 다른 상품(미니 사이즈 등)일 가능성이 커서 뺌
def norm(s): return re.sub(r"[\s　・/／&＆×()（）【】「」!！?？~～]+","",s)
OFF_PREFIX=re.compile(r"^(jp|ng|pk)-")
SET_PAREN=re.compile(r"全\s*\d+\s*種|ランダム|アソート|ブラインド|BOX|ボックス",re.I)
def mk_query(ja,want=()):
    """일본어 이름 → 검색어: 【予約】 같은 안내문만 빼고 그대로.
       옵션별로 쪼갠 상품(이름 끝이 （全6種） 등)은 그 부분 대신 캐릭터 이름으로"""
    ja=re.sub(r"【[^】]*】|［[^］]*］|[（(]ご確認ください[）)]|※.*$","",ja).strip()
    paren=(re.findall(r"[（(]([^）)]*)[）)]\s*$",ja) or [""])[0]
    base=re.sub(r"[（(][^）)]*[）)]\s*$","",ja).strip()
    if SET_PAREN.search(paren): paren=" ".join(want)
    head="ちいかわぽけっと " if base.startswith("ちいかわぽけっと") else "ちいかわ "
    core=BRAND.sub("",base).strip()
    return re.sub(r"\s+"," ",head+core+" "+paren).strip(),core,paren

# 일본어 이름이 없는 상품 중 검색어를 확실히 만들 수 있는 것들
NINE={"mascot":("マスコット",),"rubber":("ラバー",),"tee":("tシャツ","tee"),"pants":("パンツ",)}   # 9090 콜라보 (메루카리에선 「ちいかわ 9090 マスコット うさぎ」식)
KUJI_SER=[("생일",("誕生日","バースデー","バースデイ","birthday")),("너구리",("たぬき","タヌキ")),("베이비",("baby","ベビー")),
  ("크리스마스",("クリスマス","xmas","x'mas")),("문어 오징어",("タコ","イカ","たこ","いか")),("크레이프",("クレープ",)),
  ("라멘",("ラーメン","らーめん")),("아이스크림",("アイス",))]
DARAKE={"모몽가 쿠지":"モモンガ","쿠리만쥬 쿠지":"くりまんじゅう","우사기 쿠지":"うさぎ","시사 쿠지":"シーサー"}   # ○○だらけくじ
def mk_plan(it):
    """메루카리 검색 계획. 우선순위: 공식몰 일본어 이름 → 다른 공식 일본어 이름 → 9090·쿠지 규칙.
       한국어 이름이나 「ちいかわ マスコット」 같은 대충 만든 검색어로는 검색하지 않음 (엉뚱한 게 잡혀서) → None"""
    iid=it["id"];want=[j for j,ko in CH if ko in (it.get("chars") or [])]
    ja=(it.get("nameJa") or "").strip()
    m9=re.match(r"ex-9090-(\w+)-",iid)
    if re.search(r"[ぁ-ヿ]",ja) and not m9:
        kw,core,paren=mk_query(ja,want)
        if not want: want=[c for c in CHJ if paren and c in paren]
        toks=[(t,) for t in re.split(r"\s+",core) if len(norm(t))>=2]
        off=bool(OFF_PREFIX.match(iid) or it.get("jaSrc")=="official")
        return {"kw":kw,"must":toks,"miss":1 if len(toks)>=3 else 0,"want":want,"paren":"" if want else paren,"ctx":ja,"src":"official" if off else "ja"}
    if m9 and m9.group(1) in NINE and want:
        t=NINE[m9.group(1)]
        return {"kw":f"ちいかわ 9090 {t[0]} {' '.join(want)}","must":[("9090",),t],"miss":0,"want":want,"paren":"","ctx":"","src":"collab"}
    series=it.get("series") or ""
    m=re.search(r"(?<![A-Za-z])([A-Z])\s*상(?![가-힣])|(라스트\s*원)",it.get("name",""))
    if m and want and "쿠지" in series:
        prize=("ラストワン",) if m.group(2) else (m.group(1)+"賞",)
        if series in DARAKE:
            dj=DARAKE[series]
            return {"kw":f"ちいかわ {dj}だらけくじ {prize[0]} {' '.join(want)}","must":[("だらけ",),prize],"miss":0,"want":want,"paren":"","ctx":dj,"src":"kuji"}
        alt=next((v for k,v in KUJI_SER if k in series),None)
        if alt:
            return {"kw":f"ちいかわ くじ {prize[0]} {' '.join(want)}","must":[("くじ",),alt,prize],"miss":0,"want":want,"paren":"","ctx":"","src":"kuji"}
    return None
def mk_name(it):
    p=mk_plan(it);return p["kw"] if p else ""

def mkt_job(it):
    from mercari import search
    P=mk_plan(it)
    want=P["want"];low=lambda x:norm(unicodedata.normalize("NFKC",x)).lower()   # 전각 Ｄ賞·ＴＥＥ 등도 같게
    others=[c for c in CHJ if c!="ちいかわ" and c not in P["ctx"] and c not in want]   # 이 상품과 상관없는 다른 캐릭터
    retail=float(it.get("price") or 0) if it.get("currency")=="JPY" else 0
    d=None
    for a in range(3):
        try: d=search(P["kw"][:80],n=120);break
        except Exception: time.sleep(3+a*5)
    if d is None: return it["id"],None
    sold=[]
    for x in d.get("items",[]):
        nm=x.get("name","");n=low(nm)
        if SETW.search(nm) or JUNK_MK.search(nm): continue
        if sum(1 for alts in P["must"] if not any(low(t) in n for t in alts))>P["miss"]: continue   # 이름의 단어가 (거의) 다 들어 있어야
        if want and not all(c in nm for c in want): continue
        if P["paren"] and low(P["paren"])[:6] not in n: continue
        if any(c in nm for c in others): continue
        try: p=int(x["price"])
        except Exception: continue
        if retail and P["src"]!="collab" and p<retail*MKT_FLOOR: continue   # 9090처럼 이름이 확실한 콜라보는 정가 아래로 팔린 것도 그대로 씀
        sold.append((int(x.get("updated") or x.get("created") or 0),p,str(x.get("id") or ""),nm[:60]))   # updated = 팔린 시각
    sold.sort(reverse=True)
    top=sold[:3];last=[t[1] for t in top]
    base={"at":TODAY,"v":2,"src":P["src"]}
    if len(last)<3: return it["id"],{**base,"n":len(last)}
    return it["id"],{**base,"p":int(statistics.median(last)),"lo":min(last),"hi":max(last),"r":last,"n":3,
        "m":[[t[2],t[3],t[1]] for t in top]}   # 계산에 쓴 메루카리 매물 (화면에서 직접 확인용)

def update_market(catalog,added,extra,market,limit):
    items=[dict(i) for i in catalog["items"]+added+extra]
    try: auto_series(items)   # 쿠지 시리즈 이름이 필요해서 (복사본에만 적용)
    except Exception as e: print("자동 시리즈 실패",e)
    alive={i["id"] for i in items if mk_plan(i)}
    for k in [k for k in market if k not in alive]: del market[k]   # 없어진 상품·검색어를 못 만드는 상품의 시세는 정리
    pool=[i for i in items if i["id"] in alive and i.get("available") is False and not i.get("upcoming")]
    mv=lambda i:market.get(i["id"]) or {}
    # 순서: ⓪ 직접 지정한 상품(MKT_FIRST) → ① 예전 방식으로 구해서 화면에 잘못 보일 수 있는 시세
    #       → ② 아직 안 구한 인기 상품 → ③ 아직 안 구한 것 → ④ 새 방식 중 오래된 것
    first={x.strip() for x in os.environ.get("MKT_FIRST","").split(",") if x.strip()}
    pop=catalog.get("rank") or {}
    hot=lambda i:i["id"] in pop or (i.get("popRank") or 9999)<9999
    def rank(i):
        if i["id"] in first: return 0
        if mv(i).get("p") and mv(i).get("v")!=2: return 1
        if not mv(i): return 2 if hot(i) else 3
        return 4
    pool.sort(key=lambda i:(rank(i),pop.get(i["id"],9999),mv(i).get("at","0000")))
    todo=[i for i in pool if i["id"] in first or mv(i).get("at")!=TODAY][:limit]   # 직접 지정한 건 오늘 구했어도 다시
    print("메루카리 시세 조회",len(todo),"개")
    ok=fail=0
    with cf.ThreadPoolExecutor(3) as ex:
        for iid,r in ex.map(mkt_job,todo):
            if r is None: fail+=1;continue
            old=market.get(iid) or {}
            if r.get("p") or not old.get("p") or old.get("v")!=2: market[iid]=r   # 예전 방식 값은 믿지 않고 바꿈
            else: old["at"]=TODAY;market[iid]=old   # 이번에 3건이 안 모이면 지난번 값 유지
            ok+=1
    print("시세 성공",ok,"실패",fail)
    for m in market.values(): m.pop("chk",None)   # (같은 라인업보다 비싸도 진짜인 경우가 많아서 숨기지 않음 · 근거 매물 링크로 확인)
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

# ---------- 자동 시리즈: 쿠지 · 치이카와 포켓 · 할로윈(연도별) ----------
POCKET_FIX=[("江戸","에도"),("夏마츠리","여름 축제"),("恐竜","공룡"),("오弁当","도시락"),("오店屋산","가게놀이"),("피쿠닛쿠","피크닉"),("千社札風스티커","센자후다풍 스티커"),
  ("후루츠","과일"),("아리스","앨리스"),("앗수","애쉬"),("코스타","코스터"),("바스타올","목욕 타월"),("오후화이트","오프화이트"),("후리사이즈","프리사이즈")]
POCKET_THEME=["피크닉","에도","과일","판타지","여름 축제","공룡","앨리스","도시락","가게놀이"]
KJ_CH=["치이카와","하치와레","우사기","모몽가","쿠리만쥬","쿠리만주","시사","랏코","후루혼야","검은별","가르마","토끼"]
KJ_RX=re.compile(r"^(.*?)\s*([A-Z]|라스트\s*원)\s*상(?![가-힣])")
KJ_CHRX=re.compile(r"^(치이카와|하치와레|우사기|모몽가|쿠리만쥬|시사|랏코|후루혼야)\s+([A-Z]|라스트\s*원)\s*상(?![가-힣])")
KJ_REN={"2023 제일복권":"2023 이치방쿠지","2022 제일복권":"2022 이치방쿠지","아이스크림 제일복권":"아이스크림","아기":"베이비","2023":"2023 이치방쿠지","2022":"2022 이치방쿠지"}
HW_RX=re.compile(r"할로윈|핼러윈|ハロウィン|仮装")
def auto_series(items):
    by_line={}
    for i in items:
        iid=i["id"];nm=i.get("name","")
        if iid.startswith("pk-"):
            for a,b in POCKET_FIX: nm=nm.replace(a,b)
            i["name"]=nm
            th=next((t for t in POCKET_THEME if f"포켓 {t}" in nm),None)
            if not i.get("series"): i["series"]=f"치이카와 포켓 · {th}" if th else "치이카와 포켓"
        elif re.search(r"(^|\s)포켓 (피크닉|에도|도시락)",nm) and not i.get("series"):
            th=re.search(r"포켓 (피크닉|에도|도시락)",nm).group(1);i["series"]=f"치이카와 포켓 · {th}"
        if not (i.get("series") or "").endswith(("쿠지","이치방쿠지")):
            m=KJ_RX.search(nm)
            if m:
                pfx=m.group(1)
                for c in KJ_CH: pfx=pfx.replace(c," ")
                pfx=re.sub(r"먼작귀|이치방쿠지|이치방 쿠지|쿠지|\s+"," ",pfx).strip()
                if pfx and not pfx.startswith("+"):
                    pfx=KJ_REN.get(pfx,pfx)
                    if i.get("shop")!="경품(프라이즈)": i["shop"]="이치방쿠지·쿠지"
                    i["series"]=f"{pfx} 쿠지" if "이치방쿠지" not in pfx else pfx
                else:
                    m2=KJ_CHRX.search(nm)
                    if m2: i["series"]=f"{m2.group(1)} 쿠지";i["shop"]="이치방쿠지·쿠지"
    # 할로윈: 발매 연도별
    def year(i):
        r=i.get("released") or ""
        if re.match(r"\d{4}\.(0[6-9]|1[01])",r): return r[:4]
        m=re.search(r"(20\d\d)",i.get("name","")+" "+(i.get("nameJa") or ""));return m.group(1) if m else ""
    hw=[i for i in items if HW_RX.search(i.get("name","")+" "+(i.get("nameJa") or ""))]
    key=lambda i:re.sub(r"[（(][^（）()]*[）)]\s*$","",(i.get("nameJa") or "")).strip()
    ky={}
    for i in hw:
        y=year(i)
        if y and key(i): ky.setdefault(key(i),y)
    for i in hw:
        if i.get("series") and not i["series"].startswith("할로윈"): continue
        y=year(i) or ky.get(key(i),"")
        i["series"]=f"할로윈 {y}" if y else "할로윈"

BUNDLE_DROP={"mq","nameSrc","addedAt","jaSrc"}
def bundle():
    catalog=load("catalog.json",{"items":[]});added=load("added.json",[])
    c=dict(catalog);c["items"]=catalog["items"]+added
    try: auto_series(c["items"])
    except Exception as e: print("자동 시리즈 실패",e)
    ex=load("extra.json",[])
    try:
        from namefix import fix_all
        print("이름 다듬기",fix_all(c["items"])+fix_all(ex),"개")
    except Exception as e: print("이름 다듬기 실패",e)
    # 화면에서 안 쓰는 칸은 빼서 bundle.js 를 가볍게 (원본 json 에는 그대로 남음)
    c["items"]=[{k:v for k,v in i.items() if k not in BUNDLE_DROP} for i in c["items"]]
    for i in c["items"]+ex:   # 일본어 이름이 없는 상품(9090·쿠지 등)도 화면의 메루카리 버튼이 같은 검색어를 쓰게
        try: P=mk_plan(i)
        except Exception: P=None
        if P and P["src"] in ("collab","kuji"): i["mkq"]=P["kw"]
    data={"catalog":c,"market":load("market.json",{}),"extra":ex,"restock":load("restock.json",{"items":[]}),"hidden":[h for h in load("hidden.json",[]) if not h.startswith(("tbx-","tm-"))],"dup":load("dup.json",{}),"updated":load("sync.json",{}).get("lastRun","")}
    with open(D("bundle.js.tmp"),"w",encoding="utf-8") as f: f.write("window.DOGAM_DATA="+json.dumps(data,ensure_ascii=False,separators=(",",":"))+";\n")
    os.replace(D("bundle.js.tmp"),D("bundle.js"))
    print("bundle.js 작성",os.path.getsize(D("bundle.js"))//1024,"KB")

def main():
    if "--bundle-only" in sys.argv: return bundle()
    catalog=load("catalog.json",{"items":[]});extra=load("extra.json",[]);added=load("added.json",[]);market=load("market.json",{})
    if "--restock" in sys.argv:
        update_restock(catalog["items"]+added+extra);return bundle()
    n=0
    if not os.environ.get("SKIP_SHOP"):
        n,official=update_shops(catalog,extra,added)
        retranslate(added,int(os.environ.get("RETRANSLATE_LIMIT","1500")))
        maps={"jp":ko_titles("https://chiikawamarket.jp"),"ng":ko_titles("https://nagano-market.jp")}
        apply_official_names([catalog["items"],added,extra],maps)
        try: link_official(catalog,added,extra,official,maps)
        except Exception as e: print("공식몰 사진 교체 실패",e)
        update_series([catalog["items"],added,extra]);save("extra.json",extra)
        save("catalog.json",catalog);save("added.json",added)
    if not os.environ.get("SKIP_MERCARI"):
        try: update_market(catalog,added,extra,market,int(os.environ.get("MKT_LIMIT","200")))
        except Exception as e: print("메루카리 갱신 실패",e)
        save("market.json",market)
    try: update_restock(catalog["items"]+added+extra)
    except Exception as e: print("재입고 갱신 실패",e)
    save("sync.json",{"lastRun":TODAY,"added":n})
    bundle()

if __name__=="__main__": main()
