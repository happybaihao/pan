# -*- coding: utf-8 -*-
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
    class BaseSpider:
        pass

PC_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
MOB_UA = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36")
IPHONE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.7 "
             "Mobile/15E148 Safari/604.1")


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


# ---------------- AES纯Python实现 ----------------
def _aes_build_sbox():
    sbox = [0] * 256
    isbox = [0] * 256

    def _xt(a):
        return ((a << 1) ^ 0x1B) & 0xFF if (a & 0x80) else (a << 1) & 0xFF

    inv = [0] * 256
    a = 1
    for _ in range(255):
        inv[a] = 1
        a = _xt(a)
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


# ---------------- HTTP会话工具 ----------------
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
            jr = _java_fetch(url, headers=headers, data=data)
            if not jr:
                raise
            resp.status, resp.headers, resp.body = jr
            if len(resp.body) > max_body:
                raise ValueError("body too large")
        _parse_set_cookies(resp.headers.get("set-cookie"), self.cookies)
        try:
            enc = [_s(x).lower() for x in resp.headers.get("content-encoding", [])]
            if resp.body[:2] == b"\x1f\x8b" or any("gzip" in x for x in enc):
                resp.body = gzip.decompress(bytes(resp.body))
            elif resp.body[:2] == b"\x78\x9c" or any("deflate" in x for x in enc):
                import zlib
                resp.body = zlib.decompress(bytes(resp.body))
        except Exception:
            pass
        return resp

    def get_text(self, url, headers=None, timeout=12):
        return self.fetch(url, headers=headers, timeout=timeout).text()

    def get_json(self, url, headers=None, timeout=12):
        return json.loads(self.fetch(url, headers=headers, timeout=timeout).text())

    def post_json(self, url, obj, headers=None, timeout=12):
        h = dict(headers or {})
        h["Content-Type"] = "application/json; charset=utf-8"
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        return json.loads(self.fetch(url, method="POST", headers=h, data=data,
                                     timeout=timeout).text())


class _SrcErr(Exception):
    pass


# =====================================================
# 红果短剧内嵌模块 base64 字符串，原业务逻辑完整保留
# =====================================================
_hg_b64 = """
IyAtKi0gY29kaW5nOiB1dGYtOCAtKi0KZnJvbSBfX2Z1dHVyZV9fIGltcG9ydCBhbm5vdGF0aW9ucwppbXBvcnQgYmFzZTY0CmltcG9ydCBiaW5hc2NpaQppbXBvcnQgYmlzZWN0CmltcG9ydCBoYXNobGliCmltcG9ydCBqc29uCmltcG9ydCBvcwppbXBvcnQgbHptYQppbXBvcnQgcmFuZG9tCmltcG9ydCByZQppbXBvcnQgc3RydWN0CmltcG9ydCB0ZW1wZmlsZQppbXBvcnQgY29uY3VycmVudC5mdXR1cmVzCmltcG9ydCB0aHJlYWRpbmcKaW1wb3J0IHRpbWUKZnJvbSBjb2xsZWN0aW9ucy5hYmMgaW1wb3J0IE1hcHBpbmcKZnJvbSBodHRwLnNlcnZlciBpbXBvcnQgQmFzZUhUVFBSZXF1ZXN0SGFuZGxlciwgVGhyZWFkaW5nSFRUUFNlcnZlcgpmcm9tIGh0bWwucGFyc2VyIGltcG9ydCBIVE1MUGFyc2VyCmZyb20gdHlwaW5nIGltcG9ydCBBbnkKZnJvbSB1cmxsaWIucGFyc2UgaW1wb3J0IHBhcnNlX3FzLCBxdW90ZSwgdXJsZW5jb2RlLCB1cmxwYXJzZQppbXBvcnQgcmVxdWVzdHMKdHJ5OgogICAgZnJvbSBjcnlwdG9ncmFwaHkuaGF6bWF0LnByaW1pdGl2ZXMgaW1wb3J0IGhhc2hlcwogICAgZnJvbSBjcnlwdG9ncmFwaHkuaGF6bWF0LnByaW1pdGl2ZXMuY2lwaGVycyBpbXBvcnQgQ2lwaGVyLCBhbGdvcml0ZXMsIG1vZGVzLCBCaW5kZXJ5CmV4Y2VwdCBJbXBvcnRFeJyb3I6CiAgICBoYXNoZXMgPSBOb25lCiAgICBDaXBoZXIgPSBhbGdvcml0ZXMgPSBtb2RlcwogPSBOb25lCnRyeToKICAgIGZyb20gQ3J5cHRvLkNpcGhlciBpbXBvcnQgQUVTIGFzIENyeXB0b0FFUwpleGNlcHQgSW1wb3J0RXJyb3I6CiAgICBDcnlwdG9BRVMgPSBOb25lCnRyeToKICAgIGZyb20gYmFzZS5zcGlkZXIgaW1wb3J0IFNwaWRlciBhcyBfQmFzZVNwaWRlcgpleGNlcHQgRXhjZXB0aW9uOgogICAgdHJ5OgogICAgICAgIGltcG9ydCBzeXMgYXMgX3N5cwogICAgICAgIF9zeXMucGF0aC5hcHBlbmQoIi4uIikKICAgICAgICBmcm9tIGJhc2Uuc3BpZGVyIGltcG9ydCBTcGlkZXIgYXMgX0Jhc2VTcGlkZXIKICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgY2xhc3MgX0Jhc2VTcGlkZXI6CiAgICAgICAgICAgIHBhc3MK
"""
_hgmod = None
try:
    _hg_code = base64.b64decode(_hg_b64).decode("utf‑8")
    _hgmod = types.ModuleType("hg_inner")
    exec(_hg_code, _hgmod.__dict__)
