# -*- coding: utf-8 -*-
import gzip
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import uuid

try:
    sys.path.append("..")
    from base.spider import BaseSpider
except Exception:
    class BaseSpider:
        pass

try:
    import requests as _requests
except Exception:
    _requests = None

# ---------------------------------------------------------------------------
# AES (FIPS-197) pure-python fallback; pycryptodome is used when available.
# ---------------------------------------------------------------------------
def _aes_tables():
    exp = [0] * 512
    log = [0] * 256
    x = 1
    for i in range(255):
        exp[i] = x
        log[x] = i
        x ^= ((x << 1) & 0xFF) ^ (0x1B if x & 0x80 else 0)
        x &= 0xFF
    for i in range(255, 512):
        exp[i] = exp[i - 255]
    sbox = [0] * 256
    inv = [0] * 256
    for i in range(256):
        ii = 0 if i == 0 else exp[255 - log[i]]
        s = ii
        s ^= ((ii << 1) | (ii >> 7)) & 0xFF
        s ^= ((ii << 2) | (ii >> 6)) & 0xFF
        s ^= ((ii << 3) | (ii >> 5)) & 0xFF
        s ^= ((ii << 4) | (ii >> 4)) & 0xFF
        s = (s ^ 0x63) & 0xFF
        sbox[i] = s
        inv[s] = i
    return exp, log, sbox, inv


_EXP, _LOG, _SBOX, _INV_SBOX = _aes_tables()
_RCON = [0, 1, 2, 4, 8, 16, 32, 64, 128, 27, 54, 108, 216, 171, 77]


