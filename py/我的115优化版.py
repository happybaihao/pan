# coding=utf-8
import base64, gzip, json, os, random, re, ssl, time, urllib.parse, urllib.request

MY115_COOKIE = ""

PAGE_SIZE = 115
SEARCH_LIMIT = 50
PLAY_FROM = "115Drive"
MIN_VIDEO_SIZE = 1024 * 1024     # 小于 1MB 的"视频"直接忽略（多半是 nfo/url 改名之类）
DEBUG = False                    # True 才在 JSON 里输出 _debug / 诊断 / 原文
TIMEOUT = 20

WEB_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
BROWSER_UA = WEB_UA + " 115Browser/36.0.0 Chromium/125.0"

FOLDER_PIC = "https://img.icons8.com/fluency/96/folder-invoices--v1.png"
VIDEO_PIC = "https://img.icons8.com/color/48/video.png"
VIDEO_EXTS = (
    ".mp4", ".mkv", ".webm", ".avi", ".wmv", ".flv", ".mov", ".mpeg", ".mpg", ".m4v",
    ".ts", ".m2ts", ".mts", ".tp", ".trp",              # 蓝光 / 高清录制
    ".vob", ".evo",                                      # DVD / HD-DVD
    ".3gp", ".rm", ".rmvb", ".iso",
    ".f4v", ".ogv", ".divx", ".xvid", ".asf", ".dat",   # 其它常见容器 / VCD
)

RSA_N = int("8686980c0f5a24c4b9d43020cd2c22703ff3f450756529058b1cf88f09b8602136477198a6e2683149659bd122c33592fdb5ad47944ad1ea4d36c6b172aad6338c3bb6ac6227502d010993ac967d1aef00f0c8e038de2e4d3bc2ec368af2e9f10a6f1eda4f7262f136420c07c331b871bf139f74f3010e3c4fe57df3afb71683", 16)
RSA_E = 65537
KEY_TABLE = bytes([0xf0, 0xe5, 0x69, 0xae, 0xbf, 0xdc, 0xbf, 0x8a, 0x1a, 0x45, 0xe8, 0xbe, 0x7d, 0xa6, 0x73, 0xb8, 0xde, 0x8f, 0xe7, 0xc4, 0x45, 0xda, 0x86, 0xc4, 0x9b, 0x64, 0x8b, 0x14, 0x6a, 0xb4, 0xf1, 0xaa, 0x38, 0x01, 0x35, 0x9e, 0x26, 0x69, 0x2c, 0x86, 0x00, 0x6b, 0x4f, 0xa5, 0x36, 0x34, 0x62, 0xa6, 0x2a, 0x96, 0x68, 0x18, 0xf2, 0x4a, 0xfd, 0xbd, 0x6b, 0x97, 0x8f, 0x4d, 0x8f, 0x89, 0x13, 0xb7, 0x6c, 0x8e, 0x93, 0xed, 0x0e, 0x0d, 0x48, 0x3e, 0xd7, 0x2f, 0x88, 0xd8, 0xfe, 0xfe, 0x7e, 0x86, 0x50, 0x95, 0x4f, 0xd1, 0xeb, 0x83, 0x26, 0x34, 0xdb, 0x66, 0x7b, 0x9c, 0x7e, 0x9d, 0x7a, 0x81, 0x32, 0xea, 0xb6, 0x33, 0xde, 0x3a, 0xa9, 0x59, 0x34, 0x66, 0x3b, 0xaa, 0xba, 0x81, 0x60, 0x48, 0xb9, 0xd5, 0x81, 0x9c, 0xf8, 0x6c, 0x84, 0x77, 0xff, 0x54, 0x78, 0x26, 0x5f, 0xbe, 0xe8, 0x1e, 0x36, 0x9f, 0x34, 0x80, 0x5c, 0x45, 0x2c, 0x9b, 0x76, 0xd5, 0x1b, 0x8f, 0xcc, 0xc3, 0xb8, 0xf5])

K1 = b"\x8d\xa5\xa5\x8d"
K2 = b"\x78\x06\xad\x4c\x33\x86\x5d\x18\x4c\x01\x3f\x46"


def _xor_bytes(inp, key):
    kl = len(key)
    return bytes((inp[i] ^ key[i % kl]) & 0xff for i in range(len(inp)))


def _xor_by_key(inp, key):
    ln = len(inp)
    head = ln & 3
    out = b""
    if head:
        out += _xor_bytes(inp[:head], key[:head])
    kl = len(key)
    pos = head
    while pos < ln:
        end = min(pos + kl, ln)
        out += _xor_bytes(inp[pos:end], key)
        pos = end
    return out


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