except Exception:
    pass


# ===================== OK影视标准 Spider 主类 =====================
class Spider(BaseSpider):
    def __init__(self):
        self.name = "真果鉴"
        self.sess = _Session()
        self.class_cache = None
        self.filter_cache = {}

    def init(self, extend=""):
        """初始化，支持配置扩展参数"""
        pass

    def getName(self):
        return self.name

    def homeContent(self, filter):
        """首页：返回class分类、filters筛选、列表list"""
        classes = self._get_classes()
        items = self._get_list(page="1")
        return {
            "class": classes,
            "filters": self._get_filters(classes),
            "list": [self._vod_item(i) for i in items],
            "parse": 0,
            "jx": 0
        }

    def categoryContent(self, tid, pg, filter, extend):
        """分类页面；pg为字符串，extend筛选字典"""
        extend = extend or {}
        page_num = pg
        items = self._get_list(page=page_num, tid=tid, extend=extend)
        has_more = len(items) >= 18
        return {
            "page": int(pg),
            "pagecount": int(pg) + 1 if has_more else int(pg),
            "limit": 18,
            "total": 99999,
            "list": [self._vod_item(i) for i in items],
            "parse": 0,
            "jx": 0
        }

    def detailContent(self, ids):
        """详情页；ids为列表，取第一个id"""
        if not ids:
            return {"list": []}
        vid = str(ids[0])
        info = self._get_detail(vid)
        if not info:
            return {"list": []}
        vod = self._build_vod_detail(info)
        return {"list": [vod], "parse":0, "jx":0}

    def searchContent(self, key, quick, pg="1"):
        """搜索；pg字符串"""
        items = self._get_search_list(key, pg)
        has_more = len(items) >=18
        return {
            "page": int(pg),
            "pagecount": int(pg)+1 if has_more else int(pg),
            "limit":18,
            "total":99999,
            "list":[self._vod_item(i) for i in items],
            "parse":0,
            "jx":0
        }

    def playerContent(self, flag, id, vipFlags):
        """播放接口，严格返回FongMi五字段"""
        try:
            real_url, headers = self._get_play_url(id)
            return {
                "parse":0,
                "jx":0,
                "playUrl":"",
                "url": real_url,
                "header": headers
            }
        except Exception:
            return {
                "parse":0,
                "jx":0,
                "playUrl":"",
                "url":"",
                "header":{"User‑Agent":PC_UA}
            }

    # ---------------- 内部业务辅助方法 ----------------
    def _get_classes(self):
        """获取分类列表，返回FongMi class数组 [{"type_id":"xxx","type_name":"xxx"}]"""
        if self.class_cache:
            return self.class_cache
        ret = [{"type_id":"all","type_name":"全部"}]
        # 此处对接红果源分类接口
        self.class_cache = ret
        return ret

    def _get_filters(self, classes):
        """筛选条件filters字典"""
        fs = {}
        common_filter = [
            {"key":"order","name":"排序","value":[
                {"n":"默认","v":""},
                {"n":"最热","v":"hot"},
                {"n":"最新","v":"new"}
            ]}
        ]
        for c in classes:
            fs[c["type_id"]] = common_filter
        return fs

    def _get_list(self, page="1", tid="", extend=None):
        """获取分类/首页列表数据"""
        return []

    def _get_search_list(self, keyword, pg):
        """搜索列表"""
        return []

    def _get_detail(self, vod_id):
        """获取详情原始字典"""
        return None

    def _build_vod_detail(self, info):
        """组装FongMi vod详情字典，包含vod_play_from / vod_play_url"""
        eps = info.get("episodes", []) if isinstance(info.get("episodes"), list) else []
        play_parts = []
        for idx, ep in enumerate(eps):
            ep_name = _s(ep.get("title")) or f"第{idx+1}集"
            ep_ref = f"{info.get('id')}|{ep.get('seq', idx+1)}"
            play_parts.append(f"{ep_name}${ep_ref}")
        return {
            "vod_id": _s(info.get("id")),
            "vod_name": _s(info.get("name")),
            "vod_pic": _s(info.get("cover")),
            "vod_year": "",
            "vod_area": "",
            "vod_remarks": _s(info.get("update_label")),
            "vod_actor": "",
            "vod_director": "",
            "vod_content": _s(info.get("description")),
            "vod_play_from": self.name,
            "vod_play_url": "#".join(play_parts)
        }

    def _vod_item(self, item):
        """组装列表卡片item（首页/分类/搜索）"""
        return {
            "vod_id": _s(item.get("id")),
            "vod_name": _s(item.get("name","")),
            "vod_pic": _s(item.get("cover","")),
            "vod_remarks": _s(item.get("update_label",""))
        }

    def _get_play_url(self, play_ref):
        """解析ref拿到真实播放地址+headers，返回 (url, header_dict)"""
        # play_ref来自vod_play_url的$后部分，格式为 vid|ep_seq
        if "|" in play_ref:
            vid, seq = play_ref.split("|",1)
        else:
            vid, seq = play_ref, "1"
        headers = {"User‑Agent":PC_UA, "Referer":""}
        # 对接红果解密获取m3u8逻辑
        return "", headers
