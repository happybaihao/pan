import json
import hashlib
import time
import threading
import base64
import struct
import re
import urllib.request
import urllib.parse
import urllib.error

try:
    import requests
except ImportError:
    requests = None

try:
    from concurrent.futures import (ThreadPoolExecutor,
        wait as _cf_wait,
        FIRST_COMPLETED)
except ImportError:
    ThreadPoolExecutor = None
    _cf_wait = None
    FIRST_COMPLETED = None

PAN6_USER = ""#6盘账号
PAN6_PASS = ""#6盘密码
PAN6_TOKEN = ""
PAN6_REFRESH = ""

PAN6_API_BASE = "https://grpcuserapi.2dland.cn"
PAN6_SITE = "https://drive.2dland.cn"
PAN6_APP_ID = "2dland/web"
PAN6_APP_VER = "202603182100"
PAN6_APP_SEC = "izzX0kNu3sIIq3CK"
PAN6_UA = ("Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36")

PAN6_BROWSE_PREFIX = "pan6:"
PAN6_FILE_PREFIX = "pan6f:"

OFF_PREFIX_6PAN = "http://6panoff/"
PAN6_POLL_TIMEOUT = 30
PAN6_POLL_INTERVAL = 1
PAN6_PLAY_WAIT = 30
PAN6_DEFAULT_SAVE_PATH = "/最近接收"
PAN6_INBOX_PATHS = ("/最近接收", "/")
PAN6_SKIP_KEYWORDS = ("sample", "trailer", "preview", "预告", "预告片",
    "cm.", "cm_", "-cm", "_cm")

PAN6_PAGE_SIZE = 50
PAN6_SEARCH_LIMIT = 50

PAN6_WALK_MAX_DEPTH = 6
PAN6_WALK_MAX_ITEMS = 66
PAN6_WALK_PAGE_LIMIT = 50
PAN6_SEARCH_COOLDOWN = 5

PAN6_URL_TTL = 1800
PAN6_SUBMIT_COOLDOWN = 8
PAN6_TASK_LIST_TTL = 2.0
PAN6_FIND_PAGES = 4
PAN6_FIND_PAGE_LIMIT = 50
PAN6_MAX_TRACKED = 3
PAN6_MONITOR_IDLE = 10.0
PAN6_MONITOR_BUSY = 3.0
PAN6_MONITOR_MAX_AGE = 7200
PAN6_TASK_WAIT_MAX = 45
PAN6_RESOLVE_MAX_AGE = 600
PAN6_FAILED_TTL = 60
PAN6_FILE_URL_TTL = 1500
PAN6_FILE_URL_FAIL_TTL = 10
PAN6_FILE_URL_CACHE_MAX = 200
PAN6_FILE_INFO_TTL = 120
PAN6_FILE_INFO_CACHE_MAX = 200
PAN6_DIR_TTL = 30
PAN6_DIR_LIMIT = 100
PAN6_DIR_CACHE_MAX = 300
PAN6_SEARCH_TTL = 60
PAN6_LOGIN_FAIL_TTL = 10

_PAN6_SESSION_HEADERS = {
    "User-Agent": PAN6_UA,
    "Accept": "*/*",
    "Origin": PAN6_SITE,
    "Referer": PAN6_SITE + "/",
}
_PAN6_GRPC_HEADERS = {
    "Content-Type": "application/grpc-web+proto",
    "X-User-Agent": "grpc-web-javascript/0.1",
    "Accept": "application/grpc-web+proto",
}

FOLDER_PIC = "https://img.icons8.com/fluency/96/folder-invoices--v1.png"
VIDEO_PIC = "https://img.icons8.com/color/48/video.png"
VIDEO_EXTS = (
    ".mp4", ".mkv", ".webm", ".avi", ".wmv", ".flv", ".mov",
    ".mpeg", ".mpg", ".m4v", ".ts", ".m2ts", ".3gp", ".rm",
    ".rmvb", ".iso",
)

def _to_text(v):
    return str(v or "").strip()

def _safe_int(v, default=0):
    try:
        return int(v)
    except Exception:
        try:
            return int(str(v or "").strip() or default)
        except Exception:
            return default

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
        if fn not in out:
            out[fn] = v
        elif isinstance(out[fn], list):
            out[fn].append(v)
        else:
            out[fn] = [out[fn], v]
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