def _rsa_enc_block(block):
    ln = len(block)
    if ln > 117:
        block = block[:117]
        ln = 117
    buf = bytearray(128)
    for i in range(1, 127 - ln):
        buf[i] = 2
    buf[128 - ln:] = block
    m = int.from_bytes(bytes(buf), "big")
    c = pow(m, RSA_E, RSA_N)
    return c.to_bytes(128, "big")


def _rsa_dec_block(block):
    """RSA 公钥运算 + 剥掉 PKCS#1 v1.5 的 00 01 FF..FF 00 填充头

    ⚠ 关键：JS 的 bigIntToBytes 会丢掉前导 0x00，所以它的 indexOf(0)
    命中的是 FF 填充之后的分隔符。而 Python 的 to_bytes(128) 保留了前导 0，
    如果直接 find(b'\x00') 会命中第 0 字节，整块被当垃圾丢掉。
    这里从下标 1 开始找分隔符。
    """
    c = int.from_bytes(block, "big")
    m = pow(c, RSA_E, RSA_N)
    dec = m.to_bytes(128, "big")
    # 00 01 FF...FF 00 <payload>
    if len(dec) >= 3 and dec[0] == 0 and dec[1] == 1:
        i = dec.find(b"\x00", 2)          # 跳过前导 00 和 01
        if i >= 0:
            return dec[i + 1:]
        return dec
    # 其他情况：从下标 1 开始找第一个 0
    i = dec.find(b"\x00", 1)
    return dec[i + 1:] if i >= 0 else dec


def encrypt_payload(text):
    if isinstance(text, str):
        text = text.encode("utf-8")
    t = _xor_by_key(text, K1)[::-1]
    t = _xor_by_key(t, K2)
    padded = b"\x00" * 16 + t
    out = b""
    pos = 0
    while pos < len(padded):
        out += _rsa_enc_block(padded[pos:pos + 117])
        pos += 117
    return base64.b64encode(out).decode()


def decrypt_payload(b64):
    raw = base64.b64decode(b64)
    merged = b""
    pos = 0
    while pos < len(raw):
        merged += _rsa_dec_block(raw[pos:pos + 128])
        pos += 128
    if len(merged) < 17:
        return ""
    key = _table_key(merged[:16], 12)
    body = _xor_by_key(merged[16:], key)[::-1]
    return _xor_by_key(body, K1).decode("utf-8", "replace")


def _ssl():
    try:
        c = ssl.create_default_context()
        c.check_hostname = False
        c.verify_mode = ssl.CERT_NONE
        return c
    except Exception:
        return None


def _http(url, data=None, headers=None, timeout=None):
    h = headers or {}
    req = urllib.request.Request(url, data=data, headers=h)
    try:
        r = urllib.request.urlopen(req, timeout=timeout or TIMEOUT, context=_ssl())
        body = r.read()
        hd = dict(r.headers)
        if body[:2] == b"\x1f\x8b":
            body = gzip.decompress(body)
        return body.decode("utf-8", "replace"), hd
    except Exception as e:
        return "", {"_err": "%s: %s" % (type(e).__name__, e)}


def _to_text(v):
    return "" if v is None else str(v)


def _item_name(it):
    n = it.get("n") or it.get("name") or ""
    return n if n else "未知"


def _is_folder(it):
    try:
        return int(it.get("fc")) == 0
    except Exception:
        return False


def _size_text(sz):
    try:
        s = float(sz or 0)
    except Exception:
        return ""
    if s <= 0:
        return ""
    units = ("B", "KB", "MB", "GB", "TB")
    i = 0
    while s >= 1024 and i < 4:
        s /= 1024.0
        i += 1
    return ("%.0f" if i == 0 else "%.1f") % s + units[i]


def maybe_diag(msg, raw):
    """只有 DEBUG 打开时才把失败原因/原始响应写进简介"""
    if not DEBUG:
        return ""
    txt = msg
    if raw:
        txt += "\n原文: " + raw[:300]
    return txt


