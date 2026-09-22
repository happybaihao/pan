# -*- coding: utf-8 -*-
import os
import re
import json
import time
import base64
import hashlib
from urllib.parse import quote, unquote

try:
    import requests
except ImportError:
    requests = None


API_PATH = "/video/my115"
PAGE_SIZE = 115
SEARCH_LIMIT = 50
PLAY_FROM = "115"
FOLDER_PIC = "https://img.icons8.com/fluency/96/folder-invoices--v1.png"
VIDEO_PIC = "https://img.icons8.com/color/48/video.png"
VIDEO_EXTS = (
    ".mp4", ".mkv", ".webm", ".avi", ".wmv", ".flv", ".mov",
    ".mpeg", ".mpg", ".m4v", ".ts", ".m2ts", ".3gp", ".rm",
    ".rmvb", ".iso",
)

WEB_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
BROWSER_UA = WEB_UA + " 115Browser/36.0.0 Chromium/125.0"

LIST_HEADERS = {
    "User-Agent": BROWSER_UA,
    "Referer": "https://webapi.115.com/bridge_2.0.html?namespace=Core.DataAccess&api=UDataAPI&_t=v5",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://115.com",
}

SEARCH_HEADERS = {
    "User-Agent": WEB_UA,
    "Referer": "https://115.com/",
    "Origin": "https://115.com",
    "Accept": "application/json, text/plain, */*",
}

DEFAULT_COOKIE = "UID=2102308_R1_1772000990; CID=4005b191e64f7d02dcb7e89d0ed0a5d5; SEID=61dc762e209edaf0fe56eb6bbb94a79669d09e1d0687a1718c01884f57fd25e4d9360d8c463597c513a1a0b69a8a6dcf0d52cd5d97dad0adeed12314; KID=6b7d1efff3d8766105a397774a941046"

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

OFF_PREFIX_115 = "http://115off/"
OFFLINE_UA = WEB_UA + " 115Browser/36.0.0"

OFFLINE_POLL_TIMEOUT = 25
OFFLINE_POLL_INTERVAL = 1
OFFLINE_ADD_API = "https://115.com/web/lixian/?ct=lixian&ac=add_task_urls"
OFFLINE_LIST_API = "https://115.com/web/lixian/?ct=lixian&ac=task_lists"

JAVDB_API_BASE = "https://jdforrepam.com/api"
JAVDB_IMG_BASE = "https://c0.jdbstatic.com"
JAVDB_UA = ("Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36")
JAVDB_TIMEOUT = 15
JAVDB_PAGE_SIZE = 32
JAVDB_MAGNET_LIMIT = 40
JAVDB_SALT = "lpw6vgqzsp"
JAVDB_KEY = ("71cf27bb3c0bcdf207b64abecddc970098c7421ee7203b9cdae544784"
             "78a199e7d5a6e1a57691123c1a931c057842fb73ba3b3c83bcd69c17cc"
             "f174081e3d8aa")

JAVDB_CLASSES = [
    {"type_id": "jav_latest", "type_name": "全部"},
    {"type_id": "jav_maker",  "type_name": "片商"},
    {"type_id": "jav_tag1",   "type_name": "无码"},
    {"type_id": "jav_tag0",   "type_name": "有码"},
    {"type_id": "jav_tag3",   "type_name": "FC2"},
    {"type_id": "jav_tag2",   "type_name": "欧美"},
]

JAVDB_SORTS = [
    {"n": "最新上市", "v": "release"},
    {"n": "评分最高", "v": "score"},
    {"n": "磁链更新", "v": "magnet-updated"},
]

JAVDB_FILTERS = [
    {"n": "全部",   "v": ""},
    {"n": "含磁链", "v": "magnet"},
    {"n": "含字幕", "v": "subtitle"},
    {"n": "可播放", "v": "play"},
]

JAVDB_FILTER_KEY = {
    "magnet": "%s:t:m::::",
    "subtitle": "%s:t:s::::",
    "play": "%s:t:p::::",
    "": "%s:t::::::",
}

JAVDB_LATEST_FILTER = {
    "latest": "all",
    "play": "can_play",
    "sub": "subtitle",
    "magnet": "magnets",
}

# ============ 片商库配置 ============

