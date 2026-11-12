"""메루카리 판매완료 시세 조회 (메루카리 웹과 같은 방식의 서명 헤더 사용)"""
import json,time,uuid,base64,urllib.request
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
_key=ec.generate_private_key(ec.SECP256R1())
_pub=_key.public_key().public_numbers()
_b64=lambda b:base64.urlsafe_b64encode(b).rstrip(b"=").decode()
_jwk={"crv":"P-256","kty":"EC","x":_b64(_pub.x.to_bytes(32,"big")),"y":_b64(_pub.y.to_bytes(32,"big"))}
def _dpop(url,method="POST"):
    h={"typ":"dpop+jwt","alg":"ES256","jwk":_jwk}
    p={"iat":int(time.time()),"jti":str(uuid.uuid4()),"htu":url,"htm":method,"uuid":str(uuid.uuid4())}
    si=_b64(json.dumps(h,separators=(",",":")).encode())+"."+_b64(json.dumps(p,separators=(",",":")).encode())
    r,s=decode_dss_signature(_key.sign(si.encode(),ec.ECDSA(hashes.SHA256())))
    return si+"."+_b64(r.to_bytes(32,"big")+s.to_bytes(32,"big"))
def search(kw,status=("STATUS_SOLD_OUT",),n=60):
    url="https://api.mercari.jp/v2/entities:search"
    body={"userId":"","pageSize":n,"pageToken":"","searchSessionId":uuid.uuid4().hex,"indexRouting":"INDEX_ROUTING_UNSPECIFIED","thumbnailTypes":[],
      "searchCondition":{"keyword":kw,"excludeKeyword":"","sort":"SORT_CREATED_TIME","order":"ORDER_DESC","status":list(status),"sizeId":[],"categoryId":[],"brandId":[],"sellerId":[],"priceMin":0,"priceMax":0,"itemConditionId":[],"shippingPayerId":[],"shippingFromArea":[],"shippingMethod":[],"colorId":[],"hasCoupon":False,"attributes":[],"itemTypes":[],"skuIds":[]},
      "defaultDatasets":["DATASET_TYPE_MERCARI","DATASET_TYPE_BEYOND"],"serviceFrom":"suruga","withItemBrand":False,"withItemSize":False,"withItemPromotions":False,"withItemSizes":False,"withShopname":False}
    req=urllib.request.Request(url,data=json.dumps(body).encode(),method="POST",headers={"DPoP":_dpop(url),"X-Platform":"web","Content-Type":"application/json","Accept":"application/json","User-Agent":"Mozilla/5.0"})
    return json.load(urllib.request.urlopen(req,timeout=30))
