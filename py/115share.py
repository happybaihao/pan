# -*- coding: utf-8 -*-
"""
115分享集合 —— OK影视 / TVBox(Python) 站源

移植自「【网盘】115分享.js」（T4 插件版），数据源、目录结构、分页规则、
播放线路聚合方式与 JS 版一一对应。

==================== 它是什么 ====================

JS 版不是 API 源，它读的是一个 SQLite 分享库（约 38MB，15.8 万行）：
  表 share(id, share_code, receive_code, cid, fid, pid, name, sha1)
  · 目录行：fid 为空，cid = 目录自身 ID，pid = 父目录 cid
  · 文件行：fid = 文件 ID，cid = 所在目录，pid 为空
  · pid = '0' 的 13 行 = 分享合集根

所以这本 py 也是同一个套路：首次访问自动下载分享库到本地缓存，
然后用 sqlite3 直接查，不依赖任何上游接口。

==================== 配置方式（三选一，优先级从高到低） ====================

1) 写在站点地址后面（OK影视「数据源」里填这一整行）：
   115share.py
   115share.py?db=http://your-host/share.db&cookie=UID=xxx;CID=xxx;SEID=xxx;KID=xxx
   115share.py?db=/sdcard/115share.db&size=60
   多参数用 & 连，也可以整套塞 JSON：
   115share.py?{"db":"http://x/share.db","cookie":"UID=...;KID=...","size":60}

2) 环境变量：PAN115SHARE_DB / PAN115SHARE_DB_URL / PAN115SHARE_COOKIE

3) 直接改下面 DEFAULT_* 常量

参数说明：
  db        分享库路径或 URL。不填就用内置默认镜像（首次自动下载 38MB）
  cookie    115 登录 cookie，只有「播放出直链」才需要，不填也能浏览/搜索
  size      每页条数，默认 60（搜索固定 40，跟 JS 版一致）
  transfer  1 = 播放时若未转存，自动转存到你自己网盘再取直链（默认 0，保守）
  cache     分享库缓存目录，默认自动挑一个可写目录

==================== 能力 ====================
首页 13 个合集 + 分类逐层浏览（目录/视频混排分页）/ 关键词搜索（目录命中优先）/
详情（目录内按子目录聚合成播放线路，单文件目录合并成「单片合集」）/
播放（有 cookie 出 115 直链；没有就返回分享页让播放器外挂打开）

==================== 播放说明（重要） ====================
115 分享直链必须登录态，未登录只能拿到分享页：
  https://115cdn.com/s/<share_code>?password=<receive_code>
所以填了 cookie 才能真播。cookie 从浏览器登录 115 后复制，形如
  UID=1234567_A1_1699999999; CID=xxxx; SEID=xxxx; KID=xxxx
只填 UID/CID/SEID/KID 四项即可，别的不用。

==================== 关于分享库 ====================
库是别人整理好的公开合集索引，经常更新。库更新后把 cache 目录里的
fake115share.db 删掉，下次访问会自动重新下载。
也可以自己维护：任意同名结构的 SQLite 放进 db= 指过去就行。
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
except Exception:  # 极少数精简运行环境没有 sqlite3，给出可读提示而不是直接崩
    sqlite3 = None

try:
    from base.spider import Spider as _BaseSpider
except Exception:  # 本地自测时没有 base 模块
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
    """$ 和 # 是 vod_play_from / vod_play_url 的分隔符，展示名里必须剔掉。"""
    text = re.sub(r"[#$]+", " ", _text(value))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def _short_name(value, max_len=14):
    """合集名普遍带【】[] 的体积/数量后缀，分类标签只留主干。"""
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
    """自然排序：把数字段按数值比较，中文按原字符比较。"""
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
    payload = {
        "c": _text(row.get("share_code")),
        "r": _text(row.get("receive_code")),
        "f": _text(row.get("fid")),
        "p": _text(row.get("cid")),
        "n": _text(row.get("name")),
    }
    return FILE_PREFIX + _b64e(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def _decode_file(value):
    raw = _text(value)
    if not raw.startswith(FILE_PREFIX):
        return None
    try:
        data = json.loads(_b64d(raw[len(FILE_PREFIX):]))
    except Exception:
        return None
    if not data or not data.get("f"):
        return None
    return data


def _share_url(share_code, receive_code):
    code = _text(share_code)
    if not code:
        return ""
    pwd = _text(receive_code)
    return "https://115cdn.com/s/%s%s" % (code, ("?password=" + pwd) if pwd else "")


def _http_get(url, headers=None, timeout=None, data=None):
    """统一走 urllib，兼容性最好（OK影视 / TVBox 的 py 环境都不保证有 requests）。"""
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


def _parse_extend(extend):
    """init 传进来的可能是 dict、JSON 串、query 串，甚至是路径。全都吃。"""
    cfg = {}
    raw = extend
    if isinstance(raw, (dict, list)):
        data = raw
        if isinstance(data, list):
            data = data[0] if data and isinstance(data[0], dict) else {}
        if isinstance(data, dict):
            cfg.update({str(k): v for k, v in data.items()})
        return cfg

    text = _text(raw)
    if not text:
        return cfg

    parsed = _maybe_json(text)
    if isinstance(parsed, dict):
        cfg.update({str(k): v for k, v in parsed.items()})
        return cfg
    if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
        cfg.update({str(k): v for k, v in parsed[0].items()})
        return cfg

    if "=" in text:
        query = text.split("?", 1)[-1]
        try:
            for key, val in urllib.parse.parse_qsl(query, keep_blank_values=True):
                cfg[key] = val
        except Exception:
            pass
    elif text.lower().endswith(".db") or "/" in text or "\\" in text:
        # 有些播放器会把 extend 直接当路径传进来
        cfg["db"] = text
    return cfg


# ---------------------------------------------------------------- 分享库
class _Library(object):
    """分享库的下载、打开、查询。整个进程共一份连接。"""

    def __init__(self, cfg):
        self.cfg = cfg or {}
        self.lock = threading.Lock()
        self.conn = None
        self.path = ""
        self.error = ""
        self.booting = False
        self.ready = threading.Event()

    # ---------- 路径 ----------
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
        """返回 (库文件路径, 是否远程地址)。参数 db 可以给本地路径，也可以给 URL。"""
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

    # ---------- 校验 / 下载 ----------
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
        # 原库只有 unique(cid, sha1)，按 pid 逐层浏览会全表扫描，这里补两个索引。
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
        except Exception as error:  # noqa: BLE001
            self.error = _text(error)
        finally:
            self.ready.set()

    def ensure(self, wait_seconds=0):
        """wait_seconds > 0 时最多等这么久（首次下载 38MB 库可能来不及），
        多个请求同时进来共用同一个后台任务，不会各自白等一轮。"""
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
            except Exception as error:  # noqa: BLE001
                self.error = _text(error)
                self.conn = None
            finally:
                self.booting = False
            return self.conn

    # ---------- 查询 ----------
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
            # 行号最多 6 位，目录 cid 是 19 位长整数，长度足以区分两种入参。
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
class _Pan115(object):
    """分享浏览 + 直链解析。直链必须带登录 cookie，没有就只能给分享页。"""

    def __init__(self, cookie=""):
        self.cookie = _text(cookie)
        self.header = {
            "User-Agent": UA,
            "Referer": "https://115.com/",
            "Accept": "application/json, text/plain, */*",
        }
        if self.cookie:
            self.header["Cookie"] = self.cookie

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

    def download(self, share_code, receive_code, file_id):
        query = {
            "share_code": _text(share_code),
            "receive_code": _text(receive_code),
            "file_id": _text(file_id),
        }
        url = "https://webapi.115.com/share/download?" + urllib.parse.urlencode(query)
        data = _http_json(url, headers=self.header)
        if not isinstance(data, dict):
            return {"state": False, "url": "", "msg": "接口无响应"}
        payload = data.get("data") if isinstance(data.get("data"), dict) else {}
        url_out = _text(payload.get("file_url") or payload.get("url"))
        return {
            "state": bool(data.get("state")) and bool(url_out),
            "url": url_out,
            "msg": _text(data.get("error")) or _text(data.get("error_msg")),
            "errno": _int(data.get("errno")),
        }

    def receive(self, share_code, receive_code, file_id):
        """把分享里的文件转存到自己网盘，转存后 download 才会给直链。"""
        body = urllib.parse.urlencode({
            "share_code": _text(share_code),
            "receive_code": _text(receive_code),
            "file_id": _text(file_id),
        }).encode("utf-8")
        header = dict(self.header)
        header["Content-Type"] = "application/x-www-form-urlencoded"
        data = _http_json("https://webapi.115.com/share/receive", headers=header, data=body)
        if not isinstance(data, dict):
            return False
        return bool(data.get("state"))


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

    # ---------- 生命周期 ----------
    def getName(self):
        return "115分享"

    def init(self, extend=""):
        self.cfg = _parse_extend(extend)
        cookie = _text(self.cfg.get("cookie") or os.environ.get("PAN115SHARE_COOKIE") or DEFAULT_COOKIE)
        self.pan = _Pan115(cookie)
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

    # ---------- 详情缓存 ----------
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

    # ---------- 卡片 ----------
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

    # ---------- 首页 ----------
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

    # ---------- 分类 ----------
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

    # ---------- 搜索 ----------
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

    # ---------- 目录树聚合 ----------
    def _collect_groups(self, root_row):
        """按「子目录路径」分组，每组一条播放线路。

        必须深度优先：剧集常见“年份/剧名/Season 1/文件”结构，
        广度优先会把步数耗在空的中间层，深层文件一个都取不到。
        """
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
        """多文件目录各占一条线路（相当于“季”）；只有一部片的目录并成一条。"""
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

    # ---------- 详情 ----------
    _SEASON_RE = re.compile(r"^(season\s*\d+|s\d+|第[一二三四五六七八九十\d]+季)$", re.I)

    def _dir_title(self, row):
        """文件详情挂在 “Season 1” 这种目录下时，标题补上剧名，别只显示 Season 1。"""
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
        if siblings:
            siblings.sort(key=lambda r: _nat_key(r.get("name")))
            rows = siblings
        else:
            rows = [{
                "share_code": info["c"], "receive_code": info["r"],
                "cid": info.get("p"), "fid": info["f"], "name": info["n"],
            }]
        play = self._build_play([{"label": parent_name or "115分享", "rows": rows}])
        return {
            "vod_id": token,
            "vod_name": _clean(parent_name or _strip_ext(info["n"])),
            "vod_pic": VIDEO_PIC,
            "vod_remarks": "%d个文件" % len(rows),
            "vod_content": "\n".join([x for x in [
                _share_url(info["c"], info["r"]),
                _clean(info["n"], 200),
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

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vipFlags=None):
        info = _decode_file(id)
        if not info:
            return {"parse": 0, "url": "", "msg": "115分享播放参数无效"}

        share_code = info["c"]
        receive_code = info["r"]
        file_id = info["f"]
        share_page = _share_url(share_code, receive_code)

        if not self.pan.cookie:
            return {
                "parse": 1,
                "url": share_page,
                "header": {"User-Agent": UA, "Referer": "https://115.com/"},
                "msg": "没配 115 cookie，只能打开分享页；填上 cookie 就能直接播",
            }

        result = self.pan.download(share_code, receive_code, file_id)
        if result.get("state") and result.get("url"):
            header = {"User-Agent": UA, "Referer": "https://115.com/"}
            if self.pan.cookie:
                header["Cookie"] = self.pan.cookie
            return {"parse": 0, "url": result["url"], "header": header}

        # 未转存时 download 不给直链，转存一次再取（默认关闭，靠 transfer=1 打开）
        if self.auto_transfer:
            if self.pan.receive(share_code, receive_code, file_id):
                retry = self.pan.download(share_code, receive_code, file_id)
                if retry.get("state") and retry.get("url"):
                    header = {"User-Agent": UA, "Referer": "https://115.com/"}
                    header["Cookie"] = self.pan.cookie
                    return {"parse": 0, "url": retry["url"], "header": header}

        return {
            "parse": 1,
            "url": share_page,
            "header": {"User-Agent": UA, "Referer": "https://115.com/"},
            "msg": result.get("msg") or "115 直链获取失败，已退回分享页",
        }
