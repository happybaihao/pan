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


# ---------------- HTTP 层 ----------------
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


class _SrcErr(Exception):
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
    cats = [("", "推荐")]

    def __init__(self):
        self.sess = _Session()

    def home(self, pg):
        return self.cat("", pg)

    def cat(self, catid, pg):
        raise _SrcErr("本站源暂无目录")

    def detail(self, sid):
        raise _SrcErr("本站源暂无详情")

    def play(self, sid, ep):
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
# 红果内嵌模块 base64，完整保留
# ============================================================
_hgmod = None
_HG_IMPORT_ERR = ""
try:
    import base64 as _b64m, types as _tmod
    _hg_raw = _b64m.b64decode(
        "IyAtKi0gY29kaW5nOiB1dGYtOCAtKi0KZnJvbSBfX2Z1dHVyZV9fIGltcG9ydCBhbm5vdGF0aW9ucwppbXBvcnQgYmFzZTY0CmltcG9ydCBiaW5hc2NpaQppbXBvcnQgYmlzZWN0CmltcG9ydCBoYXNobGliCmltcG9ydCBqc29uCmltcG9ydCBvcwppbXBvcnQgbHptYQppbXBvcnQgcmFuZG9tCmltcG9ydCByZQppbXBvcnQgc3RydWN0CmltcG9ydCB0ZW1wZmlsZQppbXBvcnQgY29uY3VycmVudC5mdXR1cmVzCmltcG9ydCB0aHJlYWRpbmcKaW1wb3J0IHRpbWUKZnJvbSBjb2xsZWN0aW9ucy5hYmMgaW1wb3J0IE1hcHBpbmcKZnJvbSBodHRwLnNlcnZlciBpbXBvcnQgQmFzZUhUVFBSZXF1ZXN0SGFuZGxlciwgVGhyZWFkaW5nSFRUUFNlcnZlcgpmcm9tIGh0bWwucGFyc2VyIGltcG9ydCBIVE1MUGFyc2VyCmZyb20gdHlwaW5nIGltcG9ydCBBbnkKZnJvbSB1cmxsaWIucGFyc2UgaW1wb3J0IHBhcnNlX3FzLCBxdW90ZSwgdXJsZW5jb2RlLCB1cmxwYXJzZQppbXBvcnQgcmVxdWVzdHMKdHJ5OgogICAgZnJvbSBjcnlwdG9ncmFwaHkuaGF6bWF0LnByaW1pdGl2ZXMgaW1wb3J0IGhhc2hlcwogICAgZnJvbSBjcnlwdG9ncmFwaHkuaGF6bWF0LnByaW1pdGl2ZXMuY2lwaGVycyBpbXBvcnQgQ2lwaGVyLCBhbGdvcml0ZXMsIG1vZGVzLCBCaW5kZXJ5CmV4Y2VwdCBJbXBvcnRFeJyb3I6CiAgICBoYXNoZXMgPSBOb25lCiAgICBDaXBoZXIgPSBhbGdvcml0ZXMgPSBtb2RlcwogPSBOb25lCnRyeToKICAgIGZyb20gQ3J5cHRvLkNpcGhlciBpbXBvcnQgQUVTIGFzIENyeXB0b0FFUwpleGNlcHQgSW1wb3J0RXJyb3I6CiAgICBDcnlwdG9BRVMgPSBOb25lCnRyeToKICAgIGZyb20gYmFzZS5zcGlkZXIgaW1wb3J0IFNwaWRlciBhcyBfQmFzZVNwaWRlcgpleGNlcHQgRXhjZXB0aW9uOgogICAgdHJ5OgogICAgICAgIGltcG9ydCBzeXMgYXMgX3N5cwogICAgICAgIF9zeXMucGF0aC5hcHBlbmQoIi4uIikKICAgICAgICBmcm9tIGJhc2Uuc3BpZGVyIGltcG9ydCBTcGlkZXIgYXMgX0Jhc2VTcGlkZXIKICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgY2xhc3MgX0Jhc2VTcGlkZXI6CiAgICAgICAgICAgIHBhc3MKCiMgRm9uZ01pL1RWQm94IOeahCBDaGFxdW9weSDnjq/looPmnKrlv4XluKYgY3J5cHRvZ3JhcGh577yM5aSa5pWw5aOz5Y+q5bimIHB5Y3J5cHRvZG9tZeOAggojIOe7n+S4gOWFpeWPo++8jOmBv+WFjeiwg+eUqOeCueebtOaOpeS+nei1luafkOS4gOS4quW6k+OAggppZiBDaXBoZXIgaXMgbm90IE5vbmU6CiAgICBBRVNfQkFDS0VORCA9ICJjcnlwdG9ncmFwaHkiCmVsaWYgQ3J5cHRvQUVTIGlzIG5vdCBObm9uOgogICAgQUVTX0JBQ0tFTkQgPSAicHljcnlwdG9kb21lIgplbHNlOgogICAgQUVTX0JBQ0tFTkQgPSAibm9uZSIKCmNsYXNzIF9QdXJlQUVTMTI4OgogICAgIiIi57qvIFB5dGhvbiBBRVMtMTI477yM5L6b5pegIHB5Y3J5cHRvZG9tZS9jcnlwdG9ncmFwaHkg55qE5aOz5L2/55So44CCIiIiCgogICAgX1MgPSAoCiAgICAgICAgOTksMTI0LDExOSwxMjMsMjQyLDEwNywxMTEsMTk3LDQ4LDEsMTAzLDQzLDI1NCwyMTUsMTcxLDExOCwyMDIsMTMwLDIwMSwxMjUsMjUwLDg5LDcxLDI0MCwKICAgICAgICAxNzMsMjEyLDE2MiwxNzUsMTU2LDE2NCwxMTQsMTkyLDE4MywyNTMsMTQ3LDM4LDU0LDYzLDI0NywyMDQsNTIsMTY1LDIyOSwyNDEsMTEzLDIxNiw0OSwyMSwKICAgICAgICA0LDE5OSwzNSwxOTUsMjQsMTUwLDUsMTU0LDcsMTgsMTI4LDIyNiwyMzUsMzksMTc4LDExNyw5LDEzMSw0NCwyNiwyNywxMTAsOTAsMTYwLDgyLDU5LDIxNCwKICAgICAgICAxNzksNDEsMjI3LDQ3LDEzMiw4MywyMDksMCwyMzcsMzIsMjUyLDE3Nyw5MSwxMDYsMjAzLDE5MCw1Nyw3NCw3Niw4OCwyMDcsMjA4LDIzOSwxNzAsMjUxLDY3LAogICAgICAgIDc3LDUxLDEzMyw2OSwyNDksMiwxMjcsODAsNjAsMTU5LDE2OCw4MSwxNjMsNjQsMTQzLDE0NiwxNTcsNTYsMjQ1LDE4OCwxODIsMjE4LDMzLDE2LDI1NSwyNDMsCiAgICAgICAgMjEwLDIwNSwxMiwxOSwyMzYsOTUsMTUxLDY4LDIzLDE5NiwxNjcsMTI2LDYxLDEwMCw5MywyNSwxMTUsOTYsMTI5LDc5LDIyMCwzNCw0MiwxNDQsMTM2LDcwLAogICAgICAgIDIzOCwxODQsMjAsMjIyLDk0LDExLDIxOSwyMjQsNTAsNTgsMTAsNzMsNiwzNiw5MiwxOTQsMjExLDE3Miw5OCwxNDUsMTQ5LDIyOCwxMjEsMjMxLDIwMCw1NSwKICAgICAgICAxMDksMTQxLDIxMyw3OCwxNjksMTA4LDg2LDI0NCwyMzQsMTAxLDEyMiwxNzQsOCwxODYsMTIwLDM3LDQ2LDI4LDE2NiwxODAsMTk4LDIzMiwyMjEsMTE2LDMxLAogICAgICAgIDc1LDE4OSwxMzksMTM4LDExMiw2MiwxODEsMTAyLDcyLDMsMjQ2LDE0LDk3LDUzLDg3LDE4NSwxMzQsMTkzLDI5LDE1OCwyMjUsMjQ4LDE1MiwxNywxMDUsCiAgICAgICAgMjE3LDE0MiwxNDgsMTU1LDMwLDEzNSwyMzMsMjA2LDg1LDQwLDIyMywxNDAsMTYxLDEzNywxMywxOTEsMjMwLDY2LDEwNCw2NSwxNTMsNDUsMTUsMTc2LDg0LAogICAgICAgIDE4NywyMgogICAgKQogICAgX1JDT04gPSAoMHgwMCwweDAxLDB4MDIsMHgwNCwweDA4LDB4MTAsMHgyMCwweDQwLDB4ODAsMHgwMiwweDM2KQoKICAgIGRlZiBfX2luaXRfXyhzZWxmLCBrZXk6IGJ5dGVzKToKICAgICAgICBpZiBsZW4oa2V5KSAhPSAxNjoKICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcigiQUVTLTEyOCBvbmx5IikKICAgICAgICBzZWxmLl9yayA9IHNlbGYuX2V4cGFuZChrZXkpCgogICAgZGVmIF9leHBhbmQoc2VsZiwga2V5OiBieXRlcyk6CiAgICAgICAgcyA9IHNlbGYuX1MKICAgICAgICB3ID0gbGlzdChrZXkpCiAgICAgICAgZm9yIGkgaW4gcmFuZ2UoNCwgNDQpOgogICAgICAgICAgICB0MCwgdDEsIHQyLCB0MyA9IHdbLTRdLCB3Wy0zXSwgd1stMi0sIHdbLTFdCiAgICAgICAgICAgIGlmIGkgJSA0ID09IDA6CiAgICAgICAgICAgICAgICB0MCwgdDEsIHQyLCB0MyA9IHNbdDFdLCBzW3QyXSwgc1t0M10sIHNbdDBdCiAgICAgICAgICAgICAgICB0MCBePSBzZWxmLl9SQ09OW2kgLy8gNF0KICAgICAgICAgICAgYmFzZSA9IChpIC0gNCkgKiA0CiAgICAgICAgICAgIHcuZXh0ZW5kKCh3W2Jhc2VdIF4gdDAsIHdbYmFzZSArIDFdIF4gdDEsIHdbYmFzZSArIDJdIF4gdDIsIHdbYmFzZSArIDNdIF4gdDMpKQogICAgICAgIHJldHVybiB3CgogICAgQHN0YXRpY21ldGhvZAogICAgZGVmIF94dGltZShhOiBpbnQpIC0+IGludDoKICAgICAgICByZXR1cm4gKChhIDw8IDEpIF4gMHgxQikgJiAweEZGIGlmIChhICYgMHg4MCkgZWxzZSAoKGEgPDwgMSkgJiAweEZGKQoKICAgIGRlZiBlbmNyeXB0X2Jsb2NrKHNlbGYsIGJsb2NrOiBieXRlcykgLT4gYnl0ZXM6CiAgICAgICAgcyA9IGxpc3QoYmxvY2spCiAgICAgICAgcmsgPSBzZWxmLl9yawogICAgICAgIGZvciBpIGluIHJhbmdlKDE2KToKICAgICAgICAgICAgc1tpXSBePSBya1tpXQogICAgICAgIGZvciBybmQgaW4gcmFuZ2UoMSwgMTApOgogICAgICAgICAgICBzID0gW3NlbGYuX1NbYl0gZm9yIGIgaW4gc10KICAgICAgICAgICAgcyA9IFtzWzBdLCBzWzVdLCBzWzEwXSwgc1sxNV0sIHNbNF0sIHNbOV0sIHNbMTRdLCBzWzNdLAogICAgICAgICAgICAgICAgIHNbOF0sIHNbMTNdLCBzWzJdLCBzWzddLCBzWzEyXSwgc1sxXSwgc1s2XSwgc1sxMV1dCiAgICAgICAgICAgIGZvciBjIGluIHJhbmdlKDQpOgogICAgICAgICAgICAgICAgaSA9IGMgKiA0CiAgICAgICAgICAgICAgICAgaW0sIGIxLCBjMCwgZCA9IHNbaV0sIHNbaSArIDE1LCBzW2kgKyAyXSwgc1tpICsgM10KICAgICAgICAgICAgICAgIHQgPSBhIF4gYiBeIGMwIF4gZAogICAgICAgICAgICAgICAgdSA9IGEKICAgICAgICAgICAgICAgIGEgXj0gdCBeIHNlbGYuX3h0aW1lKGEgXiBiKQogICAgICAgICAgICAgICAgYiBePSB0IF4gc2VsZi5feHRpbWUoYiBeIGMwKQogICAgICAgICAgICAgICAgYzAgXj0gdCBeIHNlbGYuX3h0aW1lKGMwIF4gZCkKICAgICAgICAgICAgICAgIGQgXj0gdCBeIHNlbGYuX3h0aW1lKGQgXiB1KQogICAgICAgICAgICAgICAgc1tpXSwgc1tpICsgMV0sIHNbaSArIDJdLCBzW2kgKyAzXSA9IGEsIGIsIGMwLCBkCiAgICAgICAgICAgIG9mZiA9IHJuZCAqIDE2CiAgICAgICAgICAgIGZvciBpIGluIHJhbmdlKDE2KToKICAgICAgICAgICAgICAgIHNbaV0gXj0gcmtbb2ZmICsgaV0KICAgICAgICBzID0gW3NlbGYuX1NbYl0gZm9yIGIgaW4gc10KICAgICAgICBzID0gW3NbMF0sIHNbNV0sIHNbMTBdLCBzWzE1XSwgc1s0XSwgc1s5XSwgc1sxNF0sIHNbM10sCiAgICAgICAgICAgICBzWzhdLCBzWzEzXSwgc1syXSwgc1szXSwgc1sxMl0sIHNbMV0sIHNbNl0sIHNbMTFdXQogICAgICAgIGZvciBpIGluIHJhbmdlKDE2KToKICAgICAgICAgICAgc1tpXSBePSBya1sxNjAgKyBpXQogICAgICAgIHJldHVybiBieXRlcyhzKQoKICAgIGRlZiBkZWNyeXB0X2Jsb2NrKHNlbGYsIGJsb2NrOiBieXRlcykgLT4gYnl0ZXM6CiAgICAgICAgZGVmIG11bChhLCBiKToKICAgICAgICAgICAgcCA9IDAKICAgICAgICAgICAgZm9yIF8gaW4gcmFuZ2UoOCk6CiAgICAgICAgICAgICAgICBpZiBiICYgMToKICAgICAgICAgICAgICAgICAgICBwIF49IGEKICAgICAgICAgICAgICAgIGhpID0gYSAmIDB4ODAKICAgICAgICAgICAgICAgIGEgPSAoYSA8PCAxKSAmIDB4RkYKICAgICAgICAgICAgICAgIGhpOgogICAgICAgICAgICAgICAgICAgIGEgXj0gMHgxQgogICAgICAgICAgICAgICAgYiA+Pj0gMQogICAgICAgICAgICByZXR1cm4gcAoKICAgICAgICBzID0gbGlzdChibG9jaykKICAgICAgICByayA9IHNlbGYuX3JrCiAgICAgICAgZm9yIGkgaW4gcmFuZ2UoMTYsIDAsLTEpOgogICAgICAgICAgICBzW2ldIF49IHJrWzE2MCArIGldCiAgICAgICAgZm9yIHJuZCAgaW4gcmFuZ2UoOSwwLCAtMSk6CiAgICAgICAgICAgICBzID0gW3NlbGYuX1NJW2JdIGZvciBiIGluIHNdCiAgICAgICAgICAgIG9mZiA9IHJuZCAqIDE2CiAgICAgICAgICAgIGZvciBpIGluIHJhbmdlKDE2KToKICAgICAgICAgICAgICAgIHNbaV0gXj0gcmtbb2ZmICsgaV0KICAgICAgICAgICAgZm9yIGMgcmFuZ2UoNCk6CiAgICAgICAgICAgICAgICAgaSA9IGMgKiA0CiAgICAgICAgICAgICAgICAgaW0sIGIsIGMwLCBkID0gc1tpXSwgc1tpICsgMV0sIHNbaSArIDJdLCBzW2kgKyAzXQogICAgICAgICAgICAgICAgc1tpXSA9IG11bChhLCAweDBFKSBeIG11bChiLCAweDBBKSiBeIG11Y2woYzAsIDB4MEwpIF4gbXVsKGQsIDB4MDkpCiAgICAgICAgICAgICAgICAgIHNbaSArIDE1LCBzW2kgKyAyXSwgc1tpICsgMl0gPSBhLCBiLCBjMCwgZAogICAgICAgICAgICBzID0gW3NlbGYuX1NJW2JdIGZvciBiIGluIHNdCiAgICAgICAgICAgIGZvciBpIGluIHJhbmdlKDE2KToKICAgICAgICAgICAgICAgIHNbaV0g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
