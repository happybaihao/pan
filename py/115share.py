# -*- coding: utf-8 -*-
"""
115 分享集合 · OK影视 / TVBox Python 源（type 3）

数据来源：fake115share 分享库（SQLite，约 38MB），首个请求自动下载并缓存。
播放：115 分享直链（webapi.115.com/share/downurl），需要 115 cookie。

配置（ext 里写，全都可以不写）：
    cookie=UID=..; CID=..; SEID=..; KID=..      115 登录 cookie
    cookie_file=/路径/115cookie.txt              cookie 放文件里，一行
    db=/路径/fake115share.db                     换库（默认内置镜像）
    cache=/可写目录                              库缓存目录（默认自动挑）
    size=60                                      每页条数
    transfer=1                                   取链失败且提示要转存时，自动转存后重取
    diag=1                                       播放失败时把 115 原始返回带在提示里（排查用）
"""

import base64
import json
import os
import re
import socket
import sqlite3
import tempfile
import threading
import time
import traceback
import urllib.parse
import urllib.request

# ---------------------------------------------------------------- 常量

DB_URL = (
    "https://file.ljcdn.com/psd-sinan-file/prod/appeal_evidence/"
    "C1606F803D024AD89ED9992532752CC5/kY8AWp.local"
)
DB_NAME = "fake115share.db"
SQLITE_MAGIC = b"SQLite format 3"

UA_WEB = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
UA_115 = (
    "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36 115Browser/27.0.5.7"
)

DIR_PREFIX = "115d@"
FILE_PREFIX = "115f@"
PAGE_SIZE = 60
SEARCH_SIZE = 40
HOME_WAIT = 8.0
MAX_DEPTH = 6
MAX_GROUPS = 40
MAX_FILES_PER_GROUP = 500
MAX_FILES = 1500
MAX_WALK_STEPS = 2000
DETAIL_TTL = 600

VIDEO_EXTS = [
    ".mp4", ".mkv", ".webm", ".avi", ".wmv", ".flv", ".mov", ".mpeg", ".mpg",
    ".m4v", ".3gp", ".ts", ".m2ts", ".rm", ".rmvb", ".iso",
]
VIDEO_RE = re.compile("(" + "|".join(re.escape(e) for e in VIDEO_EXTS) + ")$", re.I)
FILE_VIDEO_SQL = "(" + " OR ".join("name LIKE '%%%s'" % e for e in VIDEO_EXTS) + ")"
IS_DIR_SQL = "(fid IS NULL OR fid = '')"
IS_FILE_SQL = "(fid IS NOT NULL AND fid <> '')"
ROW_COLUMNS = "id, share_code, receive_code, cid, fid, pid, name"

FOLDER_PIC = "https://img.icons8.com/fluency/96/folder-invoices--v1.png"
VIDEO_PIC = "https://img.icons8.com/color/48/video.png"


# ---------------------------------------------------------------- 小工具

def _s(value):
    return "" if value is None else str(value).strip()