# 片商库顶部分类 tab，对应 filter_by 第一个数字
# 0=有码 1=无码 2=欧美 3=FC2
JAVDB_MAKER_TYPES = [
    {"n": "有码", "v": "0"},
    {"n": "无码", "v": "1"},
    {"n": "欧美", "v": "2"},
    {"n": "FC2",  "v": "3"},
]

# 片商库筛选只保留无码
JAVDB_MAKER_TYPES_WM = [
    {"n": "无码", "v": "1"},
]

# 片商列表（手工维护）
# v 是 filter_by=1:m:<v>:m 里的 <v>，必须是从抓包里拿到的真实 id
JAVDB_MAKERS = [
    {"n": "Tokyo-Hot", "v": "k14"},
    {"n": "麻豆傳媒映畫", "v": "N73g"},
    {"n": "神風-カミカゼ", "v": "9KE"},
]

_SAFE_CHARS = str.maketrans({
    c: " " for c in "$#&?=:|\\/\n\r\t\u200b\xa0\ufeff"
})


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


def _format_size(size):
    try:
        n = float(size or 0)
    except Exception:
        return "0B"
    if n <= 0:
        return "0B"
    units = ("B", "KB", "MB", "GB", "TB")
    idx = 0
    val = n
    while val >= 1024 and idx < 4:
        val /= 1024.0
        idx += 1
    if idx == 0:
        fixed = 0
    elif val >= 100:
        fixed = 0
    elif val >= 10:
        fixed = 1
    else:
        fixed = 2
    return "%.*f%s" % (fixed, val, units[idx])


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


def _is_folder(item):
    try:
        return int(item.get("fc") or 0) == 0
    except Exception:
        return False


def _is_video(item):
    try:
        if int(item.get("fc") or 0) != 1:
            return False
    except Exception:
        return False
    name = _to_text(item.get("n") or item.get("name")).lower()
    return name.endswith(VIDEO_EXTS)


def _item_name(item):
    return _to_text(item.get("n") or item.get("name") or "未知")


def _encode_local_id(name, id_, kind=""):
    return "LOCAL###%s###%s###%s" % (quote(_to_text(name), safe=""), _to_text(id_), kind)


def _decode_local_id(raw):
    raw = _to_text(raw)
    if not raw.startswith("LOCAL###"):
        return None
    parts = raw.split("###")
    if len(parts) < 3:
        return None
    name = parts[1] or "115资源"
    try:
        name = unquote(name)
    except Exception:
        pass
    return {
        "name": name or "115资源",
        "id": parts[2] or "0",
        "kind": parts[3] if len(parts) > 3 else "",
    }


def _map_item(item):
    name = _item_name(item)
    if _is_folder(item):
        id_ = _to_text(item.get("cid") or item.get("fid"))
        return {
            "vod_id": _encode_local_id(name, id_, "folder"),
            "vod_name": name,
            "vod_pic": FOLDER_PIC,
            "vod_remarks": "目录",
            "cate": {"id": id_, "name": name},
            "ratio": 1.33,
        }
    id_ = _to_text(item.get("pc") or item.get("pick_code") or item.get("pickcode"))
    return {
        "vod_id": _encode_local_id(name, id_, "file"),
        "vod_name": name,
        "vod_pic": VIDEO_PIC,
        "vod_remarks": _format_size(item.get("s") or item.get("size")),
        "ratio": 1.33,
    }


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


