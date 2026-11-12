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
        extra["tip"] = "未配置该网盘 Cookie，也没配公共解析：需在 json/pan_accounts.json 填 Cookie"
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
只依赖 Python 标准库，可在 TVBox / FongMi 系壳子的 Python Spider 引擎中运行。

对外接口（供 common.py 调用）：
  pick_account(typ)                  取某类型的第一个可用账号
  account_cookie(typ)                取 Cookie 原文（兜底时透传给壳子）
  pan_resolve(info, url, fid)        Cookie 换直链 → {url, header, name} / None
  pan_list_files(info, url)          列分享目录 → [{fid, name}]（展开多集用）

未能纯 REST 移植的驱动（baidu / 115 / guangya / Thunder）保留账号位，
播放时把 Cookie 透传到播放响应 header，由壳子自带的网盘解析或公共解析接管。
"""
import json
import re
import ssl
import time
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

SUPPORTED = ("quark", "uc", "aliyun", "123")


# ---------------------------------------------------------------- HTTP / Cookie
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
    cfg = load_cfg("pan_accounts.json", [])
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
    o = load_cfg("pan_options.json", {})
    return o if isinstance(o, dict) else {}


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
    except Exception as e:
        return {"error": str(e)}
    return None


def pan_list_files(info, share_url):
    """pan.list：列分享目录里的视频文件（配合 pan_options.expandShare 展开多集）"""
    typ = str(info.get("type") or "").lower()
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
    except Exception:
        return []
    return []


# -*- coding: utf-8 -*-
"""
玩偶资源站（TVBOX 本地化 Spider）
------------------------------------------------------------------
移植自 TVBOX (7).zip 的 sites/T4玩偶资源站.js（MacCMS / DYXS2 网盘资源站爬虫）
与 data/wanou.json 的 13 个站点、32 个镜像域名。

与原版的差别（因为客户端没有 Node.js 服务端）：
  * 站点地址直接内嵌在本文件（SITES），也可由配置 ext 覆盖，不读服务端文件
  * 多镜像由「并发竞速」改为「顺序容错 + 记住上次成功域名」
  * 详情页不再调用 pan.list 展开网盘目录（该能力依赖服务端账号与 Cookie），
    改为直接把页面上的网盘分享链接按网盘类型分成线路
  * 播放不再走 /pan/parse 服务端网盘桥，改为 json/parses.json 里的公共解析；
    未配置解析时返回分享链接（parse:1），由壳子自带的网盘能力处理