class Pan6Spider:
    def __init__(self):
        self.s = None
        self.session = None
        self.sess = None
        self.access_token = ""
        self.refresh_token = ""
        self.pan6_user = PAN6_USER
        self.pan6_pass = PAN6_PASS
        self._login_error = ""
        self._login_fail_ts = 0.0
        self._p6_last_search_ts = 0.0
        self.pan6_save_path = PAN6_DEFAULT_SAVE_PATH
        self.pan6_timeout = PAN6_POLL_TIMEOUT
        self.enable_offline_pan6 = True
        self._cache_pan6_file = {}
        self._cache_pan6_url = {}
        self._cache_pan6_task = {}
        self._p6_last_submit = {}
        self._p6_file_url_cache = {}
        self._p6_file_url_fail = {}
        self._p6_file_info_cache = {}
        self._p6_dir_cache = {}
        self._p6_walk_cache = {"ts": 0.0, "items": []}
        self._p6_task_list_ts = 0.0
        self._p6_task_list_tasks = []
        self._p6_monitor_thread = None
        self._p6_monitor_stop = False
        self._p6_monitor_lock = threading.Lock()
        self.enable_offline_monitor = True
        self.enable_offline_prewarm = True
        self.pan6_prewarm_count = 1
        self.pan6_find_pages = PAN6_FIND_PAGES
        self.pan6_file_url_ttl = PAN6_FILE_URL_TTL
        self.pan6_file_url_fail_ttl = PAN6_FILE_URL_FAIL_TTL
        self.pan6_file_info_ttl = PAN6_FILE_INFO_TTL
        self.pan6_dir_ttl = PAN6_DIR_TTL
        self.pan6_dir_limit = PAN6_DIR_LIMIT
        self.pan6_search_ttl = PAN6_SEARCH_TTL
        self.pan6_login_fail_ttl = PAN6_LOGIN_FAIL_TTL
        self.pan6_play_wait = PAN6_PLAY_WAIT
        self._offline_lock = threading.RLock()
        self._offline_pending = set()

    def getName(self):
        return "6盘"

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
        pan6 = extend.get("pan6") if isinstance(extend.get("pan6"), dict) else {}
        self.pan6_user = (
            _to_text(extend.get("pan6User") or extend.get("pan6_user")
                or extend.get("pan6Account") or pan6.get("username")
                or pan6.get("user")) or PAN6_USER
        )
        self.pan6_pass = (
            _to_text(extend.get("pan6Pass") or extend.get("pan6_pass")
                or extend.get("pan6Password") or pan6.get("password")) or PAN6_PASS
        )
        self.access_token = (
            _to_text(extend.get("pan6Token") or extend.get("pan6_token")
                or extend.get("pan6AccessToken") or pan6.get("token")
                or pan6.get("access_token")) or PAN6_TOKEN
        )
        self.refresh_token = (
            _to_text(extend.get("pan6Refresh") or extend.get("pan6_refresh")
                or pan6.get("refresh_token")) or PAN6_REFRESH
        )
        if extend.get("pan6SavePath") or pan6.get("save_path"):
            self.pan6_save_path = _to_text(
                extend.get("pan6SavePath") or pan6.get("save_path"))
        if "enableOfflinePan6" in extend:
            self.enable_offline_pan6 = bool(extend["enableOfflinePan6"])
        if extend.get("pan6Timeout"):
            try:
                self.pan6_timeout = max(5, int(extend["pan6Timeout"]))
            except Exception:
                pass
        for _key in ("pan6PlayWait", "pan6FirstWait"):
            if extend.get(_key) is not None:
                try:
                    self.pan6_play_wait = max(0, min(120, int(extend[_key])))
                except Exception:
                    pass
                break
        if "pan6Monitor" in extend:
            self.enable_offline_monitor = bool(extend["pan6Monitor"])
        if "pan6Prewarm" in extend:
            self.enable_offline_prewarm = bool(extend["pan6Prewarm"])
        if extend.get("pan6PrewarmCount") is not None:
            try:
                self.pan6_prewarm_count = max(0, int(extend["pan6PrewarmCount"]))
            except Exception:
                pass
        if extend.get("pan6FindPages") is not None:
            try:
                self.pan6_find_pages = max(1, min(10, int(extend["pan6FindPages"])))
            except Exception:
                pass
        for _key, _attr, _lo, _hi in (
            ("pan6FileUrlTTL", "pan6_file_url_ttl", 10, 86400),
            ("pan6UrlFailTTL", "pan6_file_url_fail_ttl", 0, 600),
            ("pan6FileInfoTTL", "pan6_file_info_ttl", 0, 3600),
            ("pan6DirTTL", "pan6_dir_ttl", 0, 600),
            ("pan6DirLimit", "pan6_dir_limit", 10, 500),
            ("pan6SearchTTL", "pan6_search_ttl", 0, 3600),
            ("pan6LoginFailTTL", "pan6_login_fail_ttl", 0, 600),
        ):
            _val = extend.get(_key, pan6.get(_key))
            if _val is None:
                continue
            try:
                setattr(self, _attr, max(_lo, min(_hi, int(_val))))
            except Exception:
                pass
        if requests and self.session is None:
            self.session = requests.Session()
            self.session.headers.update(_PAN6_SESSION_HEADERS)
            self.s = self.session
            self.sess = self.session

    def homeContent(self, filter=None):
        return {"class": [{"type_id": "root", "type_name": "我的文件"}],
            "filters": {}}

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        page = max(1, _safe_int(pg, 1))
        t = _to_text(tid)
        if not self._p6_ensure_login():
            return {"list": [], "page": page, "pagecount": 1,
                "limit": PAN6_PAGE_SIZE, "total": 0}
        path = "/"
        if t.startswith(PAN6_BROWSE_PREFIX):
            rest = t[len(PAN6_BROWSE_PREFIX):].strip()
            if rest:
                path = rest
        if not path.startswith("/"):
            path = "/" + path
        out = []
        seen = set()
        for c in self._p6_list_children(path, self.pan6_dir_limit):
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
                    "vod_id": vid, "vod_name": name, "vod_pic": FOLDER_PIC,
                    "vod_remarks": "目录", "vod_tag": "folder", "ratio": 1.33,
                })
            elif self.isVideoFormat(name):
                vid = "%s%s#%s" % (PAN6_FILE_PREFIX, c.get("identity") or "",
                    cpath)
                if vid in seen:
                    continue
                seen.add(vid)
                out.append({
                    "vod_id": vid, "vod_name": name, "vod_pic": VIDEO_PIC,
                    "vod_remarks": _format_size(c.get("size")),
                    "ratio": 1.33,
                })
        start = (page - 1) * PAN6_PAGE_SIZE
        page_items = out[start:start + PAN6_PAGE_SIZE] \
            if start else out[:PAN6_PAGE_SIZE]
        pagecount = max(1, (len(out) + PAN6_PAGE_SIZE - 1) // PAN6_PAGE_SIZE)
        return {"list": page_items, "page": page, "pagecount": pagecount,
            "limit": PAN6_PAGE_SIZE, "total": len(out)}

    def detailContent(self, ids):
        vid = str(ids[0]) if isinstance(ids, (list, tuple)) and ids \
            else str(ids or "")
        if vid.startswith(PAN6_FILE_PREFIX):
            rest = vid[len(PAN6_FILE_PREFIX):].replace("|", "#")
            identity, _, path = rest.partition("#")
            name = path.rsplit("/", 1)[-1] if path else "6盘文件"
            return {"list": [{
                "vod_id": vid, "vod_name": name, "vod_pic": VIDEO_PIC,
                "vod_content": "文件名: %s" % name, "vod_play_from": "6盘",
                "vod_play_url": "%s$%s" % (name or "播放",
                    vid.replace("#", "|")),
            }]}
        if vid.startswith(PAN6_BROWSE_PREFIX):
            path = vid[len(PAN6_BROWSE_PREFIX):]
            if not path.startswith("/"):
                path = "/" + path
            name = path.rsplit("/", 1)[-1] or "6盘"
            if not self._p6_ensure_login():
                return {"list": [{
                    "vod_id": vid, "vod_name": name, "vod_pic": FOLDER_PIC,
                    "vod_content": "6盘未配置账号（%s）"
                    % (self._login_error
                        or "请配置 pan6User/pan6Pass"),
                }]}
            eps = []
            for c in self._p6_list_children(path, self.pan6_dir_limit):
                if c.get("is_dir") or not c.get("path"):
                    continue
                cname = c.get("name") or c.get("path")
                if not self.isVideoFormat(cname):
                    continue
                eps.append("%s$%s%s#%s" % (cname, PAN6_FILE_PREFIX,
                    c.get("identity") or "",
                    c.get("path")))
            return {"list": [{
                "vod_id": vid, "vod_name": name, "vod_pic": FOLDER_PIC,
                "vod_content": "6盘目录: %s" % path,
                "vod_play_from": "6盘" if eps else "",
                "vod_play_url": "#".join(eps),
            }]}
        return {"list": []}

    def searchContent(self, key, quick=False, pg="1"):
        page = max(1, _safe_int(pg, 1))
        keyword = _to_text(key)
        if not keyword:
            return {"list": [], "page": page, "pagecount": 1,
                "limit": PAN6_SEARCH_LIMIT, "total": 0}
        try:
            out = self._p6_search_local(keyword)
        except Exception:
            out = []
        return {"list": out, "page": page,
            "pagecount": page + 1 if len(out) >= PAN6_SEARCH_LIMIT
            else page,
            "limit": PAN6_SEARCH_LIMIT, "total": len(out)}

    def playerContent(self, flag, ids, vipFlags=None):
        vid = str(ids[0]) if isinstance(ids, (list, tuple)) and ids \
            else str(ids or "")
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
            rest = vid[len(PAN6_FILE_PREFIX):].replace("|", "#")
            identity, _, path = rest.partition("#")
            if not self._p6_ensure_login():
                return {"parse": 0, "jx": 0, "url": "", "header": {},
                    "msg": "6盘未配置账号（%s）"
                    % (self._login_error
                        or "请配置 pan6User/pan6Pass")}
            ckey = "%s|%s" % (identity, path)
            now = time.time()
            fail = self._p6_file_url_fail.get(ckey)
            if fail and now - fail.get("ts", 0) < self.pan6_file_url_fail_ttl:
                return {"parse": 0, "jx": 0, "url": "", "header": {},
                    "msg": "6盘取链失败: %s"
                    % (fail.get("err") or "取链失败")}
            info = None
            if identity:
                now_i = time.time()
                fi = self._p6_file_info_cache.get(identity)
                if fi and now_i - fi[0] < self.pan6_file_info_ttl:
                    info = dict(fi[1])
                else:
                    msg = _p6_enc_str(1, identity)
                    data, _err = self._p6_grpc(
                        "/v6.services.pub.PubUserFile/Get",
                        msg, attempts=1, timeout=12)
                    if data:
                        f = data if isinstance(data, dict) \
                            else _p6_dec_fields(data)
                        info = {"identity": _p6_as_str(f.get(1)) or identity,
                            "path": _p6_as_str(f.get(5)) or path}
                        if len(self._p6_file_info_cache) >= \
                                PAN6_FILE_INFO_CACHE_MAX:
                            self._p6_file_info_cache.clear()
                        self._p6_file_info_cache[identity] = (
                            now_i, dict(info))
            if not info:
                info = {"identity": identity, "path": path}
            if not info.get("identity"):
                picked = self._p6_pick_video(info.get("path") or path)
                if picked and (picked.get("identity") or picked.get("path")):
                    info = picked
            addr, err = self._p6_direct_url(info.get("identity") or "",
                info.get("path") or path)
            if not addr:
                if len(self._p6_file_url_fail) >= PAN6_FILE_URL_CACHE_MAX:
                    self._p6_file_url_fail.clear()
                self._p6_file_url_fail[ckey] = {"ts": now,
                    "err": err or "取链失败"}
                return {"parse": 0, "jx": 0, "url": "", "header": {},
                    "msg": "6盘取链失败: %s" % err}
            self._p6_file_url_fail.pop(ckey, None)
            if len(self._p6_file_url_cache) >= PAN6_FILE_URL_CACHE_MAX:
                for k in [k for k, v in self._p6_file_url_cache.items()
                    if now >= v.get("expire", 0)]:
                    self._p6_file_url_cache.pop(k, None)
                if len(self._p6_file_url_cache) >= PAN6_FILE_URL_CACHE_MAX:
                    self._p6_file_url_cache.clear()
            self._p6_file_url_cache[ckey] = {"url": addr,
                "expire": now
                + self.pan6_file_url_ttl}
            return {"parse": 0, "jx": 0, "url": addr,
                "header": {"User-Agent": PAN6_UA,
                    "Referer": PAN6_SITE + "/"}}
        return {"parse": 0, "jx": 0, "url": "", "header": {},
            "msg": "不支持的播放参数"}

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
        return _to_text(url).lower().endswith(VIDEO_EXTS)

    def action(self, action):
        return {}

    def destroy(self):
        self._p6_monitor_stop = True
        self._p6_file_url_cache.clear()
        self._p6_file_url_fail.clear()
        self._p6_file_info_cache.clear()
        self._p6_dir_cache.clear()
        self._p6_walk_cache = {"ts": 0.0, "items": []}
        try:
            if self.session is not None:
                self.session.close()
        except Exception:
            pass
        self.s = self.session = self.sess = None

    @staticmethod
    def _p6_sign(path, ts, token=None):
        path = "/" + str(path or "").lstrip("/")
        r = "%s%s%s%s" % (path, ts, PAN6_APP_ID, PAN6_APP_VER)
        if token:
            r += "Bearer " + token
        return hashlib.md5((r + PAN6_APP_SEC).encode("utf-8")).hexdigest()

    def _p6_grpc(self, method, msg, token=None, attempts=2, timeout=15):
        if self.session is None:
            if not requests:
                return None, "requests 模块不可用"
            self.session = requests.Session()
            self.session.headers.update(_PAN6_SESSION_HEADERS)
            self.s = self.session
            self.sess = self.session
        path = "/" + str(method or "").lstrip("/")
        tok = token if token is not None else (self.access_token or "")
        ts = str(int(time.time() * 1000))
        headers = dict(_PAN6_GRPC_HEADERS)
        headers["timestamp"] = ts
        headers["appid"] = PAN6_APP_ID
        headers["appversion"] = PAN6_APP_VER
        headers["sign"] = self._p6_sign(path, ts, tok or None)
        if tok:
            headers["authorization"] = "Bearer " + tok
        last = None
        for i in range(max(1, attempts)):
            try:
                r = self.session.post(PAN6_API_BASE + path, headers=headers,
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
                    if str(status) == "16" and self.refresh_token and tok:
                        if self._p6_try_refresh():
                            return self._p6_grpc(
                                path, msg, token=self.access_token,
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
        cap = json.dumps({"ticket": "tvbox", "randstr": "tvbox",
            "type": "tencent"}, ensure_ascii=False)
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
        self.access_token = at
        self.refresh_token = rt or ""
        return True, ""

    def _p6_try_refresh(self):
        if not self.refresh_token:
            return False
        msg = b""
        if self.access_token:
            msg += _p6_enc_str(5, self.access_token)
        if self.refresh_token:
            msg += _p6_enc_str(6, self.refresh_token)
        data, err = self._p6_grpc("/v6.services.pub.PubUser/Refresh", msg,
            token=self.access_token, attempts=1,
            timeout=12)
        if err or not data:
            return False
        tk = data if isinstance(data, dict) else _p6_dec_fields(data)
        at = _p6_as_str(tk.get(5))
        rt = _p6_as_str(tk.get(6))
        if at:
            self.access_token = at
        if rt:
            self.refresh_token = rt
        return bool(self.access_token)

    def _p6_ensure_login(self):
        if self.access_token:
            return True
        if self.pan6_user and self.pan6_pass:
            now = time.time()
            if self._login_error and \
                    now - self._login_fail_ts < self.pan6_login_fail_ttl:
                return False
            ok, err = self._p6_login()
            if ok:
                self._login_error = ""
                return True
            self._login_error = err or "登录失败"
            self._login_fail_ts = now
        return False

    @staticmethod
    def _p6_file_row(f):
        return {
            "identity": _p6_as_str(f.get(1)), "name": _p6_as_str(f.get(4)),
            "path": _p6_as_str(f.get(5)),
            "is_dir": bool(_p6_as_int(f.get(13))),
            "size": _p6_as_int(f.get(7)),
        }

    def _p6_file_info(self, path):
        msg = _p6_enc_str(5, path)
        data, err = self._p6_grpc("/v6.services.pub.PubUserFile/Get", msg,
            attempts=2, timeout=12)
        if err or not data:
            return None
        f = data if isinstance(data, dict) else _p6_dec_fields(data)
        row = self._p6_file_row(f)
        if not row["path"]:
            row["path"] = path
        return row

    def _p6_list_children(self, path, limit=50):
        path = _to_text(path) or "/"
        limit = max(1, _safe_int(limit, 50))
        ckey = "%s|%d" % (path, limit)
        now = time.time()
        hit = self._p6_dir_cache.get(ckey)
        if hit and now - hit[0] < self.pan6_dir_ttl:
            return list(hit[1])
        parent = _p6_enc_str(5, path)
        scan = _p6_enc_i64(2, limit)
        scan += _p6_enc_msg(3, _p6_enc_str(1, "update")
            + _p6_enc_str(2, "false"))
        msg = _p6_enc_msg(1, parent) + _p6_enc_msg(3, scan)
        data, err = self._p6_grpc("/v6.services.pub.PubUserFile/List", msg,
            attempts=1, timeout=15)
        if err or not data:
            return []
        rows = [self._p6_file_row(_p6_dec_fields(fb))
            for fb in _p6_as_msgs(data.get(1)
                if isinstance(data, dict) else None)]
        if len(self._p6_dir_cache) >= PAN6_DIR_CACHE_MAX:
            self._p6_dir_cache.clear()
        self._p6_dir_cache[ckey] = (now, rows)
        return list(rows)

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
        filtered = [c for c in vids
            if not any(k in (c["name"] or "").lower()
                for k in PAN6_SKIP_KEYWORDS)]
        if filtered:
            vids = filtered
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
        data, err = self._p6_grpc(
            "/v6.services.pub.PubUserFile/GetDirectDownloadAddress",
            msg, attempts=3, timeout=18)
        if err or not data:
            return "", err or "取链失败"
        addr = _p6_as_str(data.get(1))
        if not addr:
            return "", "无下载地址"
        return addr, ""

    def _p6_play_path(self, path, info_hash=""):
        picked = self._p6_pick_video(path)
        if not picked:
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                "msg": "6盘文件不存在: %s" % path}
        addr, err = self._p6_direct_url(picked.get("identity") or "",
            picked.get("path") or path)
        if not addr:
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                "msg": "6盘取链失败: %s" % err}
        if info_hash:
            self._cache_pan6_url[info_hash] = {
                "path": picked.get("path") or path, "url": addr,
                "expire": time.time() + PAN6_URL_TTL,
            }
        return {"parse": 0, "jx": 0, "url": addr,
            "header": {"User-Agent": PAN6_UA,
                "Referer": PAN6_SITE + "/"}}

    def _p6_walk(self, path, depth, out, seen):
        if depth > PAN6_WALK_MAX_DEPTH or len(out) > PAN6_WALK_MAX_ITEMS:
            return
        if not path:
            path = "/"
        for c in self._p6_list_children(path, PAN6_WALK_PAGE_LIMIT):
            name = c.get("name") or ""
            cpath = c.get("path") or ""
            if not name or not cpath:
                continue
            if c.get("is_dir"):
                vid = PAN6_BROWSE_PREFIX + cpath
                if vid in seen:
                    continue
                seen.add(vid)
                out.append({"vod_id": vid, "vod_name": name,
                    "vod_pic": FOLDER_PIC,
                    "vod_remarks": "目录", "vod_tag": "folder",
                    "ratio": 1.33})
                self._p6_walk(cpath, depth + 1, out, seen)
            elif self.isVideoFormat(name):
                vid = "%s%s#%s" % (PAN6_FILE_PREFIX, c.get("identity") or "",
                    cpath)
                if vid in seen:
                    continue
                seen.add(vid)
                out.append({"vod_id": vid, "vod_name": name,
                    "vod_pic": VIDEO_PIC,
                    "vod_remarks": _format_size(c.get("size")),
                    "ratio": 1.33})

    def _p6_walk_items(self):
        w = self._p6_walk_cache
        if w.get("items") and \
                time.time() - w.get("ts", 0) < self.pan6_search_ttl:
            return w["items"]
        return None

    def _p6_search_local(self, key):
        key = _to_text(key).lower()
        if not key:
            return []
        if not self._p6_ensure_login():
            return []
        now = time.time()
        if now - self._p6_last_search_ts < PAN6_SEARCH_COOLDOWN:
            items = self._p6_walk_items()
            if items is None:
                return []
        else:
            self._p6_last_search_ts = now
            items = self._p6_walk_items()
            if items is None:
                all_items = []
                try:
                    self._p6_walk("/", 0, all_items, set())
                except Exception:
                    return []
                self._p6_walk_cache = {"ts": time.time(),
                    "items": all_items}
                items = all_items
        hit = []
        for item in items:
            name = (item.get("vod_name") or "").lower()
            if key in name:
                hit.append(item)
            if len(hit) >= PAN6_SEARCH_LIMIT:
                break
        return hit

    @staticmethod
    def _p6_magnet_hash(magnet):
        m = re.search(r"btih:([0-9a-fA-F]{40}|[0-9a-zA-Z]{32})",
            magnet or "")
        return m.group(1).lower() if m else ""

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
            _p6_enc_msg(3, scan), attempts=2,
            timeout=12)
        if err or not data:
            return [], err or "离线列表失败"
        return _p6_as_msgs(data.get(1)
            if isinstance(data, dict) else None), ""

    def _p6_cached_task_list(self, ttl=None):
        if ttl is None:
            ttl = PAN6_TASK_LIST_TTL
        now = time.time()
        if self._p6_task_list_ts > 0 and \
                now - self._p6_task_list_ts < ttl:
            return self._p6_task_list_tasks
        tasks = []
        pages = max(1, int(self.pan6_find_pages or PAN6_FIND_PAGES))
        for page in range(1, pages + 1):
            try:
                rows, err = self._p6_offline_list(page,
                    PAN6_FIND_PAGE_LIMIT)
            except Exception:
                break
            if err or not rows:
                break
            tasks.extend(rows)
            if len(rows) < PAN6_FIND_PAGE_LIMIT:
                break
        self._p6_task_list_tasks = tasks
        self._p6_task_list_ts = time.time()
        return tasks

    def _p6_invalidate_task_list(self):
        self._p6_task_list_ts = 0.0
        self._p6_task_list_tasks = []

    def _p6_offline_find_task(self, info_hash):
        info_hash = (info_hash or "").lower()
        if not info_hash:
            return None
        try:
            tasks = self._p6_cached_task_list()
        except Exception:
            return None
        for tb in tasks:
            try:
                t = _p6_dec_fields(tb)
                h = self._p6_magnet_hash(_p6_as_str(t.get(8)))
                if h and h == info_hash:
                    return t
            except Exception:
                continue
        return None

    def _p6_find_task_safe(self, info_hash):
        try:
            return self._p6_offline_find_task(info_hash)
        except Exception:
            return None

    @staticmethod
    def _p6_task_detail(task):
        if not task:
            return False, False, 0, "任务未找到", ""
        file = _p6_as_str(task.get(6))
        status = _p6_as_int(task.get(3), -1)
        code = _p6_as_int(task.get(12), 0)
        msg = _p6_as_str(task.get(13))
        name = _p6_as_str(task.get(10)) or file
        try:
            pct = int(float(_p6_as_int(task.get(16), 0)))
        except Exception:
            pct = 0
        if code or msg:
            return False, True, 0, msg or ("离线失败 code=%d" % code), ""
        if file or status >= 1000 or pct >= 100:
            return True, False, 100, name or "完成", file
        return False, False, pct, name or "下载中", ""

    def _p6_quick_probe(self, info_hash):
        task = self._p6_find_task_safe(info_hash)
        if not task:
            return None, False, False, 0, "任务不存在"
        done, failed, pct, msg, _ = self._p6_task_detail(task)
        return task, done, failed, pct, msg

    def _p6_resolve_task_file(self, task):
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

        name_low = name.lower()
        stem = name_low.rsplit(".", 1)[0] if "." in name_low else name_low

        def _match(cname):
            cl = (cname or "").lower()
            if not cl:
                return False
            if cl == name_low:
                return True
            cstem = cl.rsplit(".", 1)[0] if "." in cl else cl
            return cstem == stem

        def _pick_in_dir(dir_path):
            vids = []
            for c in self._p6_list_children(dir_path or "/"):
                cpath = c.get("path") or ""
                if not cpath or c.get("is_dir"):
                    continue
                cname = c.get("name") or ""
                if not self.isVideoFormat(cname):
                    continue
                vids.append(c)
            filtered = [c for c in vids
                if not any(k in (c.get("name") or "").lower()
                    for k in PAN6_SKIP_KEYWORDS)]
            if filtered:
                vids = filtered
            if not vids:
                return ""
            vids.sort(key=lambda c: c.get("size") or 0, reverse=True)
            return vids[0].get("path") or ""

        for _attempt in range(3):
            for base in bases:
                base = base.rstrip("/") or ""
                info = self._p6_file_info(base + "/" + name)
                if info:
                    return info.get("path") or (base + "/" + name)
            for base in bases:
                for c in self._p6_list_children(base or "/"):
                    cname = c.get("name") or ""
                    cpath = c.get("path") or ""
                    if not cpath:
                        continue
                    if not c.get("is_dir") and _match(cname):
                        return cpath
                    if c.get("is_dir"):
                        cn = cname.lower()
                        if ((stem and stem in cn) or (cn and cn in stem)
                            or _match(cname)):
                            hit = _pick_in_dir(cpath)
                            if hit:
                                return hit
            for base in bases:
                for c in self._p6_list_children(base or "/"):
                    cname = c.get("name") or ""
                    cpath = c.get("path") or ""
                    if not cpath or not c.get("is_dir"):
                        continue
                    hit = _pick_in_dir(cpath)
                    if hit:
                        return hit
            time.sleep(0.5)
        return ""

    def _submit_offline_pan6(self, magnet):
        if not self._p6_ensure_login():
            tip = self._login_error or \
                "请配置 pan6User/pan6Pass 或 pan6Token"
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                "msg": "未配置6盘账号，无法提交离线（%s）" % tip}
        info_hash = self._p6_magnet_hash(magnet)
        if not info_hash:
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                "msg": "无法从磁力中解析 info_hash"}

        if self.enable_offline_monitor:
            self._p6_start_monitor()

        cached_file = self._cache_pan6_file.get(info_hash)
        if cached_file:
            res = self._p6_play_path(cached_file, info_hash)
            if res.get("url"):
                return res
            self._cache_pan6_file.pop(info_hash, None)

        t = self._cache_pan6_task.get(info_hash)
        if isinstance(t, dict) and t.get("state") == "failed" \
                and time.time() - t.get("ts", 0) < PAN6_FAILED_TTL:
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                "msg": "6盘离线任务失败: %s"
                % (t.get("msg") or "离线下载失败")}

        task, done, failed, pct, msg = self._p6_quick_probe(info_hash)
        if failed:
            self._cache_pan6_task[info_hash] = {"ts": time.time(),
                "state": "failed",
                "msg": msg}
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                "msg": "6盘离线任务失败: %s" % msg}
        if done and task:
            file = self._p6_resolve_task_file(task)
            if file:
                self._cache_pan6_file[info_hash] = file
                self._cache_pan6_task[info_hash] = {"ts": time.time(),
                    "state": "done"}
                return self._p6_play_path(file, info_hash)
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                "msg": "6盘离线已完成，但未找到文件，请确认保存路径 %s"
                % self.pan6_save_path}
        if task and not done:
            self._cache_pan6_task[info_hash] = {
                "ts": time.time(), "state": "downloading",
                "pct": pct, "msg": msg}
            if self.pan6_play_wait > 0:
                task2, wait_msg = self._p6_wait_done_task(
                    info_hash, timeout=self.pan6_play_wait)
                if task2:
                    file = self._p6_resolve_task_file(task2)
                    if file:
                        self._cache_pan6_file[info_hash] = file
                        self._cache_pan6_task[info_hash] = {
                            "ts": time.time(), "state": "done"}
                        return self._p6_play_path(file, info_hash)
                return {"parse": 0, "jx": 0, "url": "", "header": {},
                    "msg": "6盘离线下载中（%s），稍后再点一次即可自动播放"
                    % (wait_msg or "请稍候")}
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                "msg": "6盘离线下载中（%d%%），请稍后重试" % pct}

        now = time.time()
        if now - self._p6_last_submit.get(info_hash, 0) < \
                PAN6_SUBMIT_COOLDOWN:
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                "msg": "刚提交过6盘离线，请稍后重试"}

        with self._offline_lock:
            inflight = info_hash in self._offline_pending
            if not inflight:
                self._offline_pending.add(info_hash)
        if inflight:
            task = self._p6_find_task_safe(info_hash)
            if task:
                done, failed, pct, msg, _ = self._p6_task_detail(task)
                if failed:
                    return {"parse": 0, "jx": 0, "url": "", "header": {},
                        "msg": "6盘离线任务失败: %s" % msg}
                if done:
                    file = self._p6_resolve_task_file(task)
                    if file:
                        self._cache_pan6_file[info_hash] = file
                        return self._p6_play_path(file, info_hash)
            if self.pan6_play_wait > 0:
                task2, wait_msg = self._p6_wait_done_task(
                    info_hash, timeout=self.pan6_play_wait)
                if task2:
                    file = self._p6_resolve_task_file(task2)
                    if file:
                        self._cache_pan6_file[info_hash] = file
                        self._cache_pan6_task[info_hash] = {
                            "ts": time.time(), "state": "done"}
                        return self._p6_play_path(file, info_hash)
                return {"parse": 0, "jx": 0, "url": "", "header": {},
                    "msg": "6盘离线下载中（%s），稍后再点一次即可自动播放"
                    % (wait_msg or "请稍候")}
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                "msg": "6盘离线正在提交中，稍后再点一次即可自动播放"}

        try:
            _res, err = self._p6_offline_add(magnet)
            self._p6_last_submit[info_hash] = now
        except Exception as e:
            self._p6_invalidate_task_list()
            with self._offline_lock:
                self._offline_pending.discard(info_hash)
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                "msg": "提交6盘离线失败：%s" % e}

        self._p6_invalidate_task_list()

        if err:
            task = self._p6_find_task_safe(info_hash)
            if task:
                done, failed, pct, msg, _ = self._p6_task_detail(task)
                if failed:
                    with self._offline_lock:
                        self._offline_pending.discard(info_hash)
                    return {"parse": 0, "jx": 0, "url": "", "header": {},
                        "msg": "6盘离线任务失败: %s" % msg}
                if done:
                    file = self._p6_resolve_task_file(task)
                    if file:
                        self._cache_pan6_file[info_hash] = file
                        with self._offline_lock:
                            self._offline_pending.discard(info_hash)
                        return self._p6_play_path(file, info_hash)
                with self._offline_lock:
                    self._offline_pending.discard(info_hash)
                return {"parse": 0, "jx": 0, "url": "", "header": {},
                    "msg": "6盘离线已在任务列表（%d%%），请稍后重试"
                    % pct}
            with self._offline_lock:
                self._offline_pending.discard(info_hash)
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                "msg": "6盘离线提交失败：%s" % err}

        self._cache_pan6_task[info_hash] = {"ts": now, "state": "submitted"}

        if self.pan6_play_wait > 0:
            try:
                task, wait_msg = self._p6_wait_done_task(
                    info_hash, timeout=self.pan6_play_wait)
                if task:
                    file = self._p6_resolve_task_file(task)
                    if file:
                        self._cache_pan6_file[info_hash] = file
                        self._cache_pan6_task[info_hash] = {
                            "ts": time.time(), "state": "done"}
                        return self._p6_play_path(file, info_hash)
                return {"parse": 0, "jx": 0, "url": "", "header": {},
                    "msg": "已提交6盘离线，正在下载中（%s），"
                    "稍后再点一次即可自动播放"
                    % (wait_msg or "等待完成")}
            finally:
                with self._offline_lock:
                    self._offline_pending.discard(info_hash)
        with self._offline_lock:
            self._offline_pending.discard(info_hash)
        return {"parse": 0, "jx": 0, "url": "", "header": {},
            "msg": "已提交6盘离线，正在下载中，稍后再点一次即可自动播放"}

    def _p6_wait_done_task(self, info_hash, timeout=None):
        budget = self.pan6_timeout if timeout is None \
            else max(0, int(timeout))
        deadline = time.time() + budget
        last = "0%"
        while True:
            task = self._p6_find_task_safe(info_hash)
            done, failed, pct, msg, _ = self._p6_task_detail(task)
            if done and task:
                return task, ""
            if failed:
                return None, msg
            last = "%d%%" % pct
            if time.time() >= deadline:
                return None, last
            time.sleep(PAN6_POLL_INTERVAL)

    def _p6_start_monitor(self):
        if not self.enable_offline_monitor:
            return
        with self._p6_monitor_lock:
            th = self._p6_monitor_thread
            if th is not None and th.is_alive():
                return
            self._p6_monitor_stop = False
            th = threading.Thread(target=self._p6_monitor_loop,
                name="pan6-offline-monitor",
                daemon=True)
            self._p6_monitor_thread = th
            th.start()

    def _p6_monitor_loop(self):
        while not self._p6_monitor_stop:
            try:
                self._p6_monitor_tick()
            except Exception:
                pass
            time.sleep(self._p6_monitor_interval())

    def _p6_monitor_interval(self):
        now = time.time()
        for t in self._cache_pan6_task.values():
            if not isinstance(t, dict):
                continue
            if t.get("state") not in ("submitted", "downloading",
                "resolving"):
                continue
            if now - t.get("ts", 0) < 60:
                return PAN6_MONITOR_BUSY
        return PAN6_MONITOR_IDLE

    def _p6_monitor_tick(self):
        now = time.time()
        targets = []
        for h, t in list(self._cache_pan6_task.items()):
            if not isinstance(t, dict):
                continue
            st = t.get("state")
            if st not in ("submitted", "downloading", "resolving"):
                continue
            if now - t.get("ts", 0) > PAN6_MONITOR_MAX_AGE:
                self._cache_pan6_task.pop(h, None)
                continue
            targets.append((h, t))
        for h, t in targets:
            try:
                self._p6_monitor_one(h, t, now)
            except Exception:
                continue

    def _p6_monitor_one(self, h, t, now):
        try:
            task = self._p6_offline_find_task(h)
        except Exception:
            return
        age = now - t.get("ts", now)
        if not task:
            if age < PAN6_TASK_WAIT_MAX:
                return
            self._cache_pan6_task[h] = {"ts": now, "state": "missing",
                "msg": "任务未找到"}
            return
        done, failed, pct, msg, file0 = self._p6_task_detail(task)
        if failed:
            self._cache_pan6_task[h] = {"ts": now, "state": "failed",
                "msg": msg}
            return
        if done:
            f = file0 or self._p6_resolve_task_file(task)
            if f:
                self._cache_pan6_file[h] = f
                self._cache_pan6_task[h] = {"ts": now, "state": "done",
                    "pct": 100, "msg": "完成"}
                try:
                    self._p6_play_path(f, h)
                except Exception:
                    pass
            elif age < PAN6_RESOLVE_MAX_AGE:
                self._cache_pan6_task[h] = {"ts": t.get("ts", now),
                    "state": "resolving",
                    "pct": 100,
                    "msg": "等待文件入库"}
            else:
                self._cache_pan6_task[h] = {"ts": now, "state": "failed",
                    "msg": "离线完成但未找到文件"}
            return
        self._cache_pan6_task[h] = {"ts": t.get("ts", now),
            "state": "downloading",
            "pct": pct, "msg": msg}

    def _p6_prewarm(self, magnet):
        try:
            if not self.enable_offline_pan6:
                return
            if not self._p6_ensure_login():
                return
            h = self._p6_magnet_hash(magnet)
            if not h:
                return
            if self._cache_pan6_url.get(h) or self._cache_pan6_file.get(h):
                return
            t = self._cache_pan6_task.get(h)
            if isinstance(t, dict) and t.get("state") in (
                "submitted", "downloading", "resolving", "done",
                "failed"):
                return
            self._submit_offline_pan6(magnet)
        except Exception:
            pass

