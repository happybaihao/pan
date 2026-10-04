

import base64
import binascii
import gzip
import hashlib
import hmac
import json
import os
import random
import re
import struct
import threading
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass

__version__ = "1.0.0"

PC_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
MOB_UA = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36")
IPHONE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.7 "
             "Mobile/15E148 Safari/604.1")


# ---------------- 基础小工具 ----------------

def _s(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else ""
    return str(v).strip()


def _pick(d, *keys):
    if not isinstance(d, dict):
        return ""
    for k in keys:
        v = d.get(k)
        if v is None or v is False:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


def _pick_int(d, *keys):
    if not isinstance(d, dict):
        return 0
    for k in keys:
        v = d.get(k)
        try:
            n = int(float(str(v).strip()))
            if n:
                return n
        except Exception:
            continue
    return 0


def _abs(base, href):
    try:
        return urllib.parse.urljoin(base, _s(href))
    except Exception:
        return _s(href)


def _strip_tags(s):
    s = _s(s)
    s = re.sub(r"(?is)<script.*?</script>", " ", s)
    s = re.sub(r"(?is)<style.*?</style>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


_EP_PATTERNS = [
    re.compile(r"第\s*0*(\d+)\s*[集话期]"),
    re.compile(r"(?:更新至|共|全)\s*0*(\d+)\s*[集话期]"),
    re.compile(r"(?i)(?:episode|ep)\s*#?\s*0*(\d+)"),
]


def _ep_no(title, default=0):
    t = _s(title)
    for p in _EP_PATTERNS:
        m = p.search(t)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
    return default


def _q(s):
    return urllib.parse.quote(_s(s), safe="")


def _uq(s):
    return urllib.parse.unquote(_s(s))


def _md5(s):
    if isinstance(s, str):
        s = s.encode("utf-8")
    return hashlib.md5(s).hexdigest()


def _sha256(s):
    if isinstance(s, str):
        s = s.encode("utf-8")
    return hashlib.sha256(s).digest()


# ---------------- AES（纯 Python，支持 128/192/256，CBC/ECB，加解密） ----------------
# 小 JSON 解密走纯 Python 足够快；pycryptodome / javax.crypto 存在时自动用快的。

def _aes_build_sbox():
    sbox = [0] * 256
    isbox = [0] * 256
    # GF(2^8) 求逆
    def _xt(a):
        return ((a << 1) ^ 0x1B) & 0xFF if (a & 0x80) else (a << 1) & 0xFF
    inv = [0] * 256
    a = 1
    for _ in range(255):
        inv[a] = 1
        a = _xt(a)
    # 构造 exp/log 求完整逆元
    exp = [0] * 512
    log = [0] * 256
    x = 1
    for i in range(255):
        exp[i] = x
        log[x] = i
        x = _xt(x) ^ x
    for i in range(255, 512):
        exp[i] = exp[i - 255]
    full_inv = [0] * 256
    for i in range(1, 256):
        full_inv[i] = exp[255 - log[i]]
    for i in range(256):
        v = full_inv[i]
        s = v
        for r in (1, 2, 3, 4):
            s ^= ((v << r) | (v >> (8 - r))) & 0xFF
        s = (s ^ 0x63) & 0xFF
        sbox[i] = s
        isbox[s] = i
    return sbox, isbox


_AES_SBOX, _AES_ISBOX = _aes_build_sbox()
_AES_RK = {}


def _aes_xtime(a):
    return ((a << 1) ^ 0x1B) & 0xFF if (a & 0x80) else (a << 1) & 0xFF


def _aes_gmul(a, b):
    p = 0
    while b:
        if b & 1:
            p ^= a
        a = _aes_xtime(a)
        b >>= 1
    return p & 0xFF


def _aes_expand_key(key):
    key = bytes(key)
    ck = _AES_RK.get(key)
    if ck:
        return ck
    nk = len(key) // 4
    nr = {4: 10, 6: 12, 8: 14}[nk]
    rcon = (0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36)
    w = [list(key[i:i + 4]) for i in range(0, len(key), 4)]
    for i in range(nk, 4 * (nr + 1)):
        t = w[i - 1][:]
        if i % nk == 0:
            t = t[1:] + t[:1]
            t = [_AES_SBOX[b] for b in t]
            t[0] ^= rcon[i // nk - 1]
        elif nk > 6 and i % nk == 4:
            t = [_AES_SBOX[b] for b in t]
        w.append([w[i - nk][j] ^ t[j] for j in range(4)])
    rk = [b for word in w for b in word]
    _AES_RK[key] = (rk, nr)
    return rk, nr


def _aes_add_rk(s, rk, off):
    return [s[i] ^ rk[off + i] for i in range(16)]


def _aes_shift_rows(s, inv=False):
    o = [0] * 16
    for r in range(4):
        for c in range(4):
            o[r + 4 * c] = s[r + 4 * ((c - r) % 4 if inv else (c + r) % 4)]
    return o


def _aes_mix_col(s, inv=False):
    o = [0] * 16
    for c in range(4):
        a0, a1, a2, a3 = s[4 * c], s[4 * c + 1], s[4 * c + 2], s[4 * c + 3]
        if inv:
            o[4 * c] = (_aes_gmul(a0, 14) ^ _aes_gmul(a1, 11) ^
                        _aes_gmul(a2, 13) ^ _aes_gmul(a3, 9))
            o[4 * c + 1] = (_aes_gmul(a0, 9) ^ _aes_gmul(a1, 14) ^
                            _aes_gmul(a2, 11) ^ _aes_gmul(a3, 13))
            o[4 * c + 2] = (_aes_gmul(a0, 13) ^ _aes_gmul(a1, 9) ^
                            _aes_gmul(a2, 14) ^ _aes_gmul(a3, 11))
            o[4 * c + 3] = (_aes_gmul(a0, 11) ^ _aes_gmul(a1, 13) ^
                            _aes_gmul(a2, 9) ^ _aes_gmul(a3, 14))
        else:
            o[4 * c] = (_aes_gmul(a0, 2) ^ _aes_gmul(a1, 3) ^ a2 ^ a3)
            o[4 * c + 1] = (a0 ^ _aes_gmul(a1, 2) ^ _aes_gmul(a2, 3) ^ a3)
            o[4 * c + 2] = (a0 ^ a1 ^ _aes_gmul(a2, 2) ^ _aes_gmul(a3, 3))
            o[4 * c + 3] = (_aes_gmul(a0, 3) ^ a1 ^ a2 ^ _aes_gmul(a3, 2))
    return o


def _aes_enc_block_py(blk, rk, nr):
    s = _aes_add_rk(list(blk), rk, 0)
    for rnd in range(1, nr):
        s = [_AES_SBOX[b] for b in s]
        s = _aes_shift_rows(s)
        s = _aes_mix_col(s)
        s = _aes_add_rk(s, rk, 16 * rnd)
    s = [_AES_SBOX[b] for b in s]
    s = _aes_shift_rows(s)
    s = _aes_add_rk(s, rk, 16 * nr)
    return bytes(s)


def _aes_dec_block_py(blk, rk, nr):
    s = _aes_add_rk(list(blk), rk, 16 * nr)
    for rnd in range(nr - 1, 0, -1):
        s = _aes_shift_rows(s, inv=True)
        s = [_AES_ISBOX[b] for b in s]
        s = _aes_add_rk(s, rk, 16 * rnd)
        s = _aes_mix_col(s, inv=True)
    s = _aes_shift_rows(s, inv=True)
    s = [_AES_ISBOX[b] for b in s]
    s = _aes_add_rk(s, rk, 0)
    return bytes(s)


def _pkcs7_pad(data):
    n = 16 - (len(data) % 16)
    return bytes(data) + bytes([n] * n)


def _pkcs7_unpad(data):
    data = bytes(data)
    if not data or len(data) % 16:
        raise ValueError("bad pkcs7 length")
    n = data[-1]
    if n < 1 or n > 16 or data[-n:] != bytes([n] * n):
        raise ValueError("bad pkcs7 padding")
    return data[:-n]


def _aes_crypt_fast(data, key, iv, encrypt, mode_cbc):
    """pycryptodome 优先，其次 javax.crypto（真机），最后纯 Python。"""
    data, key = bytes(data), bytes(key)
    try:
        from Crypto.Cipher import AES
        if mode_cbc:
            c = AES.new(key, AES.MODE_CBC, bytes(iv))
        else:
            c = AES.new(key, AES.MODE_ECB)
        return c.encrypt(data) if encrypt else c.decrypt(data)
    except Exception:
        pass
    try:
        from java import jclass
        Cipher = jclass("javax.crypto.Cipher")
        SecretKeySpec = jclass("javax.crypto.spec.SecretKeySpec")
        IvParameterSpec = jclass("javax.crypto.spec.IvParameterSpec")
        trans = "AES/%s/NoPadding" % ("CBC" if mode_cbc else "ECB")
        c = Cipher.getInstance(trans)
        ks = SecretKeySpec(key, "AES")
        if mode_cbc:
            c.init(1 if encrypt else 2, ks, IvParameterSpec(bytes(iv)))
        else:
            c.init(1 if encrypt else 2, ks)
        return bytes(c.doFinal(data))
    except Exception:
        pass
    rk, nr = _aes_expand_key(key)
    enc = _aes_enc_block_py if encrypt else _aes_dec_block_py
    out = bytearray()
    prev = bytes(iv) if (mode_cbc and not encrypt) else None
    prev_enc = bytes(iv) if (mode_cbc and encrypt) else None
    for off in range(0, len(data), 16):
        blk = data[off:off + 16]
        if mode_cbc and encrypt:
            blk = bytes(blk[i] ^ prev_enc[i] for i in range(16))
            e = enc(blk, rk, nr)
            out.extend(e)
            prev_enc = e
        elif mode_cbc:
            d = enc(blk, rk, nr)
            out.extend(bytes(d[i] ^ prev[i] for i in range(16)))
            prev = blk
        else:
            out.extend(enc(blk, rk, nr))
    return bytes(out)


def _aes_cbc_encrypt(data, key, iv):
    return _aes_crypt_fast(_pkcs7_pad(data), key, iv, True, True)


def _aes_cbc_decrypt(data, key, iv):
    return _pkcs7_unpad(_aes_crypt_fast(data, key, iv, False, True))


def _aes_ecb_decrypt(data, key):
    return _pkcs7_unpad(_aes_crypt_fast(data, key, b"\x00" * 16, False, False))


def _aes_cbc_decrypt_nopad(data, key, iv):
    return _aes_crypt_fast(data, key, iv, False, True)


# ---------------- HTTP 层 ----------------
# urllib 主用；Python 栈被目标按 TLS 指纹丢弃时，回落 App 自带 OkHttp（真机）。

_JAVA_CLIENT = [None]


def _java_client():
    if _JAVA_CLIENT[0] is not None:
        return _JAVA_CLIENT[0] or None
    try:
        from java import jclass
        Builder = jclass("okhttp3.OkHttpClient$Builder")
        TimeUnit = jclass("java.util.concurrent.TimeUnit")
        b = Builder()
        b.followRedirects(True)
        b.followSslRedirects(True)
        b.connectTimeout(12, TimeUnit.SECONDS)
        b.readTimeout(30, TimeUnit.SECONDS)
        b.writeTimeout(12, TimeUnit.SECONDS)
        _JAVA_CLIENT[0] = b.build()
    except Exception:
        _JAVA_CLIENT[0] = False
    return _JAVA_CLIENT[0] or None


def _java_fetch(url, headers=None, data=None):
    """返回 (status, headers_dict, body)；失败返回 None。"""
    client = _java_client()
    if client is None:
        return None
    try:
        from java import jclass
        ReqBuilder = jclass("okhttp3.Request$Builder")
        rb = ReqBuilder()
        rb.url(str(url))
        ctype = "application/x-www-form-urlencoded"
        for k, v in (headers or {}).items():
            lk = str(k).lower()
            if lk == "content-type":
                ctype = str(v)
                continue
            if lk in ("content-length", "host", "cookie"):
                continue
            try:
                rb.header(str(k), str(v))
            except Exception:
                pass
        if data is not None:
            MediaType = jclass("okhttp3.MediaType")
            RequestBody = jclass("okhttp3.RequestBody")
            rb.post(RequestBody.create(MediaType.parse(ctype), bytes(data)))
        resp = client.newCall(rb.build()).execute()
        code = 0
        try:
            code = int(resp.code())
        except Exception:
            pass
        h = {}
        try:
            mm = resp.headers().toMultimap()
            for e in mm.entrySet():
                vals = []
                try:
                    for v in e.getValue():
                        vals.append(str(v))
                except Exception:
                    pass
                h[str(e.getKey()).lower()] = vals
        except Exception:
            pass
        out = b""
        try:
            bd = resp.body()
            if bd is not None:
                out = bytes(bd.bytes())
        except Exception:
            pass
        try:
            resp.close()
        except Exception:
            pass
        return code, h, out
    except Exception:
        return None


class _Resp(object):
    def __init__(self):
        self.status = 0
        self.headers = {}
        self.body = b""
        self.url = ""

    def text(self, encoding="utf-8"):
        return self.body.decode(encoding, "ignore")


def _parse_set_cookies(header_vals, jar):
    for hv in header_vals or []:
        part = _s(hv).split(";", 1)[0]
        if "=" in part:
            k, v = part.split("=", 1)
            k = k.strip()
            if k:
                jar[k] = v.strip()


class _Session(object):
    """带 Cookie 罐的会话；fetch 返回 _Resp。"""

    def __init__(self):
        self.cookies = {}
        self._lock = threading.Lock()

    def _cookie_header(self):
        with self._lock:
            items = ["%s=%s" % (k, v) for k, v in self.cookies.items()]
        return "; ".join(items)

    def fetch(self, url, method="GET", headers=None, data=None,
              timeout=12, max_body=8 << 20):
        headers = dict(headers or {})
        ck = self._cookie_header()
        if ck and "cookie" not in {k.lower(): 1 for k in headers}:
            headers["Cookie"] = ck
        if "user-agent" not in {k.lower(): 1 for k in headers}:
            headers["User-Agent"] = PC_UA
        resp = _Resp()
        resp.url = url
        # 1) urllib
        try:
            req = urllib.request.Request(url, data=data, headers=headers,
                                         method=method.upper())
            with urllib.request.urlopen(req, timeout=timeout) as r:
                resp.status = r.status
                raw_h = {}
                try:
                    for k, v in r.headers.items():
                        raw_h.setdefault(k.lower(), []).append(v)
                except Exception:
                    pass
                resp.headers = raw_h
                body = r.read(max_body + 1)
                if len(body) > max_body:
                    raise ValueError("body too large")
                resp.body = body
                try:
                    resp.url = r.geturl()
                except Exception:
                    pass
        except Exception:
            # 2) 真机 OkHttp 回退
            jr = _java_fetch(url, headers=headers, data=data)
            if not jr:
                raise
            resp.status, resp.headers, resp.body = jr
            if len(resp.body) > max_body:
                raise ValueError("body too large")
        _parse_set_cookies(resp.headers.get("set-cookie"), self.cookies)
        # 部分站点不看 Accept-Encoding 直接发 gzip/deflate，中央解压
        try:
            enc = [_s(x).lower() for x in resp.headers.get(
                "content-encoding", [])]
            if resp.body[:2] == b"\x1f\x8b" or any(
                    "gzip" in x for x in enc):
                resp.body = gzip.decompress(bytes(resp.body))
            elif resp.body[:2] == b"\x78\x9c" or any(
                    "deflate" in x for x in enc):
                import zlib
                resp.body = zlib.decompress(bytes(resp.body))
        except Exception:
            pass
        return resp

    def get_text(self, url, headers=None, timeout=12):
        return self.fetch(url, headers=headers, timeout=timeout).text()

    def get_json(self, url, headers=None, timeout=12):
        return json.loads(self.fetch(url, headers=headers,
                                     timeout=timeout).text())

    def post_json(self, url, obj, headers=None, timeout=12):
        h = dict(headers or {})
        h["Content-Type"] = "application/json; charset=utf-8"
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        return json.loads(self.fetch(url, method="POST", headers=h, data=data,
                                     timeout=timeout).text())

    def post_form(self, url, fields, headers=None, timeout=12):
        h = dict(headers or {})
        h["Content-Type"] = "application/x-www-form-urlencoded"
        data = urllib.parse.urlencode(fields).encode("utf-8")
        return self.fetch(url, method="POST", headers=h, data=data,
                          timeout=timeout).text()


# ---------------- 站源框架 ----------------

class _SrcErr(Exception):
    """站源级可预期错误（接口变化/失效/加密等），Spider 会隔离。"""
    pass


def _tid(src, cat):
    return "%s::c::%s" % (src, _q(cat))


def _did(src, sid):
    return "%s::d::%s" % (src, _q(sid))


def _pid(src, sid, ep):
    return "%s::p::%s::%s" % (src, _q(sid), _q(ep))


def _split_tid(tid):
    head, _, cat = _s(tid).partition("::c::")
    return head, _uq(cat)


def _split_did(did):
    head, _, sid = _s(did).partition("::d::")
    return head, _uq(sid)


def _split_pid(pid):
    s = _s(pid)
    head, _, rest = s.partition("::p::")
    sid, _, ep = rest.partition("::")
    return head, _uq(sid), _uq(ep)


def _vod_item(src_id, sid, title, pic="", remark="", content=""):
    return {
        "vod_id": _did(src_id, sid),
        "vod_name": _s(title),
        "vod_pic": _s(pic),
        "vod_remarks": _s(remark),
        "vod_content": _s(content),
    }


def _vod_detail(src, sid, title, pic="", remark="", content="",
                year="", area="", actor="", chapters=()):
    """chapters: [(epkey, eptitle)]"""
    play_url = "#".join(
        "%s$%s" % (_s(t) or ("第%d集" % (i + 1)), _pid(src.id, sid, k))
        for i, (k, t) in enumerate(chapters))
    return {
        "vod_id": _did(src.id, sid),
        "vod_name": _s(title),
        "vod_pic": _s(pic),
        "vod_remarks": _s(remark),
        "vod_content": _s(content),
        "vod_year": _s(year),
        "vod_area": _s(area),
        "vod_actor": _s(actor),
        "vod_play_from": src.name,
        "vod_play_url": play_url,
    }


class _Src(object):
    id = ""
    name = ""
    cats = [("", "推荐")]  # [(catid, catname)] 静态分类

    def __init__(self):
        self.sess = _Session()

    # -- 以下按需覆盖 --
    def home(self, pg):
        """返回 (items, has_more)。"""
        return self.cat("", pg)

    def cat(self, catid, pg):
        raise _SrcErr("本站源暂无目录")

    def detail(self, sid):
        raise _SrcErr("本站源暂无详情")

    def play(self, sid, ep):
        """返回 (media_url, headers_dict)。"""
        raise _SrcErr("本站源暂无播放")

    def search(self, key, pg):
        raise _SrcErr("本站源不支持搜索")


_SOURCES = []


def _register(cls):
    _SOURCES.append(cls())
    return cls


def _find_src(src_id):
    for s in _SOURCES:
        if s.id == src_id:
            return s
    return None


# ============================================================
# 饭果（西饭）— 纯 JSON API，无签名
# ============================================================
@_register
class _Fanguo(_Src):
    id = "fanguo"
    name = "饭果"
    cats = [("都市", "都市"), ("甜宠", "甜宠"), ("逆袭", "逆袭"), ("战神", "战神"),
            ("古装", "古装"), ("穿越", "穿越"), ("萌宝", "萌宝")]
    BASE = "https://xifan-api-cn.youlishipin.com"

    def _list(self, keyword, pg):
        if pg > 1:
            return [], False
        url = (self.BASE + "/xifan/search/getSearchList?reqType=search&offset=0"
               "&keyword=%s&quickEngineVersion=-1&scene=" % _q(keyword or "都市"))
        j = self.sess.get_json(url, headers={"Referer": self.BASE + "/"})
        items = []
        try:
            elements = j["result"]["elements"]
        except Exception:
            elements = []
        for el in elements:
            for c in (el.get("contents") or []):
                vo = c.get("duanjuVo") or {}
                vid = _pick(vo, "duanjuId", "duanju_id", "id")
                if not vid:
                    continue
                source = _pick(vo, "source")
                sid = "%s#%s" % (vid, source)
                items.append(_vod_item(
                    self.id, sid,
                    _pick(vo, "title", "name"),
                    _pick(vo, "coverImageUrl", "cover_image_url", "cover"),
                    ("全%s集" % _pick_int(vo, "total", "totalEpisodeNum"))
                    if _pick_int(vo, "total", "totalEpisodeNum") else ""))
        return items, False

    def cat(self, catid, pg):
        return self._list(catid or "都市", pg)

    def home(self, pg):
        return self._list("都市", pg)

    def search(self, key, pg):
        items, _ = self._list(key, 1)
        return items, False

    def detail(self, sid):
        vid, _, source = sid.partition("#")
        url = (self.BASE + "/xifan/drama/getDuanjuInfo?duanjuId=%s&source=%s"
               % (_q(vid), _q(source)))
        j = self.sess.get_json(url, headers={"Referer": self.BASE + "/"})
        result = j.get("result") or {}
        eps = result.get("episodeList") or []
        chapters = []
        for i, e in enumerate(eps):
            url_ = _pick(e, "playUrl", "play_url", "videoUrl")
            if not url_:
                continue
            no = _pick_int(e, "index", "episode", "sort") or (i + 1)
            chapters.append((url_, "第%d集" % no))
        chapters.sort(key=lambda x: _ep_no(x[1]))
        info = result.get("duanjuInfo") or result
        return _vod_detail(
            self, sid, _pick(info, "title", "name", "duanjuName"),
            _pick(info, "coverImageUrl", "cover_image_url", "cover"),
            ("全%d集" % len(chapters)) if chapters else "",
            _pick(info, "desc", "description", "introduction"),
            chapters=chapters)

    def play(self, sid, ep):
        # ep 本身就是直链 playUrl（302 跳到签名 MP4，播放器跟随跳转）
        if not _s(ep).startswith("http"):
            raise _SrcErr("饭果分集地址无效")
        return _s(ep), {"Referer": self.BASE + "/"}


# ============================================================
# 星果（星星接口）— 纯 JSON API，无签名（注意是 http）
# ============================================================
@_register
class _Xingguo(_Src):
    id = "xingguo"
    name = "星果"
    cats = [("1287", "推荐一"), ("1288", "推荐二"), ("1289", "推荐三"),
            ("1290", "推荐四"), ("1291", "推荐五")]
    BASE = "http://read.api.duodutek.com"
    FIXED = {
        "productId": "2a8c14d1-72e7-498b-af23-381028eb47c0",
        "vestId": "2be070e0-c824-4d0e-a67a-8f688890cadb",
        "channel": "oppo19",
        "osType": "android",
        "version": "20",
        "token": "202509271001001446030204698626",
    }

    def _api(self, path, params):
        q = dict(self.FIXED)
        q.update(params)
        url = self.BASE + path + "?" + urllib.parse.urlencode(q)
        return self.sess.get_json(url)

    def _node(self, n):
        bid = _pick(n, "id", "bookId")
        if not bid:
            return None
        intro = _pick(n, "introduction", "desc", "description")
        sid = "%s@%s" % (bid, intro)
        heat = _pick_int(n, "heat")
        remark = (("%s万播放" % (heat / 10000)) if heat >= 10000
                  else ("%d播放" % heat)) if heat else ""
        total = _pick_int(n, "chapterCount", "total")
        if total and not remark:
            remark = "全%d集" % total
        return _vod_item(
            self.id, sid, _pick(n, "name", "title"),
            _pick(n, "icon", "cover"), remark, intro)

    def cat(self, catid, pg):
        j = self._api("/novel-api/app/pageModel/getResourceById",
                      {"resourceId": catid or "1287",
                       "pageNum": str(pg), "pageSize": "10"})
        data = j.get("data") or {}
        items = []
        for n in data.get("datalist") or []:
            v = self._node(n)
            if v:
                items.append(v)
        return items, len(items) >= 10

    def home(self, pg):
        return self.cat("1287", pg)

    def search(self, key, pg):
        j = self._api("/novel-api/basedata/book/searchBook",
                      {"key": key, "pageNum": "1", "pageSize": "20"})
        data = j.get("data") or {}
        items = []
        for n in data.get("datalist") or []:
            v = self._node(n)
            if v:
                items.append(v)
        return items, False

    def _find_urls(self, node, out):
        if isinstance(node, dict):
            for k in ("shortPlayUrl", "playUrl", "url"):
                u = node.get(k)
                if isinstance(u, str) and u.startswith("http"):
                    out.append(u)
            for k in ("shortPlayList", "chapterShortPlayVoList", "list",
                      "children"):
                v = node.get(k)
                if isinstance(v, list):
                    for x in v:
                        self._find_urls(x, out)
        elif isinstance(node, list):
            for x in node:
                self._find_urls(x, out)

    def detail(self, sid):
        bid = sid.split("@")[0]
        j = self._api("/novel-api/basedata/book/getChapterList",
                      {"bookId": bid})
        data = j.get("data")
        eps = data if isinstance(data, list) else []
        chapters = []
        title, pic, intro = "", "", ""
        for i, e in enumerate(eps):
            if not isinstance(e, dict):
                continue
            if i == 0:
                title = _pick(e, "bookName", "name", "title")
                pic = _pick(e, "icon", "cover")
                intro = _pick(e, "introduction", "desc")
            urls = []
            self._find_urls(e, urls)
            if not urls:
                continue
            no = _pick_int(e, "chapterNum", "sort", "index") or (i + 1)
            et = _pick(e, "chapterName", "name", "title") or ("第%d集" % no)
            chapters.append((urls[0], et))
        if not title:
            title = bid
        return _vod_detail(self, sid, title, pic,
                           ("全%d集" % len(chapters)) if chapters else "",
                           intro, chapters=chapters)

    def play(self, sid, ep):
        if not _s(ep).startswith("http"):
            raise _SrcErr("星果分集地址无效")
        return _s(ep), {}


# ============================================================
# 观果（围观）— 纯 JSON API；详情接口已挂（源码级确认）
# ============================================================
@_register
class _Guanguo(_Src):
    id = "guanguo"
    name = "观果"
    cats = [("", "全部")]
    BASE = "https://api.drama.9ddm.com"

    def _pub_query(self):
        ts = str(int(time.time() * 1000))[-10:]
        return {
            "version_code": "1500", "version_name": "1.5.0",
            "device_name": "Pixel 8 Pro", "device_type": "phone",
            "is_first_day": "true", "is_first_24h": "true",
            "app_launch_way": "icon",
            "default_homepage": "homepage_interaction",
            "device_owning_firm": "Google", "font_scale": "default",
            "os_type": "1", "clientInfo": _md5(ts),
        }

    def _search_api(self, subject, word, pg):
        url = (self.BASE + "/drama/home/search?"
               + urllib.parse.urlencode(self._pub_query()))
        body = {"audience": "全部", "order": "最新", "page": pg,
                "pageSize": 30, "searchWord": word, "subject": subject}
        j = self.sess.post_json(
            url, body,
            headers={"User-Agent": "okhttp/5.1.0",
                     "Referer": self.BASE + "/"})
        items = []
        data = j.get("data")
        rows = data if isinstance(data, list) else []
        for n in rows:
            if not isinstance(n, dict):
                continue
            vid = _pick(n, "oneId", "one_id", "id")
            if not vid:
                continue
            total = _pick_int(n, "episodeCount", "totalEpisodeCount")
            items.append(_vod_item(
                self.id, vid, _pick(n, "title", "name"),
                _pick(n, "horzPoster", "vertPoster", "cover"),
                ("全%d集" % total) if total else "",
                _pick(n, "intro", "description", "desc")))
        return items, len(items) >= 30

    def cat(self, catid, pg):
        return self._search_api(_s(catid), "", pg)

    def search(self, key, pg):
        return self._search_api("", key, 1)

    def detail(self, sid):
        raise _SrcErr("观果详情接口当前返回空数据，该源暂时无法查看分集")

    def play(self, sid, ep):
        raise _SrcErr("观果详情接口当前返回空数据，该源暂时无法播放")


# ============================================================
# 黄果AI — JSON 目录 + HTML 详情/播放，无登录，镜像轮换
# ============================================================
@_register
class _HuangguoAI(_Src):
    id = "hgai"
    name = "黄果AI"
    cats = [("ai-duanju", "AI短剧"), ("ai-manju", "AI漫剧"),
            ("ai-huanlian", "AI换脸"), ("ai-mogai", "AI魔改")]
    MAIN = "https://huangguoai.com"
    MIRRORS = ["https://ttvoij.ediayikma.cc", "https://thu.ediayikma.cc",
               "https://pku.ediayikma.cc", "https://fdu.ediayikma.cc",
               "https://thu.agdkczeyx.cc"]

    def _gen_mirrors(self, seed, n=8):
        out = []
        for i in range(n * 2):
            if len(out) >= n:
                break
            hx = hashlib.sha256(("%s:%d" % (seed, i)).encode()).hexdigest()
            pre = hx[:6].lstrip("0123456789")
            if len(pre) < 4:
                pre = hx[6:12].lstrip("0123456789")
            pre = (pre + "xxxxxx")[:6]
            if len(pre) >= 4:
                out.append("https://%s.ediayikma.cc" % pre)
        return out

    def _bases(self, path=""):
        bases = [self.MAIN] + self.MIRRORS
        bases += self._gen_mirrors(self.MAIN + path)
        seen = []
        for b in bases:
            if b not in seen:
                seen.append(b)
        return seen

    def _headers(self, base):
        return {"User-Agent": IPHONE_UA, "Referer": base + "/",
                "Accept-Language": "zh-CN,zh;q=0.9"}

    def _try_bases(self, path, timeout=12):
        last = None
        for base in self._bases(path):
            try:
                r = self.sess.fetch(base + path,
                                    headers=self._headers(base),
                                    timeout=timeout)
                if r.status == 200 and r.body:
                    return base, r
            except Exception as e:
                last = e
        raise _SrcErr("黄果AI线路暂不可用：%s" % last)

    def _walk_items(self, node, out):
        if isinstance(node, dict):
            vid = _pick(node, "id", "videoId", "video_id", "vid", "slug")
            title = _pick(node, "title", "name", "videoTitle", "video_title",
                          "videoName", "video_name")
            if vid and title:
                out.append(node)
                return
            for v in node.values():
                self._walk_items(v, out)
        elif isinstance(node, list):
            for v in node:
                self._walk_items(v, out)

    def _node(self, base, n):
        vid = _pick(n, "id", "videoId", "video_id", "vid", "slug")
        if not vid:
            m = re.search(r"/detail/([^\s\"'/?#]+)",
                          json.dumps(n, ensure_ascii=False))
            if m:
                vid = m.group(1)
        vid = _s(vid).strip().strip("/?#")
        if not vid or "/" in vid:
            vid = vid.split("/")[-1]
        if not vid:
            return None
        title = _pick(n, "title", "name", "videoTitle", "video_title",
                      "videoName", "video_name")
        if not title:
            return None
        pic = _pick(n, "cover", "coverUrl", "cover_url", "coverImage",
                    "cover_image", "image", "imageUrl", "thumbnail",
                    "poster", "posterUrl")
        total = _pick_int(n, "episode_count", "episodeCount", "total_episodes",
                          "totalEpisodes", "totalEpisode", "total_episode",
                          "episodes", "total")
        remark = _pick(n, "vod_remarks", "remark", "remarks")
        if not remark and total:
            fin = _pick(n, "is_finished")
            remark = ("全%d集" % total) if str(fin) in ("1", "true") else \
                ("更新至%d集" % total)
        score = _pick(n, "score", "rating")
        if score and "分" not in score:
            score += "分"
        return _vod_item(self.id, vid, title, _abs(base, pic), remark,
                         _pick(n, "desc", "description", "intro", "summary"))

    def cat(self, catid, pg):
        path = ("/api/videos/category/%s?sort=hot&page=%d&size=24"
                % (_q(catid or "ai-duanju"), pg))
        base, r = self._try_bases(path)
        try:
            j = json.loads(r.text())
        except Exception:
            raise _SrcErr("黄果AI目录解析失败")
        nodes = []
        self._walk_items(j, nodes)
        items, seen = [], set()
        for n in nodes:
            v = self._node(base, n)
            if v and v["vod_id"] not in seen:
                seen.add(v["vod_id"])
                items.append(v)
        return items, len(nodes) >= 24

    def home(self, pg):
        return self.cat("ai-duanju", pg)

    def _detail_page(self, sid):
        path = "/detail/%s/" % _q(sid.strip().strip("/"))
        return self._try_bases(path)

    def detail(self, sid):
        base, r = self._detail_page(sid)
        html = r.text()
        title = ""
        m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
        if m:
            title = _strip_tags(m.group(1)).split("_")[0].split("-")[0].strip()
        desc = ""
        m = re.search(r'''(?is)<meta[^>]+(?:name|property)=["'](?:description|og:description)["'][^>]+content=["'](.*?)["']''', html)
        if m:
            desc = m.group(1)
        pic = ""
        m = re.search(r'''(?is)<meta[^>]+property=["']og:image["'][^>]+content=["'](.*?)["']''', html)
        if m:
            pic = _abs(base, m.group(1))
        anchors = re.findall(
            r'''(?is)<a\b[^>]*href=["']([^"']*/video/[^"']+)["'][^>]*>(.*?)</a>''',
            html)
        chapters = []
        seen = set()
        for href, inner in anchors:
            href = _abs(base, href.strip())
            if href in seen:
                continue
            seen.add(href)
            tm = re.search(r'''(?is)\b(?:title|aria-label)=["'](.*?)["']''', inner)
            t = _strip_tags(tm.group(1) if tm else inner)
            no = _ep_no(t, len(chapters) + 1)
            chapters.append((href, t or ("第%d集" % no)))
        chapters.sort(key=lambda x: _ep_no(x[1]))
        if not chapters:
            # 单视频页：直接提播放地址作为第 1 集
            media = self._extract_media(base, html, r.url)
            if media:
                chapters = [(media, "正片")]
        if not chapters:
            raise _SrcErr("黄果AI未找到分集")
        return _vod_detail(self, sid, title or sid, pic,
                           ("全%d集" % len(chapters)), desc,
                           chapters=chapters)

    def _extract_media(self, base, html, page_url):
        # 1) videoInitialData
        m = re.search(r'''(?is)<script[^>]+id=["']videoInitialData["'][^>]*>(.*?)</script>''', html)
        if m:
            try:
                import html as _html
                j = json.loads(_html.unescape(m.group(1)))
            except Exception:
                j = None
            if isinstance(j, dict):
                for k in ("videoSrc", "videoUrl", "playUrl"):
                    u = _pick(j, k)
                    if self._ok_media(u):
                        return self._norm_media(base, page_url, u)
                eps = j.get("epPlaySrcs")
                if isinstance(eps, dict) and eps:
                    key = _pick(j, "ep", "episode")
                    if not key:
                        pm = re.search(r"/ep-(\d+)", page_url)
                        if pm:
                            key = pm.group(1)
                    if key in eps and self._ok_media(eps[key]):
                        return self._norm_media(base, page_url, eps[key])
                    def _ek(k):
                        mm = re.search(r"(\d+)", _s(k))
                        return int(mm.group(1)) if mm else 0
                    for k in sorted(eps, key=_ek):
                        if self._ok_media(eps[k]):
                            return self._norm_media(base, page_url, eps[k])
        # 2) data-play-src
        m = re.search(r'''data-play-src=["']([^"']+)["']''', html)
        if m and self._ok_media(m.group(1)):
            return self._norm_media(base, page_url, m.group(1))
        # 3) 通用正则
        for m in re.finditer(
                r'''["']?(?:videoSrc|videoUrl|playUrl|src|url)["']?\s*[:=]\s*["']([^"']+\.(?:m3u8|mp4)[^"']*)["']''',
                html):
            return self._norm_media(base, page_url, m.group(1))
        return ""

    @staticmethod
    def _ok_media(u):
        u = _s(u)
        return bool(u) and (".m3u8" in u or ".mp4" in u)

    @staticmethod
    def _norm_media(base, page_url, u):
        import html as _html
        u = _html.unescape(_s(u)).replace("\\/", "/").strip()
        if u.startswith("//"):
            u = "https:" + u
        elif u.startswith("http://"):
            u = "https://" + u[7:]
        elif not u.startswith("https://"):
            u = _abs(page_url or base, u)
        return u

    def play(self, sid, ep):
        ep = _s(ep)
        if self._ok_media(ep):
            return ep, {"Referer": self.MAIN + "/",
                        "User-Agent": IPHONE_UA}
        # ep 是分集页面地址
        base = self.MAIN
        r = self.sess.fetch(ep, headers=self._headers(base), timeout=15)
        media = self._extract_media(base, r.text(), r.url)
        if not media:
            raise _SrcErr("黄果AI未找到播放地址")
        return media, {"Referer": ep, "User-Agent": IPHONE_UA}

    def search(self, key, pg):
        # 无服务端搜索：拉前两页按标题过滤
        items = []
        for p in (1, 2):
            try:
                rows, _ = self.cat("ai-duanju", p)
            except Exception:
                break
            for v in rows:
                if key in v["vod_name"]:
                    items.append(v)
            if len(items) >= 30:
                break
        return items[:30], False


# ============================================================
# 黄果视频 — HTML 解析，无登录
# ============================================================
@_register
class _HuangguoVideo(_Src):
    id = "hgv"
    name = "黄果视频"
    cats = [("", "全部")]
    BASE = "https://huangguo.video"

    def _headers(self):
        return {"User-Agent": IPHONE_UA, "Referer": self.BASE + "/",
                "Accept-Language": "zh-CN,zh;q=0.9"}

    def _cards(self, html):
        blocks = re.findall(
            r'''(?is)<article\b[^>]*class=["'][^"']*\bvideo-card\b[^"']*["'][^>]*>.*?</article>''',
            html)
        if not blocks:
            blocks = re.findall(r"(?is)<article\b[^>]*video-card.*?</article>",
                                html)
        items = []
        for b in blocks:
            m = re.search(
                r'''(?is)<a\b[^>]*href=["']([^"']*/(?:series|video)/([^"'/?#]+)[^"']*)["'][^>]*>''',
                b)
            if not m:
                continue
            sid = m.group(1).strip().strip("/")
            if sid.startswith("http"):
                sid = urllib.parse.urlparse(sid).path.strip("/")
            title = ""
            tm = re.search(r'''(?is)(?:title|alt|aria-label)=["']([^"']+)["']''', b)
            if tm:
                title = tm.group(1).strip()
            if not title:
                title = _strip_tags(b)[:60]
            pic = ""
            im = re.search(r'''(?is)<img\b[^>]*?(?:data-src|data-original|src)=["']([^"']+)["']''', b)
            if im:
                pic = _abs(self.BASE, im.group(1))
            desc = ""
            dm = re.search(r'''(?is)(?:data-description|description)=["']([^"']+)["']''', b)
            if dm:
                desc = dm.group(1)
            remark = ""
            rm = re.search(r'''(?is)class=["'][^"']*(?:bg-black/55|text-gold-dim)[^"']*["'][^>]*>(.*?)<''', b)
            if rm:
                remark = _strip_tags(rm.group(1))
            items.append(_vod_item(self.id, sid, title, pic, remark, desc))
        return items

    def cat(self, catid, pg):
        url = self.BASE + "/videos?page=%d" % pg
        if catid:
            url += "&category=" + _q(catid)
        html = self.sess.get_text(url, headers=self._headers())
        if _cf_blocked(html):
            raise _SrcErr("%s被 Cloudflare 拦截，换网络或稍后重试" % self.name)
        items = self._cards(html)
        return items, len(items) >= 20

    def detail(self, sid):
        if not sid.startswith(("series/", "video/")):
            sid = "series/" + sid
        url = self.BASE + "/" + sid
        html = self.sess.get_text(url, headers=self._headers())
        if _cf_blocked(html):
            raise _SrcErr("%s被 Cloudflare 拦截，换网络或稍后重试" % self.name)
        title = ""
        m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
        if m:
            title = _strip_tags(m.group(1)).split("_")[0].split("-")[0].strip()
        pic = ""
        m = re.search(r'''(?is)<meta[^>]+property=["']og:image["'][^>]+content=["'](.*?)["']''', html)
        if m:
            pic = _abs(self.BASE, m.group(1))
        chapters = []
        if sid.startswith("series/"):
            blocks = re.findall(
                r'''(?is)<article\b[^>]*class=["'][^"']*\bvideo-card\b[^"']*["'][^>]*>.*?</article>''',
                html)
            for b in blocks:
                m = re.search(r'''(?is)<a\b[^>]*href=["']([^"']*video/[^"']*)["']''', b)
                if not m:
                    continue
                hm = re.search(r'''data-hls=["']([^"']+)["']''', b)
                media = _abs(self.BASE, hm.group(1)) if hm else ""
                if not media:
                    continue
                tm = re.search(r'''(?is)(?:title|alt|aria-label)=["']([^"']+)["']''', b)
                t = tm.group(1).strip() if tm else _strip_tags(b)[:40]
                chapters.append((media, t or ("第%d集" % (len(chapters) + 1))))
            chapters.sort(key=lambda x: _ep_no(x[1]))
        else:
            m = re.search(r'''data-hls=["']([^"']+)["']''', html)
            if m:
                chapters = [(_abs(self.BASE, m.group(1)), "正片")]
        if not chapters:
            raise _SrcErr("黄果视频未找到分集")
        return _vod_detail(self, sid, title or sid, pic,
                           ("全%d集" % len(chapters)), "",
                           chapters=chapters)

    def play(self, sid, ep):
        if _s(ep).startswith("http"):
            return _s(ep), {"Referer": self.BASE + "/"}
        raise _SrcErr("黄果视频分集地址无效")

    def search(self, key, pg):
        items = []
        for p in (1, 2):
            try:
                rows, _ = self.cat("", p)
            except Exception:
                break
            for v in rows:
                if key in v["vod_name"]:
                    items.append(v)
            if len(items) >= 30:
                break
        return items[:30], False


# ============================================================
# 河果（河马剧场）— Next.js __NEXT_DATA__ 解析
# ============================================================
@_register
class _Heguo(_Src):
    id = "heguo"
    name = "河果"
    cats = [("462", "甜宠"), ("1102", "古装仙侠"), ("1145", "现代言情"),
            ("1170", "青春"), ("585", "豪门恩怨"), ("417-464", "逆袭"),
            ("439-465", "重生"), ("1159", "系统"), ("1147", "总裁"),
            ("943", "职场商战")]
    BASE = "https://www.kuaikaw.cn"

    def _next_data(self, html):
        m = re.search(
            r'''(?is)<script[^>]+id=["']__NEXT_DATA__[^>]*>(.*?)</script>''',
            html)
        if not m:
            return {}
        try:
            j = json.loads(m.group(1))
            return j.get("props", {}).get("pageProps", {}) or {}
        except Exception:
            return {}

    def _node(self, n):
        bid = _pick(n, "bookId", "book_id", "id")
        if not bid:
            return None
        total = _pick_int(n, "totalChapterNum")
        return _vod_item(
            self.id, bid, _pick(n, "bookName", "title", "name"),
            _pick(n, "coverWap", "cover", "coverUrl"),
            ("全%d集" % total) if total else "",
            _pick(n, "introduction", "intro", "description"))

    def _parse_list_page(self, props):
        items, seen = [], set()
        buckets = []
        for k in ("bookList", "bannerList", "recommendList"):
            v = props.get(k)
            if isinstance(v, list):
                buckets += v
        for col in props.get("seoColumnVos") or []:
            if isinstance(col, dict):
                buckets += col.get("bookInfos") or []
        for n in buckets:
            if not isinstance(n, dict):
                continue
            v = self._node(n)
            if v and v["vod_id"] not in seen:
                seen.add(v["vod_id"])
                items.append(v)
        return items

    def cat(self, catid, pg):
        if pg == 1 and not catid:
            url = self.BASE + "/"
        else:
            url = "%s/browse/%s/%d" % (self.BASE, _q(catid or "462"), pg)
        html = self.sess.get_text(url, headers={"Referer": self.BASE + "/"})
        props = self._next_data(html)
        items = self._parse_list_page(props)
        pages = _pick_int(props, "pages", "page")
        more = (pg < pages) if pages else len(items) >= 20
        return items, more

    def home(self, pg):
        return self.cat("", pg)

    def detail(self, sid):
        url = "%s/drama/%s" % (self.BASE, _q(sid))
        html = self.sess.get_text(url, headers={"Referer": self.BASE + "/"})
        props = self._next_data(html)
        info = props.get("bookInfoVo") or {}
        v = self._node(info) or _vod_item(self.id, sid, sid)
        chapters = []
        for i, c in enumerate(props.get("chapterList") or []):
            if not isinstance(c, dict):
                continue
            cid = _pick(c, "chapterId", "chapter_id", "id")
            if not cid:
                continue
            no = _pick_int(c, "chapterNum", "sort", "index") or (i + 1)
            t = _pick(c, "chapterName", "title") or ("第%d集" % no)
            chapters.append((cid, t))
        chapters.sort(key=lambda x: _ep_no(x[1]))
        v.update({
            "vod_content": _pick(info, "introduction", "intro", "description"),
            "vod_remarks": ("全%d集" % len(chapters)) if chapters else "",
            "vod_play_from": self.name,
            "vod_play_url": "#".join(
                "%s$%s" % (t, _pid(self.id, sid, k)) for k, t in chapters),
        })
        return v

    def play(self, sid, ep):
        url = "%s/episode/%s/%s" % (self.BASE, _q(sid), _q(ep))
        html = self.sess.get_text(url, headers={"Referer": self.BASE + "/"})
        props = self._next_data(html)
        ci = props.get("chapterInfo") or {}
        vv = ci.get("chapterVideoVo") or {}
        media = _pick(vv, "mp4", "mp4720p", "vodMp4Url")
        if not media:
            m = re.search(r"""https?://[^"'\\\s<>]+\.(?:mp4|m3u8)[^"'\\\s<>]*""",
                          html)
            if m:
                media = m.group(0)
        if not media:
            raise _SrcErr("河果未找到播放地址")
        return _abs(self.BASE, media), {"Referer": url}

    def search(self, key, pg):
        url = self.BASE + "/seo/video/6007"
        j = self.sess.post_json(
            url, {"sourceType": 1, "keyword": key, "index": 1},
            headers={"Referer": self.BASE + "/",
                     "pname": "www.kuaikaw.cn"})
        data = j.get("data") or {}
        items = []
        for n in data.get("bookList") or []:
            v = self._node(n)
            if v:
                items.append(v)
        return items, False


# ============================================================
# MacCMS 网页类通用（花果/网果/发果/伍果；皮果被 Cloudflare 拦截）
# ============================================================

def _cf_blocked(html):
    """Cloudflare 'Just a moment' 拦截页检测"""
    if not html:
        return False
    low = html[:3000].lower()
    return ("just a moment" in low and "cloudflare" in low) or \
        "cf-challenge" in low or "cf_chl_" in low


class _MacCMS(_Src):
    BASE = ""
    UA = PC_UA

    def _headers(self, referer=None):
        return {"User-Agent": self.UA, "Referer": referer or self.BASE + "/"}

    # -- 各站覆盖 --
    def cat_url(self, catid, pg):
        raise NotImplementedError

    def detail_urls(self, sid):
        raise NotImplementedError

    def search_url(self, key, pg):
        raise NotImplementedError

    # -- 通用卡片解析（排除 /vod/type/、/vod/search/ 分类链接） --
    _DETAIL_HREF = re.compile(
        r'''(?is)<a\b[^>]*href=["']([^"']*(?:/detail/|/zywview/|/zywdetail/|/voddetail/|/xzyxvd/|/dramaDetail/|/movie/|/p/66/d/|/vod/(?!type/|search/|play/))[^"']*)["'][^>]*>(.*?)</a>''')

    def _cards(self, html, page_url):
        items, seen = [], set()
        for m in self._DETAIL_HREF.finditer(html):
            href, inner = m.group(1).strip(), m.group(2)
            if re.search(r"(?i)(app|下载|down)", _strip_tags(inner)[:20]):
                continue
            url = _abs(page_url, href)
            sid = self._sid_from_url(url)
            if not sid or sid in seen:
                continue
            # 封面：先看 <a> 标签自身（如 data-original 在锚标签上），再往前找最近的 img
            pic = ""
            start = max(0, m.start() - 3000)
            seg = html[start:m.start()]
            am0 = re.search(
                r'''(?is)\b(?:data-original|data-src|src)=["']([^"']+)["']''',
                m.group(0))
            if am0:
                pic = _abs(page_url, am0.group(1))
            if not pic:
                imgs = re.findall(
                    r'''(?is)<img\b[^>]*?(?:data-original|data-src|src)=["']([^"']+)["']''',
                    seg)
                if imgs:
                    pic = _abs(page_url, imgs[-1])
            title = ""
            tm = re.search(r'''(?is)\btitle=["']([^"']+)["']''', m.group(0))
            if tm:
                title = tm.group(1).strip()
            if not title:
                am = re.search(r'''(?is)\balt=["']([^"']+)["']''', seg[-800:])
                if am:
                    title = am.group(1).strip()
            if not title:
                title = _strip_tags(inner).strip()[:60]
            if not title:
                continue
            remark = ""
            rm = re.search(
                r'''(?is)(?:pic-text|module-item-note|imagelastChapter)[^>]*>([^<]{1,40})<''',
                seg[-1200:])
            if rm:
                remark = _strip_tags(rm.group(1))
            seen.add(sid)
            items.append(_vod_item(self.id, sid, title, pic, remark))
        return items

    def _sid_from_url(self, url):
        try:
            path = urllib.parse.urlparse(url).path
        except Exception:
            return ""
        m = re.search(r"/(\d+)\.html?$", path)
        if m:
            return m.group(1)
        m = re.search(r"/(\d+)/?$", path)
        if m:
            return m.group(1)
        m = re.search(r"/movie/([^/?#]+)", path)
        if m:
            return m.group(1)
        m = re.search(r"[?&](?:id|vid)=(\d+)", url)
        if m:
            return m.group(1)
        return ""

    # -- 通用分集解析 --
    _EP_HREF = re.compile(
        r'''(?is)<a\b[^>]*href=["']([^"']*(?:/play/|/vodplay/|/zyxplay/|/zywplay/|/xzyxplay/|/drama-play|episode_id=)[^"']*)["'][^>]*>(.*?)</a>''')

    def _episodes(self, html, page_url):
        eps, seen = [], set()
        for m in self._EP_HREF.finditer(html):
            href = _abs(page_url, m.group(1).strip())
            t = _strip_tags(m.group(2)).strip()[:40]
            if re.search(r"(?i)(app|下载|down)", t):
                continue
            if href in seen:
                continue
            seen.add(href)
            eps.append((href, t or ("第%d集" % (len(eps) + 1))))
        eps.sort(key=lambda x: _ep_no(x[1]))
        return eps

    # -- 通用播放提取 --
    def _extract_play(self, html, page_url):
        m = re.search(r"""player_aaaa\s*=\s*(\{.*?\})\s*</script>""",
                      html, re.S)
        if m:
            try:
                j = json.loads(m.group(1))
                u = _pick(j, "url")
                if u:
                    return self._norm_play(u, page_url)
            except Exception:
                pass
        m = re.search(r'''\$\.url\s*=\s*"([^"]+)"''', html)
        if m:
            return self._norm_play(m.group(1), page_url)
        m = re.search(r'''"url"\s*:\s*"([^"]+\.(?:m3u8|mp4)[^"]*)"''', html)
        if m:
            return self._norm_play(m.group(1), page_url)
        m = re.search(r"""https?://[^"'\\\s<>]+\.(?:m3u8|mp4)[^"'\\\s<>]*""",
                      html)
        if m:
            return self._norm_play(m.group(0), page_url)
        return ""

    def _norm_play(self, u, page_url):
        import html as _html
        u = _html.unescape(_s(u)).replace("\\/", "/").strip()
        # \uXXXX 转义
        try:
            u = u.encode("utf-8").decode("unicode_escape")
        except Exception:
            pass
        # 去掉 JS 拼接时带上的尾部标点（如 "...,https://x.m3u8,"）
        u = u.rstrip(" \t\r\n,;\"'")
        if not u.startswith("http"):
            u = _abs(page_url, u)
        # /p./ 或 /c1./ 伪装：取倒数第二段解码拼 index.m3u8
        if re.search(r"/[pc]1?\./", u):
            parts = [p for p in urllib.parse.urlparse(u).path.split("/")
                     if p]
            if len(parts) >= 2:
                try:
                    seg = base64.b64decode(parts[-2] + "==").decode("utf-8",
                                                                   "ignore")
                except Exception:
                    seg = ""
                if seg:
                    u = u.rsplit("/", 1)[0] + "/" + seg.strip("/") \
                        + "/index.m3u8"
        return u

    # -- 标准流程 --
    def cat(self, catid, pg):
        url = self.cat_url(_s(catid), pg)
        html = self.sess.get_text(url, headers=self._headers())
        if _cf_blocked(html):
            raise _SrcErr("%s被 Cloudflare 拦截，换网络或稍后重试" % self.name)
        items = self._cards(html, url)
        return items, len(items) >= 10

    def home(self, pg):
        return self.cat("", pg)

    def detail(self, sid):
        last = None
        for url in self.detail_urls(sid):
            try:
                html = self.sess.get_text(url,
                                          headers=self._headers())
            except Exception as e:
                last = e
                continue
            title = ""
            m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
            if m:
                title = _strip_tags(m.group(1)).split("_")[0].split("-")[0].strip()
            pic = ""
            m = re.search(
                r'''(?is)<img\b[^>]*?(?:data-original|data-src|src)=["']([^"']+)["'][^>]*class=["'][^"']*(?:poster|cover|vod-pic)''',
                html)
            if not m:
                m = re.search(
                    r'''(?is)<img\b[^>]*?(?:data-original|data-src|src)=["']([^"']+)["']''',
                    html)
            if m:
                pic = _abs(url, m.group(1))
            desc = ""
            m = re.search(
                r'''(?is)(?:vod-content|content|desc|detail-content)[^>]*>(.*?)</(?:div|p)>''',
                html)
            if m:
                desc = _strip_tags(m.group(1))[:2000]
            eps = self._episodes(html, url)
            if not title and not eps:
                last = _SrcErr("页面无内容")
                continue
            # 详情页分集不全时，跟进第一集播放页补全（如伍果详情页只有"立即播放"）
            if len(eps) <= 1:
                for href, _t in eps:
                    if ("/play/" in href or "/vodplay/" in href
                            or "zyxplay" in href or "zywplay" in href
                            or "xzyxplay" in href):
                        try:
                            ph = self.sess.get_text(
                                href, headers=self._headers(url), timeout=12)
                            peps = self._episodes(ph, href)
                            if len(peps) > len(eps):
                                eps = peps
                        except Exception:
                            pass
                        break
            chapters = [(href, t) for href, t in eps]
            return _vod_detail(self, sid, title or sid, pic,
                               ("全%d集" % len(chapters)) if chapters else "",
                               desc, chapters=chapters)
        raise _SrcErr("详情页均不可用：%s" % last)

    def play(self, sid, ep):
        html = self.sess.get_text(_s(ep),
                                  headers=self._headers())
        media = self._extract_play(html, _s(ep))
        if not media or not media.startswith("http"):
            raise _SrcErr("%s未找到播放地址" % self.name)
        return media, {"Referer": _s(ep), "User-Agent": self.UA}

    def search(self, key, pg):
        url = self.search_url(key, pg)
        html = self.sess.get_text(url, headers=self._headers())
        return self._cards(html, url), False


@_register
class _Huaguo(_MacCMS):
    id = "huaguo"
    name = "花果"
    cats = [("27", "短剧")]
    BASE = "https://www.zywest263.com"

    def cat_url(self, catid, pg):
        if pg == 1 and not catid:
            return self.BASE + "/"
        return ("%s/search.html?page=%d&searchtype=5&tid=%s&year="
                % (self.BASE, pg, _q(catid or "27")))

    def detail_urls(self, sid):
        return ["%s/zywview/%s.html" % (self.BASE, sid),
                "%s/zywdetail/%s.html" % (self.BASE, sid),
                "%s/detail/%s.html" % (self.BASE, sid)]

    def search_url(self, key, pg):
        return "%s/search.html?searchword=%s" % (self.BASE, _q(key))


@_register
class _Wangguo(_MacCMS):
    id = "wangguo"
    name = "网果"
    cats = [("", "全部")]
    BASE = "https://www.duanju2.com"

    def cat_url(self, catid, pg):
        if not catid:
            return self.BASE + "/show/duanju-----------.html"
        c = _s(catid)
        if c.endswith("---.html"):
            c = c[:-len("---.html")]
        return "%s/%s%d---.html" % (self.BASE, c, pg)

    def detail_urls(self, sid):
        return ["%s/vod/%s.html" % (self.BASE, sid),
                "%s/index.php/vod/detail/id/%s.html" % (self.BASE, sid),
                "%s/detail/%s.html" % (self.BASE, sid)]

    def search_url(self, key, pg):
        return "%s/search/%s----------1---.html" % (self.BASE, _q(key))


@_register
class _Faguo(_MacCMS):
    id = "faguo"
    name = "发果"
    cats = [("", "全部")]
    BASE = "https://www.xzyx168.com"

    def cat_url(self, catid, pg):
        if not catid:
            return "%s/xzyxvt/%szmn.html" % (self.BASE, pg)
        c = _s(catid)
        if "zmn" not in c:
            raise _SrcErr("发果分类无效")
        c = c.replace("zmn", "")
        return "%s/%s%dzmn.html" % (self.BASE, c, pg)

    def detail_urls(self, sid):
        return ["%s/xzyxvd/%s.html" % (self.BASE, sid),
                "%s/detail/%s.html" % (self.BASE, sid),
                "%s/voddetail/%s.html" % (self.BASE, sid)]

    def search_url(self, key, pg):
        return "%s/xzyxvc/%s-wdyswzqun1num.html" % (self.BASE, _q(key))


@_register
class _Wuguo(_MacCMS):
    id = "wuguo"
    name = "伍果"
    cats = [("", "全部")]
    BASE = "https://www.duanju55.com"

    def cat_url(self, catid, pg):
        if not catid:
            return self.BASE + "/"
        c = _s(catid)
        if c.endswith(".html"):
            c = c[:-5]
        return "%s%s/page/%d.html" % (self.BASE, c, pg)

    def detail_urls(self, sid):
        return ["%s/index.php/vod/detail/id/%s.html" % (self.BASE, sid),
                "%s/dramaDetail/%s.html" % (self.BASE, sid),
                "%s/detail/%s.html" % (self.BASE, sid)]

    def search_url(self, key, pg):
        return ("%s/index.php/vod/search/page/1/wd/%s.html"
                % (self.BASE, _q(key)))


@_register
class _Piguo(_MacCMS):
    id = "piguo"
    name = "皮果"
    cats = [("67", "短剧")]
    BASE = "https://ptt.red"
    _BLOCKED = "皮果 ptt.red 被 Cloudflare 人机校验拦截，纯 HTTP 无法通过，需浏览器环境"

    def cat_url(self, catid, pg):
        raise _SrcErr(self._BLOCKED)

    def detail_urls(self, sid):
        raise _SrcErr(self._BLOCKED)

    def search_url(self, key, pg):
        raise _SrcErr(self._BLOCKED)

    def cat(self, catid, pg):
        raise _SrcErr(self._BLOCKED)

    def detail(self, sid):
        raise _SrcErr(self._BLOCKED)

    def play(self, sid, ep):
        raise _SrcErr(self._BLOCKED)

    def search(self, key, pg):
        raise _SrcErr(self._BLOCKED)


# ============================================================
# 牛果 — 响应 AES-ECB 加密（密钥=请求 URI 前 16 字节）；
# 取流依赖的解析域名已死，播放明确报错。
# ============================================================
@_register
class _Niuguo(_Src):
    id = "niuguo"
    name = "牛果"
    cats = [("短剧", "短剧"), ("电影", "电影"), ("电视剧", "电视剧"),
            ("动漫", "动漫"), ("综艺", "综艺")]
    BASE = "https://ccc.chaojichaojichanga.com:35620"

    def _api(self, path, query):
        qs = urllib.parse.urlencode(query)
        uri = path + ("?" + qs if qs else "")
        key = uri.encode("utf-8")[:16].ljust(16, b"\x00")
        url = self.BASE + uri
        body = self.sess.fetch(url, headers={"Referer": self.BASE + "/"},
                               timeout=12).body
        try:
            raw = base64.b64decode(body)
        except Exception:
            raise _SrcErr("牛果响应不是合法 Base64")
        try:
            plain = _aes_ecb_decrypt(raw, key)
        except Exception as e:
            raise _SrcErr("牛果响应解密失败：%s" % e)
        try:
            return json.loads(plain.decode("utf-8", "ignore"))
        except Exception:
            raise _SrcErr("牛果响应不是合法 JSON")

    def _node(self, n):
        vid = _pick(n, "vod_id", "vodId", "vod_id", "id")
        if not vid:
            return None
        total = _pick_int(n, "vod_total", "total", "episodes")
        remark = _pick(n, "vod_remarks", "vodRemarks")
        if not remark and total:
            remark = "全%d集" % total
        return _vod_item(
            self.id, _s(vid), _pick(n, "vod_name", "vodName", "title"),
            _pick(n, "vod_pic", "vodPic", "cover"), remark,
            _pick(n, "vod_blurb", "vod_content", "desc"))

    def _rows(self, j):
        if isinstance(j, list):
            return j
        if isinstance(j, dict):
            rows = j.get("list")
            if isinstance(rows, list):
                return rows
            data = j.get("data")
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                rows = data.get("list")
                if isinstance(rows, list):
                    return rows
        return []

    def cat(self, catid, pg):
        j = self._api("/list", {"class": catid or "短剧", "order": "最新",
                                "type_id": "5", "area": "", "year": "",
                                "state": "", "wd": "", "page": str(pg)})
        rows = self._rows(j)
        items = []
        for n in rows:
            v = self._node(n)
            if v:
                items.append(v)
        return items, len(items) >= 20

    def search(self, key, pg):
        j = self._api("/list", {"class": "", "order": "最新", "type_id": "5",
                                "area": "", "year": "", "state": "",
                                "wd": key, "page": "1"})
        rows = self._rows(j)
        items = []
        for n in rows:
            v = self._node(n)
            if v:
                items.append(v)
        return items, False

    def detail(self, sid):
        j = self._api("/detail", {"vod_id": sid})
        node = j
        if isinstance(j.get("data"), dict):
            node = j["data"]
            if isinstance(node.get("list"), list) and node["list"]:
                node = node["list"][0]
        if not isinstance(node, dict):
            raise _SrcErr("牛果详情格式无效")
        v = self._node(node) or _vod_item(self.id, sid, sid)
        chapters = []
        for s in node.get("sources") or []:
            for e in (s.get("episodes") or []):
                nm = _pick(e, "name", "title")
                u = _pick(e, "url", "playUrl")
                if u:
                    chapters.append((u, nm or ("第%d集" % (len(chapters) + 1))))
        vpu = _pick(node, "vod_play_url")
        if not chapters and vpu:
            for seg in vpu.split("#"):
                if "$" in seg:
                    t, u = seg.split("$", 1)
                else:
                    t, u = "", seg
                if u.strip():
                    chapters.append((u.strip(),
                                     t.strip() or ("第%d集" % (len(chapters) + 1))))
        chapters.sort(key=lambda x: _ep_no(x[1]))
        v.update({
            "vod_remarks": ("共%d集·解析已失效" % len(chapters)) if chapters else "",
            "vod_play_from": self.name,
            "vod_play_url": "#".join(
                "%s$%s" % (t, _pid(self.id, sid, k)) for k, t in chapters),
        })
        return v

    def play(self, sid, ep):
        raise _SrcErr("牛果取流用的两个解析域名均已失效，分集无法取流")


# ============================================================
# 芽果（星芽接口）— 先 POST 登录拿 token
# ============================================================
@_register
class _Yaguo(_Src):
    id = "yaguo"
    name = "芽果"
    cats = [("1", "剧场"), ("9", "榜单")]
    BASE = "https://app.whjzjx.cn"
    LOGIN = "https://u.shytkjgs.com/user/v1/account/login"
    DEVICE = "24250683a3bdb3f118dff25ba4b1cba1a"

    def __init__(self):
        super().__init__()
        self._token = ""
        self._token_at = 0
        self._dyn_cats = None

    def _auth_headers(self):
        return {"authorization": self._token, "platform": "1",
                "version_name": "3.8.3.1"}

    def _token_get(self):
        if self._token and time.time() - self._token_at < 6 * 3600:
            return self._token
        j = self.sess.post_json(
            self.LOGIN, {"device": self.DEVICE},
            headers={"platform": "1"}, timeout=15)
        data = j.get("data") if isinstance(j.get("data"), dict) else {}
        token = _pick(data, "token") or _pick(j, "token")
        if not token:
            raise _SrcErr("芽果登录未返回 token")
        self._token, self._token_at = token, time.time()
        return token

    def categories(self):
        if self._dyn_cats is not None:
            return self._dyn_cats
        try:
            self._token_get()
            j = self.sess.get_json(self.BASE + "/cloud/v2/theater/classes",
                                   headers=self._auth_headers(), timeout=8)
            cats = []
            for g in j.get("data") or []:
                for c in (g.get("alg_class") or []):
                    cid = _pick(c, "id")
                    cn = _pick(c, "class_name", "name")
                    if cid and cn:
                        cats.append((cid, cn))
            if cats:
                self._dyn_cats = cats[:24]
                return self._dyn_cats
        except Exception:
            pass
        return self.cats

    def _node(self, n):
        node = n.get("theater") if isinstance(n.get("theater"), dict) else n
        vid = _pick(node, "id", "theater_id", "theater_parent_id")
        if not vid:
            return None
        total = _pick_int(node, "total", "total_num", "current_num")
        return _vod_item(
            self.id, vid, _pick(node, "title", "name"),
            _pick(node, "cover_url", "son_cover_url", "cover"),
            ("全%d集" % total) if total else "",
            _pick(node, "descrip", "introduction", "desc"))

    def cat(self, catid, pg):
        self._token_get()
        catid = catid or "1"
        if catid == "9":
            j = self.sess.get_json(
                self.BASE + "/cloud/v1/first_level_ranking/detail?id=1",
                headers=self._auth_headers())
            rows = (j.get("data") or {}).get("list") or []
            items = [v for v in (self._node(n) for n in rows) if v]
            return items, False
        url = (self.BASE + "/cloud/v2/theater/home_page?" +
               urllib.parse.urlencode(
                   {"theater_class_id": catid, "type": "1", "class2_ids": "0",
                    "page_num": str(pg), "page_size": "24"}))
        j = self.sess.get_json(url, headers=self._auth_headers())
        data = j.get("data") or {}
        rows = data.get("list") or []
        items = [v for v in (self._node(n) for n in rows) if v]
        total = _pick_int(data, "total")
        is_end = data.get("is_end")
        more = (not is_end) if is_end is not None else (
            len(rows) >= 24 if not total else pg * 24 < total)
        return items, more

    def home(self, pg):
        return self.cat("1", pg)

    def detail(self, sid):
        self._token_get()
        url = (self.BASE + "/v2/theater_parent/detail?" +
               urllib.parse.urlencode({"theater_parent_id": sid}))
        j = self.sess.get_json(url, headers=self._auth_headers())
        data = j.get("data") or {}
        eps = data.get("theaters") or []
        chapters = []
        title = _pick(data, "title", "theater_title", "name")
        pic = _pick(data, "cover_url", "cover")
        intro = _pick(data, "descrip", "introduction", "desc", "intro")
        for i, e in enumerate(eps):
            u = _pick(e, "son_video_url", "video_url")
            if not u:
                continue
            if not title:
                title = _pick(e, "theater_title", "title", "name")
            if not pic:
                pic = _pick(e, "cover_url", "son_cover_url", "cover")
            if not intro:
                intro = _pick(e, "descrip", "introduction", "desc")
            no = _pick_int(e, "num", "sort") or (i + 1)
            t = _pick(e, "son_title", "title") or ("第%d集" % no)
            chapters.append((u, t))
        chapters.sort(key=lambda x: _ep_no(x[1]))
        return _vod_detail(self, sid, title or sid, pic,
                           ("全%d集" % len(chapters)) if chapters else "",
                           intro, chapters=chapters)

    def play(self, sid, ep):
        if not _s(ep).startswith("http"):
            raise _SrcErr("芽果分集地址无效")
        return _s(ep), {"Referer": self.BASE + "/"}

    def search(self, key, pg):
        self._token_get()
        j = self.sess.post_json(self.BASE + "/v3/search", {"text": key},
                                headers=self._auth_headers())
        data = j.get("data") or {}
        rows = data.get("list") or []
        if not rows:
            th = data.get("theater") or {}
            rows = th.get("search_data") or []
        items = [v for v in (self._node(n) for n in rows) if v]
        return items, False


# ============================================================
# 剧果 — 访客鉴权 + CloudFront Cookie 播放
# ============================================================
@_register
class _Huangju(_Src):
    id = "huangju"
    name = "剧果"
    cats = [("", "全部")]
    BASE = "https://api.huangju.net"
    WEB = "https://huangju.net"

    def __init__(self):
        super().__init__()
        self._token = ""
        self._token_at = 0
        self._dyn_cats = None

    def _auth(self):
        if self._token and time.time() - self._token_at < 3600:
            return self._token
        j = self.sess.post_json(
            self.BASE + "/auth/guest",
            {"deviceId": str(uuid.uuid4())}, timeout=15)
        token = _pick(j, "token") or _pick(j.get("data") or {}, "token")
        if not token:
            raise _SrcErr("剧果访客鉴权失败")
        self._token, self._token_at = token, time.time()
        return token

    def _h(self):
        return {"Authorization": "Bearer " + self._auth(),
                "Referer": self.WEB + "/"}

    def _get(self, path, params=None):
        url = self.BASE + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        try:
            return self.sess.get_json(url, headers=self._h())
        except Exception as e:
            if "401" in str(e) or "403" in str(e):
                self._token = ""
                return self.sess.get_json(url, headers=self._h())
            raise

    def categories(self):
        if self._dyn_cats is not None:
            return self._dyn_cats
        try:
            j = self._get("/categories")
            rows = j if isinstance(j, list) else (
                j.get("data") if isinstance(j.get("data"), list)
                else j.get("categories") or [])
            cats = []
            for c in rows if isinstance(rows, list) else []:
                cid = _pick(c, "slug", "id")
                cn = _pick(c, "name", "title")
                if cid and cn:
                    cats.append((cid, cn))
            if cats:
                self._dyn_cats = [("", "全部")] + cats[:20]
                return self._dyn_cats
        except Exception:
            pass
        return self.cats

    def _node(self, n):
        vid = _pick(n, "slug", "slug_id", "drama_id", "id")
        if not vid:
            return None
        total = _pick_int(n, "episode_count", "total_episodes", "total",
                          "episodeCount")
        return _vod_item(
            self.id, vid, _pick(n, "title", "name"),
            _pick(n, "cover", "cover_url", "coverUrl", "poster"),
            ("全%d集" % total) if total else "",
            _pick(n, "desc", "description", "intro"))

    def _dramas(self, params, pg):
        params = dict(params or {})
        params["page"] = str(pg)
        j = self._get("/dramas", params)
        # 真实结构：{"total","page","pageSize","items":[]}；兼容 {"data":{...}}
        data = j.get("data") if isinstance(j.get("data"), dict) else j
        rows = []
        if isinstance(data, dict):
            rows = data.get("items") or data.get("dramas") or \
                data.get("list") or []
        elif isinstance(data, list):
            rows = data
        items = [v for v in (self._node(n) for n in rows
                             if isinstance(n, dict)) if v]
        total = _pick_int(data, "total") if isinstance(data, dict) else 0
        psize = _pick_int(data, "pageSize", "page_size") or 20
        more = (pg * psize < total) if total else len(items) >= psize
        return items, more

    def cat(self, catid, pg):
        if catid:
            return self._dramas({"category": catid}, pg)
        return self._dramas({"sort": "new"}, pg)

    def home(self, pg):
        return self._dramas({"sort": "new"}, pg)

    def search(self, key, pg):
        return self._dramas({"q": key}, 1)

    def detail(self, sid):
        j = self._get("/dramas/" + _q(sid))
        data = j.get("data") or j
        v = self._node(data) or _vod_item(self.id, sid, sid)
        v["vod_content"] = _pick(data, "desc", "description", "intro")
        chapters = []
        for e in data.get("episodes") or []:
            if not isinstance(e, dict):
                continue
            if e.get("playable") is False:
                continue
            eid = _pick(e, "id")
            if not eid:
                continue
            no = _pick_int(e, "epNo", "ep_no", "sort", "index") \
                or (len(chapters) + 1)
            t = _pick(e, "title", "name") or ("第%d集" % no)
            chapters.append((eid, t))
        chapters.sort(key=lambda x: _ep_no(x[1]))
        v.update({
            "vod_remarks": ("全%d集" % len(chapters)) if chapters else "",
            "vod_play_from": self.name,
            "vod_play_url": "#".join(
                "%s$%s" % (t, _pid(self.id, sid, k)) for k, t in chapters),
        })
        return v

    def play(self, sid, ep):
        r = self.sess.fetch(self.BASE + "/play/" + _q(ep),
                            headers=self._h(), timeout=15)
        try:
            j = json.loads(r.text())
        except Exception:
            raise _SrcErr("剧果播放接口返回无效")
        # 真实结构是裸 JSON：{"episodeId","dramaId","epNo","url",...}；兼容 data 包裹
        data = j.get("data") if isinstance(j.get("data"), dict) else j
        media = _pick(data, "url", "play_url", "video_url", "src")
        if not media:
            # 也可能是纯文本 URL
            t = r.text().strip()
            if t.startswith("http"):
                media = t.split()[0]
        if not media:
            raise _SrcErr("剧果未返回播放地址")
        ck = self.sess.cookies
        trio = "; ".join("%s=%s" % (k, ck[k]) for k in
                         ("CloudFront-Policy", "CloudFront-Signature",
                          "CloudFront-Key-Pair-Id") if k in ck)
        header = {"Referer": self.WEB + "/"}
        if trio:
            header["Cookie"] = trio
        return media, header


# ============================================================
# 猫果（七猫签名）— qm-params + MD5，参数顺序必须与原版一致
# ============================================================
@_register
class _Maoguo(_Src):
    id = "maoguo"
    name = "猫果"
    cats = [("0", "推荐")]
    STORE = "https://api-store.qmplaylet.com"
    READ = "https://api-read.qmplaylet.com"
    KEY = "d3dGiJc651gSQ8w1"
    TRACK_ID = "ec1280db127955061754851657967"
    # 与 Go 源码 duanjuMaoguoCharMap 逐字一致（'=' 不在表中，保持原样）
    CHARMAP = {
        '+': 'P', '/': 'X', '0': 'M', '1': 'U', '2': 'l', '3': 'E',
        '4': 'r', '5': 'Y', '6': 'W', '7': 'b', '8': 'd', '9': 'J',
        'A': '9', 'B': 's', 'C': 'a', 'D': 'I', 'E': '0', 'F': 'o',
        'G': 'y', 'H': '_', 'I': 'H', 'J': 'G', 'K': 'i', 'L': 't',
        'M': 'g', 'N': 'N', 'O': 'A', 'P': '8', 'Q': 'F', 'R': 'k',
        'S': '3', 'T': 'h', 'U': 'f', 'V': 'R', 'W': 'q', 'X': 'C',
        'Y': '4', 'Z': 'p', 'a': 'm', 'b': 'B', 'c': 'O', 'd': 'u',
        'e': 'c', 'f': '6', 'g': 'K', 'h': 'x', 'i': '5', 'j': 'T',
        'k': '-', 'l': '2', 'm': 'z', 'n': 'S', 'o': 'Z', 'p': '1',
        'q': 'V', 'r': 'v', 's': 'j', 't': 'Q', 'u': '7', 'v': 'D',
        'w': 'w', 'x': 'n', 'y': 'L', 'z': 'e',
    }

    def __init__(self):
        super().__init__()
        self._dyn_cats = None

    def _headers(self):
        payload = {
            "static_score": "0.8",
            "uuid": "00000000-7fc7-08dc-0000-000000000000",
            "device-id": "20250220125449b9b8cac84c2dd3d035c9052a2572f7dd0122edde3cc42a70",
            "mac": "",
            "sourceuid": "aa7de295aad621a6",
            "refresh-type": "0",
            "model": "22021211RC",
            "wlb-imei": "",
            "client-id": "aa7de295aad621a6",
            "brand": "Redmi",
            "oaid": "",
            "oaid-no-cache": "",
            "sys-ver": "12",
            "trusted-id": "",
            "phone-level": "H",
            "imei": "",
            "wlb-uid": "aa7de295aad621a6",
            "session-id": str(int(time.time() * 1000)),
        }
        b64 = base64.b64encode(
            json.dumps(payload, separators=(",", ":")).encode()).decode()
        qm = "".join(self.CHARMAP.get(c, c) for c in b64)
        sign = _md5("AUTHORIZATION=" + "app-version=10001" +
                    "application-id=com.duoduo.read" + "channel=unknown" +
                    "is-white=" + "net-env=5" + "platform=android" +
                    "qm-params=" + qm + "reg=" + self.KEY)
        return {
            "net-env": "5", "reg": "", "channel": "unknown", "is-white": "",
            "platform": "android", "application-id": "com.duoduo.read",
            "authorization": "", "app-version": "10001",
            "User-Agent": "webviewversion/0",
            "qm-params": qm, "sign": sign,
            "Accept": "application/json",
            "X-Requested-With": "com.duoduo.read",
        }

    def _get(self, base, path, sign_str):
        url = base + path + ("&" if "?" in path else "?") + "sign=" + sign_str
        return self.sess.get_json(url, headers=self._headers(), timeout=12)

    def categories(self):
        if self._dyn_cats is not None:
            return self._dyn_cats
        try:
            j = self._get(self.STORE, "/api/v1/playlet/tag/list?operation=1",
                          _md5("operation=1" + self.KEY))
            cats = []
            for c in (j.get("data") or {}).get("list") or []:
                cid = _pick(c, "tag_id", "id")
                cn = _pick(c, "tag_name", "name", "title")
                if cid and cn:
                    cats.append((cid, cn))
            if cats:
                self._dyn_cats = cats[:24]
                return self._dyn_cats
        except Exception:
            pass
        return self.cats

    def _node(self, n):
        vid = _pick(n, "playlet_id", "playletId", "id")
        if not vid:
            return None
        total = _pick_int(n, "total_episode_num", "totalEpisodeNum", "total")
        tags = n.get("tags") or n.get("tag_list") or []
        cat = ",".join(_s(t) for t in tags if _s(t))[:60]
        v = _vod_item(
            self.id, vid, _pick(n, "title", "playlet_name", "name"),
            _pick(n, "image_link", "imageLink", "cover", "cover_url"),
            ("全%d集" % total) if total else "",
            _pick(n, "intro", "description", "desc"))
        if cat:
            v["vod_remarks"] = (v["vod_remarks"] + " " + cat).strip()
        return v

    def cat(self, catid, pg):
        catid = _s(catid) or "0"
        if not catid.isdigit():
            catid = "0"
        if pg > 1:
            sign = _md5("next_id=%doperation=1playlet_privacy=1tag_id=%s%s"
                        % (pg, catid, self.KEY))
            path = ("/api/v1/playlet/index?tag_id=%s&playlet_privacy=1"
                    "&operation=1&next_id=%d" % (catid, pg))
        else:
            sign = _md5("operation=1playlet_privacy=1tag_id=%s%s"
                        % (catid, self.KEY))
            path = ("/api/v1/playlet/index?tag_id=%s&playlet_privacy=1"
                    "&operation=1" % catid)
        j = self._get(self.STORE, path, sign)
        rows = (j.get("data") or {}).get("list") or []
        items = [v for v in (self._node(n) for n in rows) if v]
        more = len(items) > 0 if pg > 1 else False
        return items, more

    def home(self, pg):
        return self.cat("0", pg)

    def detail(self, sid):
        sign = _md5("playlet_id=" + sid + self.KEY)
        j = self._get(self.READ, "/player/api/v1/playlet/info?playlet_id="
                      + _q(sid), sign)
        data = j.get("data") or {}
        v = self._node(data) or _vod_item(self.id, sid, sid)
        v["vod_content"] = _pick(data, "intro", "description", "desc")
        chapters = []
        for i, e in enumerate(data.get("play_list") or []):
            u = _pick(e, "video_url", "videoUrl", "url")
            if not u:
                continue
            no = _pick_int(e, "sort", "episode", "index") or (i + 1)
            t = _pick(e, "title", "name") or ("第%d集" % no)
            chapters.append((u, t))
        chapters.sort(key=lambda x: _ep_no(x[1]))
        v.update({
            "vod_remarks": ("全%d集" % len(chapters)) if chapters else "",
            "vod_play_from": self.name,
            "vod_play_url": "#".join(
                "%s$%s" % (t, _pid(self.id, sid, k)) for k, t in chapters),
        })
        return v

    def play(self, sid, ep):
        if not _s(ep).startswith("http"):
            raise _SrcErr("猫果分集地址无效")
        return _s(ep), {}

    def search(self, key, pg):
        # 顺序敏感：extend,page,read_preference,track_id,wd
        sign = _md5("extend=page=1read_preference=0track_id=%swd=%s%s"
                    % (self.TRACK_ID, key, self.KEY))
        path = ("/api/v1/playlet/search?extend=&page=1&wd=%s"
                "&read_preference=0&track_id=%s" % (_q(key), self.TRACK_ID))
        j = self._get(self.STORE, path, sign)
        data = j.get("data") or {}
        rows = data.get("list") or []
        items = [v for v in (self._node(n) for n in rows) if v]
        return items, False


# ============================================================
# 黄豆 — 自定义加密传输（HMAC-SHA256 派生 AES-256-CBC 密钥）
# ============================================================
@_register
class _Huangdou(_Src):
    id = "huangdou"
    name = "黄豆"
    cats = [("", "全部")]
    HOSTS = ["https://tideember.cc", "https://xqjurgek.top"]
    PLATFORM_KEY = "7961beb44246e3012ce228d6b5ced05a"
    VERSION = "2.0.0"

    def __init__(self):
        super().__init__()
        self._host = self.HOSTS[0]
        self._device_id = binascii.hexlify(os.urandom(16)).decode()
        self._session_id = binascii.hexlify(os.urandom(16)).decode()

    @staticmethod
    def _uuid_like():
        h = binascii.hexlify(os.urandom(16)).decode()
        return "%s-%s-%s-%s-%s" % (h[:8], h[8:12], h[12:16], h[16:20], h[20:])

    def _key(self, rid):
        msg = binascii.unhexlify(rid.replace("-", ""))
        return hmac.new(self.PLATFORM_KEY.encode(), msg,
                        hashlib.sha256).digest()

    def _call(self, path, data):
        path = "/" + path.lstrip("/")
        rid = self._uuid_like()
        key = self._key(rid)
        iv = os.urandom(16)
        plain = json.dumps({"token": "", "deviceId": self._device_id,
                            "data": data},
                           ensure_ascii=False).encode("utf-8")
        gz = gzip.compress(plain)
        body = iv + _aes_cbc_encrypt(gz, key, iv)
        ts = str(int(time.time()))
        sign_raw = "Dart|%s|%s|%s|%s" % (self._session_id, rid, ts, path)
        sign = hashlib.sha256(sign_raw.encode()).hexdigest() + "-" + ts
        headers = {
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120 Safari/537.36"),
            "Accept": "*/*",
            "Content-Type": "application/octet-stream",
            "version": self.VERSION,
            "deviceType": "web",
            "requestId": rid,
            "sessionId": self._session_id,
            "time": ts,
            "sign": sign,
        }
        last = None
        for host in [self._host] + [h for h in self.HOSTS
                                    if h != self._host]:
            headers["Origin"] = host
            headers["Referer"] = host + "/home"
            try:
                r = self.sess.fetch(host + "/api" + path, method="POST",
                                    headers=headers, data=body, timeout=20)
            except Exception as e:
                last = e
                continue
            if r.status < 200 or r.status >= 300:
                last = _SrcErr("黄豆 HTTP %d" % r.status)
                continue
            self._host = host
            return self._decode(r.body, key)
        raise _SrcErr("黄豆接口不可用：%s" % last)

    def _decode(self, blob, key):
        blob = bytes(blob).strip()
        if blob.startswith((b"{", b"[")):
            try:
                decoded = json.loads(blob.decode("utf-8", "ignore"))
            except Exception:
                raise _SrcErr("黄豆响应 JSON 无效")
        else:
            if len(blob) < 32:
                raise _SrcErr("黄豆响应过短")
            iv, ct = blob[:16], blob[16:]
            try:
                plain = _aes_cbc_decrypt(ct, key, iv)
            except Exception as e:
                raise _SrcErr("黄豆响应解密失败：%s" % e)
            if plain[:2] == b"\x1f\x8b":
                try:
                    plain = gzip.decompress(plain)
                except Exception:
                    raise _SrcErr("黄豆响应解压失败")
            try:
                decoded = json.loads(plain.decode("utf-8", "ignore"))
            except Exception:
                raise _SrcErr("黄豆响应 JSON 无效")
        if isinstance(decoded, dict):
            status = _pick(decoded, "status")
            if status and status != "y":
                code = _pick(decoded, "errorCode", "error_code", "code")
                msg = _pick(decoded, "msg", "message", "error") or status
                if code in ("813004", "813005", "813006", "813103") or \
                        "preview" in code:
                    raise _SrcErr("黄豆：该内容需 VIP/试看限制")
                raise _SrcErr("黄豆接口拒绝：%s" % msg)
        return decoded

    def _rows(self, decoded):
        if isinstance(decoded, list):
            return decoded
        if isinstance(decoded, dict):
            data = decoded.get("data")
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                for k in ("list", "items", "data"):
                    v = data.get(k)
                    if isinstance(v, list):
                        return v
            for k in ("list", "items", "data"):
                v = decoded.get(k)
                if isinstance(v, list):
                    return v
        return []

    def _node(self, n):
        vid = _pick(n, "id", "drama_id")
        if vid.startswith("rp_"):
            vid = vid[3:]
        if not vid:
            return None
        total = _pick_int(n, "episode_count")
        remark = _pick(n, "update_label", "corner")
        if not remark and total:
            remark = "全%d集" % total
        return _vod_item(
            self.id, vid, _pick(n, "name", "title", "t"),
            _pick(n, "img_y", "img_x", "img", "cover", "pic"),
            remark, _pick(n, "description", "summary"))

    def cat(self, catid, pg):
        j = self._call("/drama/list", {"page": str(pg), "page_size": "30"})
        rows = self._rows(j)
        items = [v for v in (self._node(n) for n in rows) if v]
        return items, len(items) >= 30

    def search(self, key, pg):
        j = self._call("/drama/list", {"keywords": key, "page": "1",
                                       "page_size": "50"})
        rows = self._rows(j)
        items = [v for v in (self._node(n) for n in rows) if v]
        return items, False

    def detail(self, sid):
        j = self._call("/drama/detail", {"id": sid})
        data = j.get("data") if isinstance(j, dict) else None
        node = data if isinstance(data, dict) else (j if isinstance(j, dict)
                                                   else {})
        rid = _pick(node, "id", "drama_id")
        if rid.startswith("rp_"):
            rid = rid[3:]
        if rid and rid != sid:
            raise _SrcErr("黄豆详情与请求剧集不符")
        v = self._node(node) or _vod_item(self.id, sid, sid)
        v["vod_content"] = _pick(node, "description", "summary")
        chapters = []
        for i, e in enumerate(node.get("episodes") or []):
            no = _pick_int(e, "seq", "episode", "ep") or (i + 1)
            t = _pick(e, "name", "title") or ("第%d集" % no)
            chapters.append((str(no), t))
        if not chapters:
            total = _pick_int(node, "episode_count", "free_episodes")
            chapters = [(str(i + 1), "第%d集" % (i + 1))
                        for i in range(min(total, 3000))]
        v.update({
            "vod_remarks": ("全%d集" % len(chapters)) if chapters else "",
            "vod_play_from": self.name,
            "vod_play_url": "#".join(
                "%s$%s" % (t, _pid(self.id, sid, k)) for k, t in chapters),
        })
        return v

    def _is_preview(self, data, media):
        for k in ("is_preview", "isPreview"):
            if str(data.get(k)).lower() in ("true", "1", "y"):
                return True
        for k in ("preview_m3u8", "preview_url"):
            pv = _pick(data, k)
            if pv and (not media or pv.strip() == media.strip()):
                return True
        if media:
            p = urllib.parse.urlparse(media).path.lower()
            if p.endswith("/preview.mp4") or p.endswith("/preview.m3u8") \
                    or p == "preview.mp4" or p == "preview.m3u8":
                return True
        return False

    def play(self, sid, ep):
        j = self._call("/drama/play", {"id": sid, "seq": str(ep)})
        data = j.get("data") if isinstance(j, dict) else {}
        if not isinstance(data, dict):
            data = {}
        media = _pick(data, "m3u8", "url", "play_url", "playUrl")
        if self._is_preview(data, media):
            raise _SrcErr("黄豆：该分集为 VIP 试看，不提供试看地址")
        if media:
            if not media.startswith("http"):
                media = self._host + "/" + media.lstrip("/")
            return media, {"Referer": self._host + "/home",
                           "User-Agent": PC_UA}
        # 降级直链
        url = ("%s/api/drama/hls/%s/%s/play.m3u8?line=free"
               % (self._host, _q(sid), _q(str(ep))))
        try:
            r = self.sess.fetch(url,
                                headers={"Referer": self._host + "/home"},
                                timeout=12)
            if r.body.startswith(b"#EXTM3U"):
                return url, {"Referer": self._host + "/home"}
        except Exception:
            pass
        raise _SrcErr("黄豆未返回该集播放地址")


# ============================================================
# 野果 — 配置动态发现（__NUXT_DATA__ + _nuxt/*.js），AES-CBC + 响应签名
# 配置/解码失败只重新发现并重试一次。
# ============================================================
@_register
class _Yeguo(_Src):
    id = "yeguo"
    name = "野果"
    cats = [("", "全部")]
    SITES = ["https://analyze.buxefaex.cc", "https://ygdj7.com/"]
    _PUB_FIELD = re.compile(
        r"""\b(version|mode|padding|key|iv|sign_key)\s*:\s*(?:[a-zA-Z_$][a-zA-Z0-9_$]*\(\s*)?["'`]([^"'`\\\r\n]{1,512})["'`]""")
    _IMPORT = re.compile(
        r"""(?s)import\s*\{([^{};]+)\}\s*from\s*["'`]([^"'`]+)["'`]""")

    def __init__(self):
        super().__init__()
        self._access = None
        self._lock = threading.Lock()
        self._dyn_cats = None

    # -- 发现 --
    @staticmethod
    def _pub_bytes(value):
        if "_" not in value:
            return value.encode("utf-8")
        out = bytearray()
        for part in value.split("_"):
            try:
                n = int(part)
            except Exception:
                return None
            if n < 0 or n > 255:
                return None
            out.append(n)
        return bytes(out)

    def _parse_pub_config(self, script):
        fields = {}
        for m in self._PUB_FIELD.finditer(script[:2000000]):
            fields[m.group(1)] = m.group(2)
            if len(fields) > 32:
                break
        if fields.get("version") != "v0" or fields.get("mode") != "CBC" \
                or fields.get("padding") != "Pkcs7":
            return None
        key = self._pub_bytes(fields.get("key", ""))
        iv = self._pub_bytes(fields.get("iv", ""))
        sk = self._pub_bytes(fields.get("sign_key", ""))
        if key is None or iv is None or sk is None:
            return None
        if len(key) not in (16, 24, 32) or len(iv) != 16 \
                or not (1 <= len(sk) <= 128):
            return None
        return key, iv, sk

    def _api_base(self, html):
        m = re.search(
            r'''(?is)<script[^>]*id=["']__NUXT_DATA__["'][^>]*>(.*?)</script>''',
            html)
        if not m:
            return ""
        try:
            table = json.loads(m.group(1))
        except Exception:
            return ""
        if not isinstance(table, list) or len(table) > 100000:
            return ""
        for item in table:
            if isinstance(item, dict) and "apiBaseURL" in item:
                ref = item["apiBaseURL"]
                if isinstance(ref, int) and 0 <= ref < len(table):
                    base = table[ref]
                    if isinstance(base, str) and base:
                        return base.rstrip("/")
        return ""

    def _script_url(self, page_url, ref):
        try:
            page = urllib.parse.urlparse(page_url)
            u = urllib.parse.urljoin(page_url, ref)
            p = urllib.parse.urlparse(u)
        except Exception:
            return ""
        if p.netloc != page.netloc:
            return ""
        if not p.path.startswith("/_nuxt/") or \
                not p.path.endswith(".js"):
            return ""
        return u.split("#")[0]

    def _discover_at(self, site):
        r = self.sess.fetch(site + "/", headers={"Referer": site + "/"},
                            timeout=15)
        html = r.text()
        page_url = r.url or (site + "/")
        api_base = self._api_base(html)
        if not api_base:
            raise _SrcErr("野果页面未提供有效的接口入口")
        entry = ""
        for m in re.finditer(
                r'''(?is)<script[^>]*type=["']module["'][^>]*src=["']([^"']+)["']''',
                html):
            entry = self._script_url(page_url, m.group(1))
            if entry:
                break
        if not entry:
            raise _SrcErr("野果页面未提供接口配置脚本")
        entry_body = self.sess.fetch(entry, headers={"Referer": page_url},
                                     timeout=15).text()
        imports = self._IMPORT.findall(entry_body)
        # 无逗号的 import 优先
        imports.sort(key=lambda x: ("," in x[0]))
        seen = set()
        for _names, ref in imports:
            if len(ref) > 2400:
                continue
            url = self._script_url(entry, ref)
            if not url or url in seen or len(seen) >= 20:
                continue
            seen.add(url)
            try:
                body = self.sess.fetch(url, headers={"Referer": page_url},
                                       timeout=15).text()
            except Exception:
                continue
            cfg = self._parse_pub_config(body)
            if cfg:
                key, iv, sk = cfg
                ident = binascii.hexlify(os.urandom(16)).decode()
                return {"base": api_base, "site": site, "key": key,
                        "iv": iv, "sign_key": sk, "ident": ident}
        raise _SrcErr("野果接口配置已变化，暂时无法解码")

    def _discover(self):
        with self._lock:
            if self._access:
                return self._access
            last = None
            for site in self.SITES:
                try:
                    acc = self._discover_at(site)
                    self._access = acc
                    return acc
                except Exception as e:
                    last = e
            raise _SrcErr("野果线路暂不可用：%s" % last)

    def _drop_access(self):
        with self._lock:
            self._access = None

    # -- 签名/解码 --
    @staticmethod
    def _sign(envelope, sign_key):
        pieces = []
        for name in sorted(envelope.keys()):
            if name in ("sign", "_ver"):
                continue
            v = envelope[name]
            if v is None:
                continue
            if isinstance(v, bool):
                f = "true" if v else "false"
            elif isinstance(v, (int, float)):
                f = str(v)
            elif isinstance(v, str):
                f = v
            else:
                raise _SrcErr("野果响应签名格式无效")
            if name == "data":
                f = f.replace(" ", "+")
            pieces.append(name + "=" + f)
        d1 = hashlib.sha256(
            ("&".join(pieces)).encode("utf-8") + sign_key).hexdigest()
        return hashlib.md5(d1.encode("utf-8")).hexdigest()

    def _decode(self, body, acc):
        try:
            env = json.loads(body.decode("utf-8", "ignore"))
        except Exception:
            raise _SrcErr("野果响应 JSON 无效")
        if not isinstance(env, dict):
            raise _SrcErr("野果响应格式无效")
        sig = _s(env.get("sign"))
        if sig:
            try:
                exp = self._sign(env, acc["sign_key"])
            except _SrcErr:
                raise
            except Exception:
                raise _SrcErr("野果响应验签失败")
            if exp != sig.lower():
                raise _SrcErr("野果响应验签失败")
        data = env.get("data")
        if isinstance(data, str):
            b64 = data.replace(" ", "+").strip()
            try:
                ct = base64.b64decode(b64)
            except Exception:
                raise _SrcErr("野果数据 Base64 无效")
            if not ct or len(ct) % 16:
                raise _SrcErr("野果数据长度无效")
            try:
                plain = _aes_cbc_decrypt(ct, acc["key"], acc["iv"])
            except Exception:
                raise _SrcErr("野果数据解密失败")
            try:
                payload = json.loads(plain.decode("utf-8", "ignore"))
            except Exception:
                raise _SrcErr("野果数据 JSON 无效")
        else:
            payload = env
        if not isinstance(payload, dict):
            raise _SrcErr("野果返回的数据格式无效")
        if _s(payload.get("status")) == "-1":
            raise _SrcErr("野果当前内容需要站源授权")
        if _s(payload.get("status")) != "1":
            raise _SrcErr("野果请求未完成：%s"
                          % (_s(payload.get("msg"))[:90] or "请稍后重试"))
        data = payload.get("data")
        if not isinstance(data, dict):
            raise _SrcErr("野果返回的数据格式无效")
        return data

    def _call(self, route, params):
        last = None
        for attempt in range(2):
            acc = self._discover()
            values = {"bundleId": "com.pwa.mater", "version": "1.3.2",
                      "oauth_type": "web", "language": "zh", "via": "pwa",
                      "oauth_id": acc["ident"], "trace_id": acc["ident"],
                      "token": ""}
            values.update(params or {})
            method = "GET" if route == "/api/home/contentOptions" else "POST"
            url = acc["base"] + route
            headers = {"User-Agent": PC_UA,
                       "Accept": "application/json, text/plain, */*",
                       "Origin": acc["site"], "Referer": acc["site"] + "/"}
            try:
                if method == "GET":
                    url += "?" + urllib.parse.urlencode(values)
                    r = self.sess.fetch(url, headers=headers, timeout=20)
                else:
                    headers["Content-Type"] = \
                        "application/x-www-form-urlencoded"
                    r = self.sess.fetch(
                        url, method="POST", headers=headers,
                        data=urllib.parse.urlencode(values).encode(),
                        timeout=20)
                if r.status < 200 or r.status >= 300:
                    raise _SrcErr("野果 HTTP %d" % r.status)
                return self._decode(r.body, acc)
            except _SrcErr as e:
                last = e
                msg = str(e)
                if "验签失败" in msg or "解密失败" in msg:
                    self._drop_access()
                    continue
                raise
            except Exception as e:
                last = e
                raise _SrcErr("野果请求失败：%s" % e)
        raise _SrcErr("野果解码失败：%s" % last)

    # -- 业务 --
    def _node(self, n, site):
        vid = _pick(n, "video_id", "id")
        if not vid or not vid.isdigit():
            return None
        title = _pick(n, "title")
        if not title:
            return None
        total = _pick_int(n, "episode_count", "total_episode", "total")
        return _vod_item(
            self.id, vid, title,
            _abs(site + "/", _pick(n, "cover", "cover_url", "image")),
            ("全%d集" % total) if total else "",
            _pick(n, "desc", "description", "intro"))

    def categories(self):
        if self._dyn_cats is not None:
            return self._dyn_cats
        try:
            data = self._call("/api/home/contentOptions", None)
            vf = data.get("video_filter")
            if isinstance(vf, dict):
                cats, seen = [], set()
                for field, f in vf.items():
                    if not isinstance(f, dict):
                        continue
                    for o in f.get("list") or []:
                        if not isinstance(o, dict):
                            continue
                        val, nm = _pick(o, "value"), _pick(o, "name")
                        if not val or val == "0" or not nm or \
                                len(nm) > 48:
                            continue
                        cid = "%s:%s" % (field, val)
                        if cid in seen:
                            continue
                        seen.add(cid)
                        cats.append((cid, nm))
                if cats:
                    self._dyn_cats = cats[:30]
                    return self._dyn_cats
        except Exception:
            pass
        return self.cats

    def cat(self, catid, pg):
        params = {"page": str(pg), "limit": "20"}
        if catid and ":" in catid:
            f, v = catid.split(":", 1)
            params[f] = v
        data = self._call("/api/theater/exploreList", params)
        rows = data.get("list") or []
        site = (self._access or {}).get("site", self.SITES[0])
        items = [v for v in (self._node(n, site) for n in rows
                             if isinstance(n, dict)) if v]
        total = _pick_int(data, "total", "total_count", "totalCount")
        limit = _pick_int(data, "limit", "page_size", "pageSize",
                          "per_page", "perPage") or 20
        more = (pg < (total + limit - 1) // limit) if total \
            else len(items) >= limit
        hm = data.get("has_more")
        if hm is not None:
            more = str(hm).lower() in ("1", "true", "y")
        return items, more

    def home(self, pg):
        return self.cat("", pg)

    def search(self, key, pg):
        data = self._call("/api/search/result",
                          {"keyword": key, "tab": "video",
                           "page": str(pg), "limit": "20"})
        rows = data.get("list") or []
        site = (self._access or {}).get("site", self.SITES[0])
        items = [v for v in (self._node(n, site) for n in rows
                             if isinstance(n, dict)) if v]
        return items, False

    def detail(self, sid):
        if not sid.isdigit():
            raise _SrcErr("野果剧集 ID 无效")
        row = self._call("/api/playlet/detail",
                         {"video_id": sid, "id": sid, "episode_id": "0",
                          "related_limit": "0"})
        site = (self._access or {}).get("site", self.SITES[0])
        if _pick(row, "video_id", "id") != sid:
            raise _SrcErr("野果详情与请求剧集不符")
        v = self._node(row, site) or _vod_item(self.id, sid, sid)
        v["vod_content"] = _pick(row, "desc", "description", "intro")
        chapters = []
        seen_ids, seen_no = set(), set()
        for e in row.get("episodes") or []:
            if not isinstance(e, dict):
                continue
            if str(e.get("is_adv")).lower() in ("1", "true", "y"):
                continue
            eid = _pick(e, "id")
            try:
                no = int(_s(e.get("sort")))
            except Exception:
                no = 0
            if not eid or not eid.isdigit() or no < 1 or \
                    eid in seen_ids or no in seen_no:
                continue
            seen_ids.add(eid)
            seen_no.add(no)
            t = _pick(e, "title") or ("第%d集" % no)
            chapters.append((eid, t, no))
        chapters.sort(key=lambda x: x[2])
        v.update({
            "vod_remarks": ("全%d集" % len(chapters)) if chapters else "",
            "vod_play_from": self.name,
            "vod_play_url": "#".join(
                "%s$%s" % (t, _pid(self.id, sid, k))
                for k, t, _n in chapters),
        })
        return v

    def play(self, sid, ep):
        if not _s(ep).isdigit():
            raise _SrcErr("野果分集 ID 无效")
        row = self._call("/api/playlet/play",
                         {"playlet_id": sid, "video_id": sid,
                          "episode_id": _s(ep)})
        if _pick(row, "playlet_id") != sid or _pick(row, "id") != _s(ep):
            raise _SrcErr("野果返回的播放地址与请求分集不符")
        if str(row.get("is_adv")).lower() in ("1", "true", "y"):
            raise _SrcErr("野果未返回该集正片")
        media = _pick(row, "video_url", "video_url_h265")
        if not media:
            raise _SrcErr("野果未返回播放地址")
        site = (self._access or {}).get("site", self.SITES[0])
        return _abs(site + "/", media), {"Referer": site + "/"}


# ============================================================
# 黄果旧版 — AES 加密 JSON API + 访客 token 会话
# ============================================================
@_register
class _Hgcf(_Src):
    id = "hgcf"
    name = "黄果旧版"
    cats = [("", "推荐")]
    API_DEFAULT = "https://dr6skssi3nxbk.cloudfront.net"
    FRONTEND = "https://d2pypzndaqisk.cloudfront.net"
    CDN_DEFAULT = "https://sjljsla.lkkwip.cn"
    X_UA = ("BuildID=com.abc.Butterfly;SysType=ios;DevID=00000000000000000000000000000;"
            "Ver=1.0.0;DevType=iPhone;DeviceBrand=APPLE;DeviceModel=iPhone;"
            "SystemName=iOS;SystemVersion=18.7;Terminal=1;IsH5=1;"
            "Sid=00000000000000000000000000000000")

    def __init__(self):
        super().__init__()
        self._api = ""
        self._proto = None       # (interfaceKey, paramKey, paramIV)
        self._proto_at = 0
        self._device_id = ""
        self._token = ""
        self._lock = threading.Lock()
        self._dyn_cats = None

    # -- 会话 --
    def _frontend_script(self):
        html = self.sess.get_text(self.FRONTEND + "/",
                                  headers={"User-Agent": IPHONE_UA},
                                  timeout=15)
        m = re.search(r'''(?is)<script[^>]+src=["']([^"']*main-[^"']*\.js)["']''',
                      html)
        if not m:
            raise _SrcErr("黄果旧版前端脚本未找到")
        js_url = _abs(self.FRONTEND + "/", m.group(1))
        return self.sess.get_text(js_url, headers={"User-Agent": IPHONE_UA},
                                  timeout=15)

    def _discover_api(self):
        try:
            js = self._frontend_script()
        except Exception:
            return self.API_DEFAULT
        for host in re.findall(r"https://[a-z0-9]+\.cloudfront\.net", js):
            try:
                j = self.sess.get_json(host + "/api/app/ping/check",
                                       headers={"User-Agent": IPHONE_UA},
                                       timeout=8)
                if j.get("code") == 200:
                    return host
            except Exception:
                continue
        return self.API_DEFAULT

    def _protocol(self):
        with self._lock:
            if self._proto and time.time() - self._proto_at < 24 * 3600:
                return self._proto
            js = self._frontend_script()
            def val(name):
                m = re.search(r"""["']%s["']\s*[:,]\s*["']([^"'\\\r\n]+)["']"""
                              % name, js)
                return m.group(1) if m else ""
            ik, pk, piv = val("interfaceKey"), val("parameterKey"), \
                val("parameterIv")
            if not (0 < len(ik) <= 512 and len(pk) == 16 and len(piv) == 16):
                raise _SrcErr("黄果旧版接口协议已变化")
            self._proto = (ik, pk, piv)
            self._proto_at = time.time()
            return self._proto

    def _login(self):
        ik, pk, piv = self._protocol()
        payload = self._raw_request(
            "POST", "/api/app/mine/login/h5",
            {"devID": self._device_id, "sysType": "ios",
             "isAppStore": False},
            ik, pk, piv, "")
        token = _pick(payload, "token")
        if not token:
            raise _SrcErr("黄果旧版访客登录未返回令牌")
        with self._lock:
            self._token = token

    def _x_user_agent(self):
        did = self._device_id or "00000000000000000000000000000"
        return self.X_UA.replace("DevID=00000000000000000000000000000",
                                 "DevID=" + did, 1)

    def _decrypt_response(self, data_str, interface_key):
        o = base64.b64decode(data_str.strip())
        if len(o) < 12:
            raise _SrcErr("黄果旧版加密响应过短")
        i = o[:12]
        r = interface_key.encode() + i
        l = len(r) >> 1
        s = _sha256(r)[8:24]
        c = s + r[:l]
        a = r[l:] + s
        d = _sha256(c)
        f = _sha256(a)
        m = d[:8] + f[8:24] + d[24:]
        p = f[:4] + d[12:20] + f[28:]
        g = o[12:]
        if len(g) % 16:
            raise _SrcErr("黄果旧版密文未对齐")
        return _pkcs7_unpad(_aes_crypt_fast(g, m, p, False, True), )

    def _raw_request(self, method, path, params, ik, pk, piv, token):
        enc = None
        if params is not None:
            plain = json.dumps(params, ensure_ascii=False).encode("utf-8")
            enc = base64.b64encode(
                _aes_cbc_encrypt(plain, pk.encode(), piv.encode())).decode()
        url = self._api + path
        headers = {
            "Accept": "application/json",
            "temp": "test",
            "X-User-Agent": self._x_user_agent(),
            "Origin": self.FRONTEND,
            "Referer": self.FRONTEND + "/",
            "User-Agent": IPHONE_UA,
        }
        if token:
            headers["Authorization"] = token
        if method == "GET":
            if enc:
                sep = "&" if "?" in url else "?"
                url += sep + "data=" + _q(enc)
            r = self.sess.fetch(url, headers=headers, timeout=15)
        else:
            headers["Content-Type"] = "application/json"
            body = json.dumps({"data": enc},
                              ensure_ascii=False).encode("utf-8")
            r = self.sess.fetch(url, method="POST", headers=headers,
                                data=body, timeout=15)
        if r.status < 200 or r.status >= 300:
            raise _SrcErr("黄果旧版 HTTP %d" % r.status)
        try:
            env = json.loads(r.text())
        except Exception:
            raise _SrcErr("黄果旧版响应 JSON 无效")
        code = _s(env.get("code")).strip('"')
        if code not in ("", "null", "200", "0"):
            msg = _s(env.get("msg"))[:120] or "接口错误"
            err = _SrcErr("黄果旧版 API %s: %s" % (code, msg))
            err.code = code
            raise err
        data = env.get("data")
        h = env.get("hash")
        hash_on = bool(h) if isinstance(h, bool) else _s(h).lower() not in (
            "", "0", "false", "null")
        if hash_on and data:
            if not isinstance(data, str):
                raise _SrcErr("黄果旧版加密数据格式无效")
            try:
                plain = self._decrypt_response(data, ik)
            except _SrcErr:
                raise
            except Exception as e:
                raise _SrcErr("黄果旧版响应解密失败：%s" % e)
            return json.loads(plain.decode("utf-8", "ignore"))
        return data

    def _api_call(self, method, path, params=None, retry=True):
        # 确保会话
        with self._lock:
            if not self._api:
                self._api = self._discover_api()
            if not self._device_id:
                self._device_id = ("%08X%d" % (
                    random.getrandbits(32), int(time.time() * 1000)))
            api, token = self._api, self._token
        ik, pk, piv = self._protocol()
        if not token:
            self._login()
            with self._lock:
                token = self._token
        try:
            return self._raw_request(method, path, params, ik, pk, piv,
                                     token)
        except _SrcErr as e:
            if retry and getattr(e, "code", "") == "5005":
                with self._lock:
                    self._token = ""
                self._login()
                with self._lock:
                    token = self._token
                return self._raw_request(method, path, params, ik, pk, piv,
                                         token)
            raise

    # -- 业务 --
    def _fix_cover(self, pic):
        pic = _s(pic)
        if not pic or pic.startswith("http"):
            return pic
        if pic.startswith("upload/") or pic.startswith("upload_01/"):
            return "https://pic.zdmhyg.cn/" + pic
        return "https://zzzznnn.lkkwip.cn/" + pic.lstrip("/")

    def categories(self):
        if self._dyn_cats is not None:
            return self._dyn_cats
        try:
            tabs = self._api_call("GET", "/api/app/playlet-tab/all", None)
            rows = tabs.get("list") if isinstance(tabs, dict) else tabs
            cats = []
            for t in rows if isinstance(rows, list) else []:
                cid = _pick(t, "id")
                cn = _pick(t, "name")
                if cid and cn:
                    cats.append((cid, cn))
            if cats:
                self._dyn_cats = cats[:24]
                return self._dyn_cats
        except Exception:
            pass
        return self.cats

    def _node(self, n):
        vid = _pick(n, "id", "playlet_id", "videoId")
        if not vid:
            return None
        total = _pick_int(n, "totalEpisode", "total_episode", "episodeCount",
                          "episode_count", "chapterCount", "chapter_count",
                          "total", "episodes")
        return _vod_item(
            self.id, vid, _pick(n, "title", "name"),
            self._fix_cover(_pick(n, "cover", "coverUrl", "cover_url",
                                 "image", "imageUrl", "image_url", "img",
                                 "pic", "picture", "poster", "thumb",
                                 "thumbnail")),
            ("全%d集" % total) if total else "",
            _pick(n, "desc", "description", "intro", "summary"))

    def cat(self, catid, pg):
        cats = self.categories()
        tab = catid or (cats[0][0] if cats else "")
        if not tab:
            raise _SrcErr("黄果旧版无可用分类")
        data = self._api_call(
            "GET", "/api/app/playlet/home/tab/" + _q(tab),
            {"pageNumber": str(pg), "pageSize": "20", "tabSortType": "1"})
        rows = (data.get("list") if isinstance(data, dict) else data) or []
        items = [v for v in (self._node(n) for n in rows
                             if isinstance(n, dict)) if v]
        return items, len(items) >= 20

    def home(self, pg):
        return self.cat("", pg)

    def detail(self, sid):
        try:
            data = self._api_call("GET",
                                  "/api/app/playlet/detail/" + _q(sid), None)
        except Exception as e:
            raise _SrcErr("黄果旧版详情失败：%s" % e)
        if not isinstance(data, dict):
            raise _SrcErr("黄果旧版详情格式无效")
        v = self._node(data) or _vod_item(self.id, sid, sid)
        v["vod_content"] = _pick(data, "desc", "description", "intro")
        chapters = data.get("chapters")
        if not chapters:
            try:
                chapters = self._api_call(
                    "GET", "/api/app/playlet-chapter/list/" + _q(sid), None)
            except Exception:
                chapters = []
        if isinstance(chapters, dict):
            chapters = chapters.get("list") or []
        eps = []
        for i, c in enumerate(chapters or []):
            if not isinstance(c, dict):
                continue
            vu = _pick(c, "videoUrl", "video_url", "playUrl", "url")
            if not vu:
                continue
            t = _pick(c, "title", "name") or ("第%d集" % (i + 1))
            eps.append((vu, t))
        v.update({
            "vod_remarks": ("全%d集" % len(eps)) if eps else "",
            "vod_play_from": self.name,
            "vod_play_url": "#".join(
                "%s$%s" % (t, _pid(self.id, sid, k)) for k, t in eps),
        })
        return v

    def play(self, sid, ep):
        ep = _s(ep)
        with self._lock:
            api, token = self._api, self._token
        if ep.startswith("http"):
            media = ep
        else:
            media = ("%s/api/app/vid/h5/m3u8/%s?%s"
                     % (api, _q(ep.strip("/")),
                        urllib.parse.urlencode(
                            {"token": token, "c": self.CDN_DEFAULT})))
        return media, {"Referer": self.FRONTEND + "/",
                       "User-Agent": IPHONE_UA}

    def search(self, key, pg):
        # 无服务端搜索：拉首页按标题过滤
        items = []
        try:
            rows, _ = self.cat("", 1)
        except Exception:
            rows = []
        for v in rows:
            if key in v["vod_name"]:
                items.append(v)
        return items[:30], False

# Spider 主类（FongMi 5.6.4 / Chaquopy 合约：全部返回 dict）
# ============================================================
from concurrent.futures import ThreadPoolExecutor


class Spider(BaseSpider):

    def getName(self):
        return "真果鉴·全站源"

    def init(self, extend=""):
        self.extend = _s(extend)
        return {}

    def destroy(self):
        return {}

    def isVideoFormat(self, url):
        u = _s(url).lower()
        return (".m3u8" in u or ".mp4" in u or ".flv" in u or ".ts" in u
                or ".mkv" in u)

    def manualVideoCheck(self):
        return False

    # ---------- 首页 ----------
    def _source_cats(self, src):
        try:
            if hasattr(src, "categories"):
                cats = src.categories()
                if cats:
                    return cats[:24]
        except Exception:
            pass
        return src.cats or [("", "推荐")]

    def homeContent(self, filter=False):
        # 两级分类（照 ___3_shu0.py 的写法）：
        #   大分类=站源名（顶部 tab）；子分类=各源自己的分类，走 filters 二级筛选栏。
        #   filters 必须是 list 格式：{tid: [{"key","name","value":[{"n","v"}]}]}，
        #   dict 格式 FongMi 不认。
        cats_map = {}
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = {ex.submit(self._source_cats, src): src
                    for src in _SOURCES}
            for fut in futs:
                try:
                    cats_map[futs[fut].id] = fut.result(timeout=20)
                except Exception:
                    cats_map[futs[fut].id] = futs[fut].cats or [("", "推荐")]
        classes, filters = [], {}
        for src in _SOURCES:
            tid = _tid(src.id, "")
            classes.append({"type_id": tid, "type_name": src.name})
            subs = cats_map.get(src.id) or src.cats or [("", "推荐")]
            opts, seen_n = [], set()
            for cid, cname in subs[:30]:
                if not cname or cname in seen_n:
                    continue
                seen_n.add(cname)
                opts.append({"n": cname, "v": cid})
            if opts:
                filters[tid] = [{"key": "cat", "name": "分类",
                                 "value": opts}]
        vods = []
        try:
            items, _ = _SOURCES[0].home(1)
            vods = items[:24]
        except Exception:
            pass
        return {"class": classes, "list": vods, "filters": filters}

    def homeVideoContent(self):
        try:
            items, _ = _SOURCES[0].home(1)
            return {"list": items[:24]}
        except Exception:
            return {"list": []}

    # ---------- 分类 ----------
    def categoryContent(self, tid, pg="1", filter=False, extend=None):
        src_id, _ = _split_tid(tid)
        src = _find_src(src_id)
        if not src:
            return {"list": [], "page": 1, "pagecount": 1, "limit": 20,
                    "total": 0}
        try:
            pg = max(1, int(pg))
        except Exception:
            pg = 1
        # 子分类来自 filters 二级筛选：extend = {"cat": <cid>}（照 ___3_shu0.py）
        cat = ""
        ext = extend
        if isinstance(ext, str) and ext:
            try:
                ext = json.loads(ext)
            except Exception:
                ext = {}
        if isinstance(ext, dict):
            cat = _s(ext.get("cat", ""))
        if cat:
            # 兼容 FongMi 传显示名而不是 id 的情况
            try:
                cats = self._source_cats(src)
                if cat not in set(c[0] for c in cats):
                    by_name = dict((c[1], c[0]) for c in cats)
                    cat = by_name.get(cat, "")
            except Exception:
                pass
        if not cat:
            try:
                cats = self._source_cats(src)
                cat = cats[0][0] if cats else ""
            except Exception:
                cat = ""
        try:
            items, more = src.cat(cat, pg)
        except _SrcErr:
            items, more = [], False
        except Exception:
            items, more = [], False
        return {"list": items or [], "page": pg,
                "pagecount": 9999 if more else pg,
                "limit": 20, "total": 999999 if more else len(items or [])}

    # ---------- 详情 ----------
    def detailContent(self, ids):
        did = ids[0] if ids else ""
        src_id, sid = _split_did(did)
        src = _find_src(src_id)
        if not src:
            return {"list": []}
        try:
            vod = src.detail(sid)
        except _SrcErr as e:
            vod = _vod_detail(src, sid, "加载失败", "",
                              "", "原因：%s" % e, chapters=())
            vod["vod_id"] = did
        except Exception as e:
            vod = _vod_detail(src, sid, "加载失败", "",
                              "", "原因：%s" % type(e).__name__,
                              chapters=())
            vod["vod_id"] = did
        return {"list": [vod]}

    # ---------- 搜索（多源并行） ----------
    def _search_one(self, src, key):
        try:
            items, _ = src.search(key, 1)
            return items or []
        except Exception:
            return []

    def searchContent(self, key, quick=False, pg="1"):
        key = _s(key).strip()
        if not key:
            return {"list": []}
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        if pg > 1:
            return {"list": []}
        out = []
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = {ex.submit(self._search_one, src, key): src
                    for src in _SOURCES}
            for fut in futs:
                try:
                    items = fut.result(timeout=30)
                except Exception:
                    continue
                src = futs[fut]
                for v in (items or [])[:12]:
                    # 搜索结果名前缀站源，便于区分
                    if not v["vod_name"].startswith(src.name):
                        v["vod_name"] = "[%s] %s" % (src.name,
                                                     v["vod_name"])
                    out.append(v)
                if len(out) >= 160:
                    break
        return {"list": out}

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vipFlags=None):
        src_id, sid, ep = _split_pid(id)
        src = _find_src(src_id)
        if not src:
            return {"parse": 0, "playUrl": "", "url": "", "header": {}}
        try:
            url, header = src.play(sid, ep)
        except _SrcErr:
            return {"parse": 0, "playUrl": "", "url": "", "header": {}}
        except Exception:
            return {"parse": 0, "playUrl": "", "url": "", "header": {}}
        return {"parse": 0, "playUrl": "", "url": _s(url),
                "header": dict(header or {})}