def _clean(value, max_len=160):
    text = _s(value)
    text = re.sub(r"[#$]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def _short(value, max_len=14):
    text = re.sub(r"[【】]", "", _s(value)).split("[")[0]
    text = re.sub(r"\s+", " ", text).strip()
    return (text or _s(value))[:max_len]


def _strip_ext(value):
    return VIDEO_RE.sub("", _s(value))


def _leaf(value):
    parts = [p for p in _s(value).split("/") if p]
    return parts[-1] if parts else ""


def _line_label(value):
    parts = [p for p in _s(value).split("/") if p]
    return "/".join(parts[-2:])


def _b64e(value):
    raw = _s(value).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(value):
    text = _s(value)
    pad = "=" * (-len(text) % 4)
    try:
        return base64.urlsafe_b64decode((text + pad).encode("ascii")).decode("utf-8", "replace")
    except Exception:
        return ""


def _num(value, default=0):
    try:
        out = int(str(value).strip())
        return out
    except Exception:
        return default


def _natkey(text):
    """自然排序：EP2 排在 EP10 前面。"""
    text = _s(text).lower()
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", text)]


def _share_page(share_code, receive_code):
    code = _s(share_code)
    if not code:
        return ""
    pwd = _s(receive_code)
    return "https://115cdn.com/s/%s%s" % (code, ("?password=" + pwd) if pwd else "")


class _Resp(object):
    def __init__(self, code, body, url=""):
        self.code = code
        self.body = body
        self.url = url

    @property
    def text(self):
        try:
            return self.body.decode("utf-8", "replace")
        except Exception:
            return str(self.body)


def _http(url, data=None, headers=None, timeout=20, redirect=True):
    """极简 HTTP；data 为 dict 时按 form 编码。"""
    hdrs = {
        "User-Agent": UA_WEB,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Connection": "close",
    }
    if headers:
        for k, v in headers.items():
            if v is not None and v != "":
                hdrs[k] = v
    body = None
    if data is not None:
        if isinstance(data, dict):
            body = urllib.parse.urlencode(data).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
        elif isinstance(data, str):
            body = data.encode("utf-8")
            hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
        else:
            body = data
    req = urllib.request.Request(url, data=body, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return _Resp(resp.getcode(), resp.read(), url)
    except urllib.error.HTTPError as err:
        try:
            return _Resp(err.code, err.read(), url)
        except Exception:
            return _Resp(err.code, b"", url)
    except Exception as err:
        return _Resp(0, ("%s" % err).encode("utf-8"), url)


# ---------------------------------------------------------------- 115 cookie

COOKIE_PARTS = ("UID", "CID", "SEID", "KID")


def _norm_cookie(raw):
    """把各种写法归一成 `UID=..; CID=..; SEID=..; KID=..`，缺项照实保留。"""
    text = _s(raw).replace("\n", " ").replace("\r", " ").replace("\t", " ")
    if not text:
        return ""
    # 整段塞进来的地址 / URL 编码 / JSON 都拆一遍
    if "://" in text and "?" in text:
        text = urllib.parse.unquote(text.split("?", 1)[1])
    if "%3B" in text.upper() or "%20" in text.upper():
        text = urllib.parse.unquote(text)
    if text.startswith("{"):
        try:
            obj = json.loads(text)
            text = _s(obj.get("cookie") or obj.get("Cookie") or "")
        except Exception:
            pass
    text = re.sub(r"^\s*cookie\s*[:=]\s*", "", text, flags=re.I)
    pairs = []
    seen = {}
    for chunk in re.split(r"[;；]", text):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" in chunk:
            key, val = chunk.split("=", 1)
        else:
            key, val = chunk, ""
        key = key.strip().strip('"').strip("'")
        val = val.strip().strip('"').strip("'").rstrip(",")
        if not key:
            continue
        low = key.upper()
        if low in seen:
            pairs[seen[low]] = (key, val)
        else:
            seen[low] = len(pairs)
            pairs.append((key, val))
    return "; ".join("%s=%s" % (k, v) for k, v in pairs)


def _cookie_report(cookie):
    got = {}
    for chunk in _s(cookie).split(";"):
        if "=" in chunk:
            key, val = chunk.split("=", 1)
            got[key.strip().upper()] = val.strip()
    missing = [k for k in COOKIE_PARTS if not got.get(k)]
    return got, missing


# ---------------------------------------------------------------- 分享库

class _Store(object):
    """分享库：下载 / 缓存 / 索引 / 查询，全进程一份。"""

    def __init__(self):
        self.lock = threading.Lock()
        self.db = None
        self.path = ""
        self.error = ""
        self.cache = {}
        self.cache_lock = threading.Lock()

    # ---- 位置
    def _candidates(self, env):
        out = []
        if env.get("db"):
            out.append(env["db"])
        roots = []
        if env.get("cache"):
            roots.append(env["cache"])
        for base in (
            os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "",
            os.getcwd(),
            "/storage/emulated/0/Download",
            "/sdcard/Download",
            "/storage/emulated/0/Android/data",
            tempfile.gettempdir(),
        ):
            if base:
                roots.append(base)
        for root in roots:
            for sub in ("", "115share"):
                out.append(os.path.join(root, sub, DB_NAME) if sub else os.path.join(root, DB_NAME))
        return out

    @staticmethod
    def _valid(path):
        try:
            if not os.path.exists(path) or os.path.getsize(path) < 4096:
                return False
            with open(path, "rb") as fh:
                return fh.read(len(SQLITE_MAGIC)) == SQLITE_MAGIC
        except Exception:
            return False

    def _pick_target(self, env):
        for path in self._candidates(env):
            if self._valid(path):
                return path
            folder = os.path.dirname(path)
            try:
                if folder and not os.path.isdir(folder):
                    os.makedirs(folder)
                test = os.path.join(folder, ".w")
                with open(test, "wb") as fh:
                    fh.write(b"1")
                os.remove(test)
                return path
            except Exception:
                continue
        return os.path.join(tempfile.gettempdir(), DB_NAME)

    def _download(self, path):
        print("[115share] 下载分享库 %s" % path)
        tmp = path + ".tmp"
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        req = urllib.request.Request(DB_URL, headers={"User-Agent": UA_WEB})
        folder = os.path.dirname(path)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        total = 0
        with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as fh:
            while True:
                chunk = resp.read(262144)
                if not chunk:
                    break
                fh.write(chunk)
                total += len(chunk)
        if not self._valid(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass
            raise RuntimeError("分享库下载校验失败")
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
        os.rename(tmp, path)
        print("[115share] 分享库就绪 %d 字节" % total)

    def _open(self, env):
        path = self._pick_target(env)
        if not self._valid(path):
            self._download(path)
        db = sqlite3.connect(path, check_same_thread=False, timeout=20)
        db.row_factory = sqlite3.Row
        try:
            db.execute("CREATE INDEX IF NOT EXISTS idx_share_pid ON share(pid)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_share_cid_pid ON share(cid, pid)")
            db.commit()
        except Exception:
            pass
        row = db.execute("SELECT COUNT(*) AS total FROM share").fetchone()
        if not row or not _num(row["total"]):
            db.close()
            raise RuntimeError("分享库内容为空")
        self.path = path
        print("[115share] 库行数 %s" % row["total"])
        return db

    def get(self, env, wait=None):
        if self.db is not None:
            return self.db
        if not self.lock.acquire(False):
            deadline = time.time() + (HOME_WAIT if wait is None else wait)
            while time.time() < deadline:
                if self.db is not None:
                    return self.db
                if self.error:
                    raise RuntimeError(self.error)
                time.sleep(0.2)
            raise RuntimeError("分享库仍在准备中")
        try:
            if self.db is None:
                try:
                    self.db = self._open(env)
                    self.error = ""
                except Exception as err:
                    self.error = "%s" % err
                    raise
            return self.db
        finally:
            self.lock.release()

    # ---- 缓存
    def cache_get(self, key):
        with self.cache_lock:
            hit = self.cache.get(key)
            if not hit:
                return None
            if time.time() - hit[0] > DETAIL_TTL:
                self.cache.pop(key, None)
                return None
            return hit[1]

    def cache_set(self, key, value):
        with self.cache_lock:
            if len(self.cache) > 200:
                self.cache.clear()
            self.cache[key] = (time.time(), value)


STORE = _Store()


# ---------------------------------------------------------------- 主类

class Spider(object):

    def __init__(self):
        self.env = {}
        self.cookie = ""
        self.cookie_raw = ""

    # ============ 初始化 ============
    def init(self, extend=""):
        self.env = self._parse_ext(extend)
        self.cookie_raw = self._read_cookie(self.env)
        self.cookie = _norm_cookie(self.cookie_raw)
        if self.cookie:
            _, missing = _cookie_report(self.cookie)
            print("[115share] cookie 已载入，缺项：%s" % (",".join(missing) if missing else "无"))
        else:
            print("[115share] 未配置 115 cookie，播放请在 ext 里写 cookie=UID=..;CID=..;SEID=..;KID=..")

    @staticmethod
    def _parse_ext(extend):
        env = {}
        text = _s(extend)
        if not text:
            return env
        if "://" in text and "?" in text and "=" not in text.split("?", 1)[0]:
            text = text.split("?", 1)[1]
        text = urllib.parse.unquote(text).strip()
        if text.startswith("{"):
            try:
                obj = json.loads(text)
            except Exception:
                obj = None
            if isinstance(obj, dict):
                for key, val in obj.items():
                    if isinstance(val, (dict, list)):
                        env[_s(key).lower()] = json.dumps(val, ensure_ascii=False)
                    else:
                        env[_s(key).lower()] = _s(val)
                return env
        # cookie 里本身带分号，所以有 cookie= 时只按 & 和换行切，绝不按分号切
        seps = r"[&\n]" if re.search(r"(?i)\bcookie\s*=", text) else r"[&;；\n]"
        for chunk in re.split(seps, text):
            chunk = chunk.strip()
            if not chunk or "=" not in chunk:
                continue
            key, val = chunk.split("=", 1)
            key = key.strip().lower()
            if key in env and key != "cookie":
                continue
            env[key] = val.strip()
        if "cookie" not in env:
            # ext 直接就是一段 cookie
            if re.search(r"(?i)(^|[;&\s])UID\s*=", text):
                env["cookie"] = text
        return env

    @staticmethod
    def _read_cookie(env):
        for key in ("cookie", "cookies", "115cookie", "115_cookie"):
            val = env.get(key)
            if _s(val):
                return val
        path = env.get("cookie_file") or env.get("cookiefile")
        if path:
            try:
                with open(path, "r") as fh:
                    return fh.read()
            except Exception:
                print("[115share] 读不到 cookie 文件 %s" % path)
        # 同目录约定文件
        try:
            base = os.path.dirname(os.path.abspath(__file__))
            for name in ("115cookie.txt", "cookie.txt"):
                path = os.path.join(base, name)
                if os.path.exists(path):
                    with open(path, "r") as fh:
                        return fh.read()
        except Exception:
            pass
        return ""

    def _size(self):
        size = _num(self.env.get("size"), PAGE_SIZE)
        if size <= 0 or size > 200:
            size = PAGE_SIZE
        return size

    # ============ 115 取链 ============
    def _headers(self, referer="https://115.com/", ua=None):
        hdrs = {
            "User-Agent": ua or UA_WEB,
            "Referer": referer,
            "Origin": "https://115.com",
            "Accept": "application/json, text/plain, */*",
        }
        if self.cookie:
            hdrs["Cookie"] = self.cookie
        return hdrs

    @staticmethod
    def _json(resp):
        text = resp.text
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            start = text.find("{")
            end = text.rfind("}")
            if 0 <= start < end:
                try:
                    return json.loads(text[start:end + 1])
                except Exception:
                    return None
        return None

    @staticmethod
    def _pick_url(obj):
        """从各种返回结构里挖直链。"""
        if not isinstance(obj, dict):
            return ""
        data = obj.get("data")
        if isinstance(data, str) and data.startswith("http"):
            return data
        for holder in (data, obj):
            if not isinstance(holder, dict):
                continue
            url = holder.get("url")
            if isinstance(url, str) and url.startswith("http"):
                return url
            if isinstance(url, dict):
                for key in ("url", "file_url", "download_url", "src"):
                    val = url.get(key)
                    if isinstance(val, str) and val.startswith("http"):
                        return val
            for key in ("file_url", "download_url", "src", "m3u8"):
                val = holder.get(key)
                if isinstance(val, str) and val.startswith("http"):
                    return val
        return ""

    @staticmethod
    def _err(obj, resp):
        if isinstance(obj, dict):
            for key in ("error", "message", "msg", "errmsg"):
                text = _s(obj.get(key))
                if text:
                    return text
            code = obj.get("errno", obj.get("errNo"))
            if code not in (None, "", 0, "0"):
                return "115 返回错误码 %s" % code
        text = _s(resp.text)[:120]
        return text or "115 无返回"

    def _need_receive(self, obj):
        text = ""
        if isinstance(obj, dict):
            text = _s(obj.get("error")) + _s(obj.get("message"))
        return any(word in text for word in ("转存", "接收", "保存到"))

    def _receive(self, share_code, receive_code):
        resp = _http(
            "https://webapi.115.com/share/receive",
            {"share_code": _s(share_code), "receive_code": _s(receive_code), "action": "receive_share"},
            self._headers("https://115.com/s/%s" % _s(share_code)),
        )
        obj = self._json(resp)
        ok = isinstance(obj, dict) and (obj.get("state") is True or obj.get("errno") == 0)
        print("[115share] 转存 %s -> %s" % (_s(share_code), "OK" if ok else self._err(obj, resp)))
        return ok

    def _resolve(self, share_code, receive_code, file_id):
        """返回 (直链, 说明)。"""
        share_code = _s(share_code)
        receive_code = _s(receive_code)
        file_id = _s(file_id)
        if not share_code or not file_id:
            return "", "播放参数缺失"
        if not self.cookie:
            return "", "未配置 115 cookie：ext 里写 cookie=UID=..; CID=..; SEID=..; KID=.."

        _, missing = _cookie_report(self.cookie)
        if missing:
            return "", "cookie 缺项（%s），115 要 UID/CID/SEID/KID 四项" % "/".join(missing)

        referer = "https://115.com/s/%s" % share_code
        body = {"share_code": share_code, "receive_code": receive_code, "file_id": file_id}
        tries = [
            ("web-downurl", "https://webapi.115.com/share/downurl", body, referer, None),
            ("web-downurl-115ua", "https://webapi.115.com/share/downurl", body, "https://115.com/", UA_115),
            ("app-downurl", "https://proapi.115.com/app/share/downurl",
             {"data": json.dumps(body)}, "https://115.com/", UA_115),
        ]
        diag = []
        primary = ""
        for name, url, data, ref, ua in tries:
            resp = _http(url, data, self._headers(ref, ua), timeout=20)
            obj = self._json(resp)
            direct = self._pick_url(obj)
            if direct:
                print("[115share] 取链成功（%s）" % name)
                return direct, ""
            reason = self._err(obj, resp)
            if not primary:
                primary = reason
            diag.append("%s: %s" % (name, reason[:80]))
            print("[115share] 取链失败（%s）%s" % (name, reason[:160]))
            if self._need_receive(obj) and _s(self.env.get("transfer")) in ("1", "true", "yes"):
                if self._receive(share_code, receive_code):
                    resp2 = _http(url, data, self._headers(ref, ua), timeout=20)
                    direct2 = self._pick_url(self._json(resp2))
                    if direct2:
                        print("[115share] 取链成功（%s + 转存后）" % name)
                        return direct2, ""

        # 全部失败：按主接口（web downurl）的说法给结论
        joined = " | ".join(diag)
        if "登录" in primary or "990001" in primary:
            return "", "115 登录态失效：重新复制一份完整 cookie（UID / CID / SEID / KID 四项）"
        if "转存" in primary:
            return "", "这个分享要转存后才给直链：ext 里加 transfer=1，或先在 115 里转存一次"
        if "版本过低" in primary:
            return "", "115 只放分享页不放直链：先在 115 App/网页把这个分享转存到自己网盘（ext 加 transfer=1 可自动试）"
        if _s(self.env.get("diag")) in ("1", "true", "yes"):
            return "", "115 取链失败 · " + joined[:200]
        return "", "115 取链失败（%s），稍后重试或换一集" % primary[:40]

    # ============ 数据封装 ============
    @staticmethod
    def _encode_dir(row_id):
        text = _s(row_id)
        if text.startswith(DIR_PREFIX):
            return text
        return "%s%s" % (DIR_PREFIX, text)

    @staticmethod
    def _encode_file(row):
        payload = {
            "c": _s(row["share_code"]),
            "r": _s(row["receive_code"]),
            "f": _s(row["fid"]),
            "p": _s(row["cid"]) if "cid" in row.keys() else "",
            "n": _s(row["name"]),
        }
        return FILE_PREFIX + _b64e(json.dumps(payload, ensure_ascii=False))

    @staticmethod
    def _decode_file(token):
        raw = _s(token)
        if not raw.startswith(FILE_PREFIX):
            return None
        try:
            data = json.loads(_b64d(raw[len(FILE_PREFIX):]) or "{}")
        except Exception:
            return None
        return data if _s(data.get("f")) else None

    @staticmethod
    def _folder_card(row_id, name, remarks=""):
        return {
            "vod_id": Spider._encode_dir(row_id),
            "vod_name": _clean(name),
            "vod_pic": FOLDER_PIC,
            "vod_remarks": _clean(remarks, 40),
            "vod_tag": "folder",
            "action": "folder",
        }

    @staticmethod
    def _file_card(row):
        return {
            "vod_id": Spider._encode_file(row),
            "vod_name": _clean(_strip_ext(row["name"])),
            "vod_pic": VIDEO_PIC,
            "vod_remarks": "115分享",
        }

    # ============ 查询层 ============
    def _db(self, wait=None):
        return STORE.get(self.env, wait)

    @staticmethod
    def _roots(db):
        return db.execute(
            "SELECT %s FROM share WHERE pid = '0' AND %s ORDER BY id" % (ROW_COLUMNS, IS_DIR_SQL)
        ).fetchall()

    @staticmethod
    def _dir_by_rowid(db, row_id):
        return db.execute(
            "SELECT %s FROM share WHERE id = ? AND %s" % (ROW_COLUMNS, IS_DIR_SQL), (row_id,)
        ).fetchone()

    @staticmethod
    def _dir_by_cid(db, cid):
        return db.execute(
            "SELECT %s FROM share WHERE cid = ? AND %s LIMIT 1" % (ROW_COLUMNS, IS_DIR_SQL), (_s(cid),)
        ).fetchone()

    def _resolve_dir(self, db, raw):
        text = _s(raw)
        if not text or text == "0" or text.startswith(FILE_PREFIX):
            return None
        value = text[len(DIR_PREFIX):] if text.startswith(DIR_PREFIX) else text
        if not re.match(r"^\d+$", value):
            return None
        if len(value) >= 10:
            return self._dir_by_cid(db, value)
        return self._dir_by_rowid(db, value) or self._dir_by_cid(db, value)

    @staticmethod
    def _count(db, sql, args):
        row = db.execute(sql, args).fetchone()
        return _num(row[0] if row else 0)

    def _folders(self, db, cid, limit=None, offset=0):
        sql = "SELECT %s FROM share WHERE pid = ? ORDER BY name" % ROW_COLUMNS
        if limit:
            return db.execute(sql + " LIMIT ? OFFSET ?", (_s(cid), limit, offset)).fetchall()
        return db.execute(sql, (_s(cid),)).fetchall()

    def _files(self, db, cid, limit=None, offset=0):
        sql = "SELECT %s FROM share WHERE cid = ? AND %s AND %s ORDER BY name" % (
            ROW_COLUMNS, IS_FILE_SQL, FILE_VIDEO_SQL)
        if limit:
            return db.execute(sql + " LIMIT ? OFFSET ?", (_s(cid), limit, offset)).fetchall()
        return db.execute(sql, (_s(cid),)).fetchall()

    # ============ 首页 / 分类 ============
    def homeContent(self, filter=False):
        fallback = {"class": [{"type_id": "0", "type_name": "115分享集合"}], "filters": {}, "list": []}
        try:
            db = self._db(HOME_WAIT)
        except Exception as err:
            print("[115share] 首页库未就绪：%s" % err)
            return fallback
        roots = self._roots(db)
        if not roots:
            return fallback
        return {
            "class": [{"type_id": "0", "type_name": "全部合集"}] + [
                {"type_id": self._encode_dir(row["id"]), "type_name": _short(row["name"])} for row in roots
            ],
            "filters": {},
            "list": [
                self._folder_card(self._encode_dir(row["id"]), row["name"], "合集 · %s" % row["share_code"])
                for row in roots
            ],
        }

    def homeVideoContent(self):
        try:
            db = self._db(HOME_WAIT)
        except Exception:
            return {"list": []}
        roots = self._roots(db)
        return {"list": [
            self._folder_card(self._encode_dir(row["id"]), row["name"], "合集 · %s" % row["share_code"])
            for row in roots
        ]}

    def categoryContent(self, tid, pg, filter=False, extend=None):
        size = self._size()
        page = max(1, _num(pg, 1))
        try:
            db = self._db()
        except Exception as err:
            return {"list": [], "page": page, "pagecount": 1, "limit": size, "total": 0,
                    "msg": "分享库准备中：%s" % err}
        row = self._resolve_dir(db, tid)
        if row is None:
            roots = self._roots(db)
            listing = [self._folder_card(self._encode_dir(r["id"]), r["name"], "合集 · %s" % r["share_code"])
                       for r in roots]
            return {"list": listing, "page": 1, "pagecount": 1, "limit": size, "total": len(listing)}

        cid = _s(row["cid"])
        folder_total = self._count(db, "SELECT COUNT(*) FROM share WHERE pid = ?", (cid,))
        file_total = self._count(
            db, "SELECT COUNT(*) FROM share WHERE cid = ? AND %s AND %s" % (IS_FILE_SQL, FILE_VIDEO_SQL), (cid,))
        total = folder_total + file_total
        offset = (page - 1) * size
        listing = []
        if offset < folder_total:
            folders = self._folders(db, cid, size, offset)
            for item in folders:
                listing.append(self._folder_card(self._encode_dir(item["id"]), item["name"], "目录"))
            rest = size - len(folders)
            if rest > 0 and file_total > 0:
                for item in self._files(db, cid, rest, 0):
                    listing.append(self._file_card(item))
        elif file_total > 0:
            for item in self._files(db, cid, size, offset - folder_total):
                listing.append(self._file_card(item))
        pagecount = max(1, (total + size - 1) // size)
        return {"list": listing, "page": page, "pagecount": pagecount, "limit": size, "total": total}

    # ============ 搜索 ============
    def searchContent(self, key, quick=False, pg="1"):
        word = _clean(key, 60)
        page = max(1, _num(pg, 1))
        if not word:
            return {"list": [], "page": page, "pagecount": 1, "limit": SEARCH_SIZE, "total": 0}
        try:
            db = self._db()
        except Exception as err:
            return {"list": [], "page": page, "pagecount": 1, "limit": SEARCH_SIZE, "total": 0,
                    "msg": "分享库准备中：%s" % err}
        like = "%" + re.sub(r"([\\%_])", r"\\\1", word) + "%"
        rows = db.execute(
            "SELECT %s, CASE WHEN %s THEN 0 ELSE 1 END AS kind FROM share "
            "WHERE name LIKE ? ESCAPE '\\' AND (%s OR %s) ORDER BY kind, id LIMIT ? OFFSET ?"
            % (ROW_COLUMNS, IS_DIR_SQL, IS_DIR_SQL, FILE_VIDEO_SQL),
            (like, SEARCH_SIZE, (page - 1) * SEARCH_SIZE),
        ).fetchall()
        listing = []
        for row in rows:
            if _num(row["kind"]) == 0:
                remark = "分享合集" if _s(row["pid"]) == "0" else "目录"
                listing.append(self._folder_card(self._encode_dir(row["id"]), row["name"], remark))
            else:
                listing.append(self._file_card(row))
        pagecount = page + 1 if len(rows) >= SEARCH_SIZE else page
        return {"list": listing, "page": page, "pagecount": max(1, pagecount),
                "limit": SEARCH_SIZE, "total": len(listing)}

    # ============ 详情 ============
    def _collect_groups(self, db, root_row):
        groups = []
        stack = [{"cid": _s(root_row["cid"]), "label": "", "depth": 0}]
        files = 0
        steps = 0
        while stack and len(groups) < MAX_GROUPS and files < MAX_FILES and steps < MAX_WALK_STEPS:
            steps += 1
            node = stack.pop(0)
            rows = self._files(db, node["cid"])
            if rows:
                picked = sorted(rows, key=lambda r: _natkey(r["name"]))
                picked = picked[:min(MAX_FILES_PER_GROUP, MAX_FILES - files)]
                groups.append({"label": node["label"], "rows": picked})
                files += len(picked)
            if node["depth"] >= MAX_DEPTH:
                continue
            folders = self._folders(db, node["cid"])
            if not folders:
                continue
            children = []
            for folder in folders:
                label = ("%s/%s" % (node["label"], folder["name"])) if node["label"] else _s(folder["name"])
                children.append({"cid": _s(folder["cid"]), "label": label, "depth": node["depth"] + 1})
            stack = children + stack
        return groups

    @staticmethod
    def _build_play(groups):
        lines = []
        singles = []
        for group in groups:
            if len(group["rows"]) == 1:
                singles.append(group)
            else:
                lines.append({"from": group["label"],
                              "items": [{"name": _strip_ext(r["name"]), "row": r} for r in group["rows"]]})
        if len(singles) == 1:
            lines.append({"from": singles[0]["label"],
                          "items": [{"name": _strip_ext(singles[0]["rows"][0]["name"]),
                                     "row": singles[0]["rows"][0]}]})
        elif len(singles) > 1:
            lines.append({"from": "单片合集",
                          "items": [{"name": _leaf(g["label"]) or _strip_ext(g["rows"][0]["name"]),
                                     "row": g["rows"][0]} for g in singles]})
        froms = []
        urls = []
        used_from = set()
        for line in lines:
            label = _line_label(line["from"])
            base = _clean(label, 34) or "主目录"
            name_from = _clean(label, 40) or "主目录"
            suffix = 2
            while name_from in used_from:
                name_from = "%s(%d)" % (base, suffix)
                suffix += 1
            used = set()
            episodes = []
            for item in line["items"]:
                name = _clean(item["name"], 60) or "正片"
                idx = 2
                while name in used:
                    name = "%s(%d)" % (name, idx)
                    idx += 1
                used.add(name)
                episodes.append("%s$%s" % (name, Spider._encode_file(item["row"])))
            if not episodes:
                continue
            used_from.add(name_from)
            froms.append(name_from)
            urls.append("#".join(episodes))
        return {"vod_play_from": "$$$".join(froms), "vod_play_url": "$$$".join(urls)}

    def _dir_detail(self, db, row):
        key = "dir:%s" % row["id"]
        cached = STORE.cache_get(key)
        if cached:
            return cached
        groups = self._collect_groups(db, row)
        count = sum(len(g["rows"]) for g in groups)
        vod = {
            "vod_id": self._encode_dir(row["id"]),
            "vod_name": _clean(row["name"]),
            "vod_pic": FOLDER_PIC,
            "vod_remarks": ("%d个文件" % count) if count else "暂无可播文件",
            "vod_content": "\n".join(x for x in [
                _share_page(row["share_code"], row["receive_code"]), _clean(row["name"], 200)] if x),
            "type_name": "115分享",
        }
        vod.update(self._build_play(groups))
        STORE.cache_set(key, vod)
        return vod

    def _file_detail(self, db, token):
        info = self._decode_file(token)
        if not info:
            return None
        parent = self._dir_by_cid(db, info.get("p")) if _s(info.get("p")) else None
        siblings = self._files(db, info["p"]) if _s(info.get("p")) else []
        if siblings:
            rows = sorted(siblings, key=lambda r: _natkey(r["name"]))
        else:
            rows = [{"share_code": info["c"], "receive_code": info.get("r", ""),
                     "cid": info.get("p", ""), "fid": info["f"], "name": info.get("n", ""), "id": 0, "pid": ""}]
        play = self._build_play([{"label": (parent["name"] if parent else "115分享"), "rows": rows}])
        vod = {
            "vod_id": token,
            "vod_name": _clean(parent["name"] if parent else _strip_ext(info.get("n"))),
            "vod_pic": VIDEO_PIC,
            "vod_remarks": "%d个文件" % len(rows),
            "vod_content": "\n".join(x for x in [
                _share_page(info.get("c"), info.get("r")), _clean(info.get("n"), 200)] if x),
            "type_name": "115分享",
        }
        vod.update(play)
        return vod

    def detailContent(self, ids):
        try:
            db = self._db()
        except Exception as err:
            return {"list": [], "msg": "分享库准备中：%s" % err}
        raw = ids[0] if isinstance(ids, (list, tuple)) and ids else ids
        listing = []
        for token in [_s(x) for x in _s(raw).split(",") if _s(x)]:
            try:
                if token.startswith(FILE_PREFIX):
                    vod = self._file_detail(db, token)
                else:
                    row = self._resolve_dir(db, token)
                    vod = self._dir_detail(db, row) if row is not None else None
            except Exception:
                print("[115share] 详情异常 %s\n%s" % (token[:40], traceback.format_exc()))
                vod = None
            if vod:
                listing.append(vod)
        return {"list": listing}

    # ============ 播放 ============
    def playerContent(self, flag, id, vipFlags=None):
        info = self._decode_file(id)
        if not info:
            return {"parse": 0, "url": "", "msg": "播放参数无效"}
        try:
            url, msg = self._resolve(info.get("c"), info.get("r"), info.get("f"))
        except Exception as err:
            print("[115share] 播放异常：%s\n%s" % (err, traceback.format_exc()))
            return {"parse": 0, "url": "", "msg": "115 取链异常：%s" % err}
        if not url:
            print("[115share] 播放失败：%s" % msg)
            return {"parse": 0, "url": "", "msg": msg}
        out = {
            "parse": 0,
            "url": url,
            "header": {
                "User-Agent": UA_WEB,
                "Referer": "https://115.com/",
            },
        }
        if _s(info.get("n")).lower().endswith(".iso"):
            out["format"] = "video/x-iso"
            out["msg"] = "ISO 原盘多数播放器解不了，建议换 mp4/mkv 版本"
        return out

    # ============ 可选 ============
    def destroy(self):
        try:
            if STORE.db is not None:
                STORE.db.close()
        except Exception:
            pass