from html import unescape

API = "https://rulel.com/wp-json/wp/v2"

HOST = "https://rulel.com"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

CAT_ID = 22392

CATE = [
    {"type_id": str(CAT_ID), "type_name": "全部磁力"},
    {"type_id": "22393", "type_name": "亚洲有码"},
    {"type_id": "22395", "type_name": "亚洲无码"},
    {"type_id": "22396", "type_name": "欧美无码"},
    {"type_id": "22394", "type_name": "国产原创"},
    {"type_id": "20222", "type_name": "中文字幕"},
]

TAG_IDS = {22393, 22395, 22396, 22394, 20222}

PER_PAGE = 12

CAT_IDS = str(CAT_ID)

PIC_PROXY = {"mode": "wsrv"}

MAGNET_RE = re.compile(r"magnet:\?xt=urn:btih:[A-Za-z0-9]+(?:&[^\s\"'<>）)】]*)?")

TAG_RE = re.compile(r"<[^>]+>")

def _headers():
    return {
        "User-Agent": UA,
        "Accept": "application/json, text/html;q=0.9,*/*;q=0.8",
        "Referer": HOST + "/",
    }

def http_get(url, timeout=20, retry=2):
    last = None
    for i in range(retry + 1):
        try:
            if requests is not None:
                r = requests.get(url, headers=_headers(), timeout=timeout)
                r.encoding = "utf-8"
                return r.text
            req = urllib.request.Request(url, headers=_headers())
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception as e:
            last = e
            if i < retry:
                time.sleep(0.8 * (i + 1))
    raise RuntimeError("请求失败: %s (%s)" % (url, last))

