# -*- coding: utf-8 -*-
"""
115分享集合 —— OK影视 / TVBox(Python) 站源【修复版】
移植自「【网盘】115分享.js」（T4 插件版）
修复点：登录状态永久缓存bug、双重url解码token、网络抖动误判cookie失效、播放兜底初始化、错误提示优化
"""
import base64
import json
import os
import re
import tempfile
import threading
import time
import urllib.parse
import urllib.request
try:
    import sqlite3
except Exception:
    sqlite3 = None
try:
    from base.spider import Spider as _BaseSpider
except Exception:
    class _BaseSpider(object):
        pass

# ---------------------------------------------------------------- 默认配置
DEFAULT_DB_URL = (
    "https://file.ljcdn.com/psd-sinan-file/prod/appeal_evidence/"
    "C1606F803D024AD89ED9992532752CC5/kY8AWp.local"
)
DEFAULT_DB_NAMES = ["fake115share.db", "730e55806735c2548917cfb21806c4f2.db"]
DEFAULT_COOKIE = ""
DEFAULT_PAGE_SIZE = 60
DEFAULT_SEARCH_SIZE = 40
DEFAULT_TIMEOUT = 20
HOME_WAIT_MS = 8.0
MAX_DEPTH = 6
MAX_GROUPS = 40
MAX_FILES_PER_GROUP = 500
MAX_FILES = 1500
MAX_WALK_STEPS = 2000
DETAIL_CACHE_TTL = 600
DETAIL_CACHE_MAX = 200
DIR_PREFIX = "115d@"
FILE_PREFIX = "115f@"
VIDEO_EXTS = [
    ".mp4", ".mkv", ".webm", ".avi", ".wmv", ".flv", ".mov", ".mpeg", ".mpg",
    ".m4v", ".3gp", ".ts", ".m2ts", ".rm", ".rmvb", ".iso",
]
VIDEO_RE = re.compile(r"(" + "|".join(e.replace(".", r"\.") for e in VIDEO_EXTS) + r")$", re.I)
FILE_VIDEO_SQL = "(" + " OR ".join("name LIKE '%%%s'" % e for e in VIDEO_EXTS) + ")"
IS_DIR_SQL = "(fid IS NULL OR fid = '')"
IS_FILE_SQL = "(fid IS NOT NULL AND fid <> '')"
FOLDER_PIC = "https://img.icons8.com/fluency/96/folder-invoices--v1.png"
VIDEO_PIC = "https://img.icons8.com/color/48/video.png"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
)
SQLITE_MAGIC = b"SQLite format 3"
_LAST_EXTEND = {"value": ""}

# ---------------------------------------------------------------- 小工具
def _text(value):
    if value is None:
        return ""
    return str(value).strip()

def _first(value):
    if isinstance(value, (list, tuple)):
        return value[0] if value else ""
    return value

def _int(value, default=0):
    try:
        num = int(str(value).strip())
        return num
    except Exception:
        return default

def _clean(value, max_len=160):
    text = re.sub(r"[#$]+", " ", _text(value))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]

def _short_name(value, max_len=14):
    text = _text(value)
    plain = re.sub(r"[【】]", "", text).split("[")[0]
    plain = re.sub(r"\s+", " ", plain).strip()
    return (plain or text)[:max_len]

def _strip_ext(value):
    return VIDEO_RE.sub("", _text(value))

def _leaf_label(value):
    parts = [p for p in _text(value).split("/") if p]
    return parts[-1] if parts else ""

def _line_label(value):
    parts = [p for p in _text(value).split("/") if p]
    return "/".join(parts[-2:])

def _nat_key(value):
    return [
        (0, int(chunk)) if chunk.isdigit() else (1, chunk.lower())
        for chunk in re.split(r"(\d+)", _text(value))
        if chunk != ""
    ]

def _b64e(value):
    raw = _text(value).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

def _b64d(value):
    text = _text(value)
    if not text:
        return ""
    pad = "=" * (-len(text) % 4)
    try:
        return base64.urlsafe_b64decode(text + pad).decode("utf-8", "replace")
    except Exception:
        return ""

def _encode_dir(row_id):
    return "%s%s" % (DIR_PREFIX, row_id)

def _encode_file(row):
    parts = [
        _text(row.get("share_code")),
        _text(row.get("receive_code")),
        _text(row.get("fid")),
        _text(row.get("cid")),
    ]
    return FILE_PREFIX + _b64e("|".join(parts))

def _decode_file(value):
    raw = _text(value)
    if not raw:
        return None
    # 修复：播放器可能双重url编码，尝试一次解码
    try:
        raw2 = urllib.parse.unquote(raw)
        if raw2 != raw:
            raw = raw2
    except Exception:
        pass
    if not raw.startswith(FILE_PREFIX):
        return None
    body = raw[len(FILE_PREFIX):]
    plain = _b64d(body)
    if plain.count("|") == 3:
        c, r, f, p = plain.split("|")
        if f:
            return {"c": c, "r": r, "f": f, "p": p, "n": ""}
    try:
        data = json.loads(plain)
    except Exception:
        return None
    if not isinstance(data, dict) or not data.get("f"):
        return None
    return data

def _share_url(share_code, receive_code):
    code = _text(share_code)
    if not code:
        return ""
    pwd = _text(receive_code)
    return "https://115cdn.com/s/%s%s" % (code, ("?password=" + pwd) if pwd else "")