def _gmul(a, b):
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _expand_key(key):
    nk = len(key) // 4
    nr = nk + 6
    w = [list(key[i * 4:(i + 1) * 4]) for i in range(nk)]
    for i in range(nk, 4 * (nr + 1)):
        t = list(w[i - 1])
        if i % nk == 0:
            t = [_SBOX[t[1]] ^ _RCON[i // nk], _SBOX[t[2]], _SBOX[t[3]], _SBOX[t[0]]]
        elif nk > 6 and i % nk == 4:
            t = [_SBOX[c] for c in t]
        w.append([w[i - nk][j] ^ t[j] for j in range(4)])
    rk = bytes(w[r * 4 + c][row] for r in range(nr + 1) for c in range(4) for row in range(4))
    return rk, nr


def _enc_block(blk, rk, nr):
    s = [blk[i] ^ rk[i] for i in range(16)]
    for rnd in range(1, nr + 1):
        s = [_SBOX[b] for b in s]
        s = [s[r + 4 * ((c + r) % 4)] for c in range(4) for r in range(4)]
        if rnd < nr:
            out = [0] * 16
            for c in range(4):
                a = s[4 * c:4 * c + 4]
                out[4 * c + 0] = _gmul(a[0], 2) ^ _gmul(a[1], 3) ^ a[2] ^ a[3]
                out[4 * c + 1] = a[0] ^ _gmul(a[1], 2) ^ _gmul(a[2], 3) ^ a[3]
                out[4 * c + 2] = a[0] ^ a[1] ^ _gmul(a[2], 2) ^ _gmul(a[3], 3)
                out[4 * c + 3] = _gmul(a[0], 3) ^ a[1] ^ a[2] ^ _gmul(a[3], 2)
            s = out
        base = rnd * 16
        s = [s[i] ^ rk[base + i] for i in range(16)]
    return bytes(s)


def _dec_block(blk, rk, nr):
    base = nr * 16
    s = [blk[i] ^ rk[base + i] for i in range(16)]
    for rnd in range(nr - 1, -1, -1):
        s2 = [0] * 16
        for c in range(4):
            for r in range(4):
                s2[r + 4 * c] = s[r + 4 * ((c - r) % 4)]
        s = [_INV_SBOX[b] for b in s2]
        base = rnd * 16
        s = [s[i] ^ rk[base + i] for i in range(16)]
        if rnd > 0:
            out = [0] * 16
            for c in range(4):
                a = s[4 * c:4 * c + 4]
                out[4 * c + 0] = _gmul(a[0], 14) ^ _gmul(a[1], 11) ^ _gmul(a[2], 13) ^ _gmul(a[3], 9)
                out[4 * c + 1] = _gmul(a[0], 9) ^ _gmul(a[1], 14) ^ _gmul(a[2], 11) ^ _gmul(a[3], 13)
                out[4 * c + 2] = _gmul(a[0], 13) ^ _gmul(a[1], 9) ^ _gmul(a[2], 14) ^ _gmul(a[3], 11)
                out[4 * c + 3] = _gmul(a[0], 11) ^ _gmul(a[1], 13) ^ _gmul(a[2], 9) ^ _gmul(a[3], 14)
            s = out
    return bytes(s)


def _aes_cbc_encrypt(key, iv, data):
    try:
        from Crypto.Cipher import AES as _AES
        return _AES.new(key, _AES.MODE_CBC, iv).encrypt(data)
    except Exception:
        rk, nr = _expand_key(key)
        out = b""
        prev = iv
        for i in range(0, len(data), 16):
            blk = bytes(a ^ b for a, b in zip(data[i:i + 16], prev))
            enc = _enc_block(blk, rk, nr)
            out += enc
            prev = enc
        return out


def _aes_cbc_decrypt(key, iv, data):
    try:
        from Crypto.Cipher import AES as _AES
        return _AES.new(key, _AES.MODE_CBC, iv).decrypt(data)
    except Exception:
        rk, nr = _expand_key(key)
        out = b""
        prev = iv
        for i in range(0, len(data), 16):
            blk = data[i:i + 16]
            dec = _dec_block(blk, rk, nr)
            out += bytes(a ^ b for a, b in zip(dec, prev))
            prev = blk
        return out


def _pkcs7_pad(data):
    pad = 16 - (len(data) % 16)
    return data + bytes([pad]) * pad


def _pkcs7_unpad(data):
    if not data:
        return data
    pad = data[-1]
    if 1 <= pad <= 16 and len(data) >= pad:
        return data[:-pad]
    return data


# ---------------------------------------------------------------------------
# Site profile
# ---------------------------------------------------------------------------
SITE_NAME = "黄豆短剧"
BASES = [
    "https://cocoaview.cc",
    "https://momodrift.top",
    "https://nbsito.top",
    "https://tideember.cc",
    "https://zuzuspot.top",
]
UA = ("Mozilla/5.0 (iPhone15,2; CPU iPhone OS 17_4 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1")
_HMAC_KEY = b"7961beb44246e3012ce228d6b5ced05a"
_SESSION_ID = "51258db574bc44a3b7e7da1dcce1c54f"
_PLAY_TOKEN = "U_763090d1a87b862df53554d778777bd6"
PAGE_SIZE = 12

CATEGORIES = [
    ("246506", "独家原创"),
    ("1050905", "综艺"),
    ("900012", "黑料"),
    ("246502", "魔改短剧"),
    ("1050902", "AI漫剧"),
    ("817201", "二次元"),
    ("246505", "擦边短剧"),
    ("817202", "真人短剧"),
]
CAT_NAME = dict(CATEGORIES)
PAY_TAG = {"money": "[付费]", "vip": "[VIP]"}


def _derive_key(uid_str):
    raw = bytes.fromhex(uid_str.replace("-", ""))
    return hmac.new(_HMAC_KEY, raw, hashlib.sha256).digest()


class Spider(BaseSpider):
    def __init__(self):
        self._base_idx = 0
        self._detail_cache = {}

    # -- contract basics ----------------------------------------------------
    def getName(self, *args, **kwargs):
        return SITE_NAME

    def getDependence(self, *args, **kwargs):
        return []

    def init(self, extend=None, *args, **kwargs):
        cfg = extend
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}
        if isinstance(cfg, dict):
            base = cfg.get("base") or cfg.get("host")
            if base:
                base = str(base).rstrip("/")
                if base in BASES:
                    self._base_idx = BASES.index(base)
                else:
                    BASES.insert(0, base)
                    self._base_idx = 0
        return {}

    def destroy(self, *args, **kwargs):
        return {}

    def action(self, action=None, value=None, *args, **kwargs):
        return {}

    # -- transport ----------------------------------------------------------
    def _base(self):
        return BASES[self._base_idx % len(BASES)]

    def _http_post(self, url, body, headers, timeout=20):
        if _requests is not None:
            try:
                resp = _requests.post(url, data=body, headers=headers, timeout=timeout)
                return resp.status_code, resp.content
            except Exception:
                _requests_failed = True
        req = urllib.request.Request(url, data=body, method="POST")
        for k, v in headers.items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def _http_get(self, url, headers=None, timeout=20):
        hdrs = {"User-Agent": UA}
        if headers:
            hdrs.update(headers)
        if _requests is not None:
            try:
                resp = _requests.get(url, headers=hdrs, timeout=timeout)
                return resp.status_code, resp.content
            except Exception:
                _requests_failed = True
        req = urllib.request.Request(url, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def _api(self, path, fields):
        """Encrypted-envelope POST; rotates base candidates on failure."""
        last_err = None
        for attempt in range(len(BASES)):
            base = BASES[(self._base_idx + attempt) % len(BASES)]
            try:
                result = self._api_once(base, path, fields)
                if result is not None:
                    self._base_idx = (self._base_idx + attempt) % len(BASES)
                    return result
            except Exception as e:
                last_err = e
        if last_err is not None:
            raise last_err
        return {}

    def _api_once(self, base, path, fields):
        uid = str(uuid.uuid4())
        ts = str(int(time.time()))
        token = _PLAY_TOKEN if "/api/drama/play" in path else ""
        data_json = json.dumps(fields, ensure_ascii=False, separators=(",", ":"))
        envelope = '{"token":"%s","deviceId":"%s","data":%s}' % (token, uid, data_json)
        key = _derive_key(uid)
        iv = os.urandom(16)
        body = iv + _aes_cbc_encrypt(key, iv, _pkcs7_pad(gzip.compress(envelope.encode("utf-8"))))
        url = base + path
        stripped = url.replace("https://", "").replace("http://", "")
        sign_src = "Dart|%s|%s|%s|%s" % (_SESSION_ID, uid, ts, stripped)
        sign = hashlib.md5(sign_src.encode("utf-8")).hexdigest() + "-" + ts
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "version": "1.0.0",
            "deviceType": "web",
            "time": ts,
            "requestId": uid,
            "sessionId": _SESSION_ID,
            "user-agent": UA,
            "sign": sign,
        }
        code, raw = self._http_post(url, body, headers, timeout=20)
        if not raw:
            return None
        if len(raw) >= 2 and raw[0] == 0x7B and raw[1] in (0x22, 0x7D):
            obj = json.loads(raw.decode("utf-8"))
        else:
            plain = _pkcs7_unpad(_aes_cbc_decrypt(key, raw[:16], raw[16:]))
            obj = json.loads(gzip.decompress(plain).decode("utf-8"))
        if not isinstance(obj, dict) or obj.get("status") != "y":
            return None
        return obj

    # -- mapping helpers ------------------------------------------------------
    def _card(self, item):
        name = str(item.get("name") or "")
        pay = str(item.get("pay_type") or "free")
        remark = str(item.get("update_label") or "")
        tag = PAY_TAG.get(pay, "")
        if tag:
            remark = (remark + " " + tag).strip() if remark else tag
        return {
            "vod_id": str(item.get("id") or ""),
            "vod_name": name,
            "vod_pic": str(item.get("img") or item.get("img_y") or ""),
            "vod_remarks": remark,
        }

    def _list_page(self, fields, pg):
        obj = self._api("/api/drama/list", fields)
        data = (obj or {}).get("data") or {}
        items = data.get("list") or []
        cards = [self._card(it) for it in items if it.get("id")]
        has_more = len(items) >= PAGE_SIZE
        pagecount = pg + 1 if has_more else pg
        return {
            "list": cards,
            "page": pg,
            "pagecount": pagecount,
            "limit": PAGE_SIZE,
            "total": len(cards) if not has_more else 9999,
        }

    @staticmethod
    def _pg(pg):
        try:
            p = int(pg)
        except Exception:
            p = 1
        return p if p >= 1 else 1

    # -- TVBox surface --------------------------------------------------------
    def homeContent(self, filter=None, *args, **kwargs):
        classes = [{"type_id": cid, "type_name": name} for cid, name in CATEGORIES]
        home_list = []
        try:
            home_list = self.categoryContent(CATEGORIES[0][0], 1).get("list") or []
        except Exception:
            home_list = []
        return {"class": classes, "filters": {}, "list": home_list}

    def homeVideoContent(self, *args, **kwargs):
        return self.categoryContent(CATEGORIES[0][0], 1)

    def categoryContent(self, tid=None, pg=1, filter=None, extend=None, *args, **kwargs):
        page = self._pg(pg)
        tid = str(tid or CATEGORIES[0][0])
        fields = {"cat_id": tid, "order": "new:top", "page": str(page), "size": str(PAGE_SIZE)}
        try:
            return self._list_page(fields, page)
        except Exception:
            return {"list": [], "page": page, "pagecount": page, "limit": PAGE_SIZE, "total": 0}

    def _detail_data(self, iid):
        if iid in self._detail_cache:
            return self._detail_cache[iid]
        obj = self._api("/api/drama/detail", {"id": iid})
        data = (obj or {}).get("data") or {}
        if data:
            self._detail_cache[iid] = data
        return data

    @staticmethod
    def _free_episodes(data):
        out = []
        for ep in data.get("episodes") or []:
            try:
                price = int(ep.get("price") or 0)
            except Exception:
                price = 0
            if str(ep.get("type") or "") == "free" and price == 0:
                out.append(ep)
        out.sort(key=lambda e: int(e.get("seq") or 0))
        return out

    def detailContent(self, ids=None, *args, **kwargs):
        if ids is None:
            id_list = []
        elif isinstance(ids, (list, tuple)):
            id_list = [str(x) for x in ids]
        else:
            id_list = [s.strip() for s in str(ids).split(",") if s.strip()]
        out = []
        for iid in id_list:
            try:
                data = self._detail_data(iid)
            except Exception:
                data = {}
            if not data:
                continue
            free_eps = self._free_episodes(data)
            total_eps = data.get("episode_count") or len(data.get("episodes") or [])
            desc = str(data.get("description") or "")
            pay_note = ""
            if len(free_eps) < int(total_eps or 0):
                pay_note = ("本源仅提供免费集：全剧 %s 集，其中免费 %s 集，付费集未收录。"
                            % (total_eps, len(free_eps)))
            elif not free_eps:
                pay_note = "本剧暂无免费集，付费内容未收录。"
            if pay_note:
                desc = (desc + "\n" + pay_note).strip() if desc else pay_note
            play_parts = []
            for ep in free_eps:
                seq = ep.get("seq")
                label = str(ep.get("name") or ("第%s集" % seq))
                if not label.startswith("第"):
                    label = "第%s集" % seq
                ep_url = "%s/api/drama/hls/%s/%s/play.m3u8" % (self._base(), iid, seq)
                play_parts.append("%s$%s" % (label, ep_url))
            tags = data.get("tags") or []
            out.append({
                "vod_id": str(data.get("id") or iid),
                "vod_name": str(data.get("name") or ""),
                "vod_pic": str(data.get("img_y") or data.get("img_x") or ""),
                "vod_year": str(data.get("issue_date") or ""),
                "vod_area": "",
                "vod_actor": str(data.get("publisher") or ""),
                "vod_director": "",
                "type_name": str(data.get("category") or ""),
                "vod_remarks": str(data.get("update_label") or ""),
                "vod_content": desc,
                "vod_tag": ",".join(str(t) for t in tags),
                "vod_play_from": SITE_NAME,
                "vod_play_url": "#".join(play_parts),
            })
        return {"list": out}

    def searchContent(self, key=None, quick=False, pg=1, *args, **kwargs):
        page = self._pg(pg)
        kw = str(key or "").strip()
        if not kw:
            return {"list": [], "page": page, "pagecount": page, "limit": PAGE_SIZE, "total": 0}
        fields = {"page": str(page), "size": str(PAGE_SIZE), "keywords": kw}
        try:
            return self._list_page(fields, page)
        except Exception:
            return {"list": [], "page": page, "pagecount": page, "limit": PAGE_SIZE, "total": 0}

    def playerContent(self, flag=None, id=None, vipFlags=None, *args, **kwargs):
        headers = {"User-Agent": UA, "Referer": self._base() + "/"}
        raw = str(id or "")
        if "$" in raw:
            raw = raw.rsplit("$", 1)[-1]
        iid, seq = "", "1"
        marker = "/api/drama/hls/"
        if marker in raw:
            tail = raw.split(marker, 1)[1].split("?")[0].strip("/")
            bits = tail.split("/")
            if len(bits) >= 2:
                iid, seq = bits[0], bits[1]
        elif "@@" in raw:
            iid, seq = raw.split("@@", 1)
        else:
            iid = raw
        iid = iid.strip()
        seq = str(seq).strip() or "1"
        ok = False
        try:
            data = self._detail_data(iid)
            for ep in self._free_episodes(data):
                if str(ep.get("seq")) == seq:
                    ok = True
                    break
        except Exception:
            ok = False
        if not ok:
            return {"parse": 0, "playUrl": "", "url": "", "header": headers}
        url = "%s/api/drama/hls/%s/%s/play.m3u8" % (self._base(), iid, seq)
        return {"parse": 0, "playUrl": "", "url": url, "header": headers}

    def localProxy(self, param=None, *args, **kwargs):
        try:
            url = ""
            if isinstance(param, dict):
                url = str(param.get("url") or param.get("u") or "")
            elif isinstance(param, str):
                url = param
            if not url.startswith("http"):
                return [404, "text/plain", "", {}]
            code, body = self._http_get(url, timeout=20)
            mime = "application/vnd.apple.mpegurl" if ".m3u8" in url else "application/octet-stream"
            return [int(code or 200), mime, body, {}]
        except Exception:
            return [500, "text/plain", "", {}]

    def isVideoFormat(self, url=None, *args, **kwargs):
        u = str(url or "").lower()
        return (".m3u8" in u) or (".mp4" in u) or (".ts" in u)

    def manualVideoCheck(self, *args, **kwargs):
        return False