def api(path, **params):
    q = urllib.parse.urlencode(params, doseq=True)
    url = "%s/%s?%s" % (API, path.lstrip("/"), q)
    return json.loads(http_get(url))

def _posts(params):
    params.setdefault("per_page", PER_PAGE)
    params.setdefault("_embed", "wp:featuredmedia")
    return api("posts", **params)

def fix_url(url, host=HOST):
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("http://") or url.startswith("https://") or url.startswith("magnet:"):
        return url
    return urllib.parse.urljoin(host.rstrip("/") + "/", url)

def _proxy_pic(url):
    if not url:
        return ""
    mode = PIC_PROXY.get("mode", "wsrv")
    if mode == "origin":
        return url
    if mode == "local":
        port = PIC_PROXY.get("port", 9978)
        return "http://127.0.0.1:%s/proxy?url=%s" % (port, urllib.parse.quote(url, safe=""))

    try:
        host_path = re.sub(r"^https?://", "", url)
        return "https://wsrv.nl/?url=" + urllib.parse.quote(host_path, safe="/?&=%-._~:")
    except Exception:
        return url

def clean_text(html):
    if not html:
        return ""
    t = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    t = re.sub(r"</p>", "\n", t, flags=re.I)
    t = TAG_RE.sub("", t)
    t = unescape(t)
    lines = [re.sub(r"[ \t\u3000]+", " ", ln).strip() for ln in t.splitlines()]
    return "\n".join([ln for ln in lines if ln])

def pick_pic(post):
    emb = post.get("_embedded") or {}
    media = emb.get("wp:featuredmedia") or []
    if media and isinstance(media, list):
        src = (media[0] or {}).get("source_url")
        if src:
            return fix_url(src)
    body = (post.get("content") or {}).get("rendered", "")
    m = re.search(r'<img[^>]+src="([^"]+)"', body)
    return fix_url(m.group(1)) if m else ""

def pick_remarks(post):
    body = clean_text((post.get("content") or {}).get("rendered", ""))
    excerpt = clean_text((post.get("excerpt") or {}).get("rendered", ""))
    text = body + "\n" + excerpt
    m = re.search(r"【(?:影片容量|资源大小|资源容量|文件大小|资源体积)】\s*[：:]?\s*([^\s【】\n]+)", text)
    if m:
        return m.group(1).replace("[", "").replace("]", "")
    m = re.search(r"\[?\d+(?:\.\d+)?\s*[VvGgTt](?:\d+(?:\.\d+)?[GgMm])?\]?", text)
    if m:
        return m.group(0).strip("[]")
    day = (post.get("date") or "")[:10]
    return day or "磁力"

def pick_magnets(text):
    out, seen = [], set()
    for m in MAGNET_RE.findall(text or ""):
        key = m.lower()
        if key not in seen:
            seen.add(key)
            out.append(m.rstrip("&"))
    return out

def post_to_vod(post):
    title = clean_text((post.get("title") or {}).get("rendered", ""))
    return {
        "vod_id": str(post.get("id", "")),
        "vod_name": title,
        "vod_pic": _proxy_pic(pick_pic(post)),
        "vod_remarks": pick_remarks(post),
        "vod_time": (post.get("date") or "").replace("T", " "),
    }

def build_detail(post):
    body = (post.get("content") or {}).get("rendered", "")
    text = clean_text(body)
    vod = post_to_vod(post)
    vod["vod_year"] = (post.get("date") or "")[:4]
    vod["vod_area"] = "磁力"
    vod["vod_actor"] = ""
    vod["vod_director"] = ""
    vod["vod_content"] = text[:1200] or vod["vod_name"]
    vod["vod_lang"] = ""

    froms, urls = [], []

    mags = pick_magnets(body)
    if mags:
        items = ["磁力%d$%s" % (i + 1, m) for i, m in enumerate(mags)]
        froms.append("磁力")
        urls.append("#".join(items))

    vod["vod_play_from"] = "$$$".join(froms)
    vod["vod_play_url"] = "$$$".join(urls)
    vod["vod_play_note"] = "注意：磁力需要系统里有 BT 下载器（迅雷/qBittorrent 一类），App 本身不下 BT"
    return vod

def home_list():
    out, seen = [], set()
    try:
        posts = _posts({"categories": CAT_ID, "page": 1, "per_page": PER_PAGE})
    except Exception:
        return out
    for p in posts:
        pid = p.get("id")
        if pid in seen:
            continue
        seen.add(pid)
        out.append(post_to_vod(p))
    return out

def category_data(tid, page=1, extend=None, filter=None):
    try:
        tid_int = int(tid)
    except (TypeError, ValueError):
        tid_int = CAT_ID
    if tid_int in TAG_IDS:
        params = {"categories": CAT_ID, "tags": tid_int, "page": page}
    else:
        params = {"categories": tid_int, "page": page}
    posts = _posts(params)

    lst, seen = [], set()
    for p in posts:
        pid = p.get("id")
        if pid in seen:
            continue
        seen.add(pid)
        lst.append(post_to_vod(p))
    return {
        "page": page,
        "pagecount": page + 1 if len(posts) >= PER_PAGE else page,
        "limit": PER_PAGE,
        "total": 0,
        "list": lst,
    }

def detail_data(vid):
    vid = str(vid or "")
    m = re.search(r"(\d+)", vid)
    pid = m.group(1) if m else vid
    arr = []
    try:
        arr = _posts({"include": pid})
    except Exception:
        arr = []
    if not arr:
        pid2 = re.search(r"/(\d+)\.html", vid)
        if pid2:
            try:
                arr = _posts({"include": pid2.group(1)})
            except Exception:
                arr = []
    if not arr:
        return []
    return [build_detail(arr[0])]

def search_data(wd, page=1):
    posts = _posts({"search": wd, "page": page, "categories": CAT_IDS})
    lst, seen = [], set()
    for p in posts:
        pid = p.get("id")
        if pid in seen:
            continue
        seen.add(pid)
        lst.append(post_to_vod(p))
    return {
        "page": page,
        "pagecount": page + 1 if len(posts) >= PER_PAGE else page,
        "limit": PER_PAGE,
        "total": 0,
        "list": lst,
    }

def play_data(flag, url):
    url = fix_url(str(url or ""))
    header = {"User-Agent": UA, "Referer": HOST + "/"}
    if url.startswith("magnet:"):
        return {"parse": 0, "jx": 0, "playUrl": "", "url": url, "header": header}
    return {"parse": 1, "jx": 1, "playUrl": "", "url": url, "header": header}

def _normalize_extend(extend):
    if isinstance(extend, str) and extend.strip().startswith("{"):
        try:
            extend = json.loads(extend)
        except Exception:
            extend = {}
    if not isinstance(extend, dict):
        extend = {}
    return extend

def _normalize_param(param):
    if isinstance(param, str):
        try:
            param = json.loads(param)
        except Exception:
            param = {}
    if not isinstance(param, dict):
        param = {}
    return param

# ===================== PikPak =====================

PKP_BROWSE_PREFIX = "pkp:"
PKP_FILE_PREFIX = "pkpf:"
PKP_PROXY_QUERY = "pkp"

PKP_DEFAULT_PROXY = "127.0.0.1:10172"
PKP_DEFAULT_DOMAIN = "mypikpak.net"

PKP_TOKEN_TTL = 6000
PKP_LIST_TTL = 45
PKP_LINK_TTL = 900
PKP_FAIL_TTL = 20
PKP_PAGE_SIZE = 60
PKP_SEARCH_LIMIT = 60
PKP_RELAY_MAX_MB = 512

PKP_WEB_CID = "YUMx5nI8ZU8Ap8pm"
PKP_WEB_SEC = "dbw2OtmVEeuUvIptb1Coyg"
PKP_WEB_VER = "2.0.0"
PKP_WEB_PKG = "mypikpak.com"
PKP_WEB_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36")

PKP_AND_CID = "YNxT9w7GMdWvEOKa"
PKP_AND_SEC = "dbw2OtmVEeuUvIptb1Coyg"
PKP_AND_VER = "1.53.2"
PKP_AND_PKG = "com.pikcloud.pikpak"

PKP_PC_CID = "YvtoWO6GNHiuCl7x"
PKP_PC_SEC = "1NIH5R1IEe2pAxZE3hv3uA"
PKP_PC_VER = "undefined"
PKP_PC_PKG = "mypikpak.com"

PKP_ALGS_WEB = ("C9qPpZLN8ucRTaTiUMWYS9cQvWOE", "+r6CQVxjzJV6LCV", "F",
    "pFJRC", "9WXYIDGrwTCz2OiVlgZa90qpECPD6olt", "/750aCr4lm/Sly/c",
    "RB+DT/gZCrbV", "", "CyLsf7hdkIRxRm215hl", "7xHvLi2tOYP0Y92b",
    "ZGTXXxu8E/MIWaEDB+Sm/", "1UI3",
    "E7fP5Pfijd+7K+t6Tg/NhuLq0eEUVChpJSkrKxpO",
    "ihtqpG6FMt65+Xk+tWUH2", "NhXXU9rg4XXdzo7u5o")

PKP_ALGS_AND = ("SOP04dGzk0TNO7t7t9ekDbAmx+eq0OI1ovEx",
    "nVBjhYiND4hZ2NCGyV5beamIr7k6ifAsAbl",
    "Ddjpt5B/Cit6EDq2a6cXgxY9lkEIOw4yC1GDF28KrA",
    "VVCogcmSNIVvgV6U+AochorydiSymi68YVNGiz",
    "u5ujk5sM62gpJOsB/1Gu/zsfgfZO", "dXYIiBOAHZgzSruaQ2Nhrqc2im",
    "z5jUTBSIpBN9g4qSJGlidNAutX6", "KJE2oveZ34du/g1tiimm")

PKP_ALGS_PC = ("KHBJ07an7ROXDoK7Db", "G6n399rSWkl7WcQmw5rpQInurc1DkLmLJqE",
    "JZD1A3M4x+jBFN62hkr7VDhkkZxb9g3rWqRZqFAAb",
    "fQnw/AmSlbbI91Ik15gpddGgyU7U", "/Dv9JdPYSj3sHiWjouR95NTQff",
    "yGx2zuTjbWENZqecNI+edrQgqmZKP", "ljrbSzdHLwbqcRn",
    "lSHAsqCkGDGxQqqwrVu", "TsWXI81fD1", "vk7hBjawK/rOSrSWajtbMk95nfgf3")

PKP_VIDEO_MIME = ("video/", "application/vnd.apple.mpegurl")


try:
    import socks as _pkp_socks  # noqa: F401
    _PKP_HAS_SOCKS = True
except Exception:
    _PKP_HAS_SOCKS = False

try:
    import socket as _pkp_socket
    import ssl as _pkp_ssl
    import zlib as _pkp_zlib
except Exception:
    _pkp_socket = None
    _pkp_ssl = None
    _pkp_zlib = None

# 没填代理时自动探测这些本地端口（jar 内置代理 / 常见代理软件）
PKP_PROXY_AUTOS = ("127.0.0.1:10172", "127.0.0.1:7890",
    "127.0.0.1:7891", "127.0.0.1:1080", "127.0.0.1:8080")


def _pkp_split_addr(addr):
    """'127.0.0.1:10172' / 'http://1.2.3.4:8080' -> (host, port)"""
    a = re.sub(r"^[a-zA-Z0-9]+://", "", _to_text(addr)).strip().strip("/")
    if not a:
        return ("", 0)
    if a.count(":") == 1:
        h, p = a.split(":")
        try:
            return (h.strip() or "127.0.0.1", int(p))
        except Exception:
            return (h.strip(), 0)
    return (a, 0)


def _pkp_read_until(sk, marker, limit=8192):
    buf = b""
    while marker not in buf:
        try:
            chunk = sk.recv(2048)
        except Exception:
            break
        if not chunk:
            break
        buf += chunk
        if len(buf) > limit:
            break
    return buf


def _pkp_http_connect(sk, host, port):
    """标准 HTTP 代理 CONNECT 隧道（https 走这条）"""
    req = ("CONNECT %s:%d HTTP/1.1\r\nHost: %s:%d\r\n"
        "Proxy-Connection: keep-alive\r\nUser-Agent: okhttp/4.12.0\r\n\r\n"
        % (host, port, host, port))
    sk.sendall(req.encode("latin1"))
    head = _pkp_read_until(sk, b"\r\n\r\n")
    line = head.split(b"\r\n", 1)[0].decode("latin1", "ignore")
    parts = line.split(" ")
    if len(parts) >= 2 and parts[1] == "200":
        return True
    raise RuntimeError("隧道被拒:%s" % line[:50])