def _http_get(url, headers=None, timeout=None, data=None):
    req = urllib.request.Request(url, data=data)
    hdr = {"User-Agent": UA}
    if headers:
        hdr.update(headers)
    for key, val in hdr.items():
        req.add_header(key, val)
    ctx = None
    try:
        import ssl
        ctx = ssl._create_unverified_context()
    except Exception:
        ctx = None
    if ctx is not None:
        resp = urllib.request.urlopen(req, timeout=timeout or DEFAULT_TIMEOUT, context=ctx)
    else:
        resp = urllib.request.urlopen(req, timeout=timeout or DEFAULT_TIMEOUT)
    try:
        return resp.read()
    finally:
        try:
            resp.close()
        except Exception:
            pass

def _http_json(url, headers=None, timeout=None, data=None):
    try:
        body = _http_get(url, headers=headers, timeout=timeout, data=data)
    except Exception:
        return {}
    try:
        return json.loads(body.decode("utf-8", "replace"))
    except Exception:
        return {}

def _http_call(url, headers=None, timeout=None, data=None):
    try:
        body = _http_get(url, headers=headers, timeout=timeout, data=data)
    except Exception as exc:
        return {}, "网络请求失败(%s)" % type(exc).__name__
    text = body.decode("utf-8", "replace") if body else ""
    if not text.strip():
        return {}, "接口无返回内容"
    try:
        obj = json.loads(text)
    except Exception:
        return {}, "接口返回的不是 JSON"
    if not isinstance(obj, dict):
        return {}, "接口返回结构异常"
    return obj, ""

# ---------------------------------------------------------------- 参数解析
def _maybe_json(value):
    if isinstance(value, (dict, list)):
        return value
    text = _text(value)
    if not text:
        return None
    if text[0] in "{[":
        try:
            return json.loads(text)
        except Exception:
            return None
    return None

COOKIE_KEYS = ("UID", "CID", "SEID", "KID")
COOKIE_FILE_NAME = "115cookie.txt"

def _cookie_from_parts(data):
    if not isinstance(data, dict):
        return ""
    flat = {}
    for key, val in data.items():
        name = _text(key).upper()
        if name in COOKIE_KEYS:
            flat[name] = _text(val)
    if not flat.get("UID"):
        return ""
    return _normalize_cookie("; ".join("%s=%s" % (k, flat[k]) for k in COOKIE_KEYS if flat.get(k)))

def _normalize_cookie(value):
    if isinstance(value, dict):
        return _cookie_from_parts(value)
    text = _text(value)
    if not text:
        return ""
    if "%" in text:
        try:
            text = urllib.parse.unquote(text)
        except Exception:
            pass
    text = text.strip().strip('"').strip("'").strip()
    low = text.lower()
    if "cookie=" in low:
        text = text[low.rfind("cookie=") + 7:]
    elif low.startswith("cookie:"):
        text = text[7:]
    text = text.strip().strip('"').strip("'").strip()
    if "UID=" not in text.upper():
        return ""
    text = text.replace("\r", ";").replace("\n", ";").replace("&", ";").replace(",", ";")
    got = {}
    for chunk in text.split(";"):
        item = chunk.strip()
        if not item or "=" not in item:
            continue
        key, _, val = item.partition("=")
        key = key.strip().upper()
        val = val.strip().strip('"').strip("'")
        if not key or not val:
            continue
        got[key] = val
    if not got.get("UID") or not got.get("CID"):
        return ""
    return "; ".join("%s=%s" % (k, got[k]) for k in COOKIE_KEYS if got.get(k))

def _cookie_missing(cookie):
    text = _text(cookie)
    have = set()
    for chunk in text.split(";"):
        key = chunk.split("=", 1)[0].strip().upper()
        if key:
            have.add(key)
    return [k for k in COOKIE_KEYS if k not in have]

def _parse_query(text):
    cfg = {}
    for chunk in _text(text).split("&"):
        item = chunk.strip()
        if not item or "=" not in item:
            continue
        key, _, val = item.partition("=")
        key = key.strip()
        if not key:
            continue
        try:
            val = urllib.parse.unquote(val)
        except Exception:
            pass
        if key == "cookie":
            cfg["cookie"] = val
        elif key not in cfg:
            cfg[key] = val
    return cfg

def _parse_extend(extend):
    cfg = {}
    raw = extend
    if isinstance(raw, (dict, list)):
        data = raw
        if isinstance(data, list):
            data = data[0] if data and isinstance(data[0], dict) else {}
        if isinstance(data, dict):
            cfg.update({str(k): v for k, v in data.items()})
            return _expand_ext(cfg)
        return cfg
    text = _text(raw)
    if not text:
        return cfg
    if "%" in text:
        low_text = text.lower()
        if any(tag in low_text for tag in ("%3d", "%7b", "%22", "%20", "%3a")):
            try:
                decoded = urllib.parse.unquote(text)
                if decoded and decoded != text:
                    text = decoded
            except Exception:
                pass
    parsed = _maybe_json(text)
    if isinstance(parsed, dict):
        cfg.update({str(k): v for k, v in parsed.items()})
        return _expand_ext(cfg)
    if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
        cfg.update({str(k): v for k, v in parsed[0].items()})
        return _expand_ext(cfg)
    lower = text.lower()
    if "uid=" in lower and ("cid=" in lower or "seid=" in lower or "kid=" in lower):
        cfg["cookie"] = text
        return _expand_ext(cfg)
    if "=" in text:
        cfg.update(_parse_query(text.split("?", 1)[-1]))
    elif lower.endswith(".db") or "/" in text or "\\" in text:
        cfg["db"] = text
    return _expand_ext(cfg)

