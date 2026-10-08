# -*- coding: utf-8 -*-
import os
import re
import json
import time
import base64
import html as _html
from urllib.parse import quote, unquote, urljoin

try:
    import requests
except ImportError:
    requests = None


HOST = "https://www.javbus.casa"
HOST_UC = HOST + "/uncensored"
IMG_HOST = HOST

PAGE_SIZE = 30
SEARCH_LIMIT = 30

WEB_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

LIST_HEADERS = {
    "User-Agent": WEB_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,ja;q=0.8,en;q=0.7",
    "Referer": HOST + "/",
}

AJAX_HEADERS = {
    "User-Agent": WEB_UA,
    "Accept": "text/html, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9,ja;q=0.8,en;q=0.7",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": HOST + "/",
}

JAVBUS_CLASSES = [
    {"type_id": "jav_home",               "type_name": "有碼"},
    {"type_id": "jav_uncensored",          "type_name": "無碼"},
    {"type_id": "jav_genre",              "type_name": "有碼類別"},
    {"type_id": "jav_uncensored_genre",   "type_name": "無碼類別"},
    {"type_id": "jav_actress",            "type_name": "有碼女優"},
    {"type_id": "jav_uncensored_actress", "type_name": "無碼女優"},
]

# 女优筛选最多显示多少个
STAR_FILTER_LIMIT = 50

# ============ 115 常量（复用片商库av.py） ============
DEFAULT_COOKIE = ("")

OFF_PREFIX_115 = "http://115off/"
OFFLINE_UA = WEB_UA + " 115Browser/36.0.0"
OFFLINE_ADD_API = "https://115.com/web/lixian/?ct=lixian&ac=add_task_urls"
OFFLINE_LIST_API = "https://115.com/web/lixian/?ct=lixian&ac=task_lists"
OFFLINE_POLL_TIMEOUT = 25
OFFLINE_POLL_INTERVAL = 1

RSA_N = 0x8686980c0f5a24c4b9d43020cd2c22703ff3f450756529058b1cf88f09b8602136477198a6e2683149659bd122c33592fdb5ad47944ad1ea4d36c6b172aad6338c3bb6ac6227502d010993ac967d1aef00f0c8e038de2e4d3bc2ec368af2e9f10a6f1eda4f7262f136420c07c331b871bf139f74f3010e3c4fe57df3afb71683
RSA_E = 0x10001
KEY_TABLE = bytes([
    240, 229, 105, 174, 191, 220, 191, 138, 26, 69, 232, 190, 125, 166, 115, 184,
    222, 143, 231, 196, 69, 218, 134, 196, 155, 100, 139, 20, 106, 180, 241, 170,
    56, 1, 53, 158, 38, 105, 44, 134, 0, 107, 79, 165, 54, 52, 98, 166,
    42, 150, 104, 24, 242, 74, 253, 189, 107, 151, 143, 77, 143, 137, 19, 183,
    108, 142, 147, 237, 14, 13, 72, 62, 215, 47, 136, 216, 254, 254, 126, 134,
    80, 149, 79, 209, 235, 131, 38, 52, 219, 102, 123, 156, 126, 157, 122, 129,
    50, 234, 182, 51, 222, 58, 169, 89, 52, 102, 59, 170, 186, 129, 96, 72,
    185, 213, 129, 156, 248, 108, 132, 119, 255, 84, 120, 38, 95, 190, 232, 30,
    54, 159, 52, 128, 92, 69, 44, 155, 118, 213, 27, 143, 204, 195, 184, 245,
])


def _env(name, default=""):
    try:
        return os.environ.get(name, default) or default
    except Exception:
        return default


def _to_text(v):
    return str(v or "").strip()


def _safe_json(text, fallback=None):
    try:
        return json.loads(str(text or ""))
    except Exception:
        return fallback if fallback is not None else {}


def _safe_int(v, default=0):
    try:
        return int(v)
    except Exception:
        try:
            return int(str(v or "").strip() or default)
        except Exception:
            return default


def _fix_url(url, host=HOST):
    if not url:
        return ""
    url = _to_text(url)
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return urljoin(host.rstrip("/") + "/", url)


def _clean_text(s):
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", "", str(s))
    s = _html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _normalize_magnet(magnet):
    if not magnet:
        return ""
    m = re.search(r"btih:([0-9a-fA-F]{40}|[0-9a-zA-Z]{32})", magnet)
    if not m:
        return magnet
    return "magnet:?xt=urn:btih:" + m.group(1)


def _extract_id(url):
    if not url:
        return ""
    m = re.search(r"/([A-Za-z0-9_\-\.]+)/?$", url)
    return m.group(1) if m else ""


def _size_mb(mb):
    try:
        mb = float(mb or 0)
    except Exception:
        return ""
    if mb <= 0:
        return ""
    if mb >= 1024:
        return "%.1fG" % (mb / 1024.0)
    return "%dM" % int(mb)


# ==================== 115 加密工具 ====================

def _chunks(start, end, step=1):
    out = []
    nxt = start + step
    while nxt < end:
        out.append((start, nxt))
        start = nxt
        nxt += step
    if start != end:
        out.append((start, end))
    return out


def _bytes_to_int(b):
    out = 0
    for byte in b:
        out = (out << 8) | byte
    return out