def _pkp_socks5(sk, host, port, user="", pwd=""):
    """纯 socket 版 SOCKS5，壳里没装 PySocks 也能用"""
    sk.sendall(b"\x05\x02\x00\x02" if user else b"\x05\x01\x00")
    rep = sk.recv(2)
    if len(rep) < 2 or rep[0] != 0x05:
        raise RuntimeError("SOCKS5无响应")
    if rep[1] == 0x02:
        u = user.encode("utf-8")
        p = pwd.encode("utf-8")
        sk.sendall(b"\x01" + bytes([len(u)]) + u + bytes([len(p)]) + p)
        r = sk.recv(2)
        if len(r) < 2 or r[1] != 0:
            raise RuntimeError("SOCKS5认证失败")
    elif rep[1] != 0x00:
        raise RuntimeError("SOCKS5不接受无认证(0x%02x)" % rep[1])
    hb = host.encode("idna")
    sk.sendall(b"\x05\x01\x00\x03" + bytes([len(hb)]) + hb
        + struct.pack(">H", int(port)))
    rep = sk.recv(4)
    if len(rep) < 4:
        raise RuntimeError("SOCKS5连接无响应")
    if rep[1] != 0x00:
        raise RuntimeError("SOCKS5连接失败(code=%d)" % rep[1])
    atyp = rep[3]
    if atyp == 1:
        sk.recv(4)
    elif atyp == 3:
        n = sk.recv(1)
        if n:
            sk.recv(n[0])
    elif atyp == 4:
        sk.recv(16)
    sk.recv(2)
    return True


def _pkp_dechunk(body):
    out = b""
    i = 0
    while True:
        j = body.find(b"\r\n", i)
        if j < 0:
            break
        try:
            n = int((body[i:j].split(b";")[0].strip() or b"0"), 16)
        except Exception:
            break
        if n <= 0:
            break
        out += body[j + 2:j + 2 + n]
        i = j + 2 + n + 2
    return out


def _pkp_parse_resp(data):
    head, _sep, body = data.partition(b"\r\n\r\n")
    lines = head.split(b"\r\n")
    status = 0
    try:
        status = int(lines[0].split(b" ")[1])
    except Exception:
        status = 0
    hdrs = {}
    for ln in lines[1:]:
        if b":" in ln:
            k, v = ln.split(b":", 1)
            hdrs[k.decode("latin1").strip().lower()] = \
                v.decode("latin1").strip()
    if "chunked" in hdrs.get("transfer-encoding", "").lower():
        body = _pkp_dechunk(body)
    if "gzip" in hdrs.get("content-encoding", "").lower() and _pkp_zlib:
        try:
            body = _pkp_zlib.decompress(body, 16 + _pkp_zlib.MAX_WBITS)
        except Exception:
            pass
    return status, hdrs, body


def _pkp_sk_http(method, url, headers=None, body=None, timeout=20,
                 proxy="", kind="direct", max_bytes=0):
    """不依赖 requests 的 HTTP(S) 客户端，支持 direct / http 隧道 / socks5。
    kind: direct | http | socks5"""
    if _pkp_socket is None:
        raise RuntimeError("当前环境不支持 socket")
    sp = urllib.parse.urlsplit(url)
    scheme = (sp.scheme or "http").lower()
    host = sp.hostname or ""
    port = sp.port or (443 if scheme == "https" else 80)
    path = sp.path or "/"
    if sp.query:
        path += "?" + sp.query
    if not host:
        raise RuntimeError("URL 无效")

    if proxy:
        ph, pp = _pkp_split_addr(proxy)
        if not ph or not pp:
            raise RuntimeError("代理地址不对")
        sk = _pkp_socket.create_connection((ph, pp), timeout)
    else:
        sk = _pkp_socket.create_connection((host, port), timeout)
    sk.settimeout(timeout)
    try:
        if proxy and kind in ("http", "https"):
            _pkp_http_connect(sk, host, port)
        elif proxy and kind in ("socks5", "socks5h"):
            _pkp_socks5(sk, host, port)
        if scheme == "https":
            ctx = _pkp_ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = _pkp_ssl.CERT_NONE
            sk = ctx.wrap_socket(sk, server_hostname=host)

        hdrs = {
            "Host": host if port in (80, 443) else "%s:%d" % (host, port),
            "Connection": "close",
            "Accept-Encoding": "identity",
        }
        if body is not None:
            hdrs["Content-Length"] = str(len(body))
        hdrs.update(headers or {})
        lines = ["%s %s HTTP/1.1" % (method, path)]
        for k, v in hdrs.items():
            if v is None:
                continue
            lines.append("%s: %s" % (k, v))
        req = ("\r\n".join(lines) + "\r\n\r\n").encode("utf-8")
        sk.sendall(req + (body or b""))

        data = b""
        while True:
            try:
                chunk = sk.recv(65536)
            except Exception:
                break
            if not chunk:
                break
            data += chunk
            if max_bytes and len(data) >= max_bytes + 512:
                break
        status, h, b = _pkp_parse_resp(data)
        if max_bytes:
            b = b[:max_bytes]
        return status, h, b
    finally:
        try:
            sk.close()
        except Exception:
            pass


class PkpHttpStatus(Exception):
    def __init__(self, code, text):
        Exception.__init__(self, "HTTP %s" % code)
        self.code = code
        self.text = text


class PkpVerifyRequired(Exception):
    def __init__(self, url):
        Exception.__init__(self, url)
        self.url = url


def _pkp_md5(s):
    return hashlib.md5(str(s or "").encode("utf-8")).hexdigest()


def _pkp_sha1(s):
    return hashlib.sha1(str(s or "").encode("utf-8")).hexdigest()


def _pkp_day(s):
    s = _to_text(s)
    if not s:
        return ""
    return s[:10]


def _pkp_join_size(v):
    try:
        return _format_size(int(str(v or "0")))
    except Exception:
        return _to_text(v)