def _expand_ext(cfg):
    if not isinstance(cfg, dict):
        return {}
    out = {}
    for key, val in cfg.items():
        out[_text(key)] = val
    nested = out.get("ext") if "ext" in out else out.get("extend")
    if nested and (isinstance(nested, (dict, list)) or "=" in _text(nested) or _text(nested).lstrip()[:1] in "{["):
        for key, val in _parse_extend(nested).items():
            out.setdefault(key, val)
    if not out.get("cookie"):
        parts = _cookie_from_parts(out)
        if parts:
            out["cookie"] = parts
    return out

def _read_file_text(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            return handle.read()
    except Exception:
        return ""

def _resolve_cookie(cfg):
    cfg = cfg or {}
    direct = _normalize_cookie(cfg.get("cookie"))
    if direct:
        return direct
    paths = []
    file_opt = _text(cfg.get("cookie_file") or cfg.get("cookiefile") or cfg.get("cookieFile"))
    if file_opt:
        paths.append(file_opt)
    try:
        paths.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), COOKIE_FILE_NAME))
    except Exception:
        pass
    for path in paths:
        if path and os.path.isfile(path):
            from_file = _normalize_cookie(_read_file_text(path))
            if from_file:
                return from_file
    env = _normalize_cookie(os.environ.get("PAN115SHARE_COOKIE"))
    if env:
        return env
    return _normalize_cookie(DEFAULT_COOKIE)