def _ep_name(path):
    """把文件名缩成适合选集显示的短名。

    只在**确实有集号标记**时才缩成「第N集」：
      S01E11 / s1e11        → 第11集
      第12集 / 第3话        → 第12集
    其余一律保留片名（去扩展名）——否则「一部电影一个文件」的目录里，
    每部片的 E01 会挤成好几个「第1集」，全撞车。
    """
    n = _to_text(path)
    base = n.split("/")[-1] if "/" in n else n
    for ext in VIDEO_EXTS:
        if base.lower().endswith(ext):
            base = base[:-len(ext)]
            break

    m = re.search(r"[Ss](\d{1,2})[Ee](\d{1,4})", base)
    if m:
        ep = int(m.group(2))
        if int(m.group(1)) > 1:
            return "第%s季第%d集" % (m.group(1), ep)
        return "第%d集" % ep

    m2 = re.search(r"第\s*(\d{1,4})\s*[集话期]", base)
    if m2:
        return "第%s集" % m2.group(1)

    # 蓝光/光盘裸号文件：BDMV/STREAM/00001.m2ts → 用上级目录当片名
    if re.match(r"^\d{1,5}$", base.strip()):
        parts = [x for x in n.split("/") if x]
        # 去掉 BDMV / STREAM / VIDEO_TS 这类结构目录
        skip = ("bdmv", "stream", "video_ts", "audio_ts", "certificate", "backup", "playlist", "clipinf")
        names = [x for x in parts[:-1] if x.lower() not in skip]
        if names:
            title = names[-1]
            if len(title) > 18:
                title = title[:18] + "…"
            return "%s %s" % (title, base.strip())
        return base.strip()

    # 没有集号标记：当独立影片，保留片名
    if len(base) > 22:
        base = base[:22] + "…"
    return base or "未命名"


def _show_name(path):
    """从文件名里剥掉集号/分辨率/编码标签，得到剧名，用来归组

    剧名.S02E08.2160p.WEB-DL.H265.AAC.mkv      → 剧名
    剧名 第12集.mp4                            → 剧名
    唐山大兄.1971.4K修复.mkv                    → 唐山大兄.1971.4K修复（没有集号，原样）
    """
    n = _to_text(path)
    base = n.split("/")[-1] if "/" in n else n
    for ext in VIDEO_EXTS:
        if base.lower().endswith(ext):
            base = base[:-len(ext)]
            break
    out = base
    m = re.search(r"[.\s_-]*[Ss](\d{1,2})[Ee](\d{1,4})", base)
    if m:
        out = base[:m.start()]
    else:
        m2 = re.search(r"[.\s_-]*第\s*\d{1,4}\s*[集话期]", base)
        if m2:
            out = base[:m2.start()]
    out = out.strip(" ._-")
    return out if out else base


def _sort_key(path):
    """按 (季, 集) 排序；认不出就按名字排，保证选集顺序稳定"""
    n = _to_text(path)
    base = n.split("/")[-1] if "/" in n else n
    m = re.search(r"[Ss](\d{1,2})[Ee](\d{1,4})", base)
    if m:
        return (0, int(m.group(1)), int(m.group(2)), base)
    m2 = re.search(r"第\s*(\d{1,2})\s*季.*?第\s*(\d{1,4})\s*[集话期]", base)
    if m2:
        return (0, int(m2.group(1)), int(m2.group(2)), base)
    m3 = re.search(r"第\s*(\d{1,4})\s*[集话期]", base)
    if m3:
        return (0, 1, int(m3.group(1)), base)
    return (1, 0, 0, base)


def _token(name, tid, kind):
    """vod_id / 选集参数用 LOCAL_<urlsafe_base64(名称\\tID\\t类型)>
    不能用 ### 分隔：vod_play_url 本身用 # 分隔选集，会把 token 劈碎。"""
    raw = "%s\t%s\t%s" % (_to_text(name), _to_text(tid), kind)
    b = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")
    return "LOCAL_" + b.rstrip("=")


def _parse_token(raw):
    raw = _to_text(raw).strip()
    if raw.startswith("LOCAL_"):
        b = raw[6:]
        b += "=" * (-len(b) % 4)
        try:
            txt = base64.urlsafe_b64decode(b.encode("ascii")).decode("utf-8", "replace")
        except Exception:
            return None
        parts = txt.split("\t")
        return {"name": parts[0] or "115资源",
                "id": parts[1] if len(parts) > 1 else "0",
                "kind": parts[2] if len(parts) > 2 else ""}
    # 兼容旧格式
    if raw.startswith("LOCAL###"):
        p = raw.split("###")
        name = urllib.parse.unquote(p[1]) if len(p) > 1 else "115资源"
        return {"name": name or "115资源",
                "id": p[2] if len(p) > 2 else "0",
                "kind": p[3] if len(p) > 3 else ""}
    return None


