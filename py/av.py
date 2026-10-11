# -*- coding: utf-8 -*-
import os
import re
import json
import time
import base64
import struct
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

DEFAULT_COOKIE = ""

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

OFF_PREFIX_6PAN = "http://6panoff/"
PAN6_API_BASE = "https://grpcuserapi.2dland.cn"
PAN6_SITE = "https://drive.2dland.cn"
PAN6_APP_ID = "2dland/web"
PAN6_APP_VER = "202603182100"
PAN6_APP_SEC = "izzX0kNu3sIIq3CK"
PAN6_UA = ("Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36")
PAN6_POLL_TIMEOUT = 25
PAN6_POLL_INTERVAL = 1
PAN6_BROWSE_PREFIX = "pan6:"
PAN6_FILE_PREFIX = "pan6f:"
PAN6_DEFAULT_SAVE_PATH = "/最近接收"
PAN6_INBOX_PATHS = ("/ss", "/最近接收", "/")

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

JAVDB_MAKER_TYPES = [
    {"n": "有码", "v": "0"},
    {"n": "无码", "v": "1"},
    {"n": "欧美", "v": "2"},
    {"n": "FC2",  "v": "3"},
]

JAVDB_MAKER_TYPES_WM = [
    {"n": "无码", "v": "1"},
]

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
    if len(input_bytes) > 117:
        raise ValueError("block too large: %d" % len(input_bytes))
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


# ============ 6盘 gRPC 基础(移植自 6pan.py) ============

def _p6_enc_varint(n):
    n = int(n) & ((1 << 64) - 1)
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _p6_enc_key(fn, wt):
    return _p6_enc_varint((fn << 3) | wt)


def _p6_enc_str(fn, s):
    b = str(s).encode("utf-8", "replace")
    return _p6_enc_key(fn, 2) + _p6_enc_varint(len(b)) + b


def _p6_enc_msg(fn, payload):
    return _p6_enc_key(fn, 2) + _p6_enc_varint(len(payload)) + payload


def _p6_enc_i32(fn, n):
    return _p6_enc_key(fn, 0) + _p6_enc_varint(int(n) & 0xFFFFFFFF)


def _p6_enc_i64(fn, n):
    return _p6_enc_key(fn, 0) + _p6_enc_varint(int(n))


def _p6_dec_varint(b, i):
    x = 0
    s = 0
    while i < len(b):
        c = b[i]
        i += 1
        x |= (c & 0x7F) << s
        if c < 0x80:
            return x, i
        s += 7
    return x, i


def _p6_dec_fields(b):
    i = 0
    out = {}
    while i < len(b):
        key, i = _p6_dec_varint(b, i)
        fn, wt = key >> 3, key & 7
        if wt == 0:
            v, i = _p6_dec_varint(b, i)
        elif wt == 1:
            v = b[i:i + 8]
            i += 8
        elif wt == 2:
            ln, i = _p6_dec_varint(b, i)
            v = b[i:i + ln]
            i += ln
        elif wt == 5:
            v = b[i:i + 4]
            i += 4
        else:
            break
        if fn in out:
            prev = out[fn]
            if not isinstance(prev, list):
                out[fn] = [prev, v]
            else:
                prev.append(v)
        else:
            out[fn] = v
    return out


def _p6_as_str(v):
    if v is None:
        return ""
    if isinstance(v, (bytes, bytearray)):
        try:
            return bytes(v).decode("utf-8")
        except Exception:
            return bytes(v).decode("utf-8", "replace")
    return str(v)


def _p6_as_int(v, default=0):
    if v is None:
        return default
    if isinstance(v, bytes):
        try:
            x = 0
            for c in v:
                x = (x << 8) | c
            return x
        except Exception:
            return default
    try:
        return int(v)
    except Exception:
        return default


def _p6_as_msgs(v):
    if v is None:
        return []
    if isinstance(v, (bytes, bytearray)):
        return [bytes(v)]
    if isinstance(v, list):
        return [bytes(x) for x in v if isinstance(x, (bytes, bytearray))]
    return []


def _p6_frame(msg):
    return struct.pack(">BI", 0, len(msg)) + msg