# ---------------------------------------------------------------- 分享库
class _Library(object):
    def __init__(self, cfg):
        self.cfg = cfg or {}
        self.lock = threading.Lock()
        self.conn = None
        self.path = ""
        self.error = ""
        self.booting = False
        self.ready = threading.Event()

    def _cache_dirs(self):
        dirs = []
        configured = _text(self.cfg.get("cache"))
        if configured:
            dirs.append(configured)
        env_home = _text(os.environ.get("PAN115SHARE_HOME"))
        if env_home:
            dirs.append(env_home)
        try:
            here = os.path.dirname(os.path.abspath(__file__))
            if here:
                dirs.append(os.path.join(here, "cache", "115share"))
        except Exception:
            pass
        try:
            dirs.append(os.path.join(os.path.expanduser("~"), ".cache", "115share"))
        except Exception:
            pass
        try:
            dirs.append(os.path.join(tempfile.gettempdir(), "115share"))
        except Exception:
            pass
        try:
            dirs.append(os.path.join(os.getcwd(), "cache", "115share"))
        except Exception:
            pass
        unique = []
        for item in dirs:
            if item and item not in unique:
                unique.append(item)
        return unique

    @staticmethod
    def _writable(dir_path):
        try:
            if not os.path.isdir(dir_path):
                os.makedirs(dir_path, exist_ok=True)
            probe = os.path.join(dir_path, ".w_%d" % int(time.time() * 1000))
            with open(probe, "wb") as handle:
                handle.write(b"1")
            os.remove(probe)
            return True
        except Exception:
            return False

    def db_path(self):
        configured = _text(self.cfg.get("db") or os.environ.get("PAN115SHARE_DB") or DEFAULT_DB_URL)
        url = _text(self.cfg.get("dburl") or os.environ.get("PAN115SHARE_DB_URL"))
        if configured.lower().startswith(("http://", "https://")):
            url = configured
            local_name = DEFAULT_DB_NAMES[0]
            target_dir = ""
            for candidate in self._cache_dirs():
                if self._writable(candidate):
                    target_dir = candidate
                    break
            if not target_dir:
                target_dir = tempfile.gettempdir()
            return os.path.join(target_dir, local_name), url
        if not url:
            url = DEFAULT_DB_URL
        path = configured
        if not os.path.isabs(path):
            for candidate in self._cache_dirs():
                probe = os.path.join(candidate, path)
                if os.path.exists(probe):
                    path = probe
                    break
        return path, url

    @staticmethod
    def _is_sqlite(path):
        try:
            if not os.path.exists(path) or os.path.getsize(path) < 4096:
                return False
            with open(path, "rb") as handle:
                return handle.read(len(SQLITE_MAGIC)) == SQLITE_MAGIC
        except Exception:
            return False

    def _download(self, path, url):
        temp = path + ".tmp"
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        except Exception:
            pass
        try:
            if os.path.exists(temp):
                os.remove(temp)
        except Exception:
            pass
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        ctx = None
        try:
            import ssl
            ctx = ssl._create_unverified_context()
        except Exception:
            ctx = None
        resp = urllib.request.urlopen(req, timeout=60, context=ctx) if ctx else urllib.request.urlopen(req, timeout=60)
        try:
            with open(temp, "wb") as handle:
                while True:
                    chunk = resp.read(262144)
                    if not chunk:
                        break
                    handle.write(chunk)
        finally:
            try:
                resp.close()
            except Exception:
                pass
        if not self._is_sqlite(temp):
            try:
                os.remove(temp)
            except Exception:
                pass
            raise RuntimeError("分享库下载校验失败，返回内容不是 SQLite 文件")
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
        os.replace(temp, path)

    def _open(self):
        if sqlite3 is None:
            raise RuntimeError("当前运行环境缺少 sqlite3 模块，无法读取分享库")
        path, url = self.db_path()
        if not self._is_sqlite(path):
            self._download(path, url) if url else None
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        total = conn.execute("SELECT COUNT(*) AS total FROM share").fetchone()
        if not total or not _int(total["total"]):
            conn.close()
            raise RuntimeError("分享库内容为空")
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_share_pid ON share(pid)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_share_cid_pid ON share(cid, pid)")
            conn.commit()
        except Exception:
            pass
        self.path = path
        return conn

    def _worker(self):
        try:
            self._boot()
        except Exception as error:
            self.error = _text(error)
        finally:
            self.ready.set()

    def ensure(self, wait_seconds=0):
        if self.conn is not None:
            return self.conn
        if wait_seconds and wait_seconds > 0:
            with self.lock:
                if not self.booting:
                    self.booting = True
                    self.ready.clear()
                    threading.Thread(target=self._worker, daemon=True).start()
            self.ready.wait(wait_seconds)
            return self.conn
        return self._boot()

    def _boot(self):
        with self.lock:
            if self.conn is not None:
                return self.conn
            try:
                self.conn = self._open()
                self.error = ""
            except Exception as error:
                self.error = _text(error)
                self.conn = None
            finally:
                self.booting = False
            return self.conn

    def roots(self):
        conn = self.conn
        if conn is None:
            return []
        try:
            return conn.execute(
                "SELECT id, share_code, receive_code, cid, fid, pid, name FROM share "
                "WHERE pid = '0' AND " + IS_DIR_SQL + " ORDER BY id"
            ).fetchall()
        except Exception:
            return []

    @staticmethod
    def _row(item):
        if item is None:
            return {}
        try:
            return {key: item[key] for key in item.keys()}
        except Exception:
            return {}

    def resolve_dir(self, raw):
        conn = self.conn
        text = _text(_first(raw))
        if not conn or not text or text == "0":
            return None
        if text.startswith(FILE_PREFIX):
            return None
        value = text[len(DIR_PREFIX):] if text.startswith(DIR_PREFIX) else text
        if not re.match(r"^\d+$", value):
            return None
        try:
            if len(value) >= 10:
                row = conn.execute(
                    "SELECT id, share_code, receive_code, cid, fid, pid, name FROM share "
                    "WHERE cid = ? AND " + IS_DIR_SQL + " LIMIT 1", (value,)
                ).fetchone()
                return self._row(row) if row else None
            row = conn.execute(
                "SELECT id, share_code, receive_code, cid, fid, pid, name FROM share "
                "WHERE id = ? AND " + IS_DIR_SQL, (value,)
            ).fetchone()
            if row:
                return self._row(row)
            row = conn.execute(
                "SELECT id, share_code, receive_code, cid, fid, pid, name FROM share "
                "WHERE cid = ? AND " + IS_DIR_SQL + " LIMIT 1", (value,)
            ).fetchone()
            return self._row(row) if row else None
        except Exception:
            return None

    def find_dir_by_cid(self, cid):
        conn = self.conn
        if not conn or not _text(cid):
            return None
        try:
            row = conn.execute(
                "SELECT id, share_code, receive_code, cid, fid, pid, name FROM share "
                "WHERE cid = ? AND " + IS_DIR_SQL + " LIMIT 1", (_text(cid),)
            ).fetchone()
            return self._row(row) if row else None
        except Exception:
            return None

    def count_folders(self, cid):
        try:
            row = self.conn.execute("SELECT COUNT(*) AS total FROM share WHERE pid = ?", (cid,)).fetchone()
            return _int(row["total"])
        except Exception:
            return 0

    def count_files(self, cid):
        try:
            row = self.conn.execute(
                "SELECT COUNT(*) AS total FROM share WHERE cid = ? AND " + IS_FILE_SQL + " AND " + FILE_VIDEO_SQL,
                (cid,)
            ).fetchone()
            return _int(row["total"])
        except Exception:
            return 0

    def page_folders(self, cid, limit, offset):
        try:
            rows = self.conn.execute(
                "SELECT id, share_code, receive_code, cid, fid, pid, name FROM share "
                "WHERE pid = ? ORDER BY name LIMIT ? OFFSET ?", (cid, limit, offset)
            ).fetchall()
            return [self._row(r) for r in rows]
        except Exception:
            return []

    def all_folders(self, cid):
        try:
            rows = self.conn.execute(
                "SELECT id, share_code, receive_code, cid, fid, pid, name FROM share "
                "WHERE pid = ? ORDER BY name", (cid,)
            ).fetchall()
            return [self._row(r) for r in rows]
        except Exception:
            return []

    def page_files(self, cid, limit, offset):
        try:
            rows = self.conn.execute(
                "SELECT id, share_code, receive_code, cid, fid, pid, name FROM share "
                "WHERE cid = ? AND " + IS_FILE_SQL + " AND " + FILE_VIDEO_SQL +
                " ORDER BY name LIMIT ? OFFSET ?", (cid, limit, offset)
            ).fetchall()
            return [self._row(r) for r in rows]
        except Exception:
            return []

    def all_files(self, cid):
        try:
            rows = self.conn.execute(
                "SELECT id, share_code, receive_code, cid, fid, pid, name FROM share "
                "WHERE cid = ? AND " + IS_FILE_SQL + " AND " + FILE_VIDEO_SQL + " ORDER BY name", (cid,)
            ).fetchall()
            return [self._row(r) for r in rows]
        except Exception:
            return []

    def search(self, word, limit, offset):
        like = "%" + re.sub(r"([\\%_])", r"\\\1", word) + "%"
        try:
            rows = self.conn.execute(
                "SELECT id, share_code, receive_code, cid, fid, pid, name, "
                "CASE WHEN " + IS_DIR_SQL + " THEN 0 ELSE 1 END AS kind "
                "FROM share WHERE name LIKE ? ESCAPE '\\' AND (" + IS_DIR_SQL + " OR " + FILE_VIDEO_SQL + ") "
                "ORDER BY kind, id LIMIT ? OFFSET ?", (like, limit, offset)
            ).fetchall()
            return [self._row(r) for r in rows]
        except Exception:
            return []

# ---------------------------------------------------------------- 115 网盘接口
_SERVER_BUSY_HINTS = ("服务器开小差", "稍后再试", "系统繁忙", "服务异常")