class PikPakSpider:
    """PikPak 网盘：浏览 / 详情 / 搜索 / 播放，全部支持走本地代理。"""

    def __init__(self):
        self.refresh_token = ""
        self.access_token = ""
        self.username = ""
        self.password = ""
        self.user_id = ""
        self.captcha_token = ""
        self.captcha_ts = 0.0
        self.token_ts = 0.0
        self.device_id = ""
        self.client_id = PKP_WEB_CID
        self.client_secret = PKP_WEB_SEC
        self.client_version = PKP_WEB_VER
        self.package_name = PKP_WEB_PKG
        self.algorithms = PKP_ALGS_WEB
        self.ua = PKP_WEB_UA
        self.domain = PKP_DEFAULT_DOMAIN
        self.user_base = ""
        self.drive_base = ""
        self.proxy = PKP_DEFAULT_PROXY
        self.proxy_type = "auto"
        self.proxy_addrs = list(PKP_PROXY_AUTOS)
        self.proxy_user = ""
        self.proxy_pass = ""
        self.allow_direct = True
        self.chan = None
        self.chan_ts = 0.0
        self.diag_on = False
        self.force_tunnel = False
        self.last_diag = []
        self.proxy_ok = None
        self.play_mode = "auto"
        self.relay_max_mb = PKP_RELAY_MAX_MB
        self.page_size = PKP_PAGE_SIZE
        self.share_root = ""
        self.enable = True
        self.enable_search = True
        self.timeout = 20
        self.last_error = ""
        self._list_cache = {}
        self._probe_cache = {}
        self._link_cache = {}
        self._fail = {}
        self._lock = threading.RLock()

    # ---------- 对外接口 ----------

    def getName(self):
        return "PikPak"

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
        cfg = extend.get("pikpak")
        if not isinstance(cfg, dict):
            cfg = {}

        def pick(*keys):
            for k in keys:
                v = extend.get(k)
                if v not in (None, ""):
                    return v
                v = cfg.get(k)
                if v not in (None, ""):
                    return v
            return ""

        self.refresh_token = _to_text(pick("pikpakRefreshToken", "pikpakToken",
            "pikpakRefresh", "refresh_token"))
        self.username = _to_text(pick("pikpakUser", "pikpakUsername",
            "pikpakAccount", "username"))
        self.password = _to_text(pick("pikpakPass", "pikpakPassword",
            "password"))
        self.access_token = _to_text(pick("pikpakAccessToken", "access_token"))
        self.device_id = _to_text(pick("pikpakDeviceId", "device_id"))
        self.user_id = _to_text(pick("pikpakUserId", "user_id"))
        self.share_root = _to_text(pick("pikpakRootId", "pikpakRoot",
            "root_id"))

        platform = _to_text(pick("pikpakPlatform", "platform")).lower()
        if platform == "android":
            self.client_id = PKP_AND_CID
            self.client_secret = PKP_AND_SEC
            self.client_version = PKP_AND_VER
            self.package_name = PKP_AND_PKG
            self.algorithms = PKP_ALGS_AND
        elif platform == "pc":
            self.client_id = PKP_PC_CID
            self.client_secret = PKP_PC_SEC
            self.client_version = PKP_PC_VER
            self.package_name = PKP_PC_PKG
            self.algorithms = PKP_ALGS_PC

        dom = _to_text(pick("pikpakDomain", "pikpakApiDomain", "api_domain"))
        if dom:
            self.domain = re.sub(r"^https?://", "", dom).strip("/")
        self.user_base = _to_text(pick("pikpakUserBase", "user_base"))
        self.drive_base = _to_text(pick("pikpakDriveBase", "drive_base"))
        if not self.user_base:
            self.user_base = "https://user." + self.domain
        if not self.drive_base:
            self.drive_base = "https://api-drive." + self.domain
        self.user_base = self.user_base.rstrip("/")
        self.drive_base = self.drive_base.rstrip("/")

        raw_proxy = _to_text(pick("pikpakProxy", "proxy")).strip()
        ptype = _to_text(pick("pikpakProxyType", "proxy_type")).lower()
        if ptype in ("http", "socks5", "socks5h", "socks4", "none", "off"):
            self.proxy_type = ptype
        self.proxy_user = _to_text(pick("pikpakProxyUser", "proxy_user"))
        self.proxy_pass = _to_text(pick("pikpakProxyPass", "proxy_pass"))
        low_proxy = raw_proxy.lower()
        if self.proxy_type in ("none", "off") or low_proxy in (
                "off", "none", "no", "0", "false"):
            self.proxy_addrs = []
        elif raw_proxy and low_proxy not in ("auto", "default"):
            # 支持逗号/分号/空格分隔多个地址，按顺序试
            self.proxy_addrs = [x for x in re.split(r"[,;\s]+", raw_proxy) if x]
        else:
            # 没填：自动探测常见本地端口（10172 = jar 内置代理）
            self.proxy_addrs = list(PKP_PROXY_AUTOS)
        self.proxy = self.proxy_addrs[0] if self.proxy_addrs else ""
        # 代理全挂时是否回退直连（默认开，否则一次失败就整个网盘空白）
        self.allow_direct = _to_text(pick("pikpakFallbackDirect",
            "fallback_direct")).lower() not in ("0", "off", "false", "no")
        self.chan = None      # 已验证能用的通道 (kind, addr)
        self.diag_on = _to_text(pick("pikpakDiag", "diag")).lower() in (
            "1", "true", "on", "yes")
        # 强制走隧道（代理只支持 CONNECT、或不认绝对 URL 转发时打开）
        self.force_tunnel = _to_text(pick("pikpakForceTunnel",
            "force_tunnel")).lower() in ("1", "true", "on", "yes")
        self.last_diag = []

        mode = _to_text(pick("pikpakPlayMode", "play_mode")).lower()
        if mode in ("auto", "direct", "proxy", "relay"):
            self.play_mode = "proxy" if mode == "relay" else mode

        for key, attr, lo, hi in (
            ("pikpakRelayMaxMB", "relay_max_mb", 0, 8192),
            ("pikpakPageSize", "page_size", 10, 200),
            ("pikpakTimeout", "timeout", 5, 120),
        ):
            val = extend.get(key, cfg.get(key))
            if val in (None, ""):
                continue
            try:
                setattr(self, attr, max(lo, min(hi, int(val))))
            except Exception:
                pass

        if "pikpakEnable" in extend:
            self.enable = bool(extend.get("pikpakEnable"))
        if "pikpakSearch" in extend:
            self.enable_search = bool(extend.get("pikpakSearch"))
        if self.device_id == "":
            self.device_id = _pkp_md5("zaka-pikpak|" + (self.username
                or self.refresh_token[:32] or "device"))
        return None

    def ready(self):
        if not self.enable:
            return False
        return bool(self.refresh_token or (self.username and self.password)
            or self.access_token)

    def hint(self):
        if not self.enable:
            return "PikPak 已关闭（ext 里设置 pikpakEnable:false 关闭的）"
        return ("PikPak 未配置账号：ext 里填 pikpakRefreshToken"
            "（浏览器登录 mypikpak.com 后从 cookie 里取 refresh_token）")

    # ---------- 分类 / 列表 ----------

    def homeContent(self, filter=None):
        cls = [{"type_id": PKP_BROWSE_PREFIX + "root",
            "type_name": "PikPak 全部文件"}]
        if self.diag_on:
            cls.append({"type_id": PKP_BROWSE_PREFIX + "diag",
                "type_name": "PikPak 连接诊断"})
        return {"class": cls, "filters": {}}

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        page = max(1, _safe_int(pg, 1))
        head = _to_text(tid)
        if head == PKP_BROWSE_PREFIX + "diag":
            rows = self.diag() or ["无诊断信息"]
            out = [{"vod_id": "pkp:diag:%d" % i,
                    "vod_name": "%02d. %s" % (i + 1, t),
                    "vod_remarks": "诊断", "ratio": 1.33}
                for i, t in enumerate(rows)]
            return {"list": out, "page": 1, "pagecount": 1,
                "limit": len(out), "total": len(out)}
        if not self.ready():
            return {"list": [], "page": page, "pagecount": 1,
                "limit": self.page_size, "total": 0, "msg": self.hint()}
        parent = ""
        if head.startswith(PKP_BROWSE_PREFIX):
            parent = head[len(PKP_BROWSE_PREFIX):].strip()
        if parent in ("root", "/"):
            parent = self.share_root
        try:
            items = self._list_all(parent)
        except PkpVerifyRequired as e:
            return {"list": [], "page": page, "pagecount": 1,
                "limit": self.page_size, "total": 0,
                "msg": "PikPak 需要人机验证：%s" % e.url}
        except Exception as e:
            return {"list": [], "page": page, "pagecount": 1,
                "limit": self.page_size, "total": 0,
                "msg": "PikPak 取列表失败：%s" % self._err(e)}
        out = []
        for it in items:
            vod = self._to_vod(it)
            if vod:
                out.append(vod)
        start = (page - 1) * self.page_size
        page_items = out[start:start + self.page_size]
        total = len(out)
        return {"list": page_items, "page": page,
            "pagecount": max(1, (total + self.page_size - 1) // self.page_size),
            "limit": self.page_size, "total": total}

    def detailContent(self, ids):
        vid = str(ids[0]) if isinstance(ids, (list, tuple)) and ids \
            else str(ids or "")
        if vid.startswith(PKP_FILE_PREFIX):
            fid = vid[len(PKP_FILE_PREFIX):].strip()
            try:
                item = self._file(fid)
            except Exception as e:
                return {"list": [{"vod_id": vid, "vod_name": "PikPak 文件",
                    "vod_content": "取文件信息失败：%s" % self._err(e)}]}
            name = item.get("name") or "PikPak 文件"
            size = _pkp_join_size(item.get("size"))
            return {"list": [{
                "vod_id": vid, "vod_name": name, "vod_pic": VIDEO_PIC,
                "vod_content": "PikPak：%s\n大小：%s\n修改：%s"
                    % (name, size, _pkp_day(item.get("modified_time"))
                        or "-"),
                "vod_play_from": "PikPak",
                "vod_play_url": "%s$%s" % (self._safe_label(name),
                    PKP_FILE_PREFIX + fid),
            }]}
        if vid.startswith(PKP_BROWSE_PREFIX):
            fid = vid[len(PKP_BROWSE_PREFIX):].strip()
            if fid == "root":
                fid = self.share_root
            if not self.ready():
                return {"list": [{"vod_id": vid, "vod_name": "PikPak",
                    "vod_content": self.hint()}]}
            try:
                items = self._list_all(fid)
            except Exception as e:
                return {"list": [{"vod_id": vid, "vod_name": "PikPak 目录",
                    "vod_content": "取目录失败：%s" % self._err(e)}]}
            name = self._folder_name(fid)
            eps = []
            used = set()
            for it in items:
                if it.get("kind") == "drive#folder":
                    continue
                if not self._is_video(it):
                    continue
                label = self._safe_label(it.get("name") or "文件", used)
                eps.append("%s$%s%s" % (label, PKP_FILE_PREFIX,
                    it.get("id") or ""))
            return {"list": [{
                "vod_id": vid, "vod_name": name, "vod_pic": FOLDER_PIC,
                "vod_content": "PikPak 目录（%d 个可播放文件）" % len(eps),
                "vod_play_from": "PikPak" if eps else "",
                "vod_play_url": "#".join(eps),
            }]}
        return {"list": []}

    def searchContent(self, key, quick=False, pg="1"):
        keyword = _to_text(key)
        page = max(1, _safe_int(pg, 1))
        if not keyword or not self.ready() or not self.enable_search:
            return {"list": [], "page": page, "pagecount": 1,
                "limit": PKP_SEARCH_LIMIT, "total": 0}
        try:
            data = self._search(keyword)
        except Exception:
            return {"list": [], "page": page, "pagecount": 1,
                "limit": PKP_SEARCH_LIMIT, "total": 0}
        out = []
        for it in data:
            vod = self._to_vod(it)
            if vod:
                out.append(vod)
            if len(out) >= PKP_SEARCH_LIMIT:
                break
        return {"list": out, "page": page,
            "pagecount": page + 1 if len(out) >= PKP_SEARCH_LIMIT else page,
            "limit": PKP_SEARCH_LIMIT, "total": len(out)}

    # ---------- 播放 ----------

    def playerContent(self, flag, ids, vipFlags=None):
        vid = str(ids[0]) if isinstance(ids, (list, tuple)) and ids \
            else str(ids or "")
        if not vid.startswith(PKP_FILE_PREFIX):
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                "msg": "不支持的播放参数"}
        if not self.ready():
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                "msg": self.hint()}
        fid = vid[len(PKP_FILE_PREFIX):].strip()
        now = time.time()
        hit = self._link_cache.get(fid)
        if hit and now - hit.get("ts", 0) < PKP_LINK_TTL:
            return self._play_result(hit.get("url"), hit.get("size") or 0)
        fail = self._fail.get(fid)
        if fail and now - fail.get("ts", 0) < PKP_FAIL_TTL:
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                "msg": "PikPak 取链失败：%s" % fail.get("err")}
        try:
            item = self._file(fid)
            url = self._media_url(item)
        except PkpVerifyRequired as e:
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                "msg": "PikPak 需要人机验证：%s" % e.url}
        except Exception as e:
            self._fail[fid] = {"ts": now, "err": self._err(e)}
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                "msg": "PikPak 取链失败：%s" % self._err(e)}
        if not url:
            self._fail[fid] = {"ts": now, "err": "没有可用的直链（会员/转码限制）"}
            return {"parse": 0, "jx": 0, "url": "", "header": {},
                "msg": "PikPak 没有可用的直链（有些文件需要会员或正在转码）"}
        size = 0
        try:
            size = int(str(item.get("size") or "0"))
        except Exception:
            size = 0
        self._link_cache[fid] = {"ts": now, "url": url, "size": size}
        return self._play_result(url, size)

    def _play_result(self, url, size):
        header = {"User-Agent": self.ua, "Referer": "https://mypikpak.com/"}
        mode = self.play_mode
        if mode == "proxy":
            return self._relay_result(url, size, "PikPak 代理播放")
        if mode == "direct":
            return {"parse": 0, "jx": 0, "url": url, "header": header}
        direct_ok = self._probe(url, False)
        if direct_ok:
            return {"parse": 0, "jx": 0, "url": url, "header": header}
        if self.proxy and self._probe(url, True):
            limit = self.relay_max_mb * 1024 * 1024
            if limit and size and size > limit:
                return {"parse": 0, "jx": 0, "url": url, "header": header,
                    "msg": "直连不通、文件过大（%s）不走中转，已在播放器里直接播"
                        % _pkp_join_size(size)}
            return self._relay_result(url, size, "PikPak 经代理中转播放")
        return {"parse": 0, "jx": 0, "url": url, "header": header}

    def _relay_result(self, url, size, note):
        payload = json.dumps({"u": url, "h": {
            "User-Agent": self.ua,
            "Referer": "https://mypikpak.com/",
        }}, ensure_ascii=False)
        token = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")
        token = token.replace("=", "")
        relay = "http://127.0.0.1:9978/proxy?do=py&%s=%s" % (
            PKP_PROXY_QUERY, token)
        return {"parse": 0, "jx": 0, "url": relay,
            "header": {"User-Agent": self.ua},
            "msg": note + ("（%s）" % _pkp_join_size(size) if size else "")}

    def relay(self, token, param=None):
        param = param if isinstance(param, dict) else {}
        try:
            pad = "=" * (-len(token) % 4)
            info = json.loads(base64.urlsafe_b64decode(
                (token + pad).encode("ascii")).decode("utf-8"))
        except Exception:
            return [400, "text/plain", b"bad relay token", {}]
        url = info.get("u") or ""
        if not url.startswith("http"):
            return [400, "text/plain", b"bad url", {}]
        headers = dict(info.get("h") or {})
        rng = param.get("range") or param.get("Range") or ""
        if rng:
            headers["Range"] = rng
        max_bytes = self.relay_max_mb * 1024 * 1024
        try:
            status, mime, body, extra = self._raw_get(url, headers,
                proxy=True, timeout=max(15, self.timeout),
                max_bytes=max_bytes or 0)
        except Exception:
            return [502, "text/plain", b"pikpak relay error", {}]
        hdrs = {"Access-Control-Allow-Origin": "*",
            "Accept-Ranges": "bytes"}
        for k in ("Content-Range", "Content-Length"):
            if extra.get(k):
                hdrs[k] = extra.get(k)
        return [status, mime or "video/mp4", body, hdrs]

    # ---------- 内部：数据 ----------

    def _to_vod(self, item):
        fid = _to_text(item.get("id"))
        name = _to_text(item.get("name"))
        if not fid or not name:
            return None
        if item.get("kind") == "drive#folder":
            return {"vod_id": PKP_BROWSE_PREFIX + fid, "vod_name": name,
                "vod_pic": FOLDER_PIC, "vod_remarks": "目录",
                "vod_tag": "folder", "ratio": 1.33}
        if not self._is_video(item):
            return None
        return {"vod_id": PKP_FILE_PREFIX + fid, "vod_name": name,
            "vod_pic": VIDEO_PIC,
            "vod_remarks": _pkp_join_size(item.get("size")),
            "vod_time": _pkp_day(item.get("modified_time")), "ratio": 1.33}

    def _folder_name(self, fid):
        if not fid:
            return "PikPak 全部文件"
        try:
            info = self._file(fid)
            return _to_text(info.get("name")) or "PikPak 目录"
        except Exception:
            return "PikPak 目录"

    def _is_video(self, item):
        mime = _to_text(item.get("mime_type")).lower()
        for prefix in PKP_VIDEO_MIME:
            if mime.startswith(prefix):
                return True
        name = _to_text(item.get("name")).lower()
        return name.endswith(VIDEO_EXTS)

    def _media_url(self, item):
        url = ""
        medias = item.get("medias") or []
        if isinstance(medias, list):
            for m in medias:
                link = (m or {}).get("link") or {}
                u = _to_text(link.get("url"))
                if u:
                    url = u
                    break
        if not url:
            url = _to_text(item.get("web_content_link"))
        return url

    def _safe_label(self, name, used=None):
        raw = _to_text(name)
        safe = "".join(" " if c in "$#&?=:|\\/\n\r\t" else c for c in raw)
        safe = " ".join(safe.split())[:60]
        if not safe:
            safe = "PikPak 文件"
        if used is None:
            return safe
        if safe not in used:
            used.add(safe)
            return safe
        n = 2
        while True:
            cand = "%s (%d)" % (safe, n)
            if cand not in used:
                used.add(cand)
                return cand
            n += 1

    def _list_all(self, parent_id):
        key = parent_id or "root"
        hit = self._list_cache.get(key)
        now = time.time()
        if hit and now - hit[0] < PKP_LIST_TTL:
            return hit[1]
        items = []
        token = ""
        pages = 0
        while pages < 10:
            data = self._files(parent_id, token, self.page_size)
            chunk = data.get("files") or []
            items.extend(chunk)
            token = _to_text(data.get("next_page_token"))
            pages += 1
            if not token or len(items) >= 300:
                break
        self._list_cache[key] = (now, items)
        return items

    def _search(self, keyword):
        items = []
        try:
            data = self._files("", "", PKP_SEARCH_LIMIT, q=keyword)
            items = data.get("files") or []
        except Exception:
            items = []
        if not items:
            items = self._walk_search(keyword, self.share_root or "", 0)
        return items

    def _walk_search(self, keyword, parent, depth):
        if depth > 4:
            return []
        out = []
        try:
            items = self._list_all(parent)
        except Exception:
            return out
        low = keyword.lower()
        for it in items:
            if it.get("kind") == "drive#folder":
                out.extend(self._walk_search(keyword, it.get("id") or "",
                    depth + 1))
            elif low in _to_text(it.get("name")).lower():
                out.append(it)
            if len(out) >= PKP_SEARCH_LIMIT:
                break
        return out

    # ---------- 内部：HTTP ----------

    def _normalize_proxy(self, proxy):
        proxy = _to_text(proxy)
        if not proxy or proxy.lower() in ("off", "none", "0", "false"):
            return ""
        if "://" not in proxy:
            proxy = "http://" + proxy.lstrip("/")
        return proxy.rstrip("/")

    def _proxy_candidates(self):
        """requests 用的代理串列表，末尾保留直连兜底"""
        out = []
        for addr in self.proxy_addrs:
            base = re.sub(r"^[a-z0-9]+://", "", _to_text(addr)).strip("/")
            if not base:
                continue
            if self.proxy_type in ("socks5", "socks5h"):
                out.extend(["socks5h://" + base, "socks5://" + base])
            elif self.proxy_type == "socks4":
                out.append("socks4://" + base)
            elif self.proxy_type == "http":
                out.append("http://" + base)
            else:
                out.append("http://" + base)
                if _PKP_HAS_SOCKS:
                    out.append("socks5h://" + base)
        if self.proxy_ok in out:
            out = [self.proxy_ok] + [x for x in out if x != self.proxy_ok]
        if self.allow_direct:
            out.append("")
        return out or [""]

    # ---------- 纯 socket 通道（不依赖 requests / PySocks）----------

    def _chan_candidates(self):
        out = []
        if self.chan:
            out.append(self.chan)
        for addr in self.proxy_addrs:
            for kind in ("http", "socks5"):
                if (kind, addr) not in out:
                    out.append((kind, addr))
        if self.allow_direct:
            out.append(("direct", ""))
        return out

    def _sock_request(self, method, url, headers=None, body=None,
                      timeout=None, max_bytes=0):
        errs = []
        for kind, addr in self._chan_candidates():
            try:
                st, h, b = _pkp_sk_http(method, url, headers, body,
                    timeout or self.timeout,
                    addr if kind != "direct" else "", kind, max_bytes)
                if self.chan != (kind, addr):
                    self.chan = (kind, addr)
                    self.chan_ts = time.time()
                return st, h, b
            except Exception as e:
                errs.append("%s%s:%s" % (kind, ("@" + addr) if addr else "",
                    str(e)[:36]))
                if self.chan == (kind, addr):
                    self.chan = None
        raise RuntimeError("通道全不通(%s)" % "; ".join(errs[:4]))

    def diag(self):
        """诊断：端口通不通、代理协议对不对、能不能直连"""
        out = []
        self.last_diag = out
        if _pkp_socket is None:
            out.append("当前环境不支持 socket 直连")
            return out
        for addr in self.proxy_addrs:
            h, p = _pkp_split_addr(addr)
            if not h or not p:
                out.append("%s 地址不合法" % addr)
                continue
            try:
                sk = _pkp_socket.create_connection((h, p), 2.0)
                sk.close()
                out.append("%s 端口通" % addr)
            except Exception as e:
                out.append("%s 端口不通(%s)" % (addr, type(e).__name__))
                continue
            for kind in ("http", "socks5"):
                try:
                    sk = _pkp_socket.create_connection((h, p), 2.0)
                    sk.settimeout(6)
                    if kind == "http":
                        _pkp_http_connect(sk, "user.mypikpak.net", 443)
                    else:
                        _pkp_socks5(sk, "user.mypikpak.net", 443)
                    sk.close()
                    out.append("  %s 隧道可用" % kind)
                except Exception as e:
                    out.append("  %s 隧道失败(%s)" % (kind, str(e)[:40]))
        try:
            sk = _pkp_socket.create_connection(
                ("user.mypikpak.net", 443), 5)
            sk.close()
            out.append("直连 user.mypikpak.net 通")
        except Exception as e:
            out.append("直连 user.mypikpak.net 不通(%s)" % type(e).__name__)
        return out

    def _http(self, method, url, params=None, body=None, headers=None,
              auth=True, timeout=None):
        if params:
            pairs = []
            for k, v in params.items():
                if v is None:
                    continue
                pairs.append((k, str(v)))
            qs = urllib.parse.urlencode(pairs)
            url = url + ("&" if "?" in url else "?") + qs
        raw = None
        if body is not None:
            raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        hdrs = {"Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*"}
        hdrs.update(headers or {})
        errors = []
        for proxy in self._proxy_candidates():
            try:
                text = self._do_request(method, url, raw, hdrs, proxy,
                    timeout or self.timeout)
                if proxy:
                    self.proxy_ok = proxy
                try:
                    return json.loads(text)
                except Exception:
                    raise RuntimeError("返回不是 JSON：%s" % text[:120])
            except PkpHttpStatus:
                raise
            except Exception as e:
                errors.append((proxy, e))
                continue
        if errors:
            prox_fail = [e for p, e in errors if p]
            direct_fail = [e for p, e in errors if not p]
            detail = str(errors[-1][1])[:80]
            if self.diag_on:
                detail += " | " + "; ".join(self.diag()[:3])
            if self.proxy_addrs and prox_fail and not direct_fail:
                raise RuntimeError("代理 %s 连不上（%s）" % (
                    re.sub(r"^[a-z0-9]+://", "", self.proxy_addrs[0]),
                    detail))
            raise RuntimeError("取数据失败（%s）" % detail)
        raise RuntimeError("请求失败")

    def _do_request(self, method, url, raw, hdrs, proxy, timeout):
        last = None
        if requests is not None and not self.force_tunnel:
            try:
                kwargs = {"headers": hdrs, "timeout": timeout}
                if raw is not None:
                    kwargs["data"] = raw
                if proxy:
                    kwargs["proxies"] = {"http": proxy, "https": proxy}
                r = requests.request(method, url, **kwargs)
                text = r.text if hasattr(r, "text") else r.content.decode(
                    "utf-8", "ignore")
                if getattr(r, "status_code", 200) >= 400:
                    try:
                        json.loads(text)
                    except Exception:
                        raise PkpHttpStatus(r.status_code, text[:120])
                return text
            except PkpHttpStatus:
                raise
            except Exception as e:
                last = e
        # 兜底：纯 socket 通道（http 隧道 / socks5 / 直连 逐个试）
        try:
            st, _h, b = self._sock_request(method, url, hdrs, raw, timeout)
            text = b.decode("utf-8", "ignore")
            if st >= 400:
                try:
                    json.loads(text)
                except Exception:
                    raise PkpHttpStatus(st, text[:120])
            return text
        except PkpHttpStatus:
            raise
        except Exception as e:
            if last is None:
                raise
            raise RuntimeError("%s / %s" % (str(last)[:60], str(e)[:90]))

    def _raw_get(self, url, headers, proxy=False, timeout=15, max_bytes=0,
                 need_meta=False):
        hdrs = dict(headers or {})
        if requests is not None:
            try:
                kwargs = {"headers": hdrs, "timeout": timeout, "stream": True}
                if proxy and self.proxy_addrs:
                    px = self._proxy_candidates()
                    if px and px[0]:
                        kwargs["proxies"] = {"http": px[0], "https": px[0]}
                r = requests.get(url, **kwargs)
                body = b""
                if max_bytes:
                    for chunk in r.iter_content(65536):
                        body += chunk
                        if len(body) >= max_bytes:
                            body = body[:max_bytes]
                            break
                else:
                    body = r.content
                return (r.status_code, r.headers.get("Content-Type") or "",
                    body, {"Content-Range": r.headers.get("Content-Range") or "",
                        "Content-Length": r.headers.get("Content-Length") or ""})
            except Exception:
                pass
        st, h, b = self._sock_request("GET", url, hdrs, None, timeout,
            max_bytes)
        return (st, h.get("content-type", ""), b,
            {"Content-Range": h.get("content-range", ""),
                "Content-Length": h.get("content-length", "")})

    def _probe(self, url, use_proxy):
        if use_proxy and not self.proxy:
            return False
        host = urllib.parse.urlsplit(url).netloc.lower()
        key = "proxy:%s" % host if use_proxy else "direct:%s" % host
        now = time.time()
        hit = self._probe_cache.get(key)
        if hit and now - hit[0] < 600:
            return hit[1]
        ok = self._probe_real(url, use_proxy)
        self._probe_cache[key] = (now, ok)
        return ok

    def _probe_real(self, url, use_proxy):
        try:
            status, _mime, _body, _extra = self._raw_get(url,
                {"Range": "bytes=0-1", "User-Agent": self.ua},
                proxy=use_proxy, timeout=5, max_bytes=2, need_meta=True)
            return status in (200, 206, 416)
        except Exception:
            return False

    # ---------- 内部：认证 ----------

    def _err(self, e):
        if isinstance(e, PkpVerifyRequired):
            return "需要人机验证"
        if isinstance(e, RuntimeError):
            msg = str(e)
            if "session lock" in msg.lower():
                return ("refresh_token 无效或已过期，请在浏览器里重新取一个"
                    "（%s）" % msg[:60])
        if isinstance(e, PkpHttpStatus):
            low = (e.text or "").lower()
            if "domain name is invalid" in low:
                return "接口域名不可用（%s）" % e.text[:60]
            if e.code in (502, 503, 504):
                return "服务端返回 %s，可能是网络或区域限制，建议开启代理" % e.code
            if e.code in (401, 403):
                return "服务端拒绝（%s），登录状态可能失效或当前网络被限制" % e.code
            return "服务端返回 HTTP %s（%s）" % (e.code, e.text[:80])
        return str(e)[:160]

    def _sign(self):
        ts = str(int(time.time() * 1000))
        s = "%s%s%s%s%s" % (self.client_id, self.client_version,
            self.package_name, self.device_id, ts)
        for alg in self.algorithms:
            s = hashlib.md5((s + alg).encode("utf-8")).hexdigest()
        return ts, "1." + s

    def _captcha(self, action, meta=None):
        ts, sign = self._sign()
        m = dict(meta or {})
        m["client_version"] = self.client_version
        m["package_name"] = self.package_name
        m["timestamp"] = ts
        m["captcha_sign"] = sign
        body = {"action": action, "captcha_token": "",
            "client_id": self.client_id, "device_id": self.device_id,
            "meta": m,
            "redirect_uri": "xlaccsdk01://xbase.cloud/callback?state=harbor"}
        data = self._http("POST", self.user_base + "/v1/shield/captcha/init",
            {"client_id": self.client_id}, body,
            {"User-Agent": self.ua, "X-Device-ID": self.device_id},
            timeout=self.timeout)
        url = _to_text(data.get("url"))
        if url:
            raise PkpVerifyRequired(url)
        self.captcha_token = _to_text(data.get("captcha_token"))
        self.captcha_ts = time.time()
        return self.captcha_token

    def _ensure_captcha(self, action, force=False):
        if self.captcha_token and not force and time.time() \
                - self.captcha_ts < 240:
            return self.captcha_token
        return self._captcha(action)

    def _refresh(self, force=False):
        if not self.refresh_token:
            raise RuntimeError("没有 refresh_token")
        body = {"client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token}
        data = self._http("POST", self.user_base + "/v1/auth/token",
            {"client_id": self.client_id}, body, {"User-Agent": ""},
            timeout=self.timeout)
        code = _safe_int(data.get("error_code"), 0)
        if code:
            raise RuntimeError(data.get("error_description")
                or data.get("error") or ("刷新令牌失败 %s" % code))
        self.access_token = _to_text(data.get("access_token"))
        new_rt = _to_text(data.get("refresh_token"))
        if new_rt:
            self.refresh_token = new_rt
        sid = _to_text(data.get("sub"))
        if sid:
            self.user_id = sid
        self.token_ts = time.time()
        if not self.access_token:
            raise RuntimeError("刷新令牌没有返回 access_token")
        return self.access_token

    def _login(self):
        if not (self.username and self.password):
            raise RuntimeError("没有可用凭据")
        meta = {}
        if re.match(r"^\w+([-+.']\w+)*@\w+([-.]\w+)*\.\w+([-.]\w+)*$",
                self.username):
            meta["email"] = self.username
        elif 11 <= len(self.username) <= 18:
            meta["phone_number"] = self.username
        else:
            meta["username"] = self.username
        action = "POST:/v1/auth/signin"
        token = self._captcha(action, meta)
        body = {"captcha_token": token, "client_id": self.client_id,
            "client_secret": self.client_secret, "username": self.username,
            "password": self.password}
        data = self._http("POST", self.user_base + "/v1/auth/signin",
            {"client_id": self.client_id}, body, {"User-Agent": self.ua},
            timeout=self.timeout)
        code = _safe_int(data.get("error_code"), 0)
        if code:
            raise RuntimeError(data.get("error_description")
                or data.get("error") or ("登录失败 %s" % code))
        self.access_token = _to_text(data.get("access_token"))
        self.refresh_token = _to_text(data.get("refresh_token")) \
            or self.refresh_token
        self.user_id = _to_text(data.get("sub")) or self.user_id
        self.token_ts = time.time()
        if not self.access_token:
            raise RuntimeError("登录没有返回 access_token")
        return self.access_token

    def _ensure_token(self, force=False):
        if self.access_token and not force and time.time() \
                - self.token_ts < PKP_TOKEN_TTL:
            return self.access_token
        if self.refresh_token:
            return self._refresh(force=force)
        if self.username and self.password:
            return self._login()
        if self.access_token:
            return self.access_token
        raise RuntimeError(self.hint())

    def _api(self, method, path, params=None, body=None, retry=2,
             base=None, action=None):
        base = base or self.drive_base
        url = base + path
        last = None
        for attempt in range(retry + 1):
            act = action or ("%s:%s" % (method, path))
            self._ensure_token()
            if not self.captcha_token:
                self._ensure_captcha(act)
            headers = {"User-Agent": self.ua,
                "X-Device-ID": self.device_id,
                "X-Captcha-Token": self.captcha_token,
                "Referer": "https://mypikpak.com/"}
            if self.access_token:
                headers["Authorization"] = "Bearer " + self.access_token
            try:
                data = self._http(method, url, params, body, headers,
                    timeout=self.timeout)
            except Exception as e:
                last = e
                continue
            code = _safe_int(data.get("error_code"), 0)
            err = _to_text(data.get("error"))
            if code in (16, 4121, 4122) or err == "unauthenticated":
                if attempt >= retry:
                    raise RuntimeError("登录状态失效，请更新 refresh_token")
                self.access_token = ""
                try:
                    self._refresh(force=True)
                except Exception as e:
                    last = e
                    if self.username and self.password:
                        self._login()
                    else:
                        raise
                continue
            if code == 9 or err in ("captcha_invalid", "captcha_required"):
                if attempt >= retry:
                    raise RuntimeError(data.get("error_description")
                        or "验证码校验失败")
                self._ensure_captcha(act, force=True)
                continue
            if code:
                raise RuntimeError("%s（错误码 %s）" % (
                    data.get("error_description") or err or "接口报错", code))
            return data
        raise last if last else RuntimeError("请求失败")

    def _files(self, parent_id="", page_token="", limit=100, q=None,
               order=None):
        params = {"parent_id": parent_id or "",
            "thumbnail_size": "SIZE_LARGE", "with_audit": "true",
            "limit": str(limit),
            "filters": '{"phase":{"eq":"PHASE_TYPE_COMPLETE"},'
                '"trashed":{"eq":false}}'}
        if page_token:
            params["page_token"] = page_token
        if q:
            params["q"] = q
        if order:
            params["order"] = order
        return self._api("GET", "/drive/v1/files", params)

    def _file(self, fid):
        params = {"_magic": "2021", "usage": "CACHE",
            "thumbnail_size": "SIZE_LARGE"}
        return self._api("GET", "/drive/v1/files/" + urllib.parse.quote(fid),
            params)

    def destroy(self):
        self._probe_cache.clear()
        self._list_cache.clear()
        self._link_cache.clear()
        self._fail.clear()


class Spider:
    _P6_SEARCH_WAIT = 2.0

    def __init__(self):
        self.p6 = Pan6Spider()
        self.pkp = PikPakSpider()
        self.ua = UA
        self.timeout = 20
        self.site_referer = HOST + "/"
        self._entity_event = threading.Event()
        self._entity_stop = False
        self._home_videos_cache = None
        self._proxy_cache = {}
        self._proxy_cache_size = 0
        self.s = None
        self.session = None
        self.sess = None
        if requests is not None:
            try:
                self.s = requests.Session()
                self.session = self.s
                self.sess = self.s
            except Exception:
                pass

    def getDependence(self):
        return []

    def init(self, extend=""):
        try:
            self.p6.init(extend)
        except Exception:
            pass
        try:
            self.pkp.init(extend)
        except Exception:
            pass
        ext = _normalize_extend(extend)
        mode = ext.get("pic_mode")
        if mode in ("wsrv", "origin", "local"):
            PIC_PROXY["mode"] = mode
        port = ext.get("pic_proxy_port") or ext.get("proxy_port")
        if port:
            try:
                PIC_PROXY["port"] = int(port)
            except (TypeError, ValueError):
                pass
        return None

    def homeContent(self, filter=None):
        classes = [{"type_id": str(c["type_id"]), "type_name": c["type_name"]}
            for c in CATE]
        classes.append({"type_id": "root", "type_name": "6盘"})
        if self.pkp.enable:
            classes.append({"type_id": PKP_BROWSE_PREFIX + "root",
                "type_name": "PikPak"})
            if getattr(self.pkp, "diag_on", False):
                classes.append({"type_id": PKP_BROWSE_PREFIX + "diag",
                    "type_name": "PikPak 连接诊断"})
        return {"class": classes, "filters": {}}

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        head = str(tid).split("@")[0]
        if head == "root" or head.startswith(PAN6_BROWSE_PREFIX) \
                or head.startswith(PAN6_FILE_PREFIX):
            return self.p6.categoryContent(tid, pg, filter, extend)
        if head.startswith(PKP_BROWSE_PREFIX) or head.startswith(PKP_FILE_PREFIX):
            try:
                return self.pkp.categoryContent(tid, pg, filter, extend)
            except Exception as e:
                return {"list": [], "page": 1, "pagecount": 1,
                    "limit": 0, "total": 0, "msg": str(e)[:120]}
        try:
            page = int(pg)
        except (TypeError, ValueError):
            page = 1
        try:
            return category_data(tid, page, extend, filter)
        except Exception:
            return {"page": page, "pagecount": page, "limit": PER_PAGE,
                "total": 0, "list": []}

    def detailContent(self, ids):
        if isinstance(ids, (list, tuple)):
            vid = str(ids[0]) if ids else ""
        else:
            vid = str(ids or "")
        if vid.startswith(PAN6_FILE_PREFIX) or vid.startswith(PAN6_BROWSE_PREFIX):
            try:
                return self.p6.detailContent(ids)
            except Exception:
                return {"list": []}
        if vid.startswith(PKP_FILE_PREFIX) or vid.startswith(PKP_BROWSE_PREFIX):
            try:
                return self.pkp.detailContent(ids)
            except Exception as e:
                return {"list": [{"vod_id": vid, "vod_name": "PikPak",
                    "vod_content": str(e)[:160]}]}
        try:
            arr = detail_data(vid)
            if arr:
                self._attach_p6(arr[0])
            return {"list": arr}
        except Exception:
            return {"list": []}

    def _attach_p6(self, vod):
        play_url = vod.get("vod_play_url") or ""
        magnets = pick_magnets(play_url.replace("$$$", "\n"))
        if not magnets or not getattr(self.p6, "enable_offline_pan6", False):
            return
        if not (getattr(self.p6, "pan6_user", "")
            or getattr(self.p6, "access_token", "")):
            return
        items = []
        seen = set()
        for mg in magnets:
            m = re.search(r"btih:([A-Za-z0-9]+)", mg, re.I)
            h = m.group(1) if m else ""
            if not h or h.lower() in seen:
                continue
            seen.add(h.lower())
            items.append({"label": "磁力[%s]" % h[:8], "hash": h,
                "magnet": mg})
        if not items:
            return
        eps = self._p6_eps(items)
        if not eps:
            return
        froms = [x for x in (vod.get("vod_play_from") or "").split("$$$") if x]
        urls = [x for x in (vod.get("vod_play_url") or "").split("$$$") if x]
        froms.insert(0, "6盘")
        urls.insert(0, "#".join(eps))
        vod["vod_play_from"] = "$$$".join(froms)
        vod["vod_play_url"] = "$$$".join(urls)
        self._p6_prewarm_async(items)

    def searchContent(self, key, quick=False, pg="1"):
        key = str(key or "").strip()
        if not key:
            return {"list": [], "page": 1, "pagecount": 1,
                "limit": 0, "total": 0}
        try:
            page = int(pg)
        except (TypeError, ValueError):
            page = 1
        result = []
        seen = set()
        if page == 1:
            try:
                data = search_data(key, 1)
                for v in (data.get("list") or []):
                    vid = v.get("vod_id") or ""
                    if vid and vid not in seen:
                        seen.add(vid)
                        result.append(v)
            except Exception:
                pass
            self._append_p6_search(result, seen, key)
            self._append_pkp_search(result, seen, key)
        return {"list": result, "page": 1, "pagecount": 1,
            "limit": len(result) or 24, "total": len(result)}

    def _append_p6_search(self, result, seen, key):
        box = []

        def run():
            try:
                box.append(self.p6.searchContent(key, False, 1))
            except Exception:
                box.append(None)

        try:
            th = threading.Thread(target=run, daemon=True)
            th.start()
            th.join(self._P6_SEARCH_WAIT)
        except Exception:
            return
        r = box[0] if box else None
        if not isinstance(r, dict):
            return
        for v in (r.get('list') or []):
            vid = v.get('vod_id') or ''
            if vid and vid not in seen:
                seen.add(vid)
                result.append(v)

    def _append_pkp_search(self, result, seen, key):
        if not self.pkp.enable_search or not self.pkp.ready():
            return
        box = []

        def run():
            try:
                box.append(self.pkp.searchContent(key, False, 1))
            except Exception:
                box.append(None)

        try:
            th = threading.Thread(target=run, daemon=True)
            th.start()
            th.join(self._P6_SEARCH_WAIT)
        except Exception:
            return
        r = box[0] if box else None
        if not isinstance(r, dict):
            return
        for v in (r.get('list') or []):
            vid = v.get('vod_id') or ''
            if vid and vid not in seen:
                seen.add(vid)
                result.append(v)

    def playerContent(self, flag, ids, vipFlags=None):
        header = {'User-Agent': self.ua, 'Referer': self.site_referer}
        if isinstance(ids, (list, tuple)):
            pid = str(ids[0]) if ids else ''
        else:
            pid = str(ids or '')
        try:
            if (pid.startswith(PAN6_FILE_PREFIX)
                or pid.startswith(OFF_PREFIX_6PAN)
                or pid.startswith('pan6off:')):
                return self.p6.playerContent(flag, ids, vipFlags)

            if pid.startswith(PKP_FILE_PREFIX):
                return self.pkp.playerContent(flag, ids, vipFlags)

            if pid.startswith('magnet:'):
                return {'parse': 0, 'jx': 0, 'playUrl': '',
                    'url': pid, 'header': header}

            if pid.startswith('http'):
                r = {'parse': 0, 'jx': 0, 'playUrl': '',
                    'url': pid, 'header': header}
                if '.m3u8' in pid:
                    r['format'] = 'application/x-mpegURL'
                return r

            return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': '',
                'header': header, 'msg': '无法解析该播放地址'}
        except Exception as e:
            return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': '',
                'header': header, 'msg': '播放失败: ' + str(e)}

    def localProxy(self, param):
        if isinstance(param, str):
            try:
                param = json.loads(param)
            except Exception:
                param = {}
        if not isinstance(param, dict):
            param = {}
        relay = param.get(PKP_PROXY_QUERY) or param.get('pkp_url') or ''
        if relay:
            try:
                return self.pkp.relay(str(relay), param)
            except Exception:
                return [502, 'text/plain', b'relay error', {}]
        url = param.get('url') or ''
        if '@' in url:
            url = url.split('@', 1)[0]
        if not url or not url.startswith('http'):
            return [404, 'text/plain', b'Not Found', {}]
        hit = self._proxy_cache.get(url)
        if hit is not None:
            return [200, hit[0], hit[1],
                {'Access-Control-Allow-Origin': '*'}]
        try:
            headers = {
                'User-Agent': self.ua,
                'Referer': self.site_referer,
                'Accept': '*/*',
            }
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read()
                mime = resp.headers.get('Content-Type') or ''
            low = url.split('?')[0].lower()
            guess = ''
            if low.endswith('.m3u8'):
                guess = 'application/vnd.apple.mpegurl'
            elif low.endswith('.ts'):
                guess = 'video/mp2t'
            elif low.endswith('.key'):
                guess = 'application/octet-stream'
            elif low.endswith('.jpg') or low.endswith('.jpeg'):
                guess = 'image/jpeg'
            elif low.endswith('.png'):
                guess = 'image/png'
            elif low.endswith('.webp'):
                guess = 'image/webp'
            if guess and (not mime or 'octet-stream' in mime
                or 'text/plain' in mime):
                mime = guess
            if not mime:
                mime = 'application/octet-stream'
            if (len(body) <= 1024 * 1024
                and self._proxy_cache_size <= 8 * 1024 * 1024
                and len(self._proxy_cache) < 256):
                self._proxy_cache[url] = (mime, body)
                self._proxy_cache_size += len(body)
            return [200, mime, body,
                {'Access-Control-Allow-Origin': '*'}]
        except Exception:
            return [502, 'text/plain', b'proxy error', {}]

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        return False

    def action(self, action):
        return {}

    def destroy(self):
        self._entity_stop = True
        self._entity_event.set()
        self._home_videos_cache = None
        try:
            self.p6.destroy()
        except Exception:
            pass
        try:
            self.pkp.destroy()
        except Exception:
            pass
        return None

    def _fix_url(self, url):
        if not url:
            return ''
        url = str(url)
        if url.startswith('//'):
            url = 'https:' + url
        if not url.startswith('http'):
            return url
        if 'tp.spfcas.com/rhe951l4q/' in url:
            url = url.replace('tp.spfcas.com/rhe951l4q/',
                'c0.jdbstatic.com/')
        if 'jdbstatic.com/' in url and '@User-Agent=' not in url:
            url = ('%s@Referer=%s@User-Agent=%s'
                % (url, self.site_referer, self.ua))
        return url

    def _p6_eps_label(self, it, used):
        raw = str(it.get('label') or '')
        safe = ''.join(' ' if c in '$#&?=:|\\/\n\r\t' else c for c in raw)
        safe = ' '.join(safe.split())[:40]
        h = str(it.get('hash') or '')[:8]
        if not safe:
            safe = ('资源[%s]' % h) if h else '资源'
        if safe not in used:
            used.add(safe)
            return safe
        cand = ('%s [%s]' % (safe, h)) if h else safe
        if cand not in used:
            used.add(cand)
            return cand
        n = 2
        while True:
            cand2 = '%s (%d)' % (cand, n)
            if cand2 not in used:
                used.add(cand2)
                return cand2
            n += 1

    def _p6_eps(self, items):
        if not items:
            return []
        file_cache = getattr(self.p6, '_cache_pan6_file', None) or {}
        eps = []
        used = set()
        for it in items:
            label = self._p6_eps_label(it, used)
            fp = file_cache.get(str(it.get('hash') or '').lower())
            if fp:
                eps.append('%s$%s|%s' % (label, PAN6_FILE_PREFIX, fp))
            else:
                b64 = base64.b64encode(
                    str(it.get('magnet') or '').encode('utf-8')
                ).decode('ascii')
                eps.append('%s$%s%s' % (label, OFF_PREFIX_6PAN, b64))
        return eps

    def _p6_prewarm_async(self, items):
        try:
            p6 = getattr(self, 'p6', None)
            if p6 is None or not p6.enable_offline_pan6:
                return
            if not getattr(p6, 'enable_offline_prewarm', False):
                return
            try:
                count = int(getattr(p6, 'pan6_prewarm_count', 1) or 0)
            except Exception:
                count = 1
            if count <= 0:
                return
            task_cache = getattr(p6, '_cache_pan6_task', {}) or {}
            active = 0
            for t in task_cache.values():
                if isinstance(t, dict) and t.get('state') in (
                    'submitted', 'downloading', 'resolving'):
                    active += 1
            if active >= PAN6_MAX_TRACKED:
                return
            now = time.time()
            url_cache = getattr(p6, '_cache_pan6_url', {}) or {}
            file_cache = getattr(p6, '_cache_pan6_file', {}) or {}
            last_submit = getattr(p6, '_p6_last_submit', {}) or {}
            for it in (items or [])[:count]:
                h = str(it.get('hash') or '')
                hl = h.lower()
                if not hl:
                    continue
                if url_cache.get(hl) or file_cache.get(hl):
                    continue
                t = task_cache.get(hl)
                if isinstance(t, dict) and t.get('state') in (
                    'submitted', 'downloading', 'resolving',
                    'done', 'failed'):
                    continue
                if now - last_submit.get(hl, 0) < PAN6_SUBMIT_COOLDOWN:
                    continue
                magnet = 'magnet:?xt=urn:btih:' + h
                try:
                    threading.Thread(target=p6._p6_prewarm,
                        args=(magnet,), daemon=True).start()
                except Exception:
                    return
                break
        except Exception:
            pass