def _p6_parse_grpc_web(data):
    msg = b""
    trailers = {}
    i = 0
    while i + 5 <= len(data):
        flag = data[i]
        ln = struct.unpack(">I", data[i + 1:i + 5])[0]
        i += 5
        chunk = data[i:i + ln]
        i += ln
        if flag & 0x80:
            text = chunk.decode("utf-8", "replace")
            for line in text.split("\r\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    trailers[k.strip().lower()] = v.strip()
        else:
            msg += chunk
    return msg, trailers


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
        self.enable_offline_pan6 = True
        self.enable_115 = True
        self.enable_javdb = True

        self.offline_save_path = "0"
        self.offline_app_ver = "4.8.2"
        self.offline_timeout = 15

        # info_hash -> pickcode 本地缓存（同一会话二次播放直接命中）
        self._cache_pickcode = {}

        # 6盘离线
        self.pan6_token = ""
        self.pan6_refresh = ""
        self.pan6_user = ""
        self.pan6_pass = ""
        self.pan6_save_path = PAN6_DEFAULT_SAVE_PATH
        self.pan6_timeout = PAN6_POLL_TIMEOUT
        self._pan6_login_error = ""
        self._sess_pan6 = None
        # info_hash -> 6盘文件路径 本地缓存
        self._cache_pan6_file = {}

        if requests:
            self.s = self.session = self.sess = requests.Session()
            self._sess_jav = requests.Session()
            self._sess_pan6 = requests.Session()
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
        if "enableOfflinePan6" in extend:
            self.enable_offline_pan6 = bool(extend["enableOfflinePan6"])
        if extend.get("offlineSavePath"):
            self.offline_save_path = str(extend["offlineSavePath"])
        if extend.get("offlineAppVer"):
            self.offline_app_ver = str(extend["offlineAppVer"])

        pan6 = extend.get("pan6") if isinstance(extend.get("pan6"), dict) else {}
        self.pan6_token = (
            _to_text(extend.get("pan6Token") or extend.get("pan6_token")
                     or extend.get("pan6AccessToken") or pan6.get("token")
                     or pan6.get("access_token"))
            or _env("PAN6_TOKEN")
        )
        self.pan6_refresh = (
            _to_text(extend.get("pan6Refresh") or extend.get("pan6_refresh")
                     or pan6.get("refresh_token"))
            or _env("PAN6_REFRESH")
        )
        self.pan6_user = (
            _to_text(extend.get("pan6User") or extend.get("pan6_user")
                     or extend.get("pan6Account") or pan6.get("username")
                     or pan6.get("user"))
            or _env("PAN6_USER")
        )
        self.pan6_pass = (
            _to_text(extend.get("pan6Pass") or extend.get("pan6_pass")
                     or extend.get("pan6Password") or pan6.get("password"))
            or _env("PAN6_PASS")
        )
        self.pan6_save_path = _to_text(
            extend.get("pan6SavePath") or pan6.get("save_path")
            or PAN6_DEFAULT_SAVE_PATH)
        if extend.get("pan6Timeout"):
            try:
                self.pan6_timeout = max(5, int(extend["pan6Timeout"]))
            except Exception:
                pass

    def homeContent(self, filter=None):
        classes = []
        if self.enable_javdb:
            classes.extend(dict(c) for c in JAVDB_CLASSES)
        if self.enable_offline_pan6:
            classes.append({"type_id": "pan6", "type_name": "6盘"})
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
        if t == "pan6" or t.startswith(PAN6_BROWSE_PREFIX):
            return self._pan6_category(t, pg)
        return self._115_category(t, pg)

    def _pan6_category(self, tid, pg):
        page = self._safe_int(pg, 1)
        path = "/"
        t = _to_text(tid)
        if t.startswith(PAN6_BROWSE_PREFIX):
            rest = t[len(PAN6_BROWSE_PREFIX):].strip()
            if rest:
                path = rest
        if not path.startswith("/"):
            path = "/" + path
        if not self._p6_ensure_login():
            return {"list": [], "page": page, "pagecount": 1,
                    "limit": PAGE_SIZE, "total": 0}
        out = []
        seen = set()
        for c in self._p6_list_children(path):
            name = c.get("name") or ""
            cpath = c.get("path") or ""
            if not name or not cpath:
                continue
            if c.get("is_dir"):
                vid = PAN6_BROWSE_PREFIX + cpath
                if vid in seen:
                    continue
                seen.add(vid)
                out.append({
                    "vod_id": vid,
                    "vod_name": name,
                    "vod_pic": FOLDER_PIC,
                    "vod_remarks": "目录",
                    "vod_tag": "folder",
                    "ratio": 1.33,
                })
            elif self.isVideoFormat(name):
                vid = "%s%s#%s" % (PAN6_FILE_PREFIX, c.get("identity") or "", cpath)
                if vid in seen:
                    continue
                seen.add(vid)
                out.append({
                    "vod_id": vid,
                    "vod_name": name,
                    "vod_pic": VIDEO_PIC,
                    "vod_remarks": _format_size(c.get("size")),
                    "ratio": 1.33,
                })
        return {"list": out, "page": page, "pagecount": page,
                "limit": PAGE_SIZE, "total": len(out)}

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

        if vid.startswith(PAN6_BROWSE_PREFIX) or vid.startswith(PAN6_FILE_PREFIX):
            return self._pan6_detail(vid)

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

    def _pan6_detail(self, vid):
        if vid.startswith(PAN6_FILE_PREFIX):
            rest = vid[len(PAN6_FILE_PREFIX):]
            identity, _, path = rest.partition("#")
            name = path.rsplit("/", 1)[-1] if path else "6盘文件"
            return {"list": [{
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": VIDEO_PIC,
                "vod_content": "文件名: %s" % name,
                "vod_play_from": PLAY_FROM,
                "vod_play_url": "播放$%s" % vid,
            }]}
        path = vid[len(PAN6_BROWSE_PREFIX):] if vid.startswith(PAN6_BROWSE_PREFIX) else vid
        if not path.startswith("/"):
            path = "/" + path
        name = path.rsplit("/", 1)[-1] or "6盘"
        if not self._p6_ensure_login():
            return {"list": [{
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": FOLDER_PIC,
                "vod_content": "6盘未配置账号（%s）" % (self._pan6_login_error or "请配置 pan6User/pan6Pass"),
            }]}
        eps = []
        for c in self._p6_list_children(path):
            if c.get("is_dir") or not c.get("path"):
                continue
            cname = c.get("name") or c.get("path")
            if not self.isVideoFormat(cname):
                continue
            eps.append("%s$%s%s#%s" % (cname, PAN6_FILE_PREFIX,
                                       c.get("identity") or "", c.get("path")))
        return {"list": [{
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": FOLDER_PIC,
            "vod_content": "6盘目录: %s" % path,
            "vod_play_from": PLAY_FROM if eps else "",
            "vod_play_url": "#".join(eps),
        }]}

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
        if self.enable_offline_pan6:
            info.append("6盘离线：提交到6盘云端下载，完成后自动取直链播放")

        froms, urls = [], []

        magnet_items = [(i, g, (g.get("hash") or "").strip()) for i, g in enumerate(magnets)]
        magnet_items = [(i, g, h) for i, g, h in magnet_items if h]

        if self.enable_offline_pan6 and magnet_items:
            eps = []
            used = set()
            for i, g, h in magnet_items:
                label = self._unique_jav_label(g, i, num, used)
                b64 = base64.b64encode(("magnet:?xt=urn:btih:%s" % h).encode("utf-8")).decode("ascii")
                eps.append("%s$%s%s" % (label, OFF_PREFIX_6PAN, b64))
            if eps:
                froms.append("6盘离线")
                urls.append("#".join(eps))

        if self.emby and self.emby_key:
            froms.append("正片")
            urls.append("播放$emby:%s|%s" % (mid, num))

        if movie.get("preview_video_url") or movie.get("has_preview_video"):
            froms.append("预告片")
            urls.append("预告片$preview:%s" % mid)

        if self.enable_magnet_play and magnet_items:
            eps = []
            used = set()
            for i, g, h in magnet_items:
                label = self._unique_jav_label(g, i, num, used)
                eps.append("%s$magnet:?xt=urn:btih:%s" % (label, h))
            if eps:
                froms.append("磁力")
                urls.append("#".join(eps))

        if self.enable_offline_115 and magnet_items:
            eps = []
            used = set()
            for i, g, h in magnet_items:
                label = self._unique_jav_label(g, i, num, used)
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

        if vid.startswith(OFF_PREFIX_6PAN):
            b64 = vid[len(OFF_PREFIX_6PAN):].strip()
            try:
                magnet = base64.b64decode(b64.encode("ascii")).decode("utf-8")
            except Exception:
                return {"parse": 0, "jx": 0, "url": "", "header": {},
                        "msg": "磁力解码失败"}
            return self._submit_offline_pan6(magnet)

        if vid.startswith("pan6off:"):
            return self._submit_offline_pan6(vid[8:].strip())

        if vid.startswith(PAN6_FILE_PREFIX):
            rest = vid[len(PAN6_FILE_PREFIX):]
            identity, _, path = rest.partition("#")
            if not self._p6_ensure_login():
                return {"parse": 0, "jx": 0, "url": "", "header": {},
                        "msg": "6盘未配置账号（%s）" % (self._pan6_login_error or "请配置 pan6User/pan6Pass")}
            info = None
            if identity:
                msg = _p6_enc_str(1, identity)
                data, _err = self._p6_grpc("/v6.services.pub.PubUserFile/Get", msg,
                                           attempts=1, timeout=12)
                if data:
                    f = data if isinstance(data, dict) else _p6_dec_fields(data)
                    info = {
                        "identity": _p6_as_str(f.get(1)) or identity,
                        "path": _p6_as_str(f.get(5)) or path,
                    }
            if not info:
                info = {"identity": identity, "path": path}
            addr, err = self._p6_direct_url(info.get("identity") or "",
                                            info.get("path") or path)
            if not addr:
                return {"parse": 0, "jx": 0, "url": "", "header": {},
                        "msg": "6盘取链失败: %s" % err}
            return {
                "parse": 0,
                "jx": 0,
                "url": addr,
                "header": {"User-Agent": PAN6_UA, "Referer": PAN6_SITE + "/"},
            }

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
        """提交/解析 115 离线。

        顺序：
          0) 本地 pickcode 缓存命中 -> 直接播
          1) （av.py 磁力无 dn，跳过按名搜网盘）
          2) 按 info_hash 查离线任务 -> 已完成则播
          3) 提交离线；提交失败也兜底再搜一次网盘
        """
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

        # 0) 本地缓存命中
        cached = self._cache_pickcode.get(info_hash)
        if cached:
            res = self._resolve_pickcode(cached)
            if res.get("url"):
                return res
            self._cache_pickcode.pop(info_hash, None)

        name_hint = ""

        # 2) 再看离线任务里是否已完成
        task = None
        try:
            task = self._offline_find_task(info_hash)
        except Exception:
            task = None
        if task:
            done, failed, name_or_msg = self._offline_task_state(task)
            if name_or_msg:
                name_hint = name_or_msg
            if done:
                pickcode = self._find_pickcode_by_name(name_or_msg, retries=3, interval=1)
                if pickcode:
                    self._cache_pickcode[info_hash] = pickcode
                    return self._resolve_pickcode(pickcode)

        # 3) 才真正提交离线
        try:
            res = self._offline_add(magnet)
        except Exception as e:
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                    "msg": "提交离线失败：%s" % e}

        if not res.get("state"):
            msg = str(res.get("message") or res.get("error") or "提交失败")
            # 提交失败也兜底搜网盘
            if name_hint:
                pickcode = self._find_pickcode_by_name(name_hint, retries=3, interval=1)
                if pickcode:
                    self._cache_pickcode[info_hash] = pickcode
                    return self._resolve_pickcode(pickcode)
            if "已存在" not in msg and "重复" not in msg:
                return {"parse": 0, "jx": 0, "url": "", "header": {},
                        "msg": "115离线提交失败：%s" % msg}

        # 提交后，用任务名再搜一次
        if not name_hint:
            try:
                task = self._offline_find_task(info_hash)
                if task:
                    name_hint = task.get("name") or task.get("file_name") or ""
            except Exception:
                pass

        if name_hint:
            pickcode = self._find_pickcode_by_name(name_hint, retries=1, interval=0)
            if pickcode:
                self._cache_pickcode[info_hash] = pickcode
                return self._resolve_pickcode(pickcode)

        done, name_or_msg = self._offline_wait_done(info_hash)

        if not done:
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                    "msg": "已提交115离线，正在下载中（%s），请稍后重试"
                           % (name_or_msg or "等待完成")}

        pickcode = self._find_pickcode_by_name(name_or_msg or name_hint, retries=3, interval=1)
        if not pickcode:
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                    "msg": "离线已完成，但115网盘里还没搜到文件，请稍后重试"}

        self._cache_pickcode[info_hash] = pickcode
        return self._resolve_pickcode(pickcode)

    # ============ 6盘离线 ============

    @staticmethod
    def _p6_sign(path, ts, token=None):
        path = "/" + str(path or "").lstrip("/")
        r = "%s%s%s%s" % (path, ts, PAN6_APP_ID, PAN6_APP_VER)
        if token:
            r += "Bearer " + token
        return hashlib.md5((r + PAN6_APP_SEC).encode("utf-8")).hexdigest()

    def _p6_grpc(self, method, msg, token=None, attempts=2, timeout=15):
        if self._sess_pan6 is None:
            if not requests:
                return None, "requests 模块不可用"
            self._sess_pan6 = requests.Session()
        path = "/" + str(method or "").lstrip("/")
        tok = token if token is not None else (self.pan6_token or "")
        ts = str(int(time.time() * 1000))
        headers = {
            "Content-Type": "application/grpc-web+proto",
            "X-User-Agent": "grpc-web-javascript/0.1",
            "Accept": "application/grpc-web+proto",
            "timestamp": ts,
            "appid": PAN6_APP_ID,
            "appversion": PAN6_APP_VER,
            "sign": self._p6_sign(path, ts, tok or None),
        }
        if tok:
            headers["authorization"] = "Bearer " + tok
        last = None
        for i in range(max(1, attempts)):
            try:
                r = self._sess_pan6.post(PAN6_API_BASE + path, headers=headers,
                                         data=_p6_frame(msg), timeout=timeout)
                body, trailers = _p6_parse_grpc_web(r.content or b"")
                status = (trailers.get("grpc-status")
                          or r.headers.get("grpc-status")
                          or r.headers.get("Grpc-Status"))
                gmsg = (trailers.get("grpc-message")
                        or r.headers.get("grpc-message")
                        or r.headers.get("Grpc-Message") or "")
                if status is None and r.content:
                    status = "0"
                if status and str(status) != "0":
                    err = "grpc %s %s" % (status, gmsg)
                    if str(status) == "16" and self.pan6_refresh and tok:
                        if self._p6_try_refresh():
                            return self._p6_grpc(path, msg, token=self.pan6_token,
                                                 attempts=1, timeout=timeout)
                    last = err
                    if str(status) in ("4", "14") and i + 1 < attempts:
                        time.sleep(0.3)
                        continue
                    return None, err
                if status is None and not body:
                    return None, "空响应"
                return (_p6_dec_fields(body) if body else {}), ""
            except Exception as e:
                last = str(e)
                if i + 1 < attempts:
                    time.sleep(0.25)
        return None, last or "请求失败"

    def _p6_login(self):
        pwd = str(self.pan6_pass or "").strip()
        if not pwd:
            return False, "未配置6盘密码"
        if not re.fullmatch(r"[0-9a-fA-F]{32}", pwd):
            pwd = hashlib.md5(pwd.encode("utf-8")).hexdigest()
        cap = json.dumps({"ticket": "tvbox", "randstr": "tvbox", "type": "tencent"},
                         ensure_ascii=False)
        msg = b""
        msg += _p6_enc_str(1, self.pan6_user)
        msg += _p6_enc_str(2, pwd)
        msg += _p6_enc_str(4, self.pan6_user)
        msg += _p6_enc_i32(5, 3)
        msg += _p6_enc_str(9, cap)
        msg += _p6_enc_str(11, "86")
        msg += _p6_enc_str(12, "web")
        msg += _p6_enc_i32(17, 1)
        data, err = self._p6_grpc("/v6.services.pub.PubUser/Login", msg,
                                  token="", attempts=2, timeout=18)
        if err or not data:
            return False, err or "登录失败"
        tok = data.get(1)
        if not tok:
            return False, "登录无token"
        tk = tok if isinstance(tok, dict) else _p6_dec_fields(tok)
        at = _p6_as_str(tk.get(5))
        rt = _p6_as_str(tk.get(6))
        if not at:
            return False, "登录无token"
        self.pan6_token = at
        self.pan6_refresh = rt or ""
        return True, ""

    def _p6_try_refresh(self):
        if not self.pan6_refresh:
            return False
        msg = b""
        if self.pan6_token:
            msg += _p6_enc_str(5, self.pan6_token)
        if self.pan6_refresh:
            msg += _p6_enc_str(6, self.pan6_refresh)
        data, err = self._p6_grpc("/v6.services.pub.PubUser/Refresh", msg,
                                  token=self.pan6_token, attempts=1, timeout=12)
        if err or not data:
            return False
        tk = data if isinstance(data, dict) else _p6_dec_fields(data)
        at = _p6_as_str(tk.get(5))
        rt = _p6_as_str(tk.get(6))
        if at:
            self.pan6_token = at
        if rt:
            self.pan6_refresh = rt
        return bool(self.pan6_token)

    def _p6_ensure_login(self):
        if self.pan6_token:
            return True
        if self.pan6_user and self.pan6_pass:
            ok, err = self._p6_login()
            if ok:
                return True
            self._pan6_login_error = err or "登录失败"
        return False

    def _p6_offline_add(self, magnet):
        msg = b""
        msg += _p6_enc_str(8, magnet)
        if self.pan6_save_path:
            msg += _p6_enc_str(20, self.pan6_save_path)
        data, err = self._p6_grpc("/v6.services.pub.PubOfflineTask/Add", msg,
                                  attempts=2, timeout=18)
        if err:
            return None, err
        return data or {}, ""

    def _p6_offline_list(self, page=1, limit=20):
        scan = b""
        scan += _p6_enc_i64(2, limit)
        scan += _p6_enc_i32(4, max(1, int(page or 1)))
        data, err = self._p6_grpc("/v6.services.pub.PubOfflineTask/List",
                                  _p6_enc_msg(3, scan), attempts=2, timeout=12)
        if err or not data:
            return [], err or "离线列表失败"
        return _p6_as_msgs(data.get(1) if isinstance(data, dict) else None), ""

    def _p6_offline_find_task(self, info_hash):
        for page in (1, 2):
            tasks, err = self._p6_offline_list(page)
            if err or not tasks:
                break
            for tb in tasks:
                t = _p6_dec_fields(tb)
                url = _p6_as_str(t.get(8)).lower()
                h = self._magnet_hash(url)
                if h and h == info_hash.lower():
                    return t
        return None

    @staticmethod
    def _p6_task_state(task):
        if not task:
            return False, False, "任务未找到"
        file = _p6_as_str(task.get(6))
        status = _p6_as_int(task.get(3), -1)
        code = _p6_as_int(task.get(12), 0)
        msg = _p6_as_str(task.get(13))
        name = _p6_as_str(task.get(10)) or file
        try:
            progress = float(_p6_as_int(task.get(16), 0))
        except Exception:
            progress = 0.0
        if code or msg:
            return False, True, msg or ("离线任务失败 code=%d" % code)
        if file or status >= 1000:
            return True, False, name or file
        if status in (0, 1, 2, 10) or status < 0 or progress < 100:
            if progress > 0:
                return False, False, "%s %d%%" % (name or "下载中", int(progress))
            return False, False, name or "下载中"
        return False, False, name or "等待完成"

    def _p6_resolve_task_file(self, task):
        """已完成任务的 file 字段常为空，按任务名在保存目录下解析实际路径。"""
        file = _p6_as_str(task.get(6))
        if file:
            return file
        name = _p6_as_str(task.get(10))
        if not name:
            return ""
        bases = []
        if self.pan6_save_path:
            bases.append(self.pan6_save_path)
        for b in PAN6_INBOX_PATHS:
            if b not in bases:
                bases.append(b)
        for _attempt in range(3):
            for base in bases:
                base = base.rstrip("/") or ""
                info = self._p6_file_info(base + "/" + name)
                if info:
                    return info.get("path") or (base + "/" + name)
            for base in bases:
                for c in self._p6_list_children(base or "/"):
                    if (c.get("name") or "") == name:
                        return c.get("path") or ""
            time.sleep(1)
        return ""

    def _p6_wait_done_task(self, info_hash, timeout=None):
        deadline = time.time() + (timeout if timeout else self.pan6_timeout)
        last = ""
        while time.time() < deadline:
            try:
                task = self._p6_offline_find_task(info_hash)
            except Exception:
                task = None
            done, failed, msg = self._p6_task_state(task)
            if done and task:
                return task, ""
            if failed:
                return None, msg
            if msg:
                last = msg
            time.sleep(PAN6_POLL_INTERVAL)
        return None, last

    def _p6_file_info(self, path):
        msg = _p6_enc_str(5, path)
        data, err = self._p6_grpc("/v6.services.pub.PubUserFile/Get", msg,
                                  attempts=2, timeout=12)
        if err or not data:
            return None
        f = data if isinstance(data, dict) else _p6_dec_fields(data)
        return {
            "identity": _p6_as_str(f.get(1)),
            "name": _p6_as_str(f.get(4)),
            "path": _p6_as_str(f.get(5)) or path,
            "is_dir": bool(_p6_as_int(f.get(13))),
            "size": _p6_as_int(f.get(7)),
        }

    def _p6_list_children(self, path, limit=50):
        parent = _p6_enc_str(5, path)
        scan = _p6_enc_i64(2, limit)
        scan += _p6_enc_msg(3, _p6_enc_str(1, "update") + _p6_enc_str(2, "false"))
        msg = _p6_enc_msg(1, parent) + _p6_enc_msg(3, scan)
        data, err = self._p6_grpc("/v6.services.pub.PubUserFile/List", msg,
                                  attempts=1, timeout=15)
        if err or not data:
            return []
        out = []
        for fb in _p6_as_msgs(data.get(1) if isinstance(data, dict) else None):
            f = _p6_dec_fields(fb)
            out.append({
                "identity": _p6_as_str(f.get(1)),
                "name": _p6_as_str(f.get(4)),
                "path": _p6_as_str(f.get(5)),
                "is_dir": bool(_p6_as_int(f.get(13))),
                "size": _p6_as_int(f.get(7)),
            })
        return out

    def _p6_pick_video(self, path):
        info = self._p6_file_info(path)
        if not info:
            return None
        if not info["is_dir"]:
            return info
        children = [c for c in self._p6_list_children(info["path"])
                    if not c["is_dir"] and c["path"]]
        vids = [c for c in children
                if self.isVideoFormat(c["name"] or c["path"])]
        if not vids:
            vids = children
        if not vids:
            sub_dirs = [c for c in self._p6_list_children(info["path"])
                        if c["is_dir"] and c["path"]]
            for d in sub_dirs[:3]:
                sub = [c for c in self._p6_list_children(d["path"])
                       if not c["is_dir"] and c["path"]
                       and self.isVideoFormat(c["name"] or c["path"])]
                if sub:
                    sub.sort(key=lambda c: c.get("size") or 0, reverse=True)
                    return sub[0]
            return None
        vids.sort(key=lambda c: c.get("size") or 0, reverse=True)
        return vids[0]

    def _p6_direct_url(self, identity, path):
        msg = b""
        if identity:
            msg += _p6_enc_str(1, identity)
        msg += _p6_enc_i32(2, 1)
        if path:
            msg += _p6_enc_str(3, path)
        msg += _p6_enc_str(6, PAN6_UA)
        for c in ("h264", "hevc", "h265", "vp9", "av1", "mpeg4"):
            msg += _p6_enc_str(7, c)
        for c in ("aac", "mp3", "opus", "ac3", "eac3"):
            msg += _p6_enc_str(8, c)
        data, err = self._p6_grpc("/v6.services.pub.PubUserFile/GetDirectDownloadAddress",
                                  msg, attempts=3, timeout=18)
        if err or not data:
            return "", err or "取链失败"
        addr = _p6_as_str(data.get(1))
        if not addr:
            return "", "无下载地址"
        return addr, ""

    def _p6_play_path(self, path):
        picked = self._p6_pick_video(path)
        if not picked:
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                    "msg": "6盘文件不存在: %s" % path}
        addr, err = self._p6_direct_url(picked.get("identity") or "",
                                        picked.get("path") or path)
        if not addr:
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                    "msg": "6盘取链失败: %s" % err}
        return {
            "parse": 0,
            "jx": 0,
            "url": addr,
            "header": {"User-Agent": PAN6_UA, "Referer": PAN6_SITE + "/"},
        }

    def _submit_offline_pan6(self, magnet):
        """提交/解析 6盘 离线，完成后取直链播放。

        顺序：
          0) 本地文件路径缓存命中 -> 直接取直链
          1) 按 info_hash 查离线任务 -> 已完成则取直链
          2) 提交离线；轮询等待；完成后取直链
        """
        if not self._p6_ensure_login():
            tip = self._pan6_login_error or "请配置 pan6User/pan6Pass 或 pan6Token"
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                    "msg": "未配置6盘账号，无法提交离线（%s）" % tip}

        info_hash = self._magnet_hash(magnet)
        if not info_hash:
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                    "msg": "无法从磁力中解析 info_hash"}

        cached = self._cache_pan6_file.get(info_hash)
        if cached:
            res = self._p6_play_path(cached)
            if res.get("url"):
                return res
            self._cache_pan6_file.pop(info_hash, None)

        task = None
        try:
            task = self._p6_offline_find_task(info_hash)
        except Exception:
            task = None
        if task:
            done, failed, name_or_msg = self._p6_task_state(task)
            if failed:
                return {"parse": 0, "jx": 0, "url": "", "header": {},
                        "msg": "6盘离线任务失败: %s" % name_or_msg}
            if done:
                file = self._p6_resolve_task_file(task)
                if file:
                    self._cache_pan6_file[info_hash] = file
                    return self._p6_play_path(file)

        try:
            res, err = self._p6_offline_add(magnet)
        except Exception as e:
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                    "msg": "提交6盘离线失败：%s" % e}
        if err:
            # 提交失败也可能任务已存在，兜底再查一次
            try:
                task = self._p6_offline_find_task(info_hash)
            except Exception:
                task = None
            if task:
                done, failed, name_or_msg = self._p6_task_state(task)
                if done:
                    file = self._p6_resolve_task_file(task)
                    if file:
                        self._cache_pan6_file[info_hash] = file
                        return self._p6_play_path(file)
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                    "msg": "6盘离线提交失败：%s" % err}

        task, wait_msg = self._p6_wait_done_task(info_hash)
        if task:
            file = self._p6_resolve_task_file(task)
            if file:
                self._cache_pan6_file[info_hash] = file
                return self._p6_play_path(file)

        return {"parse": 0, "jx": 0, "url": "", "header": {},
                "msg": "已提交6盘离线，正在下载中（%s），请稍后重试"
                       % (wait_msg or "等待完成")}

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
            mt = str(ext.get("mtype") or "1")
            mid = (ext.get("maker") or "").strip()
            if not mid:
                return [], False
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

    @staticmethod
    def _jav_magnet_label(g, i, num):
        raw_nm = (g.get("name") or "").strip() or num or ("资源%d" % (i + 1))
        safe_nm = re.sub(r"\s+", " ", raw_nm.translate(_SAFE_CHARS)).strip()[:40] or ("资源%d" % (i + 1))
        sz = _size_mb(g.get("size"))
        return safe_nm + (" " + sz if sz else "")

    @classmethod
    def _unique_jav_label(cls, g, i, num, used):
        """保证同一播放源内选集名唯一。

        冲突时优先追加短 hash，仍冲突则追加序号。
        """
        base = cls._jav_magnet_label(g, i, num)
        if base not in used:
            used.add(base)
            return base

        h = (g.get("hash") or "").strip()[:8]
        cand = "%s [%s]" % (base, h) if h else base
        if cand not in used:
            used.add(cand)
            return cand

        n = 2
        while True:
            cand2 = "%s (%d)" % (cand, n)
            if cand2 not in used:
                used.add(cand2)
                return cand2
            n += 1

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