def _friendly_error(message, errno=None):
    text = _text(message)
    code = _int(errno)
    if code in (990001, 990002, 990003) or "登录超时" in text or "重新登录" in text:
        return "115 提示登录已失效，cookie 需要重新获取"
    if code in (990009, 990010) or "会员" in text:
        return "115 提示该文件需要会员权限才能取直链"
    if any(hint in text for hint in _SERVER_BUSY_HINTS):
        return "115 接口暂时不可用，稍后重试"
    if "不存在" in text or "已删除" in text or "失效" in text:
        return "分享已失效或被取消"
    return text or "115 直链获取失败"

def _unquote_url(value):
    text = _text(value)
    if not text:
        return ""
    if text.lower().startswith("http%3a") or "%2f" in text.lower()[:40]:
        try:
            return urllib.parse.unquote(text)
        except Exception:
            return text
    return text

def _expand_direct(url, timeout=12):
    target = _text(url)
    if not target:
        return "", "空地址"
    req = urllib.request.Request(target, headers={
        "User-Agent": UA,
        "Referer": "https://115.com/",
        "Range": "bytes=0-1",
        "Accept": "*/*",
    })
    try:
        import ssl
        ctx = ssl._create_unverified_context()
        resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
    except Exception as exc:
        return target, "直链校验跳过(%s)" % type(exc).__name__
    try:
        final = _text(resp.geturl()) or target
        ctype = _text(resp.headers.get("Content-Type")).lower()
        status = int(getattr(resp, "status", 200) or 200)
        try:
            resp.read(2)
        except Exception:
            pass
    except Exception:
        return target, "直链校验跳过"
    finally:
        try:
            resp.close()
        except Exception:
            pass
    if status >= 400:
        return target, "直链返回 %s" % status
    if "text/html" in ctype or "application/json" in ctype:
        return target, "直链校验跳过(返回网页)"
    return final, ""

class _Pan115(object):
    def __init__(self, cookie=""):
        self.cookie = _normalize_cookie(cookie)
        self.header = {
            "User-Agent": UA,
            "Referer": "https://115.com/",
            "Accept": "application/json, text/plain, */*",
        }
        if self.cookie:
            self.header["Cookie"] = self.cookie
        self._login_state = None

    def clear_login_cache(self):
        """修复：清除登录状态缓存，切换cookie后重新检测"""
        self._login_state = None

    def snap(self, share_code, receive_code, cid="", offset=0, limit=100):
        query = {
            "share_code": _text(share_code),
            "receive_code": _text(receive_code),
            "offset": offset,
            "limit": limit,
        }
        if cid:
            query["cid"] = _text(cid)
        url = "https://webapi.115.com/share/snap?" + urllib.parse.urlencode(query)
        data = _http_json(url, headers=self.header)
        payload = data.get("data") if isinstance(data, dict) else None
        if not isinstance(payload, dict):
            return {"state": False, "error": _text(data.get("error")) if isinstance(data, dict) else "接口无响应"}
        return {
            "state": bool(data.get("state")),
            "error": _text(data.get("error")),
            "list": payload.get("list") or [],
            "count": _int(payload.get("count")),
            "shareinfo": payload.get("shareinfo") or {},
        }

    def check_login(self):
        """修复：网络异常不直接判定登录失效；清除缓存后重新校验"""
        if getattr(self, "_login_state", None) is not None:
            return self._login_state
        if not self.cookie:
            self._login_state = False
            return False
        data, err = _http_call("https://my.115.com/?ct=ajax&ac=nav", headers=self.header, timeout=8)
        if err:
            # 网络抖动，不标记失效，返回True
            return True
        if data.get("state"):
            self._login_state = True
            return True
        err_msg = _text(data.get("error", ""))
        if "登录" in err_msg:
            self._login_state = False
            return False
        return True

    def downurl(self, share_code, receive_code, file_id):
        params = {
            "share_code": _text(share_code),
            "receive_code": _text(receive_code),
            "file_id": _text(file_id),
        }
        endpoint = "https://webapi.115.com/share/downurl"
        header = dict(self.header)
        header["Content-Type"] = "application/x-www-form-urlencoded"
        tries = [
            (endpoint, header, urllib.parse.urlencode(params).encode("utf-8")),
            (endpoint + "?" + urllib.parse.urlencode(params), self.header, None),
        ]
        last = {"state": False, "url": "", "msg": "接口无响应", "errno": 0}
        for url, hdr, body in tries:
            data, err = _http_call(url, headers=hdr, data=body, timeout=20)
            if err:
                last = {"state": False, "url": "", "msg": err, "errno": 0}
                continue
            payload = data.get("data") if isinstance(data.get("data"), dict) else {}
            url_out = _text(payload.get("file_url") or payload.get("url") or payload.get("dl_url"))
            if data.get("state") and url_out:
                return {"state": True, "url": _unquote_url(url_out), "msg": "", "errno": 0}
            last = {
                "state": False,
                "url": "",
                "msg": _friendly_error(data.get("error") or data.get("error_msg"),
                                       data.get("errno") or data.get("errNo")),
                "errno": _int(data.get("errno") or data.get("errNo")),
                "raw": _text(data.get("error")),
            }
        return last

    def download(self, share_code, receive_code, file_id):
        query = {
            "share_code": _text(share_code),
            "receive_code": _text(receive_code),
            "file_id": _text(file_id),
        }
        url = "https://webapi.115.com/share/download?" + urllib.parse.urlencode(query)
        data, err = _http_call(url, headers=self.header, timeout=15)
        if err:
            return {"state": False, "url": "", "msg": err, "errno": 0}
        payload = data.get("data") if isinstance(data.get("data"), dict) else {}
        url_out = _text(payload.get("file_url") or payload.get("url"))
        return {
            "state": bool(data.get("state")) and bool(url_out),
            "url": _unquote_url(url_out),
            "msg": _friendly_error(data.get("error") or data.get("error_msg"),
                                   data.get("errno") or data.get("errNo")),
            "errno": _int(data.get("errno") or data.get("errNo")),
            "raw": _text(data.get("error")),
        }

    def resolve(self, share_code, receive_code, file_id):
        try:
            got = self.downurl(share_code, receive_code, file_id)
        except Exception as exc:
            return {"state": False, "url": "", "msg": "接口异常(%s)" % type(exc).__name__, "errno": 0}
        if got.get("state") and got.get("url"):
            return got
        if not got.get("errno") and "网络" in _text(got.get("msg")):
            try:
                legacy = self.download(share_code, receive_code, file_id)
                if legacy.get("state") and legacy.get("url"):
                    return legacy
            except Exception:
                pass
        return got

    def receive(self, share_code, receive_code, file_id):
        body = urllib.parse.urlencode({
            "share_code": _text(share_code),
            "receive_code": _text(receive_code),
            "file_id": _text(file_id),
        }).encode("utf-8")
        header = dict(self.header)
        header["Content-Type"] = "application/x-www-form-urlencoded"
        data, err = _http_call("https://webapi.115.com/share/receive", headers=header, data=body, timeout=20)
        if err:
            return False
        if data.get("state"):
            return True
        return _int(data.get("errno")) in (991001, 990007)