def _int_to_bytes(value, length=None):
    if length is None:
        length = max(1, (value.bit_length() + 7) // 8)
    out = bytearray(length)
    for i in range(length - 1, -1, -1):
        out[i] = value & 0xFF
        value >>= 8
    return bytes(out)


def _xor_bytes(a, b):
    return bytes(x ^ y for x, y in zip(a, b))


def _xor_by_key(input_bytes, key):
    out = bytearray(len(input_bytes))
    head = len(input_bytes) & 3
    if head:
        out[0:head] = _xor_bytes(input_bytes[0:head], key[0:head])
    for (f, t) in _chunks(head, len(input_bytes), len(key)):
        seg = input_bytes[f:t]
        klen = len(key)
        for i in range(len(seg)):
            out[f + i] = seg[i] ^ key[i % klen]
    return bytes(out)


def _mod_pow(base, exp, mod):
    if mod == 1:
        return 0
    result = 1
    base %= mod
    while exp:
        if exp & 1:
            result = (result * base) % mod
        exp >>= 1
        base = (base * base) % mod
    return result


def _encode_block(input_bytes):
    block = bytearray(128)
    fill_end = 127 - len(input_bytes)
    for i in range(1, max(1, fill_end)):
        block[i] = 2
    block[0] = 0
    block[128 - len(input_bytes):128] = input_bytes
    return _bytes_to_int(bytes(block))


def _table_key(seed, length):
    out = bytearray(length)
    n = length * (length - 1)
    s = 0
    for i in range(length):
        mixed = (seed[i] + KEY_TABLE[s]) & 255
        out[i] = KEY_TABLE[n] ^ mixed
        n -= length
        s += length
    return bytes(out)


def _encrypt_payload(value):
    input_bytes = value.encode("utf-8") if isinstance(value, str) else bytes(value)
    step1 = _xor_by_key(input_bytes, bytes([141, 165, 165, 141]))
    step2 = step1[::-1]
    step3 = _xor_by_key(step2, bytes([120, 6, 173, 76, 51, 134, 93, 24, 76, 1, 63, 70]))
    padded = bytes(16) + step3
    blocks = _chunks(0, len(padded), 117)
    out = bytearray(len(blocks) * 128)
    pos = 0
    for (f, t) in blocks:
        enc = _mod_pow(_encode_block(padded[f:t]), RSA_E, RSA_N)
        out[pos:pos + 128] = _int_to_bytes(enc, 128)
        pos += 128
    return base64.b64encode(bytes(out)).decode("ascii")


def _decrypt_payload(value):
    raw = base64.b64decode(value)
    merged = bytearray()
    for (f, t) in _chunks(0, len(raw), 128):
        dec = _int_to_bytes(_mod_pow(_bytes_to_int(raw[f:t]), RSA_E, RSA_N))
        idx = dec.find(b"\x00")
        merged.extend(dec[idx + 1:] if idx >= 0 else dec)
    if len(merged) < 16:
        return ""
    seed = merged[0:16]
    key = _table_key(seed, 12)
    body = _xor_by_key(merged[16:], key)[::-1]
    plain = _xor_by_key(body, bytes([141, 165, 165, 141]))
    try:
        return plain.decode("utf-8")
    except Exception:
        return ""


def _build_downurl_body(payload_dict):
    enc = _encrypt_payload(json.dumps(payload_dict, separators=(",", ":")))
    return "data=" + quote(enc, safe="")


def _extract_encrypted(data):
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
        except Exception:
            return data, None
        return _extract_encrypted(parsed)
    if isinstance(data, dict):
        enc = ""
        d = data.get("data")
        if isinstance(d, str):
            enc = d
        elif isinstance(d, dict) and isinstance(d.get("data"), str):
            enc = d["data"]
        return enc, data
    return "", data


def _decode_downurl_response(data):
    enc, payload = _extract_encrypted(data)
    if not enc:
        return payload or {}
    try:
        return json.loads(_decrypt_payload(enc))
    except Exception:
        if isinstance(payload, dict):
            return payload
        raise


def _find_url_deep(obj):
    if not isinstance(obj, dict):
        return ""
    u = obj.get("url")
    if isinstance(u, str) and u:
        return u
    if isinstance(u, dict) and isinstance(u.get("url"), str) and u["url"]:
        return u["url"]
    d = obj.get("data")
    if isinstance(d, dict) and isinstance(d.get("url"), str) and d["url"]:
        return d["url"]
    for v in obj.values():
        hit = _find_url_deep(v)
        if hit:
            return hit
    return ""


def _find_msg_deep(obj):
    if not isinstance(obj, dict):
        return ""
    for key in ("msg", "message", "error"):
        v = obj.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    for v in obj.values():
        hit = _find_msg_deep(v)
        if hit:
            return hit
    return ""


def _set_cookie_text(set_cookie):
    if not set_cookie:
        return ""
    if isinstance(set_cookie, str):
        set_cookie = [set_cookie]
    return "; ".join(str(v).split(";")[0].strip() for v in set_cookie if str(v).split(";")[0].strip())


# ==================== Spider ====================

class Spider:
    def __init__(self):
        self.s = self.session = self.sess = None
        self.host = HOST
        self.host_uc = HOST_UC
        self.img_host = IMG_HOST
        self.ua = WEB_UA
        self.timeout = 15
        self.page_size = PAGE_SIZE
        self.search_limit = SEARCH_LIMIT
        self.enable_magnet = True
        self.enable_uncensored = True
        self.cookie = ""
        self.img_proxy = ""
        self.lang = "zh"

        # 115 配置
        self.cookie_115 = ""
        self.enable_offline_115 = True
        self.offline_save_path = "0"
        self.offline_app_ver = "4.8.2"
        self.offline_timeout = 15

        # filters / 默认值缓存
        self._cache_filters = {}

        if requests:
            self.s = self.session = self.sess = requests.Session()
            self.s.headers.update(LIST_HEADERS)

    def getDependence(self):
        return []

    def init(self, extend=""):
        if isinstance(extend, str) and extend.strip().startswith("{"):
            try:
                extend = json.loads(extend)
            except Exception:
                extend = {}
        if not isinstance(extend, dict):
            extend = {}

        if extend.get("host"):
            self.host = str(extend["host"]).rstrip("/")
            self.host_uc = self.host + "/uncensored"
            self.img_host = self.host
        if extend.get("img") or extend.get("imgProxy"):
            self.img_proxy = str(extend.get("img") or extend.get("imgProxy") or "").strip()
        if extend.get("cookie"):
            self.cookie = str(extend["cookie"])
        if extend.get("lang"):
            self.lang = str(extend["lang"])
        if "enableMagnet" in extend:
            self.enable_magnet = bool(extend["enableMagnet"])
        if "enableUncensored" in extend:
            self.enable_uncensored = bool(extend["enableUncensored"])

        # ==== 115 ====
        self.cookie_115 = (
            _to_text(extend.get("cookie115"))
            or _to_text(extend.get("cookie"))
            or _env("Y115_COOKIE")
            or _env("MY115_COOKIE")
            or DEFAULT_COOKIE
        )
        if "enableOffline115" in extend:
            self.enable_offline_115 = bool(extend["enableOffline115"])
        if extend.get("offlineSavePath"):
            self.offline_save_path = str(extend["offlineSavePath"])
        if extend.get("offlineAppVer"):
            self.offline_app_ver = str(extend["offlineAppVer"])

        # 清空缓存
        self._cache_filters = {}

    # ========== 首页分类 ==========
    def homeContent(self, filter=None):
        classes = []
        for c in JAVBUS_CLASSES:
            if c["type_id"] in ("jav_uncensored", "jav_uncensored_genre",
                                "jav_uncensored_actress") and not self.enable_uncensored:
                continue
            classes.append(dict(c))

        filters = {}
        for c in classes:
            tid = c["type_id"]
            if tid == "jav_genre":
                filters[tid] = self._build_genre_filters(self.host + "/genre")
            elif tid == "jav_uncensored_genre":
                filters[tid] = self._build_genre_filters(self.host + "/uncensored/genre")
            elif tid == "jav_actress":
                filters[tid] = self._build_star_filters(self.host + "/actresses")
            elif tid == "jav_uncensored_actress":
                filters[tid] = self._build_star_filters(self.host + "/uncensored/actresses")
        return {"class": classes, "filters": filters}

    # ---------- 类别筛选 ----------
    def _build_genre_filters(self, index_url):
        cache_key = "genre:" + index_url
        if cache_key in self._cache_filters:
            return self._cache_filters[cache_key]

        try:
            text = self._get_html(index_url)
        except Exception:
            return []

        groups = self._parse_genre_groups(text)
        out = []
        for gname, items in groups:
            if not items:
                continue
            values = [{"n": "全部", "v": ""}]
            for it in items:
                values.append({"n": it["name"], "v": it["gid"]})
            out.append({
                "key": "genre_" + gname,
                "name": gname,
                "init": "",
                "value": values,
            })

        self._cache_filters[cache_key] = out
        return out

    def _parse_genre_groups(self, text):
        groups = []
        h4_iter = list(re.finditer(r"<h4>([^<]+)</h4>", text))
        if not h4_iter:
            return groups

        for i, m in enumerate(h4_iter):
            gname = _clean_text(m.group(1))
            start = m.end()
            end = h4_iter[i + 1].start() if i + 1 < len(h4_iter) else len(text)
            block = text[start:end]

            items = []
            seen = set()
            for gb in re.finditer(
                r'<div[^>]+class="[^"]*genre-box[^"]*"[^>]*>(.*?)</div>',
                block, re.S
            ):
                inner = gb.group(1)
                for a in re.finditer(
                    r'<a[^>]+href="([^"]*?/genre/([^"/]+))"[^>]*>([^<]+)</a>',
                    inner
                ):
                    gid = a.group(2)
                    name = _clean_text(a.group(3))
                    if not gid or not name or gid in seen:
                        continue
                    seen.add(gid)
                    items.append({"gid": gid, "name": name})
            if items:
                groups.append((gname, items))
        return groups

    # ---------- 女优筛选 ----------
    def _build_star_filters(self, index_url):
        cache_key = "star:" + index_url
        if cache_key in self._cache_filters:
            return self._cache_filters[cache_key]

        try:
            text = self._get_html(index_url)
        except Exception:
            return []

        values = [{"n": "全部", "v": ""}]
        seen = set()
        for m in re.finditer(
            r'<a[^>]+class="[^"]*avatar-box[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            text, re.S
        ):
            href = _fix_url(m.group(1), self.host)
            block = m.group(2)
            sid = _extract_id(href)
            name = ""
            nm = re.search(r"<span>([^<]+)</span>", block)
            if nm:
                name = _clean_text(nm.group(1))
            if not sid or not name or sid in seen:
                continue
            seen.add(sid)
            values.append({"n": name, "v": sid})
            if len(values) > STAR_FILTER_LIMIT:
                break

        if len(values) <= 1:
            self._cache_filters[cache_key] = []
            return []

        out = [{
            "key": "star",
            "name": "女優",
            "init": "",
            "value": values,
        }]
        self._cache_filters[cache_key] = out
        return out

    # ---------- 默认值 ----------
    def _get_default_genre(self, index_url):
        cache_key = "default_genre:" + index_url
        if cache_key in self._cache_filters:
            return self._cache_filters[cache_key]

        try:
            text = self._get_html(index_url)
        except Exception:
            return ""

        groups = self._parse_genre_groups(text)
        for gname, items in groups:
            if items:
                gid = items[0]["gid"]
                self._cache_filters[cache_key] = gid
                return gid
        return ""

    def _get_default_star(self, index_url):
        cache_key = "default_star:" + index_url
        if cache_key in self._cache_filters:
            return self._cache_filters[cache_key]

        try:
            text = self._get_html(index_url)
        except Exception:
            return ""

        for m in re.finditer(
            r'<a[^>]+class="[^"]*avatar-box[^"]*"[^>]+href="([^"]+)"',
            text
        ):
            href = _fix_url(m.group(1), self.host)
            sid = _extract_id(href)
            if sid:
                self._cache_filters[cache_key] = sid
                return sid
        return ""

    def homeVideoContent(self):
        return {"list": []}

    # ========== 分类内容 ==========
    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        t = _to_text(tid)
        page = _safe_int(pg, 1)

        genre_sel = {}
        star_sel = {}
        for src in (filter, extend):
            if isinstance(src, dict):
                for k, v in src.items():
                    k = _to_text(k)
                    v = _to_text(v)
                    if not v:
                        continue
                    if k.startswith("genre_"):
                        genre_sel[v] = True
                    elif k == "star":
                        star_sel[v] = True

        if t == "jav_home":
            if page <= 1:
                return self._list_page(self.host + "/", page)
            return self._list_page(self.host + "/page/%d" % page, page)

        if t == "jav_uncensored":
            if page <= 1:
                return self._list_page(self.host + "/uncensored", page)
            return self._list_page(self.host + "/uncensored/page/%d" % page, page)

        if t == "jav_genre":
            if len(genre_sel) == 1:
                gid = list(genre_sel.keys())[0]
                return self._category_list(self.host + "/genre", gid, page)
            default_gid = self._get_default_genre(self.host + "/genre")
            if default_gid:
                return self._category_list(self.host + "/genre", default_gid, page)
            if page <= 1:
                return self._list_page(self.host + "/", page)
            return self._list_page(self.host + "/page/%d" % page, page)

        if t == "jav_uncensored_genre":
            if len(genre_sel) == 1:
                gid = list(genre_sel.keys())[0]
                return self._category_list(self.host + "/uncensored/genre", gid, page)
            default_gid = self._get_default_genre(self.host + "/uncensored/genre")
            if default_gid:
                return self._category_list(self.host + "/uncensored/genre", default_gid, page)
            if page <= 1:
                return self._list_page(self.host + "/uncensored", page)
            return self._list_page(self.host + "/uncensored/page/%d" % page, page)

        if t == "jav_actress":
            if len(star_sel) == 1:
                sid = list(star_sel.keys())[0]
                return self._star_list(self.host + "/star", sid, page)
            default_sid = self._get_default_star(self.host + "/actresses")
            if default_sid:
                return self._star_list(self.host + "/star", default_sid, page)
            if page <= 1:
                return self._list_page(self.host + "/", page)
            return self._list_page(self.host + "/page/%d" % page, page)

        if t == "jav_uncensored_actress":
            if len(star_sel) == 1:
                sid = list(star_sel.keys())[0]
                return self._star_list(self.host + "/uncensored/star", sid, page)
            default_sid = self._get_default_star(self.host + "/uncensored/actresses")
            if default_sid:
                return self._star_list(self.host + "/uncensored/star", default_sid, page)
            if page <= 1:
                return self._list_page(self.host + "/uncensored", page)
            return self._list_page(self.host + "/uncensored/page/%d" % page, page)

        if t.startswith("jav_genre_"):
            gid = t[len("jav_genre_"):]
            return self._category_list(self.host + "/genre", gid, page)

        if t.startswith("jav_uc_genre_"):
            gid = t[len("jav_uc_genre_"):]
            return self._category_list(self.host + "/uncensored/genre", gid, page)

        if t.startswith("jav_star_"):
            sid = t[len("jav_star_"):]
            return self._star_list(self.host + "/star", sid, page)

        if t.startswith("jav_uc_star_"):
            sid = t[len("jav_uc_star_"):]
            return self._star_list(self.host + "/uncensored/star", sid, page)

        return {"list": [], "page": page, "pagecount": 1,
                "limit": self.page_size, "total": 0}

    def _category_list(self, base, gid, page):
        if page <= 1:
            url = "%s/%s" % (base.rstrip("/"), gid)
        else:
            url = "%s/%s/%d" % (base.rstrip("/"), gid, page)
        return self._list_page(url, page)

    def _star_list(self, base, sid, page):
        if page <= 1:
            url = "%s/%s" % (base.rstrip("/"), sid)
        else:
            url = "%s/%s/%d" % (base.rstrip("/"), sid, page)
        return self._list_page(url, page)

    # ========== 列表页解析 ==========
    def _list_page(self, url, page):
        seen = set()
        out = []
        try:
            text = self._get_html(url)
        except Exception:
            return {"list": [], "page": page, "pagecount": 1,
                    "limit": self.page_size, "total": 0}

        for m in re.finditer(
            r'<a[^>]+class="[^"]*movie-box[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            text, re.S
        ):
            try:
                href = _fix_url(m.group(1), self.host)
                block = m.group(2)

                img = re.search(
                    r'<img[^>]*(?:src|data-src|data-original)=["\']([^"\']+)',
                    block, re.I
                )
                pic = _fix_url(img.group(1), self.host) if img else ""

                title = ""
                tm = re.search(r'<img[^>]+title="([^"]+)"', block, re.I)
                if tm:
                    title = _clean_text(tm.group(1))
                if not title:
                    tm = re.search(r"<span>([^<]+)", block)
                    if tm:
                        title = _clean_text(tm.group(1))

                num = ""
                dates = re.findall(r"<date>([^<]+)</date>", block)
                if dates:
                    num = _clean_text(dates[0])

                vid = _extract_id(href)
                if not vid or vid in seen:
                    continue
                seen.add(vid)

                out.append({
                    "vod_id": vid,
                    "vod_name": title or num or vid,
                    "vod_pic": pic,
                    "vod_remarks": num or "",
                })
            except Exception:
                continue

        has_next = bool(re.search(r'<a[^>]+id="next"[^>]+href="[^"]+"', text))
        if not has_next:
            pag = re.search(
                r'<ul[^>]+class="[^"]*pagination[^"]*"[^>]*>(.*?)</ul>',
                text, re.S
            )
            if pag:
                nums = [
                    _safe_int(x)
                    for x in re.findall(r'href="[^"]*?/(\d+)"', pag.group(1))
                ]
                nums = [n for n in nums if n > 0]
                if nums and max(nums) > page:
                    has_next = True

        return {
            "list": out,
            "page": page,
            "pagecount": page + 1 if has_next else page,
            "limit": self.page_size,
            "total": len(out),
        }

    # ========== 详情 ==========
    def detailContent(self, ids):
        vid = str(ids[0]) if isinstance(ids, (list, tuple)) and ids else str(ids or "")
        if not vid:
            return {"list": []}

        if vid.startswith(("jav_genre_", "jav_uc_genre_",
                           "jav_star_", "jav_uc_star_")):
            return {"list": []}

        url = _fix_url("/" + vid, self.host)
        try:
            text = self._get_html(url)
        except Exception:
            return {"list": []}

        title = ""
        tm = re.search(r"<title>([^<]+)</title>", text)
        if tm:
            title = _clean_text(tm.group(1)).replace(" - JavBus", "").strip()

        pic = ""
        pm = re.search(r'<a[^>]+class="bigImage"[^>]+href="([^"]+)"', text)
        if pm:
            pic = _fix_url(pm.group(1), self.host)
        if not pic:
            pm = re.search(r'<img[^>]+src="(/imgs/cover/[^"]+)"', text)
            if pm:
                pic = _fix_url(pm.group(1), self.host)
        if not pic:
            pm = re.search(r'<img[^>]+src="(/imgs/[^"]+\.jpg)"', text)
            if pm:
                pic = _fix_url(pm.group(1), self.host)
        pic = self._proxy_pic(pic)

        num = ""
        for pat in (
            r'識別碼:</span>\s*<span[^>]*>([^<]+)',
            r'識別碼[:：]\s*</span>\s*<span[^>]*>([^<]+)',
            r'<span[^>]*class="header"[^>]*>識別碼[:：]</span>\s*<span[^>]*>([^<]+)',
        ):
            nm = re.search(pat, text)
            if nm:
                num = _clean_text(nm.group(1))
                if num:
                    break

        date = ""
        for pat in (
            r'發行日期:</span>\s*([^<]+)',
            r'發行日期[:：]\s*</span>\s*([^<]+)',
            r'<span[^>]*class="header"[^>]*>發行日期[:：]</span>\s*([^<]+)',
        ):
            dm = re.search(pat, text)
            if dm:
                date = _clean_text(dm.group(1))
                if date:
                    break

        actors = re.findall(
            r'class="avatar-box"[^>]+href="[^"]+"[^>]*>\s*<div[^>]*>\s*<img[^>]+title="([^"]+)"',
            text
        )
        if not actors:
            actors = re.findall(
                r'<a[^>]+href="[^"]*star/[^"]+"[^>]*title="([^"]+)"',
                text
            )
        actors = [_clean_text(a) for a in actors if a]

        genres = re.findall(r'<a href="[^"]*genre/[^"]+">([^<]+)</a>', text)
        genres = [_clean_text(g) for g in genres if g]
        seen_g = set()
        genres = [g for g in genres if not (g in seen_g or seen_g.add(g))]

        info_lines = []
        if num:
            info_lines.append("番号: %s" % num)
        if date:
            info_lines.append("发行: %s" % date)
        if actors:
            info_lines.append("演员: %s" % "、".join(actors))
        if genres:
            info_lines.append("类别: %s" % "、".join(genres))
        if self.enable_offline_115:
            info_lines.append("115离线：提交到115云端，完成后自动直连播放")

        # ==== 抓磁力 ====
        magnets = []
        if self.enable_magnet or self.enable_offline_115:
            try:
                magnets = self._fetch_magnets(text, vid)
            except Exception:
                magnets = []

        # 收集去重 info_hash
        magnet_items = []
        seen_h = set()
        for g in magnets:
            h = self._magnet_hash(g.get("magnet") or "")
            if not h or h in seen_h:
                continue
            seen_h.add(h)
            magnet_items.append((g, h))

        froms, urls = [], []

        # 磁力源
        if self.enable_magnet and magnet_items:
            eps = []
            for i, (g, h) in enumerate(magnet_items):
                label = self._magnet_label(g, i, num)
                eps.append("%s$magnet:?xt=urn:btih:%s" % (label, h))
            if eps:
                froms.append("磁力")
                urls.append("#".join(eps))

        # 115 离线源
        if self.enable_offline_115 and magnet_items:
            eps = []
            for i, (g, h) in enumerate(magnet_items):
                label = self._magnet_label(g, i, num)
                b64 = base64.b64encode(
                    ("magnet:?xt=urn:btih:%s" % h).encode("utf-8")
                ).decode("ascii")
                eps.append("%s$%s%s" % (label, OFF_PREFIX_115, b64))
            if eps:
                froms.append("115离线")
                urls.append("#".join(eps))

        item = {
            "vod_id": vid,
            "vod_name": (num + " " + title).strip(),
            "vod_pic": pic,
            "vod_year": (date or "")[:4],
            "vod_actor": "、".join(actors),
            "vod_content": "\n".join(info_lines),
        }
        if froms:
            item["vod_play_from"] = "$$$".join(froms)
            item["vod_play_url"] = "$$$".join(urls)
        return {"list": [item]}

    def _fetch_magnets(self, detail_html, vid):
        gid = ""
        for pat in (
            r"var\s+gid\s*=\s*(\d+)",
            r"gid\s*=\s*(\d+)",
            r'data-gid\s*=\s*"(\d+)"',
        ):
            gm = re.search(pat, detail_html)
            if gm:
                gid = gm.group(1)
                if gid:
                    break
        if not gid:
            return []

        img = ""
        im = re.search(r"var\s+img\s*=\s*'([^']+)'", detail_html)
        if im:
            img = im.group(1)

        uc = "1" if re.search(r"var\s+uc\s*=\s*1", detail_html) else "0"

        ajax_url = (
            "%s/ajax/uncledatoolsbyajax.php?gid=%s&lang=%s&img=%s&uc=%s&floor=%d"
            % (self.host, gid, self.lang, quote(img, safe=""), uc,
               int(time.time() * 1000) % 1000 + 1)
        )
        try:
            text = self._get_html(ajax_url, headers=AJAX_HEADERS)
        except Exception:
            return []
        if not text:
            return []

        out = []
        seen_hash = set()
        for m in re.finditer(r"<tr[^>]*>(.*?)</tr>", text, re.S):
            block = m.group(1)
            am = re.search(r'href="(magnet:[^"]+)"', block)
            if not am:
                continue
            magnet = am.group(1).replace("&amp;", "&")

            hm = re.search(r"btih:([0-9a-fA-F]{40}|[0-9a-zA-Z]{32})", magnet)
            if not hm:
                continue
            h = hm.group(1).lower()
            if h in seen_hash:
                continue
            seen_hash.add(h)

            name = ""
            nm = re.search(r"<a[^>]*>([^<]+)</a>", block)
            if nm:
                name = _clean_text(nm.group(1))

            size = ""
            sm = re.search(
                r"<td[^>]*>([^<]*?(?:GB|MB|TB|KB)[^<]*?)</td>",
                block, re.I
            )
            if sm:
                size = _clean_text(sm.group(1))

            out.append({
                "name": name,
                "size": size,
                "magnet": magnet,
            })

        def _size_key(g):
            s = g.get("size") or ""
            mm = re.search(r"([\d.]+)\s*(GB|MB|TB|KB)", s, re.I)
            if not mm:
                return 0
            try:
                n = float(mm.group(1))
            except Exception:
                return 0
            unit = mm.group(2).upper()
            mult = {"KB": 1.0 / 1024, "MB": 1.0, "GB": 1024.0, "TB": 1024.0 * 1024}.get(unit, 1.0)
            return n * mult

        out.sort(key=_size_key, reverse=True)
        return out

    @staticmethod
    def _magnet_label(g, i, num):
        raw = _to_text(g.get("name")) or num or ("资源%d" % (i + 1))
        safe = re.sub(r"[$#&\n\r\t]", " ", raw).strip()[:40]
        parts = [safe]
        if g.get("size"):
            parts.append(g["size"])
        return " ".join(parts) or ("资源%d" % (i + 1))

    def _proxy_pic(self, url):
        if not url:
            return ""
        p = (self.img_proxy or "").strip()
        if not p:
            return url
        try:
            return p + quote(url, safe="")
        except Exception:
            return url

    # ========== 115 离线 ==========
    def _offline_headers(self):
        return {
            "Cookie": self.cookie_115,
            "User-Agent": OFFLINE_UA,
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "https://115.com/",
            "Origin": "https://115.com",
        }

    @staticmethod
    def _magnet_hash(magnet):
        m = re.search(r"btih:([0-9a-fA-F]{40}|[0-9a-zA-Z]{32})", magnet or "")
        return m.group(1).lower() if m else ""

    def _offline_add(self, magnet):
        data = {
            "url[0]": magnet,
            "wp_save_path": self.offline_save_path,
            "appVer": self.offline_app_ver,
        }
        r = self.s.post(OFFLINE_ADD_API, data=data, headers=self._offline_headers(),
                        timeout=self.offline_timeout, verify=False)
        try:
            return r.json()
        except Exception:
            return {}

    def _offline_list(self, page=1):
        data = {"page": page, "appVer": self.offline_app_ver}
        r = self.s.post(OFFLINE_LIST_API, data=data, headers=self._offline_headers(),
                        timeout=self.offline_timeout, verify=False)
        try:
            return r.json()
        except Exception:
            return {}

    def _offline_find_task(self, info_hash):
        for page in (1, 2):
            try:
                res = self._offline_list(page)
            except Exception:
                return None
            tasks = res.get("tasks") or res.get("list") or []
            if not tasks:
                break
            for t in tasks:
                h = (t.get("info_hash") or t.get("hash") or "").lower()
                if h and h == info_hash.lower():
                    return t
        return None

    def _offline_task_state(self, task):
        if not task:
            return False, False, "任务未找到"
        status = task.get("status")
        if status is None:
            status = task.get("stat")
        try:
            status = int(status)
        except Exception:
            status = -1
        percent = task.get("percent")
        try:
            percent = float(percent)
        except Exception:
            percent = 0.0
        name = task.get("name") or task.get("file_name") or ""
        if status == 2 or percent >= 100:
            return True, False, name
        if status in (3, 4, -1):
            return False, True, task.get("error") or task.get("message") or "离线任务失败"
        return False, False, name

    def _offline_wait_done(self, info_hash, timeout=OFFLINE_POLL_TIMEOUT):
        deadline = time.time() + timeout
        last_name = ""
        while time.time() < deadline:
            try:
                task = self._offline_find_task(info_hash)
            except Exception:
                task = None
            done, failed, msg = self._offline_task_state(task)
            if done:
                return True, msg or last_name
            if failed:
                return False, msg
            if msg:
                last_name = msg
            time.sleep(OFFLINE_POLL_INTERVAL)
        return False, last_name

    @staticmethod
    def _guess_keyword_from_name(name):
        if not name:
            return ""
        base = os.path.splitext(name)[0]
        base = base.replace("_", " ").replace(".", " ").strip()
        m = re.search(r"(FC2)[- ]?(PPV)?[- ]?(\d{5,8})", base, re.I)
        if m:
            return "FC2-PPV-%s" % m.group(3)
        m = re.search(r"([A-Za-z]{2,6})[- ]?(\d{2,5})", base)
        if m:
            return "%s-%s" % (m.group(1).upper(), m.group(2))
        return base[:40]

    def _find_pickcode_by_name(self, name, retries=3, interval=1):
        keyword = self._guess_keyword_from_name(name)
        if not keyword:
            return ""
        headers = {
            "User-Agent": WEB_UA,
            "Referer": "https://115.com/",
            "Origin": "https://115.com",
            "Accept": "application/json, text/plain, */*",
            "Cookie": self.cookie_115,
        }
        for _ in range(retries):
            try:
                r = self.s.get("https://webapi.115.com/files/search", params={
                    "search_value": keyword, "type": 4, "offset": 0,
                    "limit": 50, "aid": 1, "cid": 0, "format": "json",
                }, headers=headers, timeout=20)
                data = _safe_json(r.text, {})
                for it in (data.get("data") or []):
                    if int(it.get("fc") or 0) == 1:
                        pc = it.get("pc") or it.get("pick_code") or it.get("pickcode")
                        if pc:
                            return pc
            except Exception:
                pass
            time.sleep(interval)
        return ""

    def _resolve_pickcode(self, pickcode):
        if not self.cookie_115:
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                    "msg": "未配置115 Cookie"}
        if not requests:
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                    "msg": "requests 模块不可用"}

        body = _build_downurl_body({"pickcode": pickcode})
        url = "https://proapi.115.com/app/chrome/downurl?t=%d" % int(time.time())
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Content-Length": str(len(body)),
            "Cookie": self.cookie_115,
            "User-Agent": OFFLINE_UA,
            "Referer": "https://115.com/",
            "Origin": "https://115.com",
        }
        r = self.s.post(url, data=body, headers=headers, timeout=20)

        try:
            decoded = _decode_downurl_response(r.text)
        except Exception as e:
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                    "msg": "115 解密失败: %s" % e}

        real_url = _find_url_deep(decoded)
        if not real_url:
            msg = _find_msg_deep(decoded) or "未发现下载链接"
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                    "msg": "115 限制: %s" % msg}

        new_cookie = _set_cookie_text(
            r.headers.get("Set-Cookie") if hasattr(r.headers, "get") else None
        )
        final_cookie = "; ".join(c for c in (self.cookie_115, new_cookie) if c)

        fmt = ""
        lower = real_url.lower().split("?")[0]
        if lower.endswith(".m3u8"):
            fmt = "application/x-mpegURL"
        elif lower.endswith(".mp4"):
            fmt = "video/mp4"
        elif lower.endswith(".flv"):
            fmt = "video/x-flv"

        result = {
            "parse": 0,
            "jx": 0,
            "playUrl": "",
            "url": real_url,
            "header": {
                "User-Agent": OFFLINE_UA,
                "Cookie": final_cookie,
                "Referer": "https://115.com/",
            },
        }
        if fmt:
            result["format"] = fmt
        return result

    def _submit_offline_115(self, magnet):
        if not self.cookie_115:
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                    "msg": "未配置115 Cookie，无法提交离线"}
        if not requests or self.s is None:
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                    "msg": "requests 不可用"}

        info_hash = self._magnet_hash(magnet)
        if not info_hash:
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                    "msg": "无法从磁力中解析 info_hash"}

        try:
            res = self._offline_add(magnet)
        except Exception as e:
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                    "msg": "提交离线失败：%s" % e}

        if not res.get("state"):
            msg = str(res.get("message") or res.get("error") or "提交失败")
            if "已存在" not in msg and "重复" not in msg:
                return {"parse": 0, "jx": 0, "url": "", "header": {},
                        "msg": "115离线提交失败：%s" % msg}

        name_hint = ""
        try:
            task = self._offline_find_task(info_hash)
            if task:
                name_hint = task.get("name") or task.get("file_name") or ""
        except Exception:
            pass

        if name_hint:
            pickcode = self._find_pickcode_by_name(name_hint, retries=1, interval=0)
            if pickcode:
                return self._resolve_pickcode(pickcode)

        done, name_or_msg = self._offline_wait_done(info_hash)

        if not done:
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                    "msg": "已提交115离线，下载中（%s），请稍后重试"
                           % (name_or_msg or "等待完成")}

        pickcode = self._find_pickcode_by_name(name_or_msg, retries=3, interval=1)
        if not pickcode:
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                    "msg": "离线已完成，但115网盘里还没搜到文件，请稍后重试"}

        return self._resolve_pickcode(pickcode)

    # ========== 搜索 ==========
    def searchContent(self, key, quick=False, pg="1"):
        page = _safe_int(pg, 1)
        keyword = _to_text(key)
        if not keyword:
            return {"list": [], "page": page, "pagecount": 1,
                    "limit": self.search_limit, "total": 0}

        seen = set()
        out = []
        urls = [
            "%s/search/%s&type=&parent=ce" % (self.host, quote(keyword)),
        ]
        if self.enable_uncensored:
            urls.append(
                "%s/uncensored/search/%s&type=0&parent=uc" % (self.host, quote(keyword))
            )

        for u in urls:
            try:
                text = self._get_html(u)
            except Exception:
                continue
            for m in re.finditer(
                r'<a[^>]+class="[^"]*movie-box[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                text, re.S
            ):
                try:
                    href = _fix_url(m.group(1), self.host)
                    block = m.group(2)
                    img = re.search(
                        r'<img[^>]*(?:src|data-src|data-original)=["\']([^"\']+)',
                        block, re.I
                    )
                    pic = _fix_url(img.group(1), self.host) if img else ""
                    title = ""
                    tm = re.search(r'<img[^>]+title="([^"]+)"', block, re.I)
                    if tm:
                        title = _clean_text(tm.group(1))
                    if not title:
                        tm = re.search(r"<span>([^<]+)", block)
                        if tm:
                            title = _clean_text(tm.group(1))
                    num = ""
                    dates = re.findall(r"<date>([^<]+)</date>", block)
                    if dates:
                        num = _clean_text(dates[0])
                    vid = _extract_id(href)
                    if not vid or vid in seen:
                        continue
                    seen.add(vid)
                    out.append({
                        "vod_id": vid,
                        "vod_name": title or num or vid,
                        "vod_pic": pic,
                        "vod_remarks": num or "",
                    })
                except Exception:
                    continue

        return {
            "list": out,
            "page": page,
            "pagecount": page + 1 if len(out) >= self.search_limit else page,
            "limit": self.search_limit,
            "total": len(out),
        }

    # ========== 播放 ==========
    def playerContent(self, flag, ids, vipFlags=None):
        vid = str(ids[0]) if isinstance(ids, (list, tuple)) and ids else str(ids or "")

        # 115 离线直连
        if vid.startswith(OFF_PREFIX_115):
            b64 = vid[len(OFF_PREFIX_115):].strip()
            try:
                magnet = base64.b64decode(b64.encode("ascii")).decode("utf-8")
            except Exception:
                return {"parse": 0, "jx": 0, "url": "", "header": {},
                        "msg": "磁力解码失败"}
            return self._submit_offline_115(magnet)

        if vid.startswith("115off:"):
            return self._submit_offline_115(vid[7:].strip())

        if vid.startswith("magnet:"):
            m = _normalize_magnet(vid)
            return {
                "parse": 0,
                "jx": 0,
                "playUrl": "",
                "url": m or vid,
                "header": {"User-Agent": self.ua, "Accept": "*/*"},
            }

        return {
            "parse": 0,
            "jx": 0,
            "playUrl": "",
            "url": "",
            "header": {},
        }

    def localProxy(self, param):
        if isinstance(param, str):
            try:
                param = json.loads(param)
            except Exception:
                param = {}
        if not isinstance(param, dict):
            param = {}
        return [404, "text/plain", b"Not Found", {}]

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        u = _to_text(url).lower()
        if u.startswith("magnet:"):
            return True
        u = u.split("?")[0]
        return u.endswith((".mp4", ".m3u8", ".flv", ".mkv", ".ts", ".avi"))

    def action(self, action):
        return {}

    def destroy(self):
        return None

    def _headers(self, extra=None):
        h = dict(LIST_HEADERS)
        h["Referer"] = self.host + "/"
        if self.cookie:
            h["Cookie"] = self.cookie
        if extra:
            h.update(extra)
        return h

    def _get_html(self, url, headers=None):
        if not requests or self.s is None:
            raise RuntimeError("requests 不可用")
        r = self.s.get(url, headers=headers or self._headers(),
                       timeout=self.timeout, verify=False)
        r.encoding = "utf-8"
        return r.text or ""