class Spider(object):
    def __init__(self):
        self.cookie = MY115_COOKIE.strip()
        self.last_err = ""
        self.last_raw = ""

    def getName(self):
        return "115网盘"

    def init(self, extend=""):
        try:
            if extend:
                e = json.loads(extend) if isinstance(extend, str) else extend
                if isinstance(e, dict) and e.get("cookie"):
                    self.cookie = str(e["cookie"]).strip()
        except Exception:
            pass
        return None

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def getDependence(self):
        return []

    def destroy(self):
        pass

    def localProxy(self, param):
        return ""

    # ---------- 115 接口 ----------

    def _h_list(self):
        return {"User-Agent": BROWSER_UA,
                "Referer": "https://webapi.115.com/bridge_2.0.html?namespace=Core.DataAccess&api=UDataAPI&_t=v5",
                "X-Requested-With": "XMLHttpRequest",
                "Origin": "https://115.com",
                "Cookie": self.cookie}

    def _h_web(self):
        return {"User-Agent": WEB_UA,
                "Referer": "https://115.com/",
                "Origin": "https://115.com",
                "Accept": "application/json, text/plain, */*",
                "Cookie": self.cookie}

    def _list_dir(self, cid, page):
        off = (max(1, int(page or 1)) - 1) * PAGE_SIZE
        q = urllib.parse.urlencode({
            "aid": 1, "cid": cid or "0", "o": "user_ptime", "asc": 0,
            "offset": off, "show_dir": 1, "limit": PAGE_SIZE,
            "code": "", "scid": "", "snap": 0, "natsort": 1,
            "record_open_time": 1, "source": "", "format": "json",
        })
        txt, hd = _http("https://webapi.115.com/files?" + q, None, self._h_list())
        if not txt:
            self.last_err = hd.get("_err", "请求失败")
            return {"list": [], "count": 0}
        try:
            j = json.loads(txt)
        except Exception:
            self.last_err = "返回非JSON"
            return {"list": [], "count": 0}
        if not j.get("state"):
            self.last_err = "115目录: %s" % (j.get("error") or j.get("message") or "状态异常")
            return {"list": [], "count": 0}
        arr = j.get("data") if isinstance(j.get("data"), list) else []
        return {"list": arr, "count": int(j.get("count") or 0)}

    def _search_files(self, kw, page):
        off = (max(1, int(page or 1)) - 1) * SEARCH_LIMIT
        q = urllib.parse.urlencode({
            "search_value": kw, "type": 4, "offset": off,
            "limit": SEARCH_LIMIT, "date": "", "aid": 1,
            "cid": 0, "pick_code": "", "source": "", "format": "json",
        })
        txt, hd = _http("https://webapi.115.com/files/search?" + q, None, self._h_web())
        if not txt:
            self.last_err = hd.get("_err", "请求失败")
            return {"list": [], "count": 0}
        try:
            j = json.loads(txt)
        except Exception:
            return {"list": [], "count": 0}
        arr = j.get("data") if isinstance(j.get("data"), list) else []
        return {"list": arr, "count": int(j.get("count") or len(arr))}

    def _downurl(self, pickcode):
        js = json.dumps({"pickcode": pickcode}, separators=(",", ":"))
        body = "data=" + urllib.parse.quote(encrypt_payload(js), safe="")
        h = {"Content-Type": "application/x-www-form-urlencoded",
             "Content-Length": str(len(body.encode("utf-8"))),
             "Cookie": self.cookie,
             "User-Agent": BROWSER_UA,
             "Referer": "https://115.com/",
             "Origin": "https://115.com"}
        txt, hd = _http("https://proapi.115.com/app/chrome/downurl?t=%d" % int(time.time()),
                        body.encode("utf-8"), h)
        self.last_raw = (txt or "")
        try:
            with open("/sdcard/115_debug.txt", "w", encoding="utf-8") as f:
                f.write(txt or "")
        except Exception:
            try:
                with open("/storage/emulated/0/115_debug.txt", "w", encoding="utf-8") as f:
                    f.write(txt or "")
            except Exception:
                pass
        if not txt:
            return {"url": "", "cookie": "", "msg": hd.get("_err", "请求失败")}
        try:
            j = json.loads(txt)
        except Exception:
            return {"url": "", "cookie": "", "msg": "返回非JSON"}
        d = None
        enc = ""
        dv = j.get("data")
        if isinstance(dv, str):
            enc = dv
        elif isinstance(dv, list):
            # 可能是 [ "<密文>" ] 或 [ {"data": "<密文>"} ]
            for x in dv:
                if isinstance(x, str) and len(x) > 40:
                    enc = x; break
                if isinstance(x, dict):
                    for k2 in ("data", "url", "download_url"):
                        if isinstance(x.get(k2), str) and len(x[k2]) > 40:
                            enc = x[k2]; break
                if enc: break
        elif isinstance(dv, dict) and isinstance(dv.get("data"), str):
            enc = dv["data"]
        if enc:
            try:
                rawb = base64.b64decode(enc)
            except Exception:
                rawb = b""
            info = "data=%d字符/%d字节" % (len(enc), len(rawb))
            try:
                plain = decrypt_payload(enc)
            except Exception as e:
                plain = ""
                info += " 解密异常=%s" % type(e).__name__
            if plain:
                d = json.loads(plain)
                info += " 解密=%d字符" % len(plain)
            else:
                d = None
                info += " 解密为空"
                if rawb:
                    info += " 密文头=%s" % rawb[:8].hex()
            self.last_err = info
        if d is None:
            # 回退：直接用原文找 url（有些情况服务端不加密）
            d = j
        url = self._find_url(d)
        ck = self._find_auth_cookie(d)
        if not url:
            msg = self._find_msg(d)
            if msg == "未发现下载链接":
                msg = "state=%s %s" % (j.get("state"), self.last_err or "无诊断")
            return {"url": "", "cookie": "", "msg": msg}
        return {"url": url, "cookie": ck, "msg": ""}

    def _find_auth_cookie(self, o):
        """115 直链必须在 Cookie 里带上 auth_cookie，否则 403"""
        if not isinstance(o, dict):
            return ""
        u = o.get("url")
        if isinstance(u, dict):
            ac = u.get("auth_cookie")
            if isinstance(ac, dict) and ac.get("name"):
                return "%s=%s" % (ac["name"], ac.get("value", ""))
        for v in o.values():
            h = self._find_auth_cookie(v)
            if h:
                return h
        return ""

    def _find_url(self, o):
        if not isinstance(o, dict):
            return ""
        u = o.get("url")
        if isinstance(u, str) and u:
            return u
        if isinstance(u, dict) and isinstance(u.get("url"), str):
            return u["url"]
        d = o.get("data")
        if isinstance(d, dict) and isinstance(d.get("url"), str):
            return d["url"]
        for v in o.values():
            h = self._find_url(v)
            if h:
                return h
        return ""

    def _find_msg(self, o):
        if not isinstance(o, dict):
            return "未发现下载链接"
        for k in ("msg", "message", "error", "errmsg", "errno"):
            v = o.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
            if isinstance(v, int) and v:
                return "%s=%s" % (k, v)
        for v in o.values():
            h = self._find_msg(v)
            if h and h != "未发现下载链接":
                return h
        return "未发现下载链接"

    # ---------- 映射 ----------

    def _map_item(self, it):
        folder = _is_folder(it)
        name = _item_name(it)
        if folder:
            tid = _to_text(it.get("cid") or it.get("fid") or "0")
        else:
            tid = _to_text(it.get("pc") or it.get("pick_code") or it.get("pickcode") or "")
        if folder:
            return {"vod_id": _token(name, tid, "folder"),
                    "vod_name": name,
                    "vod_pic": FOLDER_PIC,
                    "vod_remarks": "目录"}
        short = _ep_name(name)
        if name.lower().endswith(".iso"):
            short = short + "〔ISO·需外挂播放器〕"
        _raw_sz = it.get("s") or it.get("size") or 0
        try:
            if int(_raw_sz) < MIN_VIDEO_SIZE:
                short = short + "（过小）"
        except Exception:
            pass
        sz = _size_text(_raw_sz)
        return {"vod_id": _token(name, tid, "file"),
                "vod_name": short,
                "vod_pic": VIDEO_PIC,
                "vod_remarks": sz}

    def _walk(self, cid, depth=0, out=None, seen=None, limit=300, prefix=""):
        """递归把子树里的视频文件展平（供详情页当选集用），带相对路径"""
        if out is None:
            out = []
        if seen is None:
            seen = set()
        if depth > 4 or len(out) >= limit or cid in seen:
            return out
        seen.add(cid)
        page = 1
        while len(out) < limit:
            r = self._list_dir(cid, page)
            arr = r["list"]
            if not arr:
                break
            for it in arr:
                name = _item_name(it)
                if _is_folder(it):
                    sub = _to_text(it.get("cid") or it.get("fid") or "0")
                    self._walk(sub, depth + 1, out, seen, limit, prefix + name + "/")
                else:
                    lower = name.lower()
                    if not any(lower.endswith(e) for e in VIDEO_EXTS):
                        continue          # 只收视频，txt/jpg 之类跳过
                    try:
                        if int(it.get("s") or it.get("size") or 0) < MIN_VIDEO_SIZE:
                            continue      # 几十 KB 的假视频跳过
                    except Exception:
                        pass
                    pc = _to_text(it.get("pc") or it.get("pick_code") or it.get("pickcode") or "")
                    if not pc:
                        continue
                    out.append({"name": prefix + name, "pc": pc})
                if len(out) >= limit:
                    break
            if r["count"] and page * PAGE_SIZE >= r["count"]:
                break
            page += 1
        return out

    # ---------- CMS ----------

    def homeContent(self, filter):
        """根目录的文件夹直接做成分类栏 —— 这样点它进的是列表，不是播放"""
        cls = [{"type_id": "0", "type_name": "根目录"}]
        try:
            if self.cookie:
                r = self._list_dir("0", 1)
                for it in r["list"]:
                    if not _is_folder(it):
                        continue
                    cid = _to_text(it.get("cid") or it.get("fid") or "")
                    nm = _item_name(it)
                    if not cid:
                        continue
                    cls.append({"type_id": _token(nm, cid, "folder"), "type_name": nm})
        except Exception as e:
            cls.append({"type_id": "0", "type_name": "读取失败"})
            self.last_err = "%s: %s" % (type(e).__name__, e)
        return {"class": cls, "filters": {}}

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg or 1)
        except Exception:
            page = 1
        t = _parse_token(tid)
        if t is not None and t["kind"] == "file":
            return {"list": [{"vod_id": tid, "vod_name": t["name"],
                              "vod_pic": VIDEO_PIC, "vod_remarks": "文件"}],
                    "page": 1, "pagecount": 1, "limit": 1, "total": 1}
        cid = t["id"] if (t is not None and t["kind"] == "folder") else (tid or "0")
        r = self._list_dir(cid, page)
        items = [self._map_item(x) for x in r["list"]]
        total = r["count"]
        pc = (total + PAGE_SIZE - 1) // PAGE_SIZE if total else 1
        out = {"list": items, "page": page, "pagecount": pc,
               "limit": PAGE_SIZE, "total": total}
        if not items and DEBUG:
            out["_debug"] = {"tid": tid, "reason": self.last_err or "(空目录)"}
        return out

    def detailContent(self, ids):
        try:
            return self._detail(ids)
        except Exception as e:
            print("[115] 详情异常: %s: %s" % (type(e).__name__, e))
            return {"list": [{"vod_id": "err", "vod_name": "115详情异常",
                              "vod_pic": VIDEO_PIC,
                              "vod_remarks": "%s" % type(e).__name__,
                              "vod_content": str(e)[:200],
                              "vod_play_from": PLAY_FROM, "vod_play_url": ""}]}

    def _group_files(self, gid):
        """合集：按剧名去 115 搜一遍，把这个剧的所有集都找出来"""
        show = gid[6:] if _to_text(gid).startswith("GROUP:") else _to_text(gid)
        files = []
        seen = set()
        for pno in (1, 2, 3):
            try:
                rr = self._search_files(show, pno)
            except Exception:
                break
            for it in rr["list"]:
                if _is_folder(it):
                    continue
                nm = _item_name(it).lower()
                if not any(nm.endswith(e) for e in VIDEO_EXTS):
                    continue
                try:
                    if int(it.get("s") or it.get("size") or 0) < MIN_VIDEO_SIZE:
                        continue
                except Exception:
                    pass
                full = _item_name(it)
                if _show_name(full) != show:
                    continue
                pc = _to_text(it.get("pc") or it.get("pick_code") or it.get("pickcode") or "")
                if not pc or pc in seen:
                    continue
                seen.add(pc)
                files.append({"name": full, "pc": pc})
            if len(rr["list"]) < SEARCH_LIMIT:
                break
        files.sort(key=lambda f: _sort_key(f["name"]))
        return files

    def _detail(self, ids):
        raw = _to_text(ids[0] if isinstance(ids, (list, tuple)) else ids).strip()
        t = _parse_token(raw)
        if t is None:
            return {"list": [], "_debug": {"reason": "id 格式不对", "id": raw}}
        if t["kind"] == "group":
            show = t["id"][6:] if t["id"].startswith("GROUP:") else t["id"]
            files = []
            for pno in (1, 2, 3):
                rr = self._search_files(show, pno)
                for it in rr["list"]:
                    if _is_folder(it):
                        continue
                    nm = _item_name(it).lower()
                    if not any(nm.endswith(e) for e in VIDEO_EXTS):
                        continue
                    try:
                        if int(it.get("s") or it.get("size") or 0) < MIN_VIDEO_SIZE:
                            continue
                    except Exception:
                        pass
                    full = _item_name(it)
                    if _show_name(full) != show:
                        continue
                    pc = _to_text(it.get("pc") or it.get("pick_code") or it.get("pickcode") or "")
                    if pc:
                        files.append({"name": full, "pc": pc})
                if len(rr["list"]) < SEARCH_LIMIT:
                    break
            if not files:
                row = {"vod_id": raw, "vod_name": show, "vod_pic": VIDEO_PIC,
                       "vod_remarks": "目录", "vod_content": "",
                       "vod_play_from": PLAY_FROM, "vod_play_url": ""}
                return {"list": [row]}
            files.sort(key=lambda f: _sort_key(f["name"]))
            lines = ["%s$%s" % (_ep_name(f["name"]), _token(f["name"], f["pc"], "file"))
                     for f in files]
            row = {"vod_id": raw, "vod_name": show, "vod_pic": VIDEO_PIC,
                   "vod_remarks": "共%d集" % len(files),
                   "vod_content": "",
                   "vod_play_from": PLAY_FROM, "vod_play_url": "#".join(lines)}
            return {"list": [row]}

        if t["kind"] == "folder":
            # 和 JS 一致：目录一定有详情行，绝不返回空 list（空的话 TVBox 显示不出来）
            files = self._walk(t["id"])
            try:
                files.sort(key=lambda f: _sort_key(f["name"]))
            except Exception:
                pass
            lines = []
            for f in files:
                lines.append("%s$%s" % (_ep_name(f["name"]),
                                        _token(f["name"], f["pc"], "file")))
            if files:
                row = {"vod_id": raw, "vod_name": t["name"], "vod_pic": FOLDER_PIC,
                       "vod_remarks": "共%d个视频" % len(files),
                       "vod_content": "共%d个视频：%s" % (len(files),
                                     "、".join(_ep_name(f["name"]) for f in files[:8])),
                       "vod_play_from": PLAY_FROM, "vod_play_url": "#".join(lines)}
            else:
                row = {"vod_id": raw, "vod_name": t["name"], "vod_pic": FOLDER_PIC,
                       "vod_remarks": "目录",
                       "vod_content": "该目录下没扫到视频文件%s" % (
                           ("（" + self.last_err + "）") if self.last_err else ""),
                       "vod_play_from": PLAY_FROM, "vod_play_url": ""}
            return {"list": [row]}
        lower = t["name"].lower()
        if not any(lower.endswith(e) for e in VIDEO_EXTS):
            return {"list": [{"vod_id": raw, "vod_name": t["name"],
                              "vod_pic": VIDEO_PIC, "vod_remarks": "不是视频文件",
                              "vod_content": "扩展名不在支持列表里，无法播放",
                              "vod_play_from": PLAY_FROM, "vod_play_url": ""}]}
        r = self._downurl(t["id"])
        play = ("正片$" + r["url"]) if r["url"] else ""
        if r["url"] and t["name"].lower().endswith(".iso"):
            play = "ISO镜像(需外挂播放器)$" + r["url"]
        # 取址失败时把原因写进备注和简介，TVBox 里能直接看到
        rows_txt = "可播放" if r["url"] else ("取址失败: " + str(r["msg"]))
        if not play:
            play = "错误信息: %s$" % str(r["msg"])[:80]
        row = {"vod_id": raw, "vod_name": t["name"], "vod_pic": VIDEO_PIC,
               "vod_remarks": rows_txt,
               "vod_content": ("" if r["url"] else
                               maybe_diag(str(r["msg"]), self.last_raw if DEBUG else "")),
               "vod_play_from": PLAY_FROM, "vod_play_url": play}
        out = {"list": [row]}
        if not play and DEBUG:
            out["_debug"] = {"reason": r["msg"], "pickcode": t["id"]}
        return out

    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg or 1)
        except Exception:
            page = 1
        r = self._search_files(key, page)
        # 按剧名归组：一部剧一个结果，点进去才是每集
        groups = {}
        for it in r["list"]:
            if _is_folder(it):
                continue
            nm = _item_name(it).lower()
            if not any(nm.endswith(e) for e in VIDEO_EXTS):
                continue
            try:
                if int(it.get("s") or it.get("size") or 0) < MIN_VIDEO_SIZE:
                    continue
            except Exception:
                pass
            full = _item_name(it)
            show = _show_name(full)
            g = groups.get(show)
            if g is None:
                g = {"show": show, "files": [], "size": 0, "sample": full}
                groups[show] = g
            g["files"].append(full)
            try:
                g["size"] += int(it.get("s") or it.get("size") or 0)
            except Exception:
                pass
        items = []
        for show, g in groups.items():
            n = len(g["files"])
            if n > 1:
                remark = "共%d集 · %s" % (n, _size_text(g["size"]))
            else:
                remark = _size_text(g["size"]) or "单集"
            items.append({
                "vod_id": _token(show, "GROUP:" + show, "group"),
                "vod_name": show[:40],
                "vod_pic": VIDEO_PIC,
                "vod_remarks": remark,
            })
        # 集数多的排前面
        items.sort(key=lambda x: (-len(groups[_parse_token(x["vod_id"])["id"][6:]]["files"])
                                  if _parse_token(x["vod_id"])["id"].startswith("GROUP:") else 0))
        total = r["count"]
        pc = (total + SEARCH_LIMIT - 1) // SEARCH_LIMIT if total else 1
        out = {"list": items, "page": page, "pagecount": pc,
               "limit": SEARCH_LIMIT, "total": len(items)}
        if not items and DEBUG:
            out["_debug"] = {"reason": self.last_err or "(无结果)", "kw": key}
        return out


    def playerContent(self, flag, id, vipFlags):
        u = _to_text(id).strip()
        ck = ""
        t = _parse_token(u)
        if t is not None:
            if t["kind"] == "group":
                files = self._group_files(t["id"])
                out = {"jx": "0", "parse": "0", "url": "", "header": {}}
                if DEBUG:
                    out["_debug"] = "这是合集，共%d集" % len(files)
                return out
            if t["kind"] == "folder":
                files = self._walk(t["id"])
                out = {"jx": "0", "parse": "0", "url": "", "header": {}}
                if DEBUG:
                    out["_debug"] = "这是目录，共%d个视频" % len(files)
                return out
            r = self._downurl(t["id"])
            u = r["url"]
            ck = r.get("cookie", "")
            if not u:
                print("[115] 取址失败: %s (pickcode=%s)" % (r.get("msg"), t["id"]))
                out = {"jx": "0", "parse": "0", "url": "", "header": {}}
                if DEBUG:
                    out["_debug"] = "115: " + str(r.get("msg"))
                return out
        # 只带 115 给这一次直链签发的 auth_cookie，绝不塞整串登录 Cookie
        h = {"User-Agent": BROWSER_UA, "Referer": "https://115.com/"}
        if ck:
            h["Cookie"] = ck
        return {"jx": "0", "parse": "0", "url": u, "header": h}


    def diag_play(self, tok):
        t = _parse_token(_to_text(tok).strip())
        if t is None:
            return {"ok": 0, "msg": "token 解析失败", "tok": _to_text(tok)[:60]}
        if t["kind"] == "group":
            show = t["id"][6:] if t["id"].startswith("GROUP:") else t["id"]
            files = []
            for pno in (1, 2, 3):
                rr = self._search_files(show, pno)
                for it in rr["list"]:
                    if _is_folder(it):
                        continue
                    nm = _item_name(it).lower()
                    if not any(nm.endswith(e) for e in VIDEO_EXTS):
                        continue
                    try:
                        if int(it.get("s") or it.get("size") or 0) < MIN_VIDEO_SIZE:
                            continue
                    except Exception:
                        pass
                    full = _item_name(it)
                    if _show_name(full) != show:
                        continue
                    pc = _to_text(it.get("pc") or it.get("pick_code") or it.get("pickcode") or "")
                    if pc:
                        files.append({"name": full, "pc": pc})
                if len(rr["list"]) < SEARCH_LIMIT:
                    break
            if not files:
                row = {"vod_id": raw, "vod_name": show, "vod_pic": VIDEO_PIC,
                       "vod_remarks": "目录", "vod_content": "",
                       "vod_play_from": PLAY_FROM, "vod_play_url": ""}
                return {"list": [row]}
            files.sort(key=lambda f: _sort_key(f["name"]))
            lines = ["%s$%s" % (_ep_name(f["name"]), _token(f["name"], f["pc"], "file"))
                     for f in files]
            row = {"vod_id": raw, "vod_name": show, "vod_pic": VIDEO_PIC,
                   "vod_remarks": "共%d集" % len(files),
                   "vod_content": "",
                   "vod_play_from": PLAY_FROM, "vod_play_url": "#".join(lines)}
            return {"list": [row]}

        if t["kind"] == "folder":
            files = self._walk(t["id"])
            return {"ok": 1 if files else 0, "kind": "folder",
                    "files": len(files), "sample": files[:3]}
        r = self._downurl(t["id"])
        return {"ok": 1 if r["url"] else 0, "kind": "file",
                "pickcode": t["id"], "url": r["url"][:90], "msg": r["msg"]}

    def action(self, action):
        return ""

    def diag(self):
        r = self._list_dir("0", 1) if self.cookie else None
        return {"cookie": "未填" if not self.cookie else ("已填 %d 字节" % len(self.cookie)),
                "root": "跳过" if r is None else ("OK %d 项/共 %d" % (len(r["list"]), r["count"])
                                                 if r["list"] else ("FAIL " + self.last_err))}


Spider = Spider
