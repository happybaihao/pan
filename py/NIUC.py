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

class Spider:
    _P6_SEARCH_WAIT = 2.0

    def __init__(self):
        self.p6 = Pan6Spider()
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
        return {"class": classes, "filters": {}}

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        head = str(tid).split("@")[0]
        if head == "root" or head.startswith(PAN6_BROWSE_PREFIX) \
                or head.startswith(PAN6_FILE_PREFIX):
            return self.p6.categoryContent(tid, pg, filter, extend)
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