# ---------------------------------------------------------------- 主类
class Spider(_BaseSpider):
    def __init__(self):
        try:
            super(Spider, self).__init__()
        except Exception:
            pass
        self.cfg = {}
        self.library = _Library({})
        self.pan = _Pan115(DEFAULT_COOKIE)
        self.page_size = DEFAULT_PAGE_SIZE
        self._detail_cache = {}
        self._detail_lock = threading.Lock()
        self._init_done = False

    def getName(self):
        return "115分享"

    def init(self, extend=""):
        self.cfg = _parse_extend(extend)
        if self.cfg:
            try:
                _LAST_EXTEND["value"] = extend
            except Exception:
                pass
        cookie = _resolve_cookie(self.cfg)
        self.pan = _Pan115(cookie)
        self._cookie_note = _cookie_missing(self.pan.cookie) if self.pan.cookie else list(COOKIE_KEYS)
        self.page_size = max(10, min(200, _int(self.cfg.get("size"), DEFAULT_PAGE_SIZE)))
        env_db = _text(os.environ.get("PAN115SHARE_DB"))
        if env_db and "db" not in self.cfg:
            self.cfg["db"] = env_db
        self.library = _Library(self.cfg)
        self._init_done = True
        return self

    def isVideoFormat(self, url):
        return bool(VIDEO_RE.search(_text(url)))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        return None

    @property
    def auto_transfer(self):
        return _text(self.cfg.get("transfer")) in ("1", "true", "yes", "on")

    def _cache_get(self, key):
        with self._detail_lock:
            hit = self._detail_cache.get(key)
            if not hit:
                return None
            if time.time() - hit[0] > DETAIL_CACHE_TTL:
                self._detail_cache.pop(key, None)
                return None
            return hit[1]

    def _cache_set(self, key, value):
        with self._detail_lock:
            self._detail_cache[key] = (time.time(), value)
            if len(self._detail_cache) > DETAIL_CACHE_MAX:
                oldest = next(iter(self._detail_cache))
                self._detail_cache.pop(oldest, None)

    def _folder_card(self, row_id, name, remarks=""):
        return {
            "vod_id": _encode_dir(row_id),
            "vod_name": _clean(name),
            "vod_pic": FOLDER_PIC,
            "vod_remarks": _clean(remarks, 40),
            "vod_tag": "folder",
        }

    def _file_card(self, row):
        return {
            "vod_id": _encode_file(row),
            "vod_name": _clean(_strip_ext(row.get("name"))),
            "vod_pic": VIDEO_PIC,
            "vod_remarks": "115分享",
        }

    def _page(self, items, page, pagecount, total):
        return {
            "list": items,
            "page": page,
            "pagecount": max(1, pagecount or 1),
            "limit": self.page_size,
            "total": total if total is not None else len(items),
        }

    def _pending_class(self):
        return [{"type_id": "0", "type_name": "115分享集合（准备中…）"}]

    def homeContent(self, filter=None):
        conn = self.library.ensure(HOME_WAIT_MS)
        if conn is None:
            error = _text(self.library.error)
            return {
                "class": self._pending_class(),
                "filters": {},
                "list": [],
                "msg": "分享库准备中，稍后再刷新" + (("：" + error) if error else ""),
            }
        roots = self.library.roots()
        if not roots:
            return {"class": self._pending_class(), "filters": {}, "list": []}
        classes = [{"type_id": "0", "type_name": "全部合集"}]
        cards = []
        for row in roots:
            classes.append({"type_id": _encode_dir(row["id"]), "type_name": _short_name(row["name"])})
            cards.append(self._folder_card(row["id"], row["name"], "合集 · %s" % row["share_code"]))
        return {"class": classes, "filters": {}, "list": cards}

    def homeVideoContent(self):
        conn = self.library.ensure(HOME_WAIT_MS)
        if conn is None:
            return {"list": []}
        return {"list": [self._folder_card(r["id"], r["name"], "合集 · %s" % r["share_code"])
                         for r in self.library.roots()]}

    def categoryContent(self, tid, pg, filter=None, extend=None):
        conn = self.library.ensure(6.0)
        if conn is None:
            return self._page([], 1, 1, 0)
        page_no = max(1, _int(pg, 1))
        offset = (page_no - 1) * self.page_size
        row = self.library.resolve_dir(tid)
        if not row:
            roots = self.library.roots()
            cards = [self._folder_card(r["id"], r["name"], "合集 · %s" % r["share_code"]) for r in roots]
            return self._page(cards, 1, 1, len(cards))
        folder_total = self.library.count_folders(row["cid"])
        file_total = self.library.count_files(row["cid"])
        total = folder_total + file_total
        items = []
        if offset < folder_total:
            folders = self.library.page_folders(row["cid"], self.page_size, offset)
            for item in folders:
                items.append(self._folder_card(item["id"], item["name"], "目录"))
            rest = self.page_size - len(folders)
            if rest > 0 and file_total > 0:
                for item in self.library.page_files(row["cid"], rest, 0):
                    items.append(self._file_card(item))
        elif file_total > 0:
            for item in self.library.page_files(row["cid"], self.page_size, offset - folder_total):
                items.append(self._file_card(item))
        pagecount = (total + self.page_size - 1) // self.page_size if total else 1
        return self._page(items, page_no, pagecount, total)

    def searchContent(self, key, quick=False, pg="1"):
        conn = self.library.ensure(6.0)
        page_no = max(1, _int(pg, 1))
        if conn is None:
            return self._page([], page_no, 1, 0)
        word = _clean(key, 60)
        if not word:
            return self._page([], page_no, 1, 0)
        rows = self.library.search(word, DEFAULT_SEARCH_SIZE, (page_no - 1) * DEFAULT_SEARCH_SIZE)
        items = []
        for row in rows:
            if _int(row.get("kind")) == 0:
                remarks = "分享合集" if _text(row.get("pid")) == "0" else "目录"
                items.append(self._folder_card(row["id"], row["name"], remarks))
            else:
                items.append(self._file_card(row))
        pagecount = page_no + 1 if len(rows) >= DEFAULT_SEARCH_SIZE else page_no
        return self._page(items, page_no, pagecount, len(items))

    def _collect_groups(self, root_row):
        groups = []
        stack = [{"cid": root_row["cid"], "label": "", "depth": 0}]
        files = 0
        steps = 0
        while stack and len(groups) < MAX_GROUPS and files < MAX_FILES and steps < MAX_WALK_STEPS:
            steps += 1
            node = stack.pop(0)
            rows = self.library.all_files(node["cid"])
            if rows:
                rows.sort(key=lambda r: _nat_key(r.get("name")))
                picked = rows[:min(MAX_FILES_PER_GROUP, MAX_FILES - files)]
                groups.append({"label": node["label"], "rows": picked})
                files += len(picked)
            if node["depth"] >= MAX_DEPTH:
                continue
            folders = self.library.all_folders(node["cid"])
            if not folders:
                continue
            descend = []
            for folder in folders:
                label = (node["label"] + "/" + _text(folder["name"])) if node["label"] else _text(folder["name"])
                descend.append({"cid": folder["cid"], "label": label, "depth": node["depth"] + 1})
            stack = descend + stack
        return groups

    @staticmethod
    def _build_lines(groups):
        lines = []
        singles = []
        for group in groups:
            if len(group["rows"]) == 1:
                singles.append(group)
                continue
            lines.append({
                "from": group["label"],
                "items": [{"name": _strip_ext(r.get("name")), "row": r} for r in group["rows"]],
            })
        if len(singles) == 1:
            row = singles[0]["rows"][0]
            lines.append({"from": singles[0]["label"], "items": [{"name": _strip_ext(row.get("name")), "row": row}]})
        elif len(singles) > 1:
            lines.append({
                "from": "单片合集",
                "items": [{
                    "name": _leaf_label(g["label"]) or _strip_ext(g["rows"][0].get("name")),
                    "row": g["rows"][0],
                } for g in singles],
            })
        return lines

    def _build_play(self, groups):
        froms = []
        urls = []
        used_from = set()
        for line in self._build_lines(groups):
            label = _line_label(line["from"])
            base = _clean(label, 34) or "主目录"
            from_name = _clean(label, 40) or "主目录"
            suffix = 2
            while from_name in used_from:
                from_name = "%s(%d)" % (base, suffix)
                suffix += 1
            used_from.add(from_name)
            used_name = set()
            episodes = []
            for item in line["items"]:
                name = _clean(item["name"], 60) or "正片"
                name = name.replace("$", "＄").replace("#", "＃").replace("\r", " ").replace("\n", " ")
                index = 2
                while name in used_name:
                    name = "%s(%d)" % (name, index)
                    index += 1
                used_name.add(name)
                episodes.append("%s$%s" % (name, _encode_file(item["row"])))
            if not episodes:
                used_from.discard(from_name)
                continue
            froms.append(from_name)
            urls.append("#".join(episodes))
        return {"vod_play_from": "$$$".join(froms), "vod_play_url": "$$$".join(urls)}

    _SEASON_RE = re.compile(r"^(season\s*\d+|s\d+|第[一二三四五六七八九十\d]+季)$", re.I)

    def _dir_title(self, row):
        name = _text((row or {}).get("name"))
        if not name or not self._SEASON_RE.match(name.strip()):
            return name
        pid = _text((row or {}).get("pid"))
        depth = 0
        while pid and pid != "0" and depth < 3:
            up = self.library.find_dir_by_cid(pid)
            if not up:
                break
            up_name = _text(up.get("name"))
            if up_name and not self._SEASON_RE.match(up_name.strip()):
                return "%s/%s" % (up_name, name)
            pid = _text(up.get("pid"))
            depth += 1
        return name

    def _dir_detail(self, row):
        cache_key = "dir:%s" % row["id"]
        cached = self._cache_get(cache_key)
        if cached:
            return cached
        groups = self._collect_groups(row)
        count = sum(len(g["rows"]) for g in groups)
        play = self._build_play(groups)
        vod = {
            "vod_id": _encode_dir(row["id"]),
            "vod_name": _clean(row["name"]),
            "vod_pic": FOLDER_PIC,
            "vod_remarks": ("%d个文件" % count) if count else "暂无可播文件",
            "vod_content": "\n".join([x for x in [
                _share_url(row["share_code"], row["receive_code"]),
                _clean(row["name"], 200),
            ] if x]),
            "type_name": "115分享",
        }
        vod.update(play)
        self._cache_set(cache_key, vod)
        return vod

    def _file_detail(self, token):
        info = _decode_file(token)
        if not info:
            return None
        parent = self.library.find_dir_by_cid(info.get("p"))
        parent_name = self._dir_title(parent) if parent else ""
        siblings = self.library.all_files(info["p"]) if info.get("p") else []
        file_name = _text(info.get("n"))
        if not file_name and siblings:
            for row in siblings:
                if _text(row.get("fid")) == _text(info["f"]):
                    file_name = _text(row.get("name"))
                    break
        if siblings:
            siblings.sort(key=lambda r: _nat_key(r.get("name")))
            rows = siblings
        else:
            rows = [{
                "share_code": info["c"], "receive_code": info["r"],
                "cid": info.get("p"), "fid": info["f"], "name": file_name,
            }]
        play = self._build_play([{"label": parent_name or "115分享", "rows": rows}])
        return {
            "vod_id": token,
            "vod_name": _clean(parent_name or _strip_ext(file_name) or "115分享"),
            "vod_pic": VIDEO_PIC,
            "vod_remarks": "%d个文件" % len(rows),
            "vod_content": "\n".join([x for x in [
                _share_url(info["c"], info["r"]),
                _clean(file_name, 200),
            ] if x]),
            "type_name": "115分享",
            **play,
        }

    def detailContent(self, array):
        self.library.ensure(6.0)
        ids = []
        for item in (array if isinstance(array, list) else [array]):
            for part in _text(item).split(","):
                if part.strip():
                    ids.append(part.strip())
        result = []
        for vod_id in ids:
            if vod_id.startswith(FILE_PREFIX):
                vod = self._file_detail(vod_id)
                if vod:
                    result.append(vod)
                continue
            row = self.library.resolve_dir(vod_id)
            if row:
                result.append(self._dir_detail(row))
        return {"list": result, "page": 1, "pagecount": 1, "limit": len(result), "total": len(result)}

    def playerContent(self, flag, id, vipFlags=None):
        try:
            return self._player(id)
        except Exception as exc:
            return {
                "parse": 0,
                "url": "",
                "msg": "115 播放出错(%s)，退回详情页重新点击，或者更新cookie" % type(exc).__name__,
            }

    def _player(self, id):
        # 修复：每次播放前清除登录缓存，播放器新建实例不会残留旧登录状态
        if hasattr(self.pan, "clear_login_cache"):
            self.pan.clear_login_cache()
        if not self._init_done or not (self.pan and self.pan.cookie):
            try:
                self.init(_LAST_EXTEND.get("value") or "")
            except Exception:
                pass
        info = _decode_file(id)
        if not info:
            return {"parse": 0, "url": "", "msg": "播放参数解析失败，请回到详情页面重新点击播放"}
        share_code = info["c"]
        receive_code = info["r"]
        file_id = info["f"]
        share_page = _share_url(share_code, receive_code)
        page_header = {"User-Agent": UA, "Referer": "https://115.com/"}
        if not self.pan or not self.pan.cookie:
            note = ""
            missing = getattr(self, "_cookie_note", None) or []
            if missing and len(missing) < len(COOKIE_KEYS):
                note = "（cookie 缺 %s）" % "/".join(missing)
            return {
                "parse": 1,
                "url": share_page,
                "header": page_header,
                "msg": "未配置完整115 cookie%s，仅可打开分享网页；填写UID/CID/SEID/KID后才能直链播放" % note,
            }
        result = self.pan.resolve(share_code, receive_code, file_id)
        if not result.get("state") and self.auto_transfer:
            try:
                if self.pan.receive(share_code, receive_code, file_id):
                    result = self.pan.resolve(share_code, receive_code, file_id)
            except Exception:
                pass
        if result.get("state") and result.get("url"):
            final_url, note = _expand_direct(result["url"])
            header = {"User-Agent": UA, "Referer": "https://115.com/"}
            payload = {"parse": 0, "url": final_url or result["url"], "header": header}
            if note and "跳过" not in note:
                payload["msg"] = note
            return payload
        msg = result.get("msg") or "115直链获取失败"
        missing = getattr(self, "_cookie_note", None) or []
        if missing and len(missing) < len(COOKIE_KEYS):
            msg = "%s（cookie缺少字段：%s）" % (msg, "/".join(missing))
        else:
            try:
                login_ok = self.pan.check_login()
                if not login_ok:
                    msg = "115登录态已失效，请浏览器重新登录115，复制新的cookie填入ext"
            except Exception:
                pass
        if not self.auto_transfer and "登录" not in msg and "cookie" not in msg:
            msg += "；部分分享需要转存才能获取直链：ext添加 transfer=1 开启自动转存"
        return {"parse": 1, "url": share_page, "header": page_header, "msg": msg}