class Spider:
    def __init__(self):
        self.s = self.session = self.sess = None
        self.cookie = ""
        self.host = "https://115.com"

        self._sess_jav = None

        self.extend = ""
        self.api_base = JAVDB_API_BASE
        self.img_base = JAVDB_IMG_BASE
        self.img_proxy = ""
        self.emby = ""
        self.emby_key = ""
        self.ua = JAVDB_UA
        self.timeout = JAVDB_TIMEOUT
        self.page_size = JAVDB_PAGE_SIZE
        self.magnet_limit = JAVDB_MAGNET_LIMIT
        self._salt = JAVDB_SALT
        self._key = JAVDB_KEY
        self.enable_magnet_play = True
        self.enable_offline_115 = True
        self.enable_115 = True
        self.enable_javdb = True

        self.offline_save_path = "0"
        self.offline_app_ver = "4.8.2"
        self.offline_timeout = 15

        if requests:
            self.s = self.session = self.sess = requests.Session()
            self._sess_jav = requests.Session()
            self._sess_jav.headers.update({
                "User-Agent": self.ua,
                "Accept": "application/json, text/plain, */*",
            })

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

        self.cookie = (
            _to_text(extend.get("cookie"))
            or _env("Y115_COOKIE")
            or _env("MY115_COOKIE")
            or DEFAULT_COOKIE
        )

        self.extend = json.dumps(extend, ensure_ascii=False)
        if extend.get("api"):
            self.api_base = str(extend["api"]).rstrip("/")
        if extend.get("emby"):
            self.emby = str(extend["emby"]).rstrip("/")
        if extend.get("embyKey") or extend.get("emby_key"):
            self.emby_key = str(extend.get("embyKey") or extend.get("emby_key") or "")
        if extend.get("img") or extend.get("imgProxy"):
            self.img_proxy = str(extend.get("img") or extend.get("imgProxy") or "").strip()
        if "enableMagnetPlay" in extend:
            self.enable_magnet_play = bool(extend["enableMagnetPlay"])
        if "enableJavdb" in extend:
            self.enable_javdb = bool(extend["enableJavdb"])
        if "enableOffline115" in extend:
            self.enable_offline_115 = bool(extend["enableOffline115"])
        if extend.get("offlineSavePath"):
            self.offline_save_path = str(extend["offlineSavePath"])
        if extend.get("offlineAppVer"):
            self.offline_app_ver = str(extend["offlineAppVer"])

    def homeContent(self, filter=None):
        classes = []
        if self.enable_javdb:
            classes.extend(dict(c) for c in JAVDB_CLASSES)
        if self.enable_115:
            classes.append({"type_id": "0", "type_name": "115网盘"})

        filters = {}
        if self.enable_javdb:
            for t in ("0", "1", "2", "3"):
                filters["jav_tag" + t] = [
                    {"key": "filter", "name": "过滤", "init": "",
                     "value": [dict(x) for x in JAVDB_FILTERS]},
                    {"key": "sort", "name": "排序", "init": "release",
                     "value": [dict(x) for x in JAVDB_SORTS]},
                ]

            # 片商库：分类只保留无码
            if JAVDB_MAKERS:
                filters["jav_maker"] = [
                    {"key": "mtype", "name": "分类", "init": "1",
                     "value": [dict(x) for x in JAVDB_MAKER_TYPES_WM]},
                    {"key": "maker", "name": "片商", "init": JAVDB_MAKERS[0]["v"],
                     "value": [dict(x) for x in JAVDB_MAKERS]},
                ]
        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        t = _to_text(tid)
        if t.startswith("jav_"):
            return self._jav_category(t, pg, extend)
        return self._115_category(t, pg)

    def _115_category(self, tid, pg):
        page = self._safe_int(pg, 1)
        cid = "0"
        if isinstance(tid, str) and tid.startswith("LOCAL###"):
            dec = _decode_local_id(tid)
            if dec:
                cid = dec.get("id") or "0"
        elif tid and tid != "0":
            cid = str(tid)

        try:
            data = self._list_dir(cid, page)
        except Exception:
            return {"list": [], "page": page, "pagecount": 1,
                    "limit": PAGE_SIZE, "total": 0}

        raw = data.get("list") or []
        count = self._safe_int(data.get("count"), 0)
        seen = set()
        out = []
        for item in raw:
            try:
                if not (_is_folder(item) or _is_video(item)):
                    continue
                row = _map_item(item)
            except Exception:
                continue
            vid = row.get("vod_id") or ""
            if vid in seen:
                continue
            seen.add(vid)
            out.append(row)

        pagecount = (count + PAGE_SIZE - 1) // PAGE_SIZE if count > 0 else page
        return {
            "list": out,
            "page": page,
            "pagecount": max(1, pagecount),
            "limit": PAGE_SIZE,
            "total": count or len(out),
        }

    def _jav_category(self, tid, pg, extend):
        pg_s = str(pg or "1")
        page = int(pg_s) if pg_s.isdigit() else 1
        try:
            movies, has_more = self._jav_cat_page(tid, page, extend)
        except Exception:
            movies, has_more = [], False
        return {
            "list": [self._jav_card(m) for m in movies],
            "page": page,
            "pagecount": page + 1 if has_more else page,
            "limit": self.page_size,
            "total": (page + 1) * self.page_size if has_more else page * self.page_size,
        }

    def detailContent(self, ids):
        vid = str(ids[0]) if isinstance(ids, (list, tuple)) and ids else str(ids or "")

        if vid and not vid.startswith("LOCAL###"):
            return self._jav_detail(vid)

        rows = []
        for one in vid.split(","):
            one = one.strip()
            if not one:
                continue
            dec = _decode_local_id(one)
            if not dec:
                rows.append({"vod_id": one, "vod_name": "115资源"})
                continue
            if dec.get("kind") == "folder":
                rows.append({
                    "vod_id": one,
                    "vod_name": dec.get("name") or "115资源",
                    "vod_remarks": "目录",
                    "vod_pic": FOLDER_PIC,
                })
            else:
                rows.append({
                    "vod_id": one,
                    "vod_name": dec.get("name") or "115资源",
                    "vod_pic": VIDEO_PIC,
                    "vod_content": "文件名: %s" % (dec.get("name") or ""),
                    "vod_play_from": PLAY_FROM,
                    "vod_play_url": "OWN$%s" % (dec.get("id") or ""),
                })
        return {"list": rows}

    def _jav_detail(self, mid):
        movie = (self._jav_data("/v4/movies/" + mid) or {}).get("movie") or {}
        if not movie:
            return {"list": []}

        try:
            magnets = (self._jav_data(
                "/v1/movies/" + mid + "/magnets",
                {"page": 1, "limit": self.magnet_limit}
            ) or {}).get("magnets") or []
        except Exception:
            magnets = []

        num = (movie.get("number") or "").strip()
        title = (movie.get("title") or "").strip()
        actors = "、".join(a.get("name") or "" for a in (movie.get("actors") or []) if a.get("name"))
        tags = "、".join(t.get("name") or "" for t in (movie.get("tags") or []) if t.get("name"))

        info = [
            "番号: %s" % num,
            "发行: %s" % (movie.get("release_date") or "-"),
            "评分: %s" % (movie.get("score") or "-"),
            "演员: %s" % (actors or "-"),
            "标签: %s" % (tags or "-"),
        ]
        if self.enable_magnet_play:
            info.append("【磁力】：把磁力交给播放器处理")
        if self.enable_offline_115:
            info.append("115离线：提交到115云端下载，完成后到115网盘源播放")

        froms, urls = [], []

        if self.emby and self.emby_key:
            froms.append("正片")
            urls.append("播放$emby:%s|%s" % (mid, num))

        if movie.get("preview_video_url") or movie.get("has_preview_video"):
            froms.append("预告片")
            urls.append("预告片$preview:%s" % mid)

        magnet_items = [(i, g, (g.get("hash") or "").strip()) for i, g in enumerate(magnets)]
        magnet_items = [(i, g, h) for i, g, h in magnet_items if h]

        if self.enable_magnet_play and magnet_items:
            eps = []
            for i, g, h in magnet_items:
                label = self._jav_magnet_label(g, i, num)
                eps.append("%s$magnet:?xt=urn:btih:%s" % (label, h))
            if eps:
                froms.append("磁力")
                urls.append("#".join(eps))

        if self.enable_offline_115 and magnet_items:
            eps = []
            for i, g, h in magnet_items:
                label = self._jav_magnet_label(g, i, num)
                b64 = base64.b64encode(("magnet:?xt=urn:btih:%s" % h).encode("utf-8")).decode("ascii")
                eps.append("%s$%s%s" % (label, OFF_PREFIX_115, b64))
            if eps:
                froms.append("115离线")
                urls.append("#".join(eps))

        item = {
            "vod_id": mid,
            "vod_name": (num + " " + title).strip(),
            "vod_pic": self._jav_pic(movie.get("id"), movie.get("cover_url") or movie.get("thumb_url")),
            "vod_year": (movie.get("release_date") or "")[:4],
            "vod_actor": actors,
            "vod_content": "\n".join(info),
        }
        if froms:
            item["vod_play_from"] = "$$$".join(froms)
            item["vod_play_url"] = "$$$".join(urls)
        return {"list": [item]}

    def searchContent(self, key, quick=False, pg="1"):
        page = self._safe_int(pg, 1)
        keyword = _to_text(key)
        if not keyword:
            return {"list": [], "page": page, "pagecount": 1,
                    "limit": SEARCH_LIMIT, "total": 0}

        out = []

        if self.enable_115:
            try:
                data = self._search(keyword, page)
                out.extend(_map_item(it) for it in (data.get("list") or []) if _is_video(it))
            except Exception:
                pass

        if self.enable_javdb:
            try:
                d = self._jav_data("/v2/search", {
                    "q": keyword, "page": page,
                    "type": "movie", "limit": self.page_size,
                })
                out.extend(self._jav_card(m) for m in (d.get("movies") or []) if m.get("number"))
            except Exception:
                pass

        seen = set()
        uniq = []
        for row in out:
            vid = row.get("vod_id")
            if vid in seen:
                continue
            seen.add(vid)
            uniq.append(row)

        return {
            "list": uniq,
            "page": page,
            "pagecount": page + 1 if len(uniq) >= SEARCH_LIMIT else page,
            "limit": SEARCH_LIMIT,
            "total": len(uniq),
        }

    def playerContent(self, flag, ids, vipFlags=None):
        vid = str(ids[0]) if isinstance(ids, (list, tuple)) and ids else str(ids or "")

        if vid.startswith("magnet:"):
            return {"parse": 0, "jx": 0, "url": vid,
                    "header": {"User-Agent": self.ua, "Accept": "*/*"}}

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

        if vid.startswith("emby:"):
            mid, _, num = vid[5:].partition("|")
            if not num:
                movie = (self._jav_data("/v4/movies/" + mid) or {}).get("movie") or {}
                num = (movie.get("number") or "").strip()
            play = self._emby_play(num)
            if play:
                return {"parse": 0, "jx": 0, "url": play,
                        "header": {"User-Agent": self.ua, "Accept": "*/*"}}
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                    "msg": "Emby 里没找到 " + (num or mid)}

        if vid.startswith("preview:"):
            mid = vid[8:]
            movie = (self._jav_data("/v4/movies/" + mid) or {}).get("movie") or {}
            pv = (movie.get("preview_video_url") or "").strip()
            if pv.startswith("//"):
                pv = "https:" + pv
            return {"parse": 0, "jx": 0, "url": pv,
                    "header": {"User-Agent": self.ua, "Accept": "*/*"}}

        pickcode = vid[4:] if vid.startswith("OWN$") else vid
        if not pickcode:
            return {"parse": 0, "jx": 0, "playUrl": "", "url": "",
                    "header": {}, "msg": "115 播放参数错误"}

        try:
            return self._resolve_pickcode(pickcode)
        except Exception as e:
            return {"parse": 0, "jx": 0, "playUrl": "", "url": "",
                    "header": {}, "msg": "115 接口异常: %s" % e}

    def localProxy(self, param):
        if isinstance(param, str):
            try:
                param = json.loads(param)
            except Exception:
                param = {}
        return [404, "text/plain", b"Not Found", {}]

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        return _to_text(url).lower().endswith(VIDEO_EXTS)

    def action(self, action):
        return {}

    def destroy(self):
        return None

    @staticmethod
    def _safe_int(v, default=0):
        try:
            return int(v)
        except Exception:
            try:
                return int(str(v or "").strip() or default)
            except Exception:
                return default

    def _headers(self, extra=None):
        h = dict(LIST_HEADERS)
        if self.cookie:
            h["Cookie"] = self.cookie
        if extra:
            h.update(extra)
        return h

    def _list_dir(self, cid="0", page=1):
        if not self.cookie:
            raise RuntimeError("未检测到115 Cookie")
        if not requests:
            raise RuntimeError("requests 模块不可用")
        page = max(1, self._safe_int(page, 1))
        params = {
            "aid": 1,
            "cid": cid or "0",
            "o": "user_ptime",
            "asc": 0,
            "offset": (page - 1) * PAGE_SIZE,
            "show_dir": 1,
            "limit": PAGE_SIZE,
            "code": "",
            "scid": "",
            "snap": 0,
            "natsort": 1,
            "record_open_time": 1,
            "source": "",
            "format": "json",
        }
        r = self.s.get("https://webapi.115.com/files", params=params,
                       headers=self._headers(), timeout=20)
        data = _safe_json(r.text, {})
        if not data.get("state"):
            err_s = str(data.get("error") or data.get("message") or data.get("msg") or "接口状态异常")
            if "登录" in err_s or "cookie" in err_s.lower():
                raise RuntimeError("115 Cookie 已失效，请更新内置 DEFAULT_COOKIE")
            raise RuntimeError("获取115目录失败: %s" % err_s)
        return {
            "list": data.get("data") if isinstance(data.get("data"), list) else [],
            "count": self._safe_int(data.get("count"), 0),
        }

    def _search(self, keyword, page=1):
        if not self.cookie:
            raise RuntimeError("未检测到115 Cookie")
        if not requests:
            raise RuntimeError("requests 模块不可用")
        page = max(1, self._safe_int(page, 1))
        params = {
            "search_value": keyword,
            "type": 4,
            "offset": (page - 1) * SEARCH_LIMIT,
            "limit": SEARCH_LIMIT,
            "date": "",
            "aid": 1,
            "cid": 0,
            "pick_code": "",
            "source": "",
            "format": "json",
        }
        headers = dict(SEARCH_HEADERS)
        if self.cookie:
            headers["Cookie"] = self.cookie
        r = self.s.get("https://webapi.115.com/files/search", params=params,
                       headers=headers, timeout=20)
        data = _safe_json(r.text, {})
        lst = data.get("data") if isinstance(data.get("data"), list) else []
        return {
            "list": lst,
            "count": self._safe_int(data.get("count"), len(lst)),
            "limit": SEARCH_LIMIT,
        }

    def _resolve_pickcode(self, pickcode):
        if not self.cookie:
            return {"parse": 0, "jx": 0, "playUrl": "", "url": "",
                    "header": {}, "msg": "未检测到115 Cookie"}
        if not requests:
            return {"parse": 0, "jx": 0, "playUrl": "", "url": "",
                    "header": {}, "msg": "requests 模块不可用"}

        body = _build_downurl_body({"pickcode": pickcode})
        url = "https://proapi.115.com/app/chrome/downurl?t=%d" % int(time.time())
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Content-Length": str(len(body)),
            "Cookie": self.cookie,
            "User-Agent": BROWSER_UA,
            "Referer": "https://115.com/",
            "Origin": "https://115.com",
        }
        r = self.s.post(url, data=body, headers=headers, timeout=20)

        try:
            decoded = _decode_downurl_response(r.text)
        except Exception as e:
            return {"parse": 0, "jx": 0, "playUrl": "", "url": "",
                    "header": {}, "msg": "115 解密失败: %s" % e}

        real_url = _find_url_deep(decoded)
        if not real_url:
            msg = _find_msg_deep(decoded) or "未发现下载链接"
            return {"parse": 0, "jx": 0, "playUrl": "", "url": "",
                    "header": {}, "msg": "115 限制: %s" % msg}

        new_cookie = _set_cookie_text(r.headers.get("Set-Cookie") if hasattr(r.headers, "get") else None)
        final_cookie = "; ".join(c for c in (self.cookie, new_cookie) if c)

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
                "User-Agent": BROWSER_UA,
                "Cookie": final_cookie,
                "Referer": "https://115.com/",
            },
        }
        if fmt:
            result["format"] = fmt
        return result

    def _offline_headers(self):
        return {
            "Cookie": self.cookie,
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
        data = {
            "page": page,
            "appVer": self.offline_app_ver,
        }
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
        for _ in range(retries):
            try:
                data = self._search(keyword, 1)
            except Exception:
                data = {}
            for it in (data.get("list") or []):
                if not _is_video(it):
                    continue
                pc = it.get("pc") or it.get("pick_code") or it.get("pickcode")
                if pc:
                    return pc
            time.sleep(interval)
        return ""

    def _submit_offline_115(self, magnet):
        if not self.cookie:
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
                    "msg": "已提交115离线，正在下载中（%s），请稍后重试"
                           % (name_or_msg or "等待完成")}

        pickcode = self._find_pickcode_by_name(name_or_msg, retries=3, interval=1)
        if not pickcode:
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                    "msg": "离线已完成，但115网盘里还没搜到文件，请稍后重试"}

        return self._resolve_pickcode(pickcode)

    def _jav_sign(self):
        ts = str(int(time.time()))
        return "%s.%s.%s" % (ts, self._salt,
                             hashlib.md5((ts + self._key).encode("utf-8")).hexdigest())

    def _jav_headers(self):
        return {
            "User-Agent": self.ua,
            "Accept": "application/json, text/plain, */*",
            "jdsignature": self._jav_sign(),
        }

    def _jav_get(self, path, params=None, absolute=False):
        url = path if (absolute or path.startswith("http")) else (self.api_base + path)
        try:
            if self._sess_jav is None:
                return {}
            r = self._sess_jav.get(url, params=params or {},
                                   headers=self._jav_headers(),
                                   timeout=self.timeout, verify=False)
            r.encoding = "utf-8"
            try:
                return r.json()
            except Exception:
                m = re.search(r"\{.*\}", r.text or "", re.S)
                return json.loads(m.group(0)) if m else {}
        except Exception:
            return {}

    def _jav_data(self, path, params=None, absolute=False):
        return (self._jav_get(path, params, absolute) or {}).get("data") or {}

    def _jav_pic(self, mid, raw=""):
        m = str(mid or "").strip()
        url = ("%s/covers/%s/%s.jpg" % (self.img_base, m[:2].lower(), m)) if m else (raw or "")
        p = (self.img_proxy or "").strip()
        if p and url:
            try:
                return p + quote(url, safe="")
            except Exception:
                return url
        return url

    def _jav_card(self, m):
        num = (m.get("number") or "").strip()
        title = (m.get("title") or "").strip()
        marks = []
        if m.get("can_play"):
            marks.append("可播")
        if m.get("has_cnsub"):
            marks.append("中字")
        if (m.get("magnets_count") or 0) > 0:
            marks.append("磁链%d" % m.get("magnets_count"))
        return {
            "vod_id": str(m.get("id") or ""),
            "vod_name": (num + " " + title).strip(),
            "vod_pic": self._jav_pic(m.get("id"), m.get("cover_url") or m.get("thumb_url")),
            "vod_remarks": " ".join(marks) or (m.get("release_date") or ""),
            "type_name": num,
        }

    def _jav_cat_page(self, tid, pg, extend):
        ext = extend if isinstance(extend, dict) else {}
        limit = self.page_size
        raw = tid[4:] if tid.startswith("jav_") else tid

        if raw in JAVDB_LATEST_FILTER:
            d = self._jav_data("/v1/movies/latest", {
                "page": pg,
                "filter_by": JAVDB_LATEST_FILTER[raw],
                "limit": limit,
            })
        elif raw.startswith("tag"):
            n = raw[-1]
            f = (ext.get("filter") or "").strip().lower()
            fb = (JAVDB_FILTER_KEY.get(f) or JAVDB_FILTER_KEY[""]) % n
            d = self._jav_data("/v1/movies/tags", {
                "filter_by": fb,
                "page": pg,
                "limit": limit,
                "sort_by": ext.get("sort") or "release",
                "order_by": ext.get("order") or "desc",
            })
        elif raw == "maker":
            mt = str(ext.get("mtype") or "1")   # 0/1/2/3
            mid = (ext.get("maker") or "").strip()
            if not mid:
                return [], False
            # 真实格式: filter_by=1:m:k14:m
            fb = "%s:m:%s:m" % (mt, mid)
            d = self._jav_data("/v1/movies/tags", {
                "filter_by": fb,
                "page": pg,
                "limit": limit,
                "sort_by": ext.get("sort") or "release",
                "order_by": ext.get("order") or "desc",
            })
        else:
            d = {}

        movies = [m for m in (d.get("movies") or []) if m.get("number")]
        return movies, len(movies) >= 1

    def _jav_magnet_label(self, g, i, num):
        raw_nm = (g.get("name") or "").strip() or num or ("资源%d" % (i + 1))
        safe_nm = re.sub(r"\s+", " ", raw_nm.translate(_SAFE_CHARS)).strip()[:40] or ("资源%d" % (i + 1))
        sz = _size_mb(g.get("size"))
        return safe_nm + (" " + sz if sz else "")

    def _emby_play(self, code):
        if not (self.emby and self.emby_key and code):
            return ""
        try:
            d = self._jav_data(self.emby.rstrip("/") + "/Items", {
                "searchTerm": code, "Recursive": "true",
                "IncludeItemTypes": "Movie", "Limit": 5,
                "api_key": self.emby_key,
            }, absolute=True)
            items = d.get("Items") or []
            up = code.upper()
            hit = next((it for it in items
                        if up in str(it.get("Name") or "").upper()
                        or up in str(it.get("Path") or "").upper()), None)
            hit = hit or (items[0] if items else None)
            if not hit:
                return ""
            return "%s/Videos/%s/stream?static=true&api_key=%s" % (
                self.emby.rstrip("/"), hit.get("Id"), self.emby_key)
        except Exception:
            return ""