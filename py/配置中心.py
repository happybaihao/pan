# -*- coding: utf-8 -*-
"""
TVBOX 本地包 / 公共函数
------------------------------------------------------------------
本文件所有逻辑均移植自 TVBOX (7).zip 自身的文件，没有引入任何其它包的内容：
  pan/detect.js              网盘分享链接类型识别、提取码
  pan/parse.js               公共解析降级通道
  lib/block-words.js         全局屏蔽词
  sites/T4玩偶资源站.js       UA、字符集判定、多镜像容错、播放串编码
只依赖 Python 标准库，可在 TVBox / FongMi 系壳子的 Python Spider 引擎中运行。
"""
import base64
import gzip
import json
import os
import re
import ssl
import time
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
TIMEOUT = 20

# pan/detect.js 的 PATTERNS
PAN_RULES = [
    ("quark",   "夸克网盘",  r"(?:pan\.quark\.cn|www\.quark\.cn)/s/([A-Za-z0-9_-]+)"),
    ("uc",      "UC网盘",    r"(?:drive\.uc\.cn|drive\.uc\.com|browser\.uc\.cn|www\.uc\.cn)/(?:s|share)/([A-Za-z0-9_-]+)"),
    ("aliyun",  "阿里云盘",  r"(?:www\.alipan\.com|www\.aliyundrive\.com|alipan\.com|aliyundrive\.com)/s/([A-Za-z0-9_-]+)"),
    ("baidu",   "百度网盘",  r"(?:pan\.baidu\.com|yun\.baidu\.com)/s/([A-Za-z0-9_-]+)"),
    ("115",     "115网盘",   r"(?:115\.com|115\.net|115cdn\.com|115img\.com|anxia\.com|web\.115\.com|cdn\.115\.com)/(?:s/|share/s/)([A-Za-z0-9_-]+)"),
    ("Thunder", "迅雷云盘",  r"(?:pan\.xunlei\.com|cloud\.xunlei\.com)/s/([A-Za-z0-9_-]+)"),
    ("123",     "123网盘",   r"(?:www\.)?123(?:684|685|865|912|pan|592)\.(?:com|cn)/(?:s/|123pan/)([\w-]+)"),
    ("123",     "123网盘",   r".+\.share\.123pan\.cn/123pan/([\w-]+)"),
    ("guangya", "光鸭网盘",  r"(?:www\.)?guangyapan\.com/s/([A-Za-z0-9_-]+)"),
]
PAN_LOOSE = re.compile(
    r"pan\.(quark|baidu)\.cn|drive\.uc\.cn|alipan\.com|aliyundrive\.com|115\.com|"
    r"123(?:684|685|865|912|pan|592)\.(com|cn)|guangyapan\.com|pan\.xunlei\.com", re.I)


def extract_pwd(url):
    """pan/detect.js: extractPwd"""
    s = str(url or "")
    try:
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(s).query)
        for k in ("pwd", "password", "code", "提取码"):
            v = q.get(k)
            if v and v[0]:
                return v[0]
    except Exception:
        pass
    m = re.search(r"(?:提取码|%E6%8F%90%E5%8F%96%E7%A0%81)(?:[:：]|%EF%BC%9A|%3A)\s*([A-Za-z0-9]{2,8})", s, re.I)
    return m.group(1) if m else ""


def detect(url):
    """pan/detect.js: detect —— 返回 {type,name,share_id,url,pwd} 或 None"""
    s = str(url or "").strip()
    if not s:
        return None
    full = s if s.startswith("http") else "https://" + s.lstrip("/")
    for typ, name, pat in PAN_RULES:
        m = re.search(pat, full, re.I)
        if m:
            return {"type": typ, "name": name, "share_id": m.group(1),
                    "url": full, "pwd": extract_pwd(full)}
    if PAN_LOOSE.search(full):
        return {"type": "unknown", "name": "其它网盘", "share_id": "",
                "url": full, "pwd": extract_pwd(full)}
    return None


def http_get(url, headers=None, timeout=TIMEOUT):
    """T4玩偶资源站.js: fetchHtml —— 响应头/meta 判字符集、支持 gzip、跳过证书校验"""
    h = {"User-Agent": UA,
         "Accept": "text/html,application/xhtml+xml,application/json,*/*;q=0.8",
         "Accept-Language": "zh-CN,zh;q=0.9"}
    if headers:
        h.update({str(k): str(v) for k, v in headers.items()})
    req = urllib.request.Request(url, headers=h)
    kw = {"timeout": timeout}
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kw["context"] = ctx
    except Exception:
        pass
    with urllib.request.urlopen(req, **kw) as r:
        raw = r.read()
        if "gzip" in str(r.headers.get("Content-Encoding", "")).lower():
            try:
                raw = gzip.decompress(raw)
            except Exception:
                pass
        ct = str(r.headers.get("Content-Type", ""))
    m = re.search(r"charset=([\w-]+)", ct, re.I)
    enc = m.group(1).lower() if m else ""
    if not enc:
        m2 = re.search(r'charset\s*=\s*["\']?([\w-]+)', raw[:4096].decode("latin1", "ignore"), re.I)
        enc = m2.group(1).lower() if m2 else ""
    if enc in ("gb2312", "gb-2312"):
        enc = "gbk"
    for e in (enc, "utf-8", "gbk", "latin1"):
        if not e:
            continue
        try:
            return raw.decode(e)
        except Exception:
            continue
    return raw.decode("utf-8", "ignore")


def strip_tags(s):
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", str(s or ""))
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&quot;", '"'),
                 ("&#39;", "'"), ("&lt;", "<"), ("&gt;", ">")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def clean(s):
    return strip_tags(s)


def _cfg_paths(name):
    """本地包 json/ 目录的若干候选位置；找不到时用内置数据，不影响主功能"""
    out = []
    for env in ("TVBOX_LOCAL_DIR", "TVBOX_HOME"):
        v = os.environ.get(env)
        if v:
            out.append(os.path.join(v, "json", name))
    try:
        out.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "json", name))
    except Exception:
        pass
    out += [os.path.join("json", name),
            os.path.join("/sdcard", "tvboxonly", "json", name),
            os.path.join("/storage/emulated/0", "tvboxonly", "json", name)]
    return out


def load_cfg(name, default):
    for p in _cfg_paths(name):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            continue
    return default


def block_hit(title, words=None):
    """lib/block-words.js: blockHit"""
    if words is None:
        words = load_cfg("block_words.json", [])
    if isinstance(words, dict):
        words = words.get("words") or words.get("subscriptionFilterKeywords") or []
    t = str(title or "").lower()
    try:
        return any(str(w).strip().lower() in t for w in words if str(w).strip())
    except Exception:
        return False


def public_parse(share_url, pan_type=""):
    """pan/parse.js: tryParses —— 读 json/parses.json，依次尝试公共解析接口"""
    cfg = load_cfg("parses.json", [])
    if isinstance(cfg, dict):
        cfg = cfg.get("panParses") or cfg.get("parses") or []
    if not isinstance(cfg, list) or not cfg:
        return None
    q = urllib.parse.quote(share_url, safe="")
    for p in cfg:
        if not isinstance(p, dict) or not p.get("url"):
            continue
        types = p.get("types") or []
        if types and pan_type and pan_type not in types:
            continue
        tpl = str(p["url"])
        u = tpl.replace("{url}", q) if "{url}" in tpl else tpl + q
        try:
            body = http_get(u, headers=p.get("header") or {}, timeout=12)
            t = (body or "").strip()
            resolved = ""
            if t.startswith("{"):
                try:
                    d = json.loads(t)
                    cand = [d.get("url"), d.get("play_url"), d.get("link")]
                    dd = d.get("data")
                    if isinstance(dd, dict):
                        cand += [dd.get("url"), dd.get("play_url")]
                    for v in cand:
                        if isinstance(v, str) and v.startswith("http"):
                            resolved = v
                            break
                except Exception:
                    pass
            elif re.match(r"^https?://", t):
                resolved = t
            if resolved.startswith("http") and not re.search(r"api/|json\.php|\?url=", resolved):
                return {"parse": 0, "url": resolved,
                        "header": p.get("playHeader") or {"User-Agent": UA}}
        except Exception:
            continue
    return None


def pan_encode(s):
    """T4玩偶资源站.js: panB64Encode（pan!base64url，避免播放串里的 $ 被客户端截断）"""
    return base64.urlsafe_b64encode(str(s).encode("utf-8")).decode("ascii").rstrip("=")


def pan_decode(s):
    s = str(s or "")
    try:
        return base64.urlsafe_b64decode((s + "=" * (-len(s) % 4)).encode("ascii")).decode("utf-8", "ignore")
    except Exception:
        return ""


def parse_ext(extend):
    """兼容壳子传 dict / JSON 字符串 / key=value;... / 单值"""
    if isinstance(extend, dict):
        return dict(extend)
    s = str(extend or "").strip()
    if not s:
        return {}
    if s.startswith("{"):
        try:
            return json.loads(s)
        except Exception:
            pass
    out = {}
    for seg in s.split(";"):
        if "=" in seg:
            k, v = seg.split("=", 1)
            out[k.strip()] = v.strip()
        elif seg.strip():
            out.setdefault("key", seg.strip())
    return out


# ==============================================================================
# 网盘账号的「外置到站点 ext」支持
# ------------------------------------------------------------------------------
# TVBox / FongMi 的 Python Spider 有个硬约束：init(extend) 只收到【该站点自己】
# 的 ext，站点 A 的 ext 里的 Cookie，站点 B 的 Spider 看不到。所以想让
# 「配置中心」站点的 ext 成为全局配置，必须让每个 Spider 主动去读配置。
#
# 于是设计了 4 条互补通道，按优先级自动选择：
#   ① json/pan_accounts.runtime.json —— 配置中心站点被点开时把自己 init() 收到的
#                                        ext 写成运行时快照；代表用户「最近一次在
#                                        UI 里确认过的配置」，优先级最高，因此
#                                        广播过旧账号后再改 UI 也能覆盖旧值。
#                                        同时解决「壳子 UI 改 ext 只存自己的数据库、
#                                        不回写 FongMi.json」的问题。
#   ② 当前站点自己的 ext.panAccounts —— gen_config.py --broadcast 一键广播，
#                                        壳子一定会把 ext 传给该站点的 Spider，最可靠
#   ③ FongMi.json 里配置中心站点的 ext —— 直接编辑配置文件这一处即可全局生效
#   ④ json/pan_accounts.json           —— 原来的文件方式，向后兼容
# 三处 ext 的值都支持「就地写数组/对象」或「写一个 http(s) JSON 直链」：
#   "panAccounts": [ {...}, {...} ]                 就地写账号数组
#   "panAccounts": "https://host/panAccounts.json"  值本身就是直链
#   "panAccountsUrl": "https://host/acc.json"       单独的直链键（推荐，不会被广播工具覆盖）
#   "panConfigUrl":   "https://host/config.json"    一个直链同时给 panAccounts + panOptions
#   "panOptions": {...} / "panOptions": "https://host/opt.json" / "panOptionsUrl": ...
# 直链返回数组、{"panAccounts":[...], "panOptions":{...}}、单账号对象、
# 甚至 {"quark":"cookie...", "baidu":"cookie..."} 都能识别，见 normalize_accounts()。
# ==============================================================================
SITE_EXT = {}
_EXT_KEYS = ("panAccounts", "pan_accounts", "accounts", "panAccountsUrl",
             "pan_accounts_url", "accountsUrl")
_OPT_KEYS = ("panOptions", "pan_options", "options", "panOptionsUrl",
             "pan_options_url", "optionsUrl")
_CFG_KEYS = ("panConfig", "panConfigUrl", "pan_config", "pan_config_url", "configUrl")
_ALL_EXT_KEYS = _EXT_KEYS + _OPT_KEYS + _CFG_KEYS
_GLOBAL_CACHE = {"sig": None, "ext": {}}

# 远程直链：进程内 TTL 缓存 + 最后一次拉取状态（供配置中心首页显示）
REF_TTL = 300
_REF_CACHE = {}
_REF_STATE = {"url": "", "ok": False, "info": "未使用", "ts": 0}


def ref_state():
    """→ dict：最后一次远程直链拉取的状态（url / ok / info / ts）"""
    return dict(_REF_STATE)


def reset_ref_cache():
    """「立即应用到全局」时调用，强制下次重新拉取远程配置"""
    _REF_CACHE.clear()


def _is_http(v):
    return isinstance(v, str) and bool(re.match(r"^https?://", v.strip(), re.I))


def fetch_json_ref(url, force=False, timeout=8):
    """拉取一份远程 JSON 配置。成功缓存 REF_TTL 秒；失败时若有过成功缓存仍返回旧值。
    用本包自己的 http_get（跳过证书校验、自动解压/判编码），不引入第三方库。
    """
    u = str(url or "").strip()
    if not _is_http(u):
        return None
    now = time.time()
    old = _REF_CACHE.get(u)
    if not force and old and now - old[0] < REF_TTL:
        return old[1]
    try:
        txt = http_get(u, headers={"Accept": "application/json,text/plain,*/*"},
                       timeout=timeout) or ""
        t = txt.lstrip("\ufeff \r\n\t")
        if not t.startswith(("[", "{")):
            a, b = t.find("["), t.find("{")
            st = min(x for x in (a, b) if x >= 0) if (a >= 0 or b >= 0) else -1
            if st > 0:
                t = t[st:]
        data = json.loads(t)
        _REF_CACHE[u] = (now, data)
        _REF_STATE.update({"url": u, "ok": True, "ts": int(now),
                           "info": "OK · %s" % (type(data).__name__)})
        return data
    except Exception as e:
        _REF_STATE.update({"url": u, "ok": False, "ts": int(now),
                           "info": "拉取失败：%s" % str(e)[:100]})
        return old[1] if old else None


_TYPE_ALIAS = {
    "夸克": "quark", "夸克网盘": "quark", "quark": "quark", "quarkpan": "quark",
    "uc": "uc", "uc网盘": "uc", "ucpan": "uc",
    "阿里": "aliyun", "阿里云盘": "aliyun", "阿里网盘": "aliyun", "ali": "aliyun",
    "aliyun": "aliyun", "alipan": "aliyun", "aliyundrive": "aliyun",
    "123": "123", "123云盘": "123", "123网盘": "123", "123pan": "123",
    "115": "115", "115网盘": "115", "pan115": "115",
    "百度": "baidu", "百度网盘": "baidu", "bd": "baidu", "bdyun": "baidu",
    "baidu": "baidu", "baidupan": "baidu",
    "光鸭": "guangya", "光鸭网盘": "guangya", "guangya": "guangya",
    "迅雷": "Thunder", "迅雷云盘": "Thunder", "迅雷网盘": "Thunder",
    "xunlei": "Thunder", "thunder": "Thunder",
}


def normalize_accounts(rows):
    """把第三方 panAccounts.json 的常见写法规整成本包格式：
    type/cookie 别名、中文网盘名、{"type":"cookie"} 映射、单账号对象。
    """
    if not isinstance(rows, list):
        return []
    out = []
    for a in rows:
        if isinstance(a, dict):
            d = dict(a)
        elif isinstance(a, str) and a.strip():
            # ["UID=..;CID=.."] 之类无法判断类型，跳过
            continue
        else:
            continue
        t = ""
        for k in ("type", "panType", "pan_type", "pan", "drive", "id"):
            if d.get(k):
                t = str(d[k]).strip()
                break
        ck = ""
        for k in ("cookie", "Cookie", "COOKIE", "ck", "cookies", "cookieStr"):
            if d.get(k):
                ck = str(d[k]).strip()
                break
        if not ck:
            data = d.get("data") if isinstance(d.get("data"), dict) else {}
            for k in ("refresh_token", "token", "access_token", "cookie"):
                if d.get(k) or data.get(k):
                    ck = str(d.get(k) or data.get(k))
                    if k == "refresh_token":
                        ck = "refresh_token=" + ck
                    break
        if not ck or not t:
            continue
        typ = _TYPE_ALIAS.get(t.lower(), _TYPE_ALIAS.get(t, t))
        d["type"] = typ
        d["cookie"] = ck
        d.setdefault("id", typ)
        d.setdefault("name", typ)
        d["enabled"] = d.get("enabled") is not False
        out.append(d)
    return out


def _raw_json(v, depth=0):
    """把 URL / JSON 字符串还原成原始 JSON 对象，不做任何结构猜测。
    给 panConfigUrl 用：整包配置必须原样保留，才能从中分别取账号和选项。
    """
    if v is None or depth > 4:
        return None
    if isinstance(v, str):
        s = v.strip()
        if _is_http(s):
            return _raw_json(fetch_json_ref(s), depth + 1)
        if s.startswith(("[", "{")):
            try:
                return _raw_json(json.loads(s), depth + 1)
            except Exception:
                return None
        return None
    return v


def _as_json_value(v, kind, depth=0):
    """把任意 ext 值（数组/对象/JSON 字符串/URL 字符串）规整成 list 或 dict。"""
    if v is None or depth > 4:
        return None
    if isinstance(v, str):
        s = v.strip()
        if _is_http(s):
            return _as_json_value(fetch_json_ref(s), kind, depth + 1)
        if s.startswith(("[", "{")):
            try:
                return _as_json_value(json.loads(s), kind, depth + 1)
            except Exception:
                return None
        return None
    if kind == "list":
        if isinstance(v, list):
            return normalize_accounts(v)
        if isinstance(v, dict):
            for k in ("panAccounts", "pan_accounts", "accounts", "data",
                      "list", "config"):
                if k in v:
                    r = _as_json_value(v[k], "list", depth + 1)
                    if r:
                        return r
            if any(k in v for k in ("cookie", "Cookie", "ck", "token")):
                return normalize_accounts([v])          # 单个账号对象
            rows = [{"type": k, "cookie": val, "id": k, "name": k,
                     "enabled": True}
                    for k, val in v.items()
                    if isinstance(val, str) and val.strip()
                    and not k.startswith("__")
                    and str(k).lower() not in ("hint", "name", "note", "remark",
                                               "time", "ts", "date", "version",
                                               "url", "author", "tip")]
            return normalize_accounts(rows) if rows else None
        return None
    if isinstance(v, dict):
        for k in ("panOptions", "pan_options", "options", "config", "data"):
            if isinstance(v.get(k), dict) and not any(
                    x in v[k] for x in ("panAccounts", "panOptions")):
                return v[k]
        rest = {k: val for k, val in v.items()
                if not k.startswith("__") and k not in _ALL_EXT_KEYS
                and not isinstance(val, (list, dict))}
        return rest or None
    return None


def set_site_ext(extend):
    """记录当前站点 ext；由各 Spider 的 init() 与 play_result() 调用"""
    global SITE_EXT
    e = parse_ext(extend)
    if e:
        SITE_EXT = e
    return e


def _root_paths(name):
    """包根目录里配置文件的候选位置（py/ 的上一级）"""
    out = []
    for env in ("TVBOX_LOCAL_DIR", "TVBOX_HOME"):
        v = os.environ.get(env)
        if v:
            out.append(os.path.join(v, name))
    try:
        out.append(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), name))
    except Exception:
        pass
    out += [name,
            os.path.join("/sdcard", "tvboxonly", name),
            os.path.join("/storage/emulated/0", "tvboxonly", name)]
    return out


def global_ext():
    """扫描 FongMi.json，取「配置中心」站点的 ext。
    认 __tvbox_config 标记或 key=tvbox_config；站点改名叫豆瓣也不影响识别。
    按 mtime+size 缓存，避免展开目录时反复读配置文件。
    """
    for p in _root_paths("FongMi.json"):
        try:
            st = os.stat(p)
            sig = (p, st.st_mtime_ns, st.st_size)
        except Exception:
            continue
        if _GLOBAL_CACHE["sig"] == sig:
            return _GLOBAL_CACHE["ext"]
        try:
            with open(p, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            continue
        ext = {}
        for s in cfg.get("sites") or []:
            if not isinstance(s, dict):
                continue
            e = s.get("ext")
            if isinstance(e, str):
                try:
                    e = json.loads(e) if e.strip().startswith("{") else {}
                except Exception:
                    e = {}
            if not isinstance(e, dict):
                continue
            if e.get("__tvbox_config") or str(s.get("key")) == "tvbox_config":
                ext = dict(e)
                break
        _GLOBAL_CACHE["sig"] = sig
        _GLOBAL_CACHE["ext"] = ext
        return ext
    return {}


def _pick(o, keys, kind):
    """从 ext 里取 panAccounts / panOptions。值可以是数组/对象、JSON 字符串，
    也可以是一个 http(s) 直链（由 _as_json_value 拉取并规整）。
    """
    if not isinstance(o, dict):
        return None
    empty = None
    for k in keys:
        if k not in o or o[k] is None:
            continue
        v = _as_json_value(o[k], kind)
        if v:
            return v
        # 默认模板里 panAccounts:[] / panOptions:{} 是空占位，
        # 不能挡住后面 panAccountsUrl / panOptionsUrl 这类直链键
        if v is not None and empty is None:
            empty = v
    return empty


def ext_config(o):
    """把一份 ext 解析成 (账号数组或 None, panOptions 覆盖项或 None)。
    支持 panConfigUrl 这种「一个直链同时给账号和选项」的整包配置。
    """
    if not isinstance(o, dict):
        return None, None
    pack = None
    for k in _CFG_KEYS:
        if k in o and o[k] is not None:
            pack = _raw_json(o[k])
            if isinstance(pack, dict):
                break
            pack = None
    a = _pick(o, _EXT_KEYS, "list")
    if not a and isinstance(pack, dict):
        a = _pick(pack, _EXT_KEYS, "list")
    ov = _pick(o, _OPT_KEYS, "dict")
    if not ov and isinstance(pack, dict):
        ov = _pick(pack, _OPT_KEYS, "dict")
        if not ov:
            rest = {k: v for k, v in pack.items()
                    if not k.startswith("__") and k not in _ALL_EXT_KEYS
                    and not isinstance(v, (list, dict))}
            ov = rest or None
    return a, ov


def ext_has_ref(o):
    """该 ext 里是否写了远程直链（拉取失败时用来决定要不要保留旧快照）"""
    if not isinstance(o, dict):
        return False
    return any(_is_http(o.get(k)) for k in _ALL_EXT_KEYS)


def _runtime_file():
    ps = _cfg_paths("pan_accounts.runtime.json")
    for p in ps:
        d = os.path.dirname(p)
        if d and os.path.isdir(d):
            return p
    return ps[0] if ps else ""


def sync_runtime(accounts, options):
    """配置中心站点被点开时调用：把 UI 编辑后的 ext 写成全局快照。
    accounts 为空则删除快照（回到文件通道），避免空快照把文件里的 Cookie 盖掉。
    """
    p = _runtime_file()
    if not p:
        return ""
    try:
        if not accounts:
            if os.path.exists(p):
                os.remove(p)
            return "removed"
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"__tvbox_runtime": True, "ts": int(time.time()),
                       "accounts": accounts, "options": options or {}},
                      f, ensure_ascii=False)
        _GLOBAL_CACHE["sig"] = None
        return "written"
    except Exception:
        return ""


def account_source():
    """→ (accounts 或 None, options 覆盖项, 来源标签)
    accounts 为 None 表示「没有外置配置，回退 json/pan_accounts.json」。
    """
    file_opt = load_cfg("pan_options.json", {})
    if not isinstance(file_opt, dict):
        file_opt = {}
    mode = str(file_opt.get("accountSource") or "auto").lower()
    if mode == "file":
        return None, {}, "文件(强制)"

    # ① 配置中心点开后写出的运行时快照（用户最近一次 UI 确认值，最高优先）
    rt = load_cfg("pan_accounts.runtime.json", None)
    if isinstance(rt, dict) and rt.get("__tvbox_runtime") and rt.get("accounts"):
        return (list(rt.get("accounts") or []),
                dict(rt.get("options") or {}), "配置中心(运行时)")
    # ② 当前站点自己的 ext（广播模式；也可能是远程直链）
    a, ov = ext_config(SITE_EXT)
    if a:
        if not ov:
            # 广播只写 panAccounts，panOptions 仍从配置中心站点取
            _, gv = ext_config(global_ext())
            ov = gv or {}
        return a, ov, "站点ext(广播)"
    # ③ FongMi.json 里配置中心站点的 ext（就地数组或远程直链）
    g = global_ext()
    a, ov = ext_config(g)
    if a:
        return a, ov or {}, "配置中心(FongMi.json)"
    # ④ 文件
    if mode == "ext":
        return [], {}, "仅ext(未配置)"
    return None, {}, "文件"


def _split_fid(u):
    """原 T4 播放串格式：base64("分享链接|文件fid")，fid 用于指定分享目录里的某一集"""
    s = str(u or "")
    if s.startswith("http") and "|" in s:
        a, b = s.split("|", 1)
        return a.strip(), b.strip()
    return s, ""


def _expand_rows(rows):
    """pan.list：配了 Cookie 且开启 expandShare 时，把一条分享链接展开成目录里的多个文件"""
    try:
        opts = pan_options()
        if not opts.get("expandShare"):
            return rows
    except Exception:
        return rows
    out = []
    for ep, u in rows:
        share, _ = _split_fid(u)
        d = detect(share)
        files = pan_list_files(d, share) if d else []
        if not files:
            out.append((ep, u))
            continue
        for f in files[:80]:
            name = re.sub(r"[#$\n\r]", " ", clean(f.get("name") or ""))[:70].strip()
            out.append((name or ep, share + "|" + str(f.get("fid") or "")))
    return out


def play_result(flag, id_, ext_raw=""):
    """播放（对齐 pan/index.js resolveCore 的降级顺序）：
       解 pan! → ① 账号 Cookie 换官方直链 → ② ext.parseApi → ③ 公共解析 → ④ parse:1 交回壳子
    """
    u = str(id_ or "").strip()
    set_site_ext(ext_raw)
    if u.startswith("pan!") or u.startswith("pan$"):
        u = pan_decode(u[4:]) or u
    elif re.match(r"^[A-Za-z0-9_-]{24,}$", u):
        # 少数壳子会把 pan! 前缀截断；裸 base64url 尝试还原（普通 URL 不会命中）
        dec = pan_decode(u)
        if dec.startswith("http"):
            u = dec
    if not u.startswith("http"):
        m = re.search(r"(https?://\S+)$", u)
        if m:
            u = m.group(1)
    share, fid = _split_fid(u)
    d = detect(share) or {}
    e = parse_ext(ext_raw)
    tip = ""

    # ① 账号 Cookie：TVBOX pan/drivers/*.js 的 REST 流程已移植进 pan_drivers.py
    try:
        account_first = pan_options().get("accountFirst", True)
    except Exception:
        account_first = True
    if account_first and d:
        r = pan_resolve(d, share, fid)
        if r and r.get("url"):
            out = {"parse": 0, "url": r["url"],
                   "header": r.get("header") or {"User-Agent": UA},
                   "extra": {"panType": d.get("type", ""), "via": "账号Cookie"}}
            if r.get("name"):
                out["extra"]["fileName"] = r["name"]
            return out
        if isinstance(r, dict) and r.get("error"):
            tip = "账号解析失败：" + str(r["error"])[:120]

    # ② 单个站点 ext 里单独指定的解析接口
    if e.get("parseApi"):
        r = _parse_with(share, d.get("type", ""),
                        [{"name": "ext", "url": str(e.get("parseApi"))}])
        if r:
            return r
    # ③ 公共解析
    r = public_parse(share, d.get("type", ""))
    if r:
        return r

    # ④ 兜底：分享链接 + Cookie/Referer 透传，交给壳子自带的网盘解析
    typ = d.get("type", "")
    hdr = {"User-Agent": UA}
    ref = {"quark": "https://pan.quark.cn/", "uc": "https://drive.uc.cn/",
           "aliyun": "https://www.alipan.com/", "baidu": "https://pan.baidu.com/",
           "115": "https://115.com/", "123": "https://yun.123pan.com/",
           "guangya": "https://www.guangyapan.com/"}.get(typ)
    if ref:
        hdr["Referer"] = ref
    ck = account_cookie(typ) if typ else ""
    if ck:
        hdr["Cookie"] = ck
    extra = {"panType": typ, "panName": d.get("name", ""), "pwd": d.get("pwd", "")}
    if fid:
        extra["fid"] = fid
    if tip:
        extra["tip"] = tip
    elif not ck:
        msg = ("未配置该网盘 Cookie，也没配公共解析："
               "在「配置中心」站点 ext 或 json/pan_accounts.json 填 Cookie")
        if _REF_STATE.get("url") and not _REF_STATE.get("ok"):
            msg = "远程直链 %s；%s" % (_REF_STATE["info"], msg)
        extra["tip"] = msg
    else:
        extra["tip"] = "该网盘类型无本地驱动，Cookie 已透传给壳子，需壳子自带解析"
    return {"parse": 1, "url": share, "header": hdr, "extra": extra}


def build_lines(rows, vod_name=""):
    """T4玩偶资源站.js: 详情按网盘类型分线路（百度网盘1 / 夸克网盘…）"""
    groups, order = {}, []
    for ep, u in _expand_rows(rows):
        share, _ = _split_fid(u)
        d = detect(share)
        if not d:
            continue
        typ = d["type"]
        if typ not in groups:
            groups[typ] = {"name": d["name"], "items": [], "seq": 0}
            order.append(typ)
        g = groups[typ]
        g["seq"] += 1
        label = ep or ("%s %02d" % (d["name"], g["seq"]))
        if d.get("pwd"):
            label = "%s 提取码:%s" % (label, d["pwd"])
        if vod_name and label.startswith(vod_name):
            label = label[len(vod_name):].lstrip(" -_—·") or label
        label = re.sub(r"[#$\n\r]", " ", clean(label))[:70].strip() or d["name"]
        g["items"].append("%s$pan!%s" % (label, pan_encode(u)))
    counts = {}
    for t in order:
        counts[t] = counts.get(t, 0) + 1
    froms, urls, seq = [], [], {}
    for t in order:
        g = groups[t]
        if not g["items"]:
            continue
        seq[t] = seq.get(t, 0) + 1
        label = "%s%s(%d)" % (g["name"], str(seq[t]) if counts.get(t, 1) > 1 else "",
                              len(g["items"]))
        froms.append(label)
        urls.append("#".join(g["items"]))
    return "$$$".join(froms), "$$$".join(urls)


def _parse_with(share_url, pan_type, cfg):
    """用给定的解析配置执行一次（供 ext.parseApi 使用）"""
    q = urllib.parse.quote(share_url, safe="")
    for p in cfg:
        tpl = str(p.get("url") or "")
        if not tpl:
            continue
        u = tpl.replace("{url}", q) if "{url}" in tpl else tpl + q
        try:
            t = (http_get(u, timeout=12) or "").strip()
            if re.match(r"^https?://", t):
                return {"parse": 0, "url": t, "header": {"User-Agent": UA}}
            if t.startswith("{"):
                d = json.loads(t)
                for k in ("url", "play_url", "link"):
                    v = d.get(k)
                    if isinstance(v, str) and v.startswith("http"):
                        return {"parse": 0, "url": v, "header": {"User-Agent": UA}}
        except Exception:
            continue
    return None


# -*- coding: utf-8 -*-
"""
TVBOX 本地包 / 网盘账号与直链解析
------------------------------------------------------------------
本文件全部移植自 TVBOX (7).zip 自身的 pan/ 目录，没有引入任何其它包的内容：
  pan/store.js               账号结构 data/pan_accounts.json（type/cookie/data/enabled）
  pan/index.js               resolveCore：账号优先 → 公共解析 → parse:1
  pan/drivers/quark.js       sharepage/token → sharepage/detail → file/download
  pan/drivers/uc.js          同源 UC 接口（pc-api.uc.cn）
  pan/drivers/aliyun.js      refresh_token → 匿名分享 → 预览/下载直链
  pan/drivers/pan123.js      CRC32 签名 → 登录 → share/get → share/download/info
  pan/drivers/pan115.js      m115 RSA 加密 → webapi 列分享 → share/downurl 直链
  pan/drivers/baidu.js       DLNA 签名免转存直链 / share/transfer → filemetas 直链
115 的 RSA 与「转存 → pickcode → chrome/downurl」备用链路均为纯标准库复刻，
已与原包 pan115.js 做加密输出与解密字节的交叉校验。
只依赖 Python 标准库，可在 TVBox / FongMi 系壳子的 Python Spider 引擎中运行。

对外接口（供 common.py 调用）：
  pick_account(typ)                  取某类型的第一个可用账号
  account_cookie(typ)                取 Cookie 原文（兜底时透传给壳子）
  pan_resolve(info, url, fid)        Cookie 换直链 → {url, header, name} / None
  pan_list_files(info, url)          列分享目录 → [{fid, name}]（展开多集用）

目前只有 guangya / Thunder 没有本地直链驱动（原包光鸭驱动依赖 JWT 轮换 +
转存任务轮询，迅雷原包本无驱动），这两类保留账号位，播放时把 Cookie
透传到播放响应 header。
"""
import base64
import hashlib
import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

QUARK_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) quark-cloud-drive/2.5.20 "
            "Chrome/100.0.4896.160 Electron/18.3.5.4-b478491100 "
            "Safari/537.36 Channel/pckk_other_ch")

VIDEO_RE = re.compile(
    r"\.(mp4|mkv|avi|mov|wmv|flv|webm|m3u8|ts|rmvb|mpg|mpeg|m4v|iso)(\?|$)", re.I)
BIG_FILE = 100 * 1024 * 1024

# pan/drivers/quark.js + uc.js 同源接口
CD = {
    "quark": {"host": "https://drive-pc.quark.cn", "pr": "ucpro", "fr": "pc",
              "referer": "https://pan.quark.cn/", "origin": "https://pan.quark.cn",
              "ua": QUARK_UA},
    "uc": {"host": "https://pc-api.uc.cn", "pr": "UCBrowser", "fr": "pc",
           "referer": "https://drive.uc.cn/", "origin": "https://drive.uc.cn",
           "ua": None},
}
# pan/drivers/pan123.js 的 SIGN_TABLE
SIGN_TABLE = "adefghlyijmnopkqrsubcvwsz"
B123_API = "https://yun.123pan.com/b/api"

SUPPORTED = ("quark", "uc", "aliyun", "123", "115", "baidu")


# ---------------------------------------------------------------- HTTP / Cookie
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """DLNA / 百度 dlink 需要读 302 的 Location，而不是自动跳到 CDN"""


    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http_raw(url, method="GET", body=None, headers=None, timeout=15,
             form=False, follow=True):
    """返回 (text, headers, status, final_url)；headers['Set-Cookie'] 是列表。
    body 为 dict/list → JSON，str/bytes → 原样（form=True 时按表单提交）。
    115 / 百度驱动需要 HTML 响应、Set-Cookie 与 302 Location，故单独实现。
    """
    h = {"User-Agent": UA, "Accept": "application/json, text/plain, */*",
         "Accept-Language": "zh-CN,zh;q=0.9"}
    data = None
    if isinstance(body, (dict, list)):
        data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        h["Content-Type"] = "application/json"
    elif isinstance(body, str):
        data = body.encode("utf-8")
        if form:
            h["Content-Type"] = "application/x-www-form-urlencoded"
    elif isinstance(body, bytes):
        data = body
        if form:
            h["Content-Type"] = "application/x-www-form-urlencoded"
    if headers:
        h.update({str(k): str(v) for k, v in headers.items() if v not in (None, "")})
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    handlers = []
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        handlers.append(urllib.request.HTTPSHandler(context=ctx))
    except Exception:
        pass
    if not follow:
        handlers.insert(0, _NoRedirect())
    opener = urllib.request.build_opener(*handlers) if handlers \
        else urllib.request.build_opener()
    try:
        r = opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        r = e
    except Exception as e:
        raise RuntimeError(str(e))
    with r:
        raw = r.read()
        try:
            sc = r.headers.get_all("Set-Cookie") or []
        except Exception:
            sc = []
        ce = str(r.headers.get("Content-Encoding", ""))
        hd = {"Set-Cookie": sc, "Location": r.headers.get("Location", ""),
              "Content-Type": r.headers.get("Content-Type", "")}
        status = int(getattr(r, "code", 200) or 200)
        final = r.geturl() if hasattr(r, "geturl") else url
    if "gzip" in ce.lower():
        try:
            import gzip
            raw = gzip.decompress(raw)
        except Exception:
            pass
    return raw.decode("utf-8", "ignore"), hd, status, final


def raw_json(*args, **kwargs):
    txt, hd, status, final = http_raw(*args, **kwargs)
    try:
        return json.loads(txt), hd, status, final
    except Exception:
        return {}, hd, status, final


def _deep_url(obj, keys=None):
    """递归找响应里的 http 直链（115 chrome/downurl、百度 DLNA 都用得上）"""
    if keys is None:
        keys = ("url", "dlink", "download_url", "downloadurl")
    if isinstance(obj, str):
        return obj if obj.startswith("http") else ""
    if isinstance(obj, list):
        for v in obj:
            hit = _deep_url(v, keys)
            if hit:
                return hit
        return ""
    if isinstance(obj, dict):
        for k in keys:
            v = obj.get(k)
            if isinstance(v, str) and v.startswith("http"):
                return v
            if isinstance(v, dict):
                hit = _deep_url(v, keys)
                if hit:
                    return hit
        for v in obj.values():
            hit = _deep_url(v, keys)
            if hit:
                return hit
    return ""


def http_json(url, method="GET", body=None, headers=None, timeout=15):
    """urllib 版 axios：返回 (dict, Set-Cookie 列表)；HTTP 错误带出业务 message"""
    h = {"User-Agent": UA, "Accept": "application/json, text/plain, */*",
         "Content-Type": "application/json"}
    if headers:
        h.update({str(k): str(v) for k, v in headers.items() if v not in (None, "")})
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    kw = {"timeout": timeout}
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kw["context"] = ctx
    except Exception:
        pass
    try:
        r = urllib.request.urlopen(req, **kw)
    except Exception as e:
        raw = b""
        try:
            raw = e.read()
        except Exception:
            pass
        txt = raw.decode("utf-8", "ignore")
        msg = ""
        try:
            j = json.loads(txt)
            msg = str(j.get("message") or j.get("error") or "")
        except Exception:
            pass
        raise RuntimeError(msg or str(e))
    with r:
        raw = r.read()
        if "gzip" in str(r.headers.get("Content-Encoding", "")).lower():
            try:
                import gzip
                raw = gzip.decompress(raw)
            except Exception:
                pass
        try:
            sc = r.headers.get_all("Set-Cookie") or []
        except Exception:
            sc = []
    txt = raw.decode("utf-8", "ignore")
    try:
        return json.loads(txt), sc
    except Exception:
        return {}, sc


def _cookie_kv(cookie):
    jar = {}
    for seg in str(cookie or "").split(";"):
        seg = seg.strip()
        if "=" in seg:
            k, v = seg.split("=", 1)
            if k.strip():
                jar[k.strip()] = v.strip()
    return jar


def _merge(jar, setcookies):
    """quark.js collectSetCookie：把响应里的 Set-Cookie 并回 Cookie jar"""
    for line in setcookies or []:
        kv = str(line).split(";")[0]
        if "=" in kv:
            k, v = kv.split("=", 1)
            if k.strip():
                jar[k.strip()] = v.strip()
    return jar


def _cookie_header(jar):
    return "; ".join("%s=%s" % (k, v) for k, v in jar.items())


def _qs(base, params):
    return base + "?" + urllib.parse.urlencode(params)


# ---------------------------------------------------------------- 账号
def load_accounts():
    """账号来源：站点 ext（含配置中心 / 广播 / runtime 快照）优先，回退 json 文件。
    具体优先级见 common.py 的 account_source()。
    """
    try:
        src, _ov, _label = account_source()
    except Exception:
        src = None
    cfg = load_cfg("pan_accounts.json", []) if src is None else src
    if isinstance(cfg, dict):
        cfg = cfg.get("accounts") or []
    if not isinstance(cfg, list):
        return []
    return [a for a in cfg
            if isinstance(a, dict) and a.get("enabled") is not False
            and str(a.get("cookie") or "").strip()]


def pick_account(typ):
    t = str(typ or "").lower()
    for a in load_accounts():
        if str(a.get("type") or "").strip().lower() == t:
            return a
    return None


def account_cookie(typ):
    a = pick_account(typ)
    return str(a.get("cookie") or "") if a else ""


def pan_options():
    """文件里的值作默认，外置 ext 的 panOptions 逐项覆盖。
    accountSource="file" 时完全忽略外置项。
    """
    base = load_cfg("pan_options.json", {})
    if not isinstance(base, dict):
        base = {}
    if str(base.get("accountSource") or "auto").lower() == "file":
        return base
    try:
        _src, ov, _label = account_source()
    except Exception:
        ov = {}
    if ov:
        merged = dict(base)
        merged.update(ov)
        return merged
    return base


# ---------------------------------------------------------------- 夸克 / UC
def _cd_session(cfg, cookie, share_id, pwd):
    """drivers/quark.js shareToken / drivers/uc.js shareToken"""
    jar = _cookie_kv(cookie)
    body = {"pwd_id": share_id, "password": pwd or ""}
    if cfg["pr"] == "ucpro":
        body.update({"passcode": pwd or "", "share_for_transfer": True})
    hdr = {"Cookie": cookie, "Referer": cfg["referer"], "Origin": cfg["origin"]}
    d, sc = http_json(_qs(cfg["host"] + "/1/clouddrive/share/sharepage/token",
                          {"pr": cfg["pr"], "fr": cfg["fr"]}), "POST", body, hdr,
                      timeout=pan_options().get("timeout", 15))
    _merge(jar, sc)
    dd = d.get("data") or {}
    stoken = dd.get("stoken") or dd.get("share_token") or ""
    if not stoken:
        raise RuntimeError(str(d.get("message") or "获取分享 token 失败，Cookie 可能已失效"))
    return jar, stoken, str(dd.get("share_id") or share_id)


def _cd_detail(cfg, jar, share_id, stoken, pdir, page):
    """drivers/quark.js shareDetail：详情接口必须 GET，POST 会 405"""
    p = {"pr": cfg["pr"], "fr": cfg["fr"], "pwd_id": share_id, "stoken": stoken,
         "pdir_fid": pdir, "_page": page, "_size": 50, "_fetch_total": 1,
         "_fetch_share": 1, "sort": "file_type:asc,size:desc", "_sub": "1", "fugle": "1"}
    hdr = {"Cookie": _cookie_header(jar), "Referer": cfg["referer"]}
    d, sc = http_json(_qs(cfg["host"] + "/1/clouddrive/share/sharepage/detail", p),
                      "GET", None, hdr, timeout=pan_options().get("timeout", 15))
    _merge(jar, sc)
    return (d.get("data") or {}).get("list") or []


def _normalize(files):
    """drivers/quark.js pickVideoFiles"""
    out = []
    for f in files or []:
        if not isinstance(f, dict):
            continue
        isdir = bool(f.get("dir")) or str(f.get("file_type", f.get("type", ""))) == "0" \
            or str(f.get("obj_category") or "") == "0"
        out.append({
            "fid": str(f.get("fid") or f.get("file_id") or f.get("id") or ""),
            "name": str(f.get("file_name") or f.get("filename") or f.get("name") or ""),
            "size": f.get("size") or 0,
            "token": str(f.get("share_fid_token") or f.get("fid_token") or ""),
            "pdir": str(f.get("pdir_fid") or "0"),
            "isdir": isdir,
        })
    vids = [x for x in out if VIDEO_RE.search(x["name"])
            or (not x["isdir"] and int(x["size"] or 0) >= BIG_FILE)]
    if not vids:
        vids = [x for x in out if not x["isdir"]]
    return vids, out


def _cd_files(cfg, jar, share_id, sid, stoken, depth=0, pdir="0"):
    """drivers/quark.js findVideos：分页 + 最多 3 层子目录"""
    allfiles = []
    for page in range(1, 6):
        lst = _cd_detail(cfg, jar, share_id, stoken, pdir, page)
        allfiles.extend(lst)
        if len(lst) < 50:
            break
    vids, raw = _normalize(allfiles)
    if depth < 3:
        for d in [x for x in raw if x["isdir"] and x["fid"]][:5]:
            vids.extend(_cd_files(cfg, jar, share_id, sid, stoken, depth + 1, d["fid"]))
            if len(vids) >= 200:
                break
    return vids[:200]


def _cd_download(cfg, jar, share_id, sid, stoken, item):
    """drivers/quark.js fileDownload / drivers/uc.js fileDownload"""
    body = {"fids": [item["fid"]], "resolve": "1", "_ts": int(time.time() * 1000),
            "_prd": "", "pdir_fid": "0", "_scope": "public", "_platform": "web",
            "pwd_id": sid or share_id, "share_id": sid or share_id,
            "stoken": stoken, "share_token": stoken}
    if item.get("token"):
        body["fids_token"] = [item["token"]]
    hdr = {"Cookie": _cookie_header(jar), "Referer": cfg["referer"]}
    if cfg.get("ua"):
        hdr["User-Agent"] = cfg["ua"]
    d, sc = http_json(_qs(cfg["host"] + "/1/clouddrive/file/download",
                          {"pr": cfg["pr"], "fr": cfg["fr"]}), "POST", body, hdr,
                      timeout=pan_options().get("timeout", 15))
    _merge(jar, sc)
    data = d.get("data")
    first = data[0] if isinstance(data, list) and data else data
    if not isinstance(first, dict):
        first = {}
    return first.get("download_url") or first.get("url") or d.get("download_url") or "", jar


def _cd_resolve(typ, info, fid, acc):
    cfg = CD[typ]
    jar, stoken, sid = _cd_session(cfg, str(acc.get("cookie") or ""),
                                   info["share_id"], info.get("pwd") or "")
    files = _cd_files(cfg, jar, info["share_id"], sid, stoken)
    if not files:
        return None
    target = files[0]
    if fid:
        for x in files:
            if x["fid"] == str(fid):
                target = x
                break
    url, jar = _cd_download(cfg, jar, info["share_id"], sid, stoken, target)
    if not url:
        return None
    return {"url": url, "name": target["name"],
            "header": {"User-Agent": UA, "Referer": cfg["referer"],
                       "Cookie": _cookie_header(jar)}}


def _cd_list_public(typ, info, acc):
    cfg = CD[typ]
    jar, stoken, sid = _cd_session(cfg, str(acc.get("cookie") or ""),
                                   info["share_id"], info.get("pwd") or "")
    return [{"fid": x["fid"], "name": x["name"]} for x in
            _cd_files(cfg, jar, info["share_id"], sid, stoken)]


# ---------------------------------------------------------------- 阿里云盘
def _ali_creds(acc):
    """drivers/aliyun.js extractToken"""
    data = acc.get("data") or {}
    if data.get("refresh_token"):
        return str(data["refresh_token"])
    cookie = str(acc.get("cookie") or "")
    m = re.search(r"(?:^|;\s*)refresh_token=([^;]+)", cookie) or \
        re.search(r"(?:^|;\s*)token=([^;]+)", cookie)
    if m:
        return urllib.parse.unquote(m.group(1))
    return cookie if cookie and "=" not in cookie else ""


def _ali_client_headers(token):
    return {"User-Agent": UA, "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token if token else "",
            "x-device-id": "tvbox_local_01", "Origin": "https://www.alipan.com",
            "Referer": "https://www.alipan.com/"}


def _ali_resolve(info, fid, acc, list_only=False):
    rt = _ali_creds(acc)
    if not rt:
        return None
    d, _ = http_json("https://auth.aliyundrive.com/v2/account/token", "POST",
                     {"refresh_token": rt, "grant_type": "refresh_token"},
                     _ali_client_headers(""), timeout=pan_options().get("timeout", 15))
    at = d.get("access_token") or ""
    if not at:
        raise RuntimeError(str(d.get("message") or "阿里 refresh_token 已失效"))
    h = _ali_client_headers(at)
    s, _ = http_json("https://api.aliyundrive.com/adrive/v3/share_link/get_share_by_anonymous",
                     "POST", {"share_id": info["share_id"]}, h,
                     timeout=pan_options().get("timeout", 15))
    root = s.get("file_id") or s.get("share_file_id") or s.get("root_file_id")
    if not root:
        raise RuntimeError(str(s.get("message") or "获取阿里分享信息失败"))
    r, _ = http_json("https://api.aliyundrive.com/adrive/v3/file/list_share_files",
                     "POST", {"share_id": info["share_id"], "parent_file_id": root,
                              "limit": 100}, h, timeout=pan_options().get("timeout", 15))
    items = r.get("items") or r.get("files") or []
    vids = [f for f in items
            if isinstance(f, dict) and f.get("type") == "file"
            and VIDEO_RE.search(str(f.get("name") or ""))]
    if not vids:
        vids = [f for f in items if isinstance(f, dict) and f.get("type") == "file"]
    if not vids:
        raise RuntimeError("阿里分享中未找到可播放文件")
    target = vids[0]
    if fid:
        for f in vids:
            if str(f.get("file_id") or "") == str(fid):
                target = f
                break
    if list_only:
        return [{"fid": str(f.get("file_id") or ""), "name": str(f.get("name") or "")}
                for f in vids]
    try:
        p, _ = http_json(
            "https://api.aliyundrive.com/v2/file/get_share_link_video_preview_play_info",
            "POST", {"share_id": info["share_id"], "file_id": target.get("file_id"),
                     "access_token": at, "expire_sec": 3600}, h,
            timeout=pan_options().get("timeout", 15))
        tasks = (p.get("video_preview_play_info") or {}).get("live_transcoding_task_list") or []
        tasks = [t for t in tasks if isinstance(t, dict) and (t.get("url") or "")]
        if tasks:
            tasks.sort(key=lambda t: int(t.get("height") or 0), reverse=True)
            return {"url": tasks[0]["url"], "name": str(target.get("name") or ""),
                    "header": {"User-Agent": UA, "Referer": "https://www.alipan.com/"}}
    except Exception:
        pass
    dl, _ = http_json("https://api.aliyundrive.com/v2/file/get_download_url", "POST",
                      {"share_id": info["share_id"], "file_id": target.get("file_id"),
                       "expire_sec": 3600}, h, timeout=pan_options().get("timeout", 15))
    url = dl.get("url") or ""
    if not url:
        return None
    return {"url": url, "name": str(target.get("name") or ""),
            "header": {"User-Agent": UA, "Referer": "https://www.alipan.com/"}}


# ---------------------------------------------------------------- 123 网盘
def _sign_path(path):
    """drivers/pan123.js signPath：CST(UTC+8) 分钟串 + CRC32"""
    now = time.time() + 8 * 3600
    t = time.gmtime(now)
    nowstr = "%04d%02d%02d%02d%02d" % (t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min)
    mapped = "".join(SIGN_TABLE[ord(c) - 48] for c in nowstr)
    ts = str(int(now))
    rnd = str(int(time.time() * 1000) % 100000000)
    time_sign = str(zlib.crc32(mapped.encode("utf-8")) & 0xffffffff)
    raw = "|".join([ts, rnd, path, "web", "3", time_sign])
    data_sign = str(zlib.crc32(raw.encode("utf-8")) & 0xffffffff)
    return time_sign, "%s-%s-%s" % (ts, rnd, data_sign)


def _123_sign(url, extra=None):
    u = urllib.parse.urlsplit(url)
    q = dict(urllib.parse.parse_qsl(u.query))
    q.update({str(k): str(v) for k, v in (extra or {}).items()})
    k, v = _sign_path(u.path)
    q[k] = v
    return urllib.parse.urlunsplit((u.scheme, u.netloc, u.path,
                                    urllib.parse.urlencode(q), u.fragment))


def _123_creds(acc):
    """drivers/pan123.js creds：username/password 或 token / 裸 token"""
    raw = str(acc.get("cookie") or "").strip()
    data = acc.get("data") or {}
    if raw and "=" not in raw:
        raw = "token=" + raw
    kv = _cookie_kv(raw)
    return {
        "username": kv.get("username") or kv.get("passport") or kv.get("mail")
                    or data.get("username") or "",
        "password": kv.get("password") or data.get("password") or "",
        "token": kv.get("token") or kv.get("access_token") or data.get("token") or "",
    }


def _123_token(acc):
    c = _123_creds(acc)
    if c["token"]:
        return c["token"]
    if c["username"] and c["password"]:
        is_mail = bool(re.match(r"^[^@]+@[^@]+\.[^@]+$", c["username"]))
        body = ({"mail": c["username"], "password": c["password"], "type": 2}
                if is_mail else
                {"passport": c["username"], "password": c["password"], "remember": True})
        d, _ = http_json("https://login.123pan.com/api/user/sign_in", "POST", body,
                         {"User-Agent": UA, "Origin": "https://yun.123pan.com",
                          "Referer": "https://yun.123pan.com/", "platform": "web",
                          "app-version": "3"}, timeout=pan_options().get("timeout", 15))
        if int(d.get("code") or 0) != 200:
            raise RuntimeError(str(d.get("message") or "123 登录失败"))
        return ((d.get("data") or {}).get("token") or "")
    return ""


def _123_headers(token):
    return {"User-Agent": UA, "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json", "Origin": "https://yun.123pan.com",
            "Referer": "https://yun.123pan.com/", "platform": "web",
            "app-version": "3", "Authorization": "Bearer " + token}


def _123_files(info, token, parent="0", depth=0):
    h = _123_headers(token)
    out = []
    for page in range(1, 6):
        d, _ = http_json(_123_sign(B123_API + "/share/get", {
            "limit": 100, "next": 0, "orderBy": "file_id", "orderDirection": "desc",
            "parentFileId": parent, "Page": page, "shareKey": info["share_id"],
            "SharePwd": info.get("pwd") or ""}), "GET", None, h,
            timeout=pan_options().get("timeout", 15))
        dd = d.get("data") or {}
        lst = dd.get("InfoList") or []
        out.extend(lst)
        if not lst or str(dd.get("Next")) == "-1":
            break
    vids = [f for f in out if isinstance(f, dict) and str(f.get("Type")) == "0"
            and VIDEO_RE.search(str(f.get("FileName") or ""))]
    if not vids:
        vids = [f for f in out if isinstance(f, dict) and str(f.get("Type")) == "0"]
    if not vids and depth < 3:
        for d in [f for f in out if isinstance(f, dict) and str(f.get("Type")) == "1"][:5]:
            vids.extend(_123_files(info, token, str(d.get("FileId") or ""), depth + 1))
    return vids[:200]


def _123_resolve(info, fid, acc, list_only=False):
    token = _123_token(acc)
    if not token:
        return None
    files = _123_files(info, token)
    if not files:
        return None
    target = files[0]
    if fid:
        for f in files:
            if str(f.get("FileId") or "") == str(fid):
                target = f
                break
    if list_only:
        return [{"fid": str(f.get("FileId") or ""), "name": str(f.get("FileName") or "")}
                for f in files]
    d, _ = http_json(_123_sign(B123_API + "/share/download/info"), "POST", {
        "shareKey": info["share_id"], "SharePwd": info.get("pwd") or "",
        "etag": target.get("Etag") or "", "fileId": target.get("FileId"),
        "s3keyFlag": target.get("S3KeyFlag") or "", "size": target.get("Size") or 0,
    }, _123_headers(token), timeout=pan_options().get("timeout", 15))
    url = (d.get("data") or {}).get("DownloadURL") or (d.get("data") or {}).get("DownloadUrl") or ""
    if not url:
        return None
    return {"url": url, "name": str(target.get("FileName") or ""),
            "header": {"User-Agent": UA, "Referer": "https://yun.123pan.com/"}}


# ---------------------------------------------------------------- 115 网盘
# pan/drivers/pan115.js 的 m115 加密（模数/指数/密钥表/异或流程），
# 纯标准库复刻，已与原包 pan115.js 做加密/解密字节级交叉校验。
P115_MOD = int(
    "8686980c0f5a24c4b9d43020cd2c22703ff3f450756529058b1cf88f09b86021"
    "36477198a6e2683149659bd122c33592fdb5ad47944ad1ea4d36c6b172aad633"
    "8c3bb6ac6227502d010993ac967d1aef00f0c8e038de2e4d3bc2ec368af2e9f1"
    "0a6f1eda4f7262f136420c07c331b871bf139f74f3010e3c4fe57df3afb71683", 16)
P115_EXP = 0x10001
P115_KTS = bytes([
    240, 229, 105, 174, 191, 220, 191, 138,  26,  69, 232, 190,
    125, 166, 115, 184, 222, 143, 231, 196,  69, 218, 134, 196,
    155, 100, 139,  20, 106, 180, 241, 170,  56,   1,  53, 158,
     38, 105,  44, 134,   0, 107,  79, 165,  54,  52,  98, 166,
     42, 150, 104,  24, 242,  74, 253, 189, 107, 151, 143,  77,
    143, 137,  19, 183, 108, 142, 147, 237,  14,  13,  72,  62,
    215,  47, 136, 216, 254, 254, 126, 134,  80, 149,  79, 209,
    235,  131,  38,  52, 219, 102, 123, 156, 126, 157, 122, 129,
     50, 234, 182,  51, 222,  58, 169,  89,  52, 102,  59, 170,
    186, 129,  96,  72, 185, 213, 129, 156, 248, 108, 132, 119,
    255,  84, 120,  38,  95, 190, 232,  30,  54, 159,  52, 128,
     92,  69,  44, 155, 118, 213,  27, 143, 204, 195, 184, 245,
])
P115_XOR_A = bytes([0x8d, 0xa5, 0xa5, 0x8d])
P115_XOR_B = bytes([0x78, 0x06, 0xad, 0x4c, 0x33, 0x86, 0x5d, 0x18,
                    0x4c, 0x01, 0x3f, 0x46])


def _p115_b2i(b):
    v = 0
    for x in b:
        v = (v << 8) | x
    return v