"""
import re
import urllib.parse

SITES = [
  {
    "key": "MUOU",
    "name": "木偶资源站",
    "hosts": [
      "https://333.333291.xyz",
      "https://666.666291.xyz",
      "https://123.666291.xyz",
      "https://www.muoua.top"
    ]
  }
]

DETAIL_RE = re.compile(r"/(?:index\.php/vod/detail/id/|voddetail/)(\d+)(?:\.html|/|$)", re.I)
TYPE_RE = re.compile(r"/(?:index\.php/vod/(?:type|show)/id/|vodtype/)(\d+)(?:\.html|/)", re.I)
A_RE = re.compile(r'(?is)<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>')
IMG_RE = re.compile(r'(?is)<img[^>]*?(?:data-src|data-original|src)=["\']([^"\']+)["\']')
PAN_LINK_RE = re.compile(r'https?://[^\s"\'<>\\）)]+', re.I)
_active_host = {}


def _looks_junk(html):
    """T4玩偶资源站.js: looksJunk —— 空页 / Google 劫持 / 系统提示页"""
    if not html or len(html) < 500:
        return True
    s = html[:6000]
    return bool(re.search(r"<title>\s*Google\s*</title>", s, re.I) or
                re.search(r"<title>\s*系统提示", s))


def _abs(host, u):
    if not u:
        return ""
    u = str(u).strip()
    if u.startswith("//"):
        return "https:" + u
    if re.match(r"^https?://", u, re.I):
        return u
    if u.startswith("/"):
        return host + u
    return host + "/" + u


def _fetch(key, paths, hosts):
    """依次尝试「候选路径 × 镜像域名」，返回 (html, host)；记住成功域名"""
    hosts = [str(h).rstrip("/") for h in hosts if h]
    if not hosts:
        return "", ""
    prev = _active_host.get(key)
    if prev and prev in hosts:
        hosts.remove(prev)
        hosts.insert(0, prev)
    fallback = ""
    fallback_host = hosts[0]
    for p in paths:
        for h in hosts:
            try:
                html = http_get(h + p)
            except Exception:
                continue
            if not _looks_junk(html):
                _active_host[key] = h
                return html, h
            if not fallback:
                fallback, fallback_host = html, h
    return fallback, fallback_host


def _parse_classes(html):
    """parseClasses：顶部导航里的 type/show/vodtype 链接"""
    out, seen = [], set()
    for m in A_RE.finditer(html or ""):
        tm = TYPE_RE.search(m.group(1))
        if not tm:
            continue
        t = clean(m.group(2))
        if not t or len(t) > 12 or "首页" in t or "网址" in t:
            continue
        tid = tm.group(1)
        if tid in seen:
            continue
        seen.add(tid)
        out.append({"type_id": tid, "type_name": t})
    if not out:
        out = [{"type_id": "1", "type_name": "电影"},
               {"type_id": "2", "type_name": "剧集"},
               {"type_id": "3", "type_name": "动漫"}]
    return out


def _parse_list(html, host):
    """parseListPage / parseSearchPage 的通用实现：按详情链接定位卡片"""
    out, seen = [], set()
    html = html or ""
    for m in A_RE.finditer(html):
        dm = DETAIL_RE.search(m.group(1))
        if not dm:
            continue
        vid = dm.group(1)
        if vid in seen:
            continue
        tag = re.match(r"(?is)<a\b([^>]*)>", m.group(0))
        attrs = tag.group(1) if tag else ""
        tm = re.search(r'title=["\']([^"\']+)["\']', attrs)
        name = clean(tm.group(1)) if tm else ""
        if not name:
            name = clean(m.group(2))
        seg = html[max(0, m.start() - 1000): m.end() + 500]
        if not name or len(name) > 60:
            am = re.search(r'(?is)<img[^>]*alt=["\']([^"\']+)["\']', seg)
            name = clean(am.group(1)) if am else ""
        if not name:
            continue
        im = IMG_RE.search(seg)
        pic = _abs(host, im.group(1)) if im else ""
        rm = re.search(r'(?is)class=["\'][^"\']*(?:module-item-text|module-item-note|video-serial)[^"\']*["\'][^>]*>(.*?)</', seg)
        remarks = clean(rm.group(1)) if rm else ""
        seen.add(vid)
        out.append({"vod_id": vid, "vod_name": name, "vod_pic": pic,
                    "vod_remarks": remarks})
    return out


def _detail_meta(html, host):
    """详情页片名 / 封面 / 简介"""
    name = ""
    m = re.search(r'(?is)<h1[^>]*class=["\'][^"\']*page-title[^"\']*["\'][^>]*>(.*?)</h1>', html or "")
    if not m:
        m = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", html or "")
    if m:
        name = clean(m.group(1))
    pic = ""
    pm = re.search(r'(?is)<(?:div|span|img)[^>]*class=["\'][^"\']*(?:video-cover|premium-poster|video-poster|module-info-poster)[^"\']*["\'][^>]*>.{0,400}?<img[^>]*?(?:data-src|data-original|src)=["\']([^"\']+)["\']', html or "")
    if pm:
        pic = _abs(host, pm.group(1))
    content = ""
    cm = re.search(r'(?is)class=["\'][^"\']*(?:video-info-content|module-info-introduction-content|module-info-introduction)[^"\']*["\'][^>]*>(.*?)</(?:div|p)', html or "")
    if cm:
        content = clean(cm.group(1))[:400]
    return name, pic, content


def _detail_links(html):
    """parseDetail 的核心：提取页面上的网盘分享链接 + 集名"""
    rows, seen = [], set()
    html = html or ""
    # 优先：复制按钮（module-downlist / panlian_dark 模板）
    for m in re.finditer(r'(?is)(?:data-clipboard-text|data-copy)\s*=\s*["\']([^"\']+)["\']', html):
        u = m.group(1).strip()
        if not detect(u) or u in seen:
            continue
        seg = html[max(0, m.start() - 1500):m.start()]
        h4 = re.findall(r"(?is)<h4[^>]*>(.*?)</h4>", seg)
        ep = clean(h4[-1]) if h4 else ""
        seen.add(u)
        rows.append((ep, u))
    # 兜底：页面里任意网盘链接
    if not rows:
        for m in PAN_LINK_RE.finditer(html):
            u = m.group(0).rstrip('.,;)"\'')
            if not detect(u) or u in seen:
                continue
            seen.add(u)
            rows.append(("", u))
    out = []
    for ep, u in rows:
        if block_hit(ep):
            continue
        ep = re.sub(r"[#$\n\r]", " ", clean(ep))[:60].strip()
        out.append((ep, u))
    return out


class Spider(object):
    def __init__(self):
        self.key = SITES[0]["key"]
        self.name = SITES[0]["name"]
        self.hosts = [str(h).rstrip("/") for h in SITES[0].get("hosts", [])]
        self.ext_raw = ""

    def init(self, extend=""):
        self.ext_raw = extend
        e = parse_ext(extend)
        key = str(e.get("key") or "")
        site = next((s for s in SITES if s["key"] == key), None)
        if site is None:
            site = SITES[0]
        # 独立文件里只内嵌本站数据；ext 若指定了别的 key 也照用（仅影响镜像记忆），
        # 域名仍可用 ext.hosts 覆盖，避免误把别站的数据混进来
        self.key, self.name = (key or site["key"]), site["name"]
        hs = e.get("hosts") or e.get("host") or site.get("hosts") or []
        if isinstance(hs, str):
            hs = [x.strip() for x in hs.split(",") if x.strip()]
        self.hosts = [str(h).rstrip("/") for h in hs if h]
        return {}

    def _get(self, paths):
        return _fetch(self.key, paths, self.hosts)

    def homeContent(self, filter):
        html, host = self._get(["/"])
        return {"class": _parse_classes(html), "filters": {},
                "list": _parse_list(html, host)}

    def homeVideoContent(self):
        html, host = self._get(["/"])
        return {"list": _parse_list(html, host)}

    def categoryContent(self, tid, pg, filter, extend):
        t = str(tid or "1")
        try:
            p = int(pg or 1)
        except Exception:
            p = 1
        paths = ["/index.php/vod/type/id/%s/page/%d.html" % (t, p),
                 "/index.php/vod/show/id/%s/page/%d.html" % (t, p),
                 "/vodtype/%s/page/%d.html" % (t, p),
                 "/vodtype/%s-%d/" % (t, p)]
        html, host = self._get(paths)
        lst = _parse_list(html, host)
        more = len(lst) >= 20
        return {"page": p, "pagecount": p + 50 if more else p,
                "limit": len(lst) or 20,
                "total": (p + 50) * 20 if more else len(lst), "list": lst}

    def detailContent(self, ids):
        vid = str(ids[0] if isinstance(ids, (list, tuple)) else ids).split(",")[0].strip()
        paths = ["/index.php/vod/detail/id/%s.html" % urllib.parse.quote(vid),
                 "/voddetail/%s.html" % urllib.parse.quote(vid),
                 "/voddetail/%s/" % urllib.parse.quote(vid)]
        html, host = self._get(paths)
        name, pic, content = _detail_meta(html, host)
        rows = _detail_links(html)
        pf, pu = build_lines(rows, name)
        return {"list": [{"vod_id": vid, "vod_name": name or vid, "vod_pic": pic,
                          "vod_content": content, "vod_remarks": "%d 个网盘链接" % len(rows),
                          "vod_play_from": pf, "vod_play_url": pu}]}

    def searchContent(self, key, quick, pg="1"):
        w = urllib.parse.quote(str(key or ""))
        paths = ["/index.php/vod/search/page/1/wd/%s.html" % w,
                 "/index.php/vod/search.html?wd=%s" % w,
                 "/vodsearch/%s----------1---.html" % w,
                 "/vodsearch/-------------/?wd=%s" % w]
        html, host = self._get(paths)
        lst = _parse_list(html, host)
        return {"list": lst, "page": 1, "pagecount": 1, "total": len(lst)}

    def playerContent(self, flag, id, vipFlags):
        return play_result(flag, id, self.ext_raw)