def _p115_i2b(v, length=None):
    if length is None:
        length = max(1, (v.bit_length() + 7) // 8)
    out = bytearray(length)
    for i in range(length - 1, -1, -1):
        out[i] = v & 0xFF
        v >>= 8
    return bytes(out)


def _p115_xor(src, key):
    out = bytearray(len(src))
    off = len(src) & 3
    if off:
        for i in range(off):
            out[i] = src[i] ^ key[i]
    i = off
    while i < len(src):
        j = min(i + len(key), len(src))
        for k in range(i, j):
            out[k] = src[k] ^ key[k - i]
        i = j
    return bytes(out)


def _p115_modpow(b, e, m):
    if m == 1:
        return 0
    r = 1
    b %= m
    while e:
        if e & 1:
            r = (r * b) % m
        e >>= 1
        b = (b * b) % m
    return r


def _p115_pad(msg):
    """pan115.js padPkcs1V15：0x00 | 0x02 填充 | 消息"""
    buf = bytearray(128)
    end = 127 - len(msg)
    for i in range(1, max(1, end)):
        buf[i] = 2
    buf[128 - len(msg):128] = msg
    return _p115_b2i(bytes(buf))


def _p115_key(seed, sklen=12):
    """pan115.js genKey115 / G_KTS"""
    out = bytearray(sklen)
    n = sklen * (sklen - 1)
    s = 0
    for i in range(sklen):
        out[i] = P115_KTS[n] ^ ((seed[i] + P115_KTS[s]) & 0xFF)
        n -= sklen
        s += sklen
    return bytes(out)


def p115_encrypt(obj):
    """m115 加密：异或 → 反转 → 异或 → 16 字节种子 → 分块 117 → 公钥模幂 → base64"""
    raw = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    x = _p115_xor(_p115_xor(raw, P115_XOR_A)[::-1], P115_XOR_B)
    padded = bytes(16) + x
    out = bytearray()
    for i in range(0, len(padded), 117):
        out.extend(_p115_i2b(
            _p115_modpow(_p115_pad(padded[i:i + 117]), P115_EXP, P115_MOD), 128))
    return base64.b64encode(bytes(out)).decode("ascii")


def p115_decrypt(b64):
    """m115 解密：分块 128 → 模幂 → 去 0x00 → 种子换 key → 反转 → 异或"""
    try:
        raw = base64.b64decode(b64)
        merged = bytearray()
        for i in range(0, len(raw), 128):
            dec = _p115_i2b(_p115_modpow(_p115_b2i(raw[i:i + 128]),
                                         P115_EXP, P115_MOD))
            idx = dec.find(b"\x00")
            merged.extend(dec[idx + 1:] if idx >= 0 else dec)
        if len(merged) < 16:
            return {}
        key = _p115_key(bytes(merged[:16]), 12)
        body = _p115_xor(bytes(merged[16:]), key)[::-1]
        plain = _p115_xor(body, P115_XOR_A)
        return json.loads(plain.decode("utf-8"))
    except Exception:
        return {}


def _p115_headers(cookie, referer="https://115.com/"):
    return {"User-Agent": UA, "Referer": referer, "Origin": "https://115.com",
            "Cookie": cookie, "Accept": "application/json, text/plain, */*"}


def _115_timeout():
    try:
        return max(6, min(int(pan_options().get("timeout", 15)), 30))
    except Exception:
        return 15


def _115_snap(code, pwd, cid, cookie="", pro=False):
    """pan115.js fetchShareList115（webapi 公开列目录）/ 登录态 proapi 变体"""
    if pro:
        url = "https://proapi.115.com/android/2.0/share/snap"
        p = {"share_code": code, "receive_code": pwd or "", "offset": 0,
             "limit": 200, "cid": str(cid or "")}
        hdr = _p115_headers(cookie)
    else:
        url = "https://webapi.115.com/share/snap"
        p = {"share_code": code, "receive_code": pwd or "", "cid": str(cid or ""),
             "limit": 100, "asc": 0, "offset": 0, "format": "json"}
        hdr = {"User-Agent": UA, "Accept": "application/json;charset=UTF-8",
               "Referer": "https://115cdn.com/s/%s?password=%s&" % (code, pwd or "")}
        if cookie:
            hdr["Cookie"] = cookie
    d, _, _, _ = raw_json(_qs(url, p), "GET", None, hdr, timeout=_115_timeout())
    if d.get("state") is False or (d.get("errno") not in (None, 0)
                                   and d.get("errno") is not None):
        raise RuntimeError(str(d.get("error") or d.get("msg") or
                               "115 分享列表获取失败(errno=%s)" % d.get("errno")))
    data = d.get("data") or {}
    if str(data.get("share_state") or "") == "7":
        raise RuntimeError(str((data.get("shareinfo") or {}).get("forbid_reason")
                               or "115 分享链接已过期"))
    return data


def _115_files(info, cookie="", pro=False, max_files=200):
    """列分享目录里的视频；cid 先试 shareCode，再兜底 0（对齐原包）"""
    code = str(info.get("share_id") or "")
    pwd = str(info.get("pwd") or "")
    out = []
    for root in (code, "0"):
        stack, visited = [(root, 0)], set()
        while stack and len(out) < max_files:
            cid, depth = stack.pop()
            if depth > 3 or (cid, depth) in visited:
                continue
            visited.add((cid, depth))
            try:
                data = _115_snap(code, pwd, cid, cookie, pro)
            except Exception:
                continue
            for f in data.get("list") or []:
                if not isinstance(f, dict):
                    continue
                fid = str(f.get("fid") or f.get("file_id") or "")
                name = str(f.get("n") or f.get("fn") or f.get("name") or fid)
                fc = str(f.get("fc") or "")
                isdir = fc == "0" or (not fid and bool(f.get("cid")))
                if isdir:
                    sub = str(f.get("cid") or f.get("fid") or "")
                    if sub and depth < 3:
                        stack.append((sub, depth + 1))
                    continue
                if fid:
                    out.append({"fid": fid, "name": name,
                                "size": f.get("s") or f.get("fs") or 0})
        if out:
            break
    vids = [f for f in out if VIDEO_RE.search(f["name"])]
    return (vids or out)[:max_files]


def _115_pick(files, fid):
    if not files:
        raise RuntimeError("115 分享中未找到视频文件（链接失效或访问码不对）")
    if fid:
        for f in files:
            if f["fid"] == str(fid):
                return f
    return files[0]


def _115_share_resolve(info, fid, acc):
    """主路径（pan115.js）：公开列目录 → m115 加密 share/downurl → 直链，免转存"""
    cookie = str(acc.get("cookie") or "")
    target = _115_pick(_115_files(info, "", pro=False), fid)
    body = "data=" + urllib.parse.quote(p115_encrypt({
        "share_code": str(info.get("share_id") or ""),
        "receive_code": str(info.get("pwd") or ""),
        "file_id": target["fid"]}), safe="")
    hdr = {"Content-Type": "application/x-www-form-urlencoded",
           "Cookie": cookie, "User-Agent": UA, "Accept": "application/json"}
    last = ""
    for url in ("http://pro.api.115.com/app/share/downurl",
                "https://proapi.115.com/app/share/downurl"):
        try:
            d, _, _, _ = raw_json(url, "POST", body, hdr,
                                  timeout=_115_timeout(), form=True)
            if d.get("state") is False:
                last = str(d.get("msg") or d.get("error") or "")
                if "登录" in last or "登陆" in last:
                    raise RuntimeError("115 Cookie 已失效，请重新登录 115.com 复制完整 Cookie")
                continue
            enc = d.get("data")
            inner = p115_decrypt(enc) if isinstance(enc, str) else \
                (enc if isinstance(enc, dict) else {})
            real = _deep_url(inner)
            if real:
                return {"url": real, "name": target["name"],
                        "header": {"User-Agent": UA, "Referer": "https://115.com/",
                                   "Cookie": cookie}}
            last = "115 未返回直链（%s）" % str(d.get("msg") or d.get("errno") or "响应异常")
        except RuntimeError as e:
            last = str(e)
    raise RuntimeError("115 分享直链失败：%s" % (last or "接口无响应"))


def _115_folder(cookie, name):
    p = {"aid": 1, "cid": 0, "o": "user_ptime", "asc": 0, "offset": 0,
         "show_dir": 1, "limit": 200, "type": 0, "format": "json"}
    try:
        d, _, _, _ = raw_json(_qs("https://webapi.115.com/files", p), "GET", None,
                              _p115_headers(cookie), timeout=_115_timeout())
        for it in d.get("data") or []:
            if isinstance(it, dict) and str(it.get("n") or it.get("name") or "") == name:
                return str(it.get("cid") or it.get("fid") or "")
    except Exception:
        pass
    return ""


def _115_create_folder(cookie, name):
    body = urllib.parse.urlencode({"cname": name, "pid": 0})
    hdr = _p115_headers(cookie)
    hdr["Content-Type"] = "application/x-www-form-urlencoded"
    try:
        d, _, _, _ = raw_json("https://webapi.115.com/files/add", "POST", body, hdr,
                              timeout=_115_timeout(), form=True)
        data = d.get("data") or {}
        if isinstance(data, dict):
            return str(data.get("cid") or data.get("file_id") or
                       data.get("category_id") or "")
    except Exception:
        pass
    return ""


def _115_transfer_resolve(info, fid, acc):
    """备用路径（转存取链）：列目录 → 转存「最近接收」→ pickcode →
    chrome/downurl 加密取直链。会往自己的 115 网盘写入一份副本。"""
    cookie = str(acc.get("cookie") or "")
    opts = pan_options()
    savedir = str(opts.get("115SaveDir") or "最近接收")
    target = _115_pick(_115_files(info, cookie, pro=True), fid)
    cid = _115_folder(cookie, savedir) or _115_create_folder(cookie, savedir)
    if not cid:
        raise RuntimeError("115 无法获取/创建保存目录「%s」" % savedir)
    body = urllib.parse.urlencode({
        "share_code": str(info.get("share_id") or ""),
        "receive_code": str(info.get("pwd") or ""),
        "file_id": target["fid"], "cid": cid})
    hdr = _p115_headers(cookie)
    hdr["Content-Type"] = "application/x-www-form-urlencoded"
    d, _, _, _ = raw_json("https://proapi.115.com/android/2.0/share/receive",
                          "POST", body, hdr, timeout=_115_timeout(), form=True)
    if not d.get("state"):
        msg = str(d.get("error") or d.get("msg") or "转存失败")
        if "已存在" not in msg and "重复" not in msg:
            raise RuntimeError("115 转存失败：%s" % msg)
    kw = re.sub(r"\.[^.]+$", "", target["name"]).replace("_", " ")[:20]
    p = {"search_value": kw or target["fid"], "type": 4, "offset": 0,
         "limit": 50, "date": "", "aid": 1, "cid": 0, "pick_code": "",
         "source": "", "format": "json"}
    pc = ""
    deadline = time.time() + max(5, min(int(opts.get("115TransferTimeout", 20)), 30))
    while time.time() < deadline and not pc:
        try:
            s, _, _, _ = raw_json(_qs("https://webapi.115.com/files/search", p),
                                  "GET", None, _p115_headers(cookie),
                                  timeout=_115_timeout())
            items = s.get("data") or []
            for it in items:
                if not isinstance(it, dict):
                    continue
                n = str(it.get("n") or it.get("name") or "")
                if n == target["name"] or (target["name"] and target["name"] in n):
                    pc = str(it.get("pc") or it.get("pick_code") or
                             it.get("pickcode") or "")
                    if pc:
                        break
            if not pc:
                for it in items:
                    if isinstance(it, dict):
                        pc = str(it.get("pc") or it.get("pick_code") or
                                 it.get("pickcode") or "")
                        if pc:
                            break
        except Exception:
            pass
        if not pc:
            time.sleep(0.8)
    if not pc:
        raise RuntimeError("115 转存后未找到文件，请稍后重试（或关闭 115 transfer）")
    body = "data=" + urllib.parse.quote(p115_encrypt({"pickcode": pc}), safe="")
    hdr = {"Content-Type": "application/x-www-form-urlencoded",
           "Cookie": cookie, "User-Agent": UA,
           "Referer": "https://115.com/", "Origin": "https://115.com"}
    d, _, _, _ = raw_json(
        "https://proapi.115.com/app/chrome/downurl?t=%d" % int(time.time()),
        "POST", body, hdr, timeout=_115_timeout(), form=True)
    enc = d.get("data")
    inner = p115_decrypt(enc) if isinstance(enc, str) else \
        (enc if isinstance(enc, dict) else {})
    real = _deep_url(inner)
    if not real:
        raise RuntimeError("115 未返回直链（Cookie 失效 / 风控 / 需会员）")
    return {"url": real, "name": target["name"],
            "header": {"User-Agent": UA, "Referer": "https://115.com/",
                       "Cookie": cookie}}


def _115_resolve(info, fid, acc):
    method = str(pan_options().get("115Method") or "auto").lower()
    chain = {"share": ["share"], "transfer": ["transfer"],
             "auto": ["share", "transfer"]}.get(method, ["share", "transfer"])
    errs = []
    for way in chain:
        try:
            r = _115_share_resolve(info, fid, acc) if way == "share" \
                else _115_transfer_resolve(info, fid, acc)
            if r and r.get("url"):
                return r
        except Exception as e:
            errs.append("%s: %s" % (way, e))
    return {"error": " | ".join(errs)[:220] or "115 无可用直链"}


# ---------------------------------------------------------------- 百度网盘
# pan/drivers/baidu.js：DLNA 签名免转存直链（原包实测可用）+ 转存 filemetas 直链。
# 匿名 sharedownload 通道原包注释即「成功率低、常触发 -20 风控」，未移植；
# 百度直链因此要求 Cookie 里至少含 BDUSS。
BD_DLNA_UA = "netdisk;P2SP;2.2.91.136;android-android;"
BD_APP_UA = "netdisk;11.30.2;android-android;13;JSbridge4.4.0"
BD_DEVUID = "73CED981D0F186D12BC18CAE1684FFD5|VSRCQTF6W"
BD_CHANNEL = "android_12_zhao_bd-netdisk_1024266h"
BD_VERSION = "11.30.2"
BD_SALT_A = "ebrcUYiuxaZv2XGu7KIYKxUrqfnOfpDF"
BD_SALT_B = BD_DEVUID + BD_VERSION + "ae5821440fab5e1a61a025f014bd8972"


def _bd_sha1(s):
    return hashlib.sha1(str(s).encode("utf-8")).hexdigest()


def _bd_logid():
    ms = int(time.time() * 1000)
    return "%06d00%08d%04d" % (ms % 1000000, ms % 100000000, ms % 10000)


def _bd_pub(jar, bdstoken=""):
    baiduid = str(jar.get("BAIDUID") or jar.get("BAIDUID_BFESS") or "").strip()
    logid = base64.b64encode(baiduid.encode("utf-8")).decode("ascii") if baiduid else ""
    return {"app_id": "250528", "channel": "chunlei", "web": "1",
            "bdstoken": str(bdstoken or ""), "logid": logid,
            "clienttype": "0", "dp-logid": _bd_logid()}


def _bd_surl(info):
    raw = str(info.get("share_id") or "")
    # verify 接口的 surl 必须去掉分享码首位 1（带 1 会 errno=105）
    return raw, re.sub(r"^1", "", raw)


def _bd_headers(jar, ua=None, referer="https://pan.baidu.com/"):
    return {"User-Agent": ua or UA, "Referer": referer,
            "Cookie": _cookie_header(jar),
            "Accept": "application/json, text/plain, */*"}


def _bd_verify(info, jar, surl_raw, surl, pwd):
    t = str(int(time.time() * 1000))
    p = {"surl": surl, "t": t, "channel": "chunlei", "web": "1", "app_id": "250528"}
    body = urllib.parse.urlencode({"surl": surl, "pwd": pwd, "t": t,
                                   "channel": "chunlei", "web": "1", "app_id": "250528"})
    hdr = _bd_headers(jar, UA, "https://pan.baidu.com/s/%s" % surl_raw)
    hdr["Content-Type"] = "application/x-www-form-urlencoded"
    d, hd, _, _ = raw_json(_qs("https://pan.baidu.com/share/verify", p),
                           "POST", body, hdr, timeout=_115_timeout(), form=True)
    _merge(jar, hd.get("Set-Cookie") or [])
    if d.get("errno") not in (None, 0, "0"):
        raise RuntimeError("百度分享校验失败(errno=%s %s)" %
                           (d.get("errno"), d.get("errmsg") or d.get("show_msg") or ""))
    return d


def _bd_locals(jar, surl_raw):
    try:
        d, hd, _, _ = raw_json(
            "https://pan.baidu.com/share/locals?surl=" + urllib.parse.quote(surl_raw),
            "GET", None, _bd_headers(jar, UA, "https://pan.baidu.com/s/%s" % surl_raw),
            timeout=_115_timeout())
        _merge(jar, hd.get("Set-Cookie") or [])
        return d.get("data") or {}
    except Exception:
        return {}


def _bd_ids(d, lo):
    sid = str(d.get("shareid") or lo.get("shareid") or "")
    uk = str(d.get("uk") or d.get("share_uk") or lo.get("share_uk") or "")
    if not sid or not uk:
        raise RuntimeError("百度 shareid/uk 缺失（提取码不对或 Cookie 失效）")
    return sid, uk


def _bd_list(jar, sid, uk, bdstoken, dirpath="", depth=0):
    """baidu.js walkShareFiles：根 root=1，子目录 root=0&dir=路径"""
    out = []
    for page in range(1, 4):
        p = {"web": 1, "app_id": 250528, "channel": "chunlei", "clienttype": 0,
             "desc": 1, "num": 100, "page": page, "order": "time",
             "root": 1 if not dirpath else 0,
             "rnd": str(int(time.time() * 1000))[-8:],
             "shareid": sid, "uk": uk, "bdstoken": str(bdstoken or "")}
        if dirpath:
            p["dir"] = dirpath
        d, _, _, _ = raw_json(_qs("https://pan.baidu.com/share/list", p),
                              "GET", None, _bd_headers(jar), timeout=_115_timeout())
        items = d.get("list") or []
        for f in items:
            if not isinstance(f, dict):
                continue
            if str(f.get("isdir")) == "1":
                if depth < 2:
                    out.extend(_bd_list(jar, sid, uk, bdstoken,
                                        str(f.get("path") or ""), depth + 1))
            elif f.get("fs_id"):
                out.append({"fid": str(f["fs_id"]),
                            "name": str(f.get("server_filename") or "")})
        if len(items) < 100:
            break
    vids = [f for f in out if VIDEO_RE.search(f["name"])]
    return (vids or out)[:200]


def _bd_uid(cookie):
    url = ("https://mbd.baidu.com/userx/v1/info/get?appname=baiduboxapp"
           "&fields=%5B%22uid%22%5D&client&clientfrom&lang=zh-cn&tpl&ttt")
    try:
        txt, _, _, _ = http_raw(url, "GET", None,
                                {"User-Agent": UA, "Cookie": cookie},
                                timeout=_115_timeout())
        m = re.search(r'"uid"\s*:\s*"?(\d+)"?', txt)
        return m.group(1) if m else ""
    except Exception:
        return ""


def _bd_follow(u, ua=BD_APP_UA):
    """dlink 会 302 到 CDN；读 Location 拿最终直链"""
    try:
        _, hd, _, _ = http_raw(u, "GET", None, {"User-Agent": ua},
                               timeout=_115_timeout(), follow=False)
        loc = hd.get("Location") or ""
        if loc.startswith("http"):
            return loc
    except Exception:
        pass
    return u


def _bd_dlna(info, fid, acc, jar, surl_raw, surl, pwd):
    bduss = str(jar.get("BDUSS") or "")
    if not bduss:
        raise RuntimeError("百度 DLNA 直链需要 Cookie 里含 BDUSS")
    uid = _bd_uid(_cookie_header(jar))
    if not uid:
        raise RuntimeError("百度 uid 获取失败（BDUSS 可能已失效）")
    d = _bd_verify(info, jar, surl_raw, surl, pwd)
    sid, uk = _bd_ids(d, _bd_locals(jar, surl_raw))
    randsk_enc = str(d.get("randsk") or "")
    target = str(fid or "")
    if not target:
        files = _bd_list(jar, sid, uk, d.get("bdstoken") or "")
        if not files:
            raise RuntimeError("百度分享中未找到视频文件")
        target = files[0]["fid"]
    t = str(int(time.time() * 1000))
    rand = _bd_sha1(_bd_sha1(bduss) + uid + BD_SALT_A + t + BD_SALT_B)
    p = {"shareid": sid, "uk": uk, "fid": target, "sekey": randsk_enc,
         "origin": "dlna", "devuid": BD_DEVUID, "clienttype": 1,
         "channel": BD_CHANNEL, "version": BD_VERSION, "time": t, "rand": rand}
    r, _, _, _ = raw_json(_qs("https://pan.baidu.com/share/list", p), "GET", None,
                          _bd_headers(jar, BD_DLNA_UA), timeout=_115_timeout())
    if str(r.get("errno") or 0) != "0":
        raise RuntimeError("百度 DLNA errno=%s %s" %
                           (r.get("errno"), r.get("show_msg") or r.get("errmsg") or ""))
    dlink = _deep_url(r, ("dlink", "download_url", "downloadurl", "url"))
    if not dlink:
        raise RuntimeError("百度 DLNA 未返回直链")
    name = ""
    for it in r.get("list") or []:
        if isinstance(it, dict) and str(it.get("fs_id") or "") == str(target):
            name = str(it.get("server_filename") or "")
            break
    return {"url": _bd_follow(dlink, BD_DLNA_UA), "name": name,
            "header": {"User-Agent": BD_DLNA_UA}}


def _bd_transfer(info, fid, acc, jar, surl_raw, surl, pwd):
    """DLNA 失败时的备用：转存到 .tvbox_temp（失败回退根目录）→ filemetas 拿 dlink"""
    d = _bd_verify(info, jar, surl_raw, surl, pwd)
    sid, uk = _bd_ids(d, _bd_locals(jar, surl_raw))
    randsk = urllib.parse.unquote(str(d.get("randsk") or ""))
    pub = _bd_pub(jar, d.get("bdstoken") or "")
    files = _bd_list(jar, sid, uk, d.get("bdstoken") or "")
    target = str(fid) if fid else (files[0]["fid"] if files else "")
    if not target:
        raise RuntimeError("百度分享中未找到视频文件")
    p = dict(pub)
    p.update({"ondup": "newcopy", "async": "1", "shareid": sid,
              "from": uk, "sekey": randsk})
    hdr = _bd_headers(jar, UA, "https://pan.baidu.com/s/%s" % surl_raw)
    hdr["Content-Type"] = "application/x-www-form-urlencoded"
    r = None
    for path in ("/.tvbox_temp", "/"):
        body = urllib.parse.urlencode({"fsidlist": json.dumps([target]), "path": path})
        r, _, _, _ = raw_json(_qs("https://pan.baidu.com/share/transfer", p),
                              "POST", body, hdr, timeout=_115_timeout(), form=True)
        if r and str(r.get("errno") or 0) == "0":
            break
    if not r or str(r.get("errno") or 0) != "0":
        raise RuntimeError("百度转存失败(errno=%s %s)" %
                           (r.get("errno") if r else "?",
                            (r.get("show_msg") or r.get("errmsg") or "") if r else ""))
    lst = (r.get("extra") or {}).get("list") or []
    to = str(lst[0].get("to") or "") if lst and isinstance(lst[0], dict) else ""
    if not to:
        raise RuntimeError("百度转存结果缺少目标路径")
    q = dict(pub)
    q.update({"target": json.dumps([to]), "text": "1", "dlink": "1"})
    m, _, _, _ = raw_json(_qs("https://pan.baidu.com/api/filemetas", q), "GET", None,
                          _bd_headers(jar), timeout=_115_timeout())
    il = m.get("info") or []
    dlink = str(il[0].get("dlink") or "") if il and isinstance(il[0], dict) else ""
    dlink = dlink or str(m.get("dlink") or "") or \
        _deep_url(m, ("dlink", "download_url", "url"))
    if not dlink:
        raise RuntimeError("百度 filemetas 未返回直链")
    return {"url": _bd_follow(dlink, BD_APP_UA), "name": "",
            "header": {"User-Agent": BD_APP_UA, "Cookie": _cookie_header(jar)}}


def _bd_resolve(info, fid, acc):
    opts = pan_options()
    method = str(opts.get("baiduMethod") or "auto").lower()
    if method == "dlna":
        chain = ["dlna"]
    elif method == "transfer":
        chain = ["transfer"]
    else:
        chain = ["dlna"] + (["transfer"] if opts.get("baiduTransfer", True) else [])
    jar = _cookie_kv(str(acc.get("cookie") or ""))
    surl_raw, surl = _bd_surl(info)
    pwd = str(info.get("pwd") or "")
    errs = []
    for way in chain:
        try:
            r = _bd_dlna(info, fid, acc, jar, surl_raw, surl, pwd) if way == "dlna" \
                else _bd_transfer(info, fid, acc, jar, surl_raw, surl, pwd)
            if r and r.get("url"):
                return r
        except Exception as e:
            errs.append("%s: %s" % (way, e))
    return {"error": " | ".join(errs)[:220] or "百度无可用直链"}


def _bd_list_files(info, acc):
    jar = _cookie_kv(str(acc.get("cookie") or ""))
    surl_raw, surl = _bd_surl(info)
    pwd = str(info.get("pwd") or "")
    d = _bd_verify(info, jar, surl_raw, surl, pwd)
    sid, uk = _bd_ids(d, _bd_locals(jar, surl_raw))
    return _bd_list(jar, sid, uk, d.get("bdstoken") or "")


# ---------------------------------------------------------------- 对外统一入口
def pan_resolve(info, share_url, fid=""):
    """pan/index.js resolveCore：按网盘类型挑账号 → 驱动换直链。失败返回 None 由上层降级。"""
    typ = str(info.get("type") or "").lower()
    acc = pick_account(typ)
    if not acc or typ not in SUPPORTED:
        return None
    try:
        if typ in CD:
            return _cd_resolve(typ, info, fid, acc)
        if typ == "aliyun":
            return _ali_resolve(info, fid, acc)
        if typ == "123":
            return _123_resolve(info, fid, acc)
        if typ == "115":
            return _115_resolve(info, fid, acc)
        if typ == "baidu":
            return _bd_resolve(info, fid, acc)
    except Exception as e:
        return {"error": str(e)}
    return None


def pan_list_files(info, share_url):
    """pan.list：列分享目录里的视频文件（配合 pan_options.expandShare 展开多集）"""
    typ = str(info.get("type") or "").lower()
    if typ == "115":
        # 115 的 share/snap 是公开接口，不需要账号也能展开分集
        try:
            return [{"fid": f["fid"], "name": f["name"]}
                    for f in _115_files(info, "", pro=False)]
        except Exception:
            return []
    acc = pick_account(typ)
    if not acc or typ not in SUPPORTED:
        return []
    try:
        if typ in CD:
            return _cd_list_public(typ, info, acc)
        if typ == "aliyun":
            return _ali_resolve(info, "", acc, list_only=True) or []
        if typ == "123":
            return _123_resolve(info, "", acc, list_only=True) or []
        if typ == "baidu":
            return _bd_list_files(info, acc)
    except Exception:
        return []
    return []


# -*- coding: utf-8 -*-
"""
配置中心（TVBOX 本地化 Spider）
------------------------------------------------------------------
用途：把网盘账号 Cookie 从 json/pan_accounts.json 外置到本站点在
FongMi.json 里的 ext，让不懂改文件的用户能在壳子 UI（长按站点 / 编辑扩展配置）
里直接填，并由本站点广播给包内所有 Python Spider。

为什么需要这个站点：
  TVBox 的 init(extend) 只把 ext 传给该站点自己的 Spider，别的站点看不到。
  本站点被点开时，会把自己 init() / homeContent() 收到的 ext 里的 panAccounts
  写成 json/pan_accounts.runtime.json 运行时快照，其它站点播放时优先读快照，
  从而绕开「壳子 UI 改 ext 只写自己的数据库、不回写 FongMi.json」的问题。

本站点不联网抓片；只有在 ext 里写了远程 JSON 直链时才会去取那份配置。
首页只展示配置状态与用法说明（Cookie 一律脱敏显示）。

ext 的 panAccounts / panOptions 除了就地写数组/对象，也支持直接写 http(s) 地址：
  "panAccountsUrl": "https://host/panAccounts.json"
  "panOptionsUrl":  "https://host/panOptions.json"
  "panConfigUrl":   "https://host/config.json"   一个地址同时给账号与选项
  "panAccounts":    "https://host/panAccounts.json"  地址写在值里也认
远程 JSON 可以是数组、{"panAccounts":[...],"panOptions":{...}}、单账号对象，
或 {"quark":"cookie...","baidu":"cookie..."} 这样的类型→Cookie 映射。
"""
import json
import os

_TYPES = [
    ("quark", "夸克", "✅ 本地直链"),
    ("uc", "UC", "✅ 本地直链"),
    ("aliyun", "阿里云盘", "✅ 本地直链"),
    ("123", "123云盘", "✅ 本地直链"),
    ("115", "115", "✅ 本地直链"),
    ("baidu", "百度网盘", "✅ 本地直链"),
    ("guangya", "光鸭", "⚠️ 仅透传 Cookie"),
    ("Thunder", "迅雷云盘", "⚠️ 仅透传 Cookie"),
]

_HELP = [
    ("方法A｜在壳子 UI 里填（推荐）",
     "长按或选中「配置中心」站点 → 编辑/扩展配置(ext)，把 panAccounts 数组填成：\n"
     '[{"id":"bd","type":"baidu","name":"百度","cookie":"BDUSS=…","enabled":true}]\n'
     "保存后重新进入一次本站点，首页「当前生效」数量变化即表示已全局生效。\n"
     "运行时快照优先级最高，所以就算之前广播过旧账号，改完 UI 也能盖掉。\n"
     "若数量没变，说明壳子没有把改动写回配置也没传进 ext，请改用方法 B 或 C。"),
    ("方法B｜一键广播到所有站点（最稳）",
     "把 Cookie 填进 json/pan_accounts.json，然后运行：\n"
     "    python tools/gen_config.py --broadcast\n"
     "生成器会把同一份账号写进所有 Python 站点的 ext.panAccounts。\n"
     "壳子一定会把每个站点自己的 ext 传给该站点的 Spider，所以必定生效。\n"
     "以后改 Cookie 要重新广播一次，或先 --clear-broadcast 再改用方法 A。\n"
     "代价：Cookie 明文出现在 FongMi.json 里，别把这个文件分享给别人。"),
    ("方法C｜直接编辑配置中心站点的 ext",
     "用文本编辑器打开 FongMi.json，找到 key=tvbox_config 的站点，\n"
     "把它的 ext.panAccounts 填成账号数组即可，所有站点读同一份配置。\n"
     "运行 python tools/gen_config.py 重建时不会覆盖你填的内容。"),
    ("方法D｜原文件方式（向后兼容）",
     "继续用 json/pan_accounts.json，什么都不用改。\n"
     "只要配置中心站点的 ext.panAccounts 为空、且没有运行时快照，就自动走这里。"),
    ("方法E｜panAccounts / panOptions 写远程直链（Cookie 不落配置文件）",
     "把账号放到一个自己维护的在线 JSON，ext 里只留地址：\n"
     '{"__tvbox_config":true,\n'
     ' "panAccountsUrl":"https://host/panAccounts.json",\n'
     ' "panOptionsUrl":"https://host/panOptions.json"}\n'
     "两种等价写法：\n"
     '  "panAccounts":"https://host/panAccounts.json"   地址直接写在值里\n'
     '  "panConfigUrl":"https://host/config.json"       一个地址同时给账号+选项\n'
     "远程 JSON 可以是以下任一形态：\n"
     '  ① [{"type":"baidu","cookie":"BDUSS=…"}, ...]   账号数组（推荐）\n'
     '  ② {"panAccounts":[...], "panOptions":{...}}    整包对象\n'
     '  ③ {"type":"115","cookie":"UID=…"}              单个账号\n'
     '  ④ {"quark":"cookie…","baidu":"cookie…"}       类型→Cookie 映射\n'
     "字段仍是 type + cookie（也认 panType / ck / 中文网盘名等别名），\n"
     "完整格式见 json/pan_accounts.example.json 与 网盘说明.txt 3.0。\n"
     "拉取成功缓存 5 分钟并写运行时快照，其它站点不必再联网；\n"
     "改完远端内容后点「立即应用到全局」强制刷新。拉取失败保留上次成功的账号。\n"
     "★ 地址必须是「返回原始 JSON」的直链（raw / 对象存储 / 自己的服务器），\n"
     "  返回 404 或网页 HTML 会拉取失败，首页会显示失败原因。"),
    ("优先级与开关",
     "① 运行时快照 → ② 当前站点 ext → ③ 配置中心站点 ext → ④ json 文件。\n"
     "上面 ②③ 的 panAccounts / panOptions 都可以是就地值或远程直链。\n"
     "json/pan_options.json 的 accountSource：\n"
     "  auto(默认) 自动按上面顺序；file 只认 json 文件（远程直链也不拉）；\n"
     "  ext 只认前三种、忽略文件。"),
    ("panOptions 也能外置",
     "ext 里可同时放 panOptions 对象，例如：\n"
     '{"accountFirst":true,"expandShare":false,"115Method":"share","baiduMethod":"dlna"}\n'
     "它会覆盖 json/pan_options.json 里的同名字段。"),
    ("安全提示",
     "Cookie 等于网盘登录态，本包不会预置任何凭据、也不会回传。\n"
     "首页只显示脱敏后的片段。清空 panAccounts 并重新进入本站点会删除运行时快照，\n"
     "自动回到 json/pan_accounts.json。"),
]


def _mask(c):
    s = str(c or "")
    if len(s) > 18:
        return s[:6] + "…" + s[-4:]
    return (s[:3] + "…") if s else "(空)"


def _ref_line():
    """远程直链状态的一行文字（不含任何 Cookie 内容）"""
    st = ref_state()
    if not st.get("url"):
        return "远程直链：未使用"
    return "远程直链：%s ｜ %s" % (st.get("ok") and "已生效" or "失败",
                              st.get("info") or "")


def _sync(ext, refresh=False):
    """把本站点 ext 里的账号写成全局运行时快照；空则删除快照回到文件模式。
    拿不到本站点 ext 时直接跳过，避免壳子传空串把已填的账号清掉。
    ext 里写了远程直链时先拉取再写快照；拉取失败则保留上次成功的快照。
    """
    e = parse_ext(ext) if isinstance(ext, str) else dict(ext or {})
    if not e:
        return "skip", []
    has_conf = any(k in e for k in _ALL_EXT_KEYS)
    if not (e.get("__tvbox_config") or str(e.get("key")) == "tvbox_config"
            or has_conf):
        return "skip", []
    if refresh:
        reset_ref_cache()
    accounts, options = ext_config(e)
    if not accounts and ext_has_ref(e):
        return "拉取失败(保留上次快照)", []
    accounts = accounts or []
    set_site_ext(e)
    state = sync_runtime(accounts, options or {})
    if accounts and ext_has_ref(e):
        state = "written·远程直链 %d 条" % len(accounts)
    return state, accounts


class Spider(object):
    def __init__(self):
        self.ext_raw = ""
        self.sync_state = ""

    def init(self, extend=""):
        self.ext_raw = extend
        self.sync_state, _ = _sync(extend)
        return {}

    def homeContent(self, filter):
        # 部分壳子不调 init，进入首页时再同步一次
        self.sync_state, _ = _sync(self.ext_raw)
        acc, _ov, label = account_source()
        eff = load_accounts()
        n = len(eff)
        return {
            "class": [
                {"type_id": "status", "type_name": "账号状态"},
                {"type_id": "help", "type_name": "配置方法"},
                {"type_id": "types", "type_name": "网盘类型"},
            ],
            "list": [
                {"vod_id": "status", "vod_name": "当前生效 %d 个网盘账号" % n,
                 "vod_pic": "", "vod_remarks": "来源：" + label},
                {"vod_id": "apply", "vod_name": "点此立即应用到全局",
                 "vod_pic": "", "vod_remarks": "同步状态：" + (self.sync_state or "未触发")},
                {"vod_id": "reset", "vod_name": "恢复为 json 文件配置",
                 "vod_pic": "", "vod_remarks": "清空外置账号"},
                {"vod_id": "ref", "vod_name": _ref_line(),
                 "vod_pic": "", "vod_remarks": "远程直链状态"},
            ],
        }

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        if str(tid) == "help":
            rows = [{"vod_id": "help_%d" % i, "vod_name": t, "vod_pic": "",
                     "vod_remarks": "配置方法"} for i, (t, _body) in enumerate(_HELP)]
        elif str(tid) == "types":
            eff = load_accounts()
            have = set(str(a.get("type") or "").lower() for a in eff)
            rows = [{"vod_id": "type_%s" % k, "vod_name": "%s  %s" % (name, cap),
                     "vod_pic": "", "vod_remarks": "已配置" if k.lower() in have else "未配置"}
                    for k, name, cap in _TYPES]
        else:
            eff = load_accounts()
            acc, _ov, label = account_source()
            opts = pan_options()
            rows = [
                {"vod_id": "status", "vod_name": "来源：%s ｜ 生效账号 %d 个" % (label, len(eff)),
                 "vod_pic": "", "vod_remarks": label},
                {"vod_id": "status", "vod_name": "accountSource：%s" % opts.get("accountSource", "auto"),
                 "vod_pic": "", "vod_remarks": "可设为 auto / file / ext"},
                {"vod_id": "status", "vod_name": "快照同步：%s" % (self.sync_state or "未触发"),
                 "vod_pic": "", "vod_remarks": "点开「立即应用」可重做"},
                {"vod_id": "ref", "vod_name": _ref_line(),
                 "vod_pic": "", "vod_remarks": "远程直链"},
            ]
            for a in eff:
                rows.append({"vod_id": "status",
                             "vod_name": "%s ｜ %s" % (a.get("name") or a.get("type"),
                                                     _mask(a.get("cookie"))),
                             "vod_pic": "",
                             "vod_remarks": str(a.get("type") or "")})
            if not rows:
                rows.append({"vod_id": "help_0", "vod_name": "还没有账号，看「配置方法」",
                             "vod_pic": "", "vod_remarks": ""})
        return {"list": rows, "page": 1, "pagecount": 1,
                "limit": len(rows), "total": len(rows)}

    def detailContent(self, ids):
        vid = str((ids or [""])[0])
        if vid == "apply":
            self.sync_state, acc = _sync(self.ext_raw, refresh=True)
            text = ("已把配置中心 ext 应用到全局。\n"
                    "同步结果：%s ｜ 账号 %d 个。\n"
                    "%s\n"
                    "返回其它站点播放时会读取这份快照。" % (
                        self.sync_state, len(acc), _ref_line()))
            title = "立即应用到全局"
        elif vid == "reset":
            try:
                _p = _runtime_file()
                if _p and os.path.exists(_p):
                    os.remove(_p)
                _GLOBAL_CACHE["sig"] = None
                text = "运行时快照已删除，账号改回 json/pan_accounts.json。"
            except Exception as e:
                text = "删除快照失败：%s" % e
            self.sync_state = "removed"
            title = "恢复为 json 文件配置"
        elif vid == "ref":
            title = "远程直链状态"
            st = ref_state()
            text = ("%s\n\n地址：%s\n缓存：%d 秒（点「立即应用到全局」可强制刷新）\n"
                    "账号/选项的直链可以写在 panAccounts / panAccountsUrl /\n"
                    "panOptions / panOptionsUrl / panConfigUrl 里。\n"
                    "拉取失败会保留上次成功的快照，并自动降级到 json 文件方式。" % (
                        _ref_line(), st.get("url") or "(未配置)", REF_TTL))
        elif vid.startswith("help_"):
            try:
                title, text = _HELP[int(vid[5:])]
            except Exception:
                title, text = "说明", "没有这条说明"
        elif vid.startswith("type_"):
            k = vid[5:]
            title = k
            text = "该类型的账号 Cookie 填在 panAccounts 里，type 必须写 %r。" % k
        else:
            eff = load_accounts()
            _a, _o, label = account_source()
            title = "配置中心状态"
            text = ("来源：%s\n生效账号：%d 个\n%s\n\n" % (
                label, len(eff), _ref_line()))
            for a in eff:
                text += "  %s ｜ %s ｜ %s\n" % (
                    a.get("type"), a.get("name") or "-", _mask(a.get("cookie")))
            if not eff:
                text += "尚未配置任何 Cookie，网盘内容只能返回分享链接（parse:1）。\n"
            text += "\n按「配置方法」分类查看四种填写方式。"
        return {"list": [{"vod_id": vid, "vod_name": title, "vod_pic": "",
                          "type_name": "配置中心", "vod_year": "",
                          "vod_area": "", "vod_remarks": "", "vod_actor": "",
                          "vod_director": "", "vod_content": text,
                          "vod_play_from": "配置中心",
                          "vod_play_url": "说明$noplay"}]}

    def searchContent(self, key, quick, pg="1"):
        k = str(key or "").lower()
        rows = [{"vod_id": "help_%d" % i, "vod_name": t, "vod_pic": "",
                 "vod_remarks": "配置方法"}
                for i, (t, body) in enumerate(_HELP) if k in (t + body).lower()]
        return {"list": rows}

    def playerContent(self, flag, id, vipFlags):
        return {"parse": 1, "url": "", "header": {},
                "extra": {"tip": "配置中心不提供播放，请在详情里查看说明"}}
