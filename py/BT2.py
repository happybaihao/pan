# -*- coding: utf-8 -*-
# ============================================================
#  两个BT影视 (www.bttwo.top) —— t3py / type=3 Python 源
#  适配: 蜂蜜影视 / 影视TV(FongMi) 的 py 源, 以及影视壳 t3py(type=12)
#
#  能力: 分类浏览 / 多维筛选(类型·地区·年份·排序) / 搜索 / 详情 /
#        剧集选集(长剧集分页) / m3u8 直链播放
#
#  关于播放: 该站播放地址不是写死在页面里的, 是前端 wasm 现算签名再换的。
#           本源已经把签名算法完整还原成纯 Python(见 _sign), 不需要跑 wasm。
#           万一签名接口改版/挂掉, 会自动退化成"交给壳子嗅探"模式, 不会黑屏。
#
#  ext 用法(源配置的 ext 里填, 可留空):
#    {"parse": 1}   强制走壳子嗅探(不直连取 m3u8)
#    {"host": "https://www.bttwo.xxx"}  换域名
# ============================================================
import base64
import gzip
import hashlib
import json
import re
import time
from urllib.parse import quote, urlencode

try:
    import requests
except Exception:                # 壳子外纯 python 兜底
    requests = None

try:
    from base.spider import Spider as _BaseSpider
except Exception:                # 本地调试兜底, 壳子里会自动走上面那行
    class _BaseSpider(object):
        pass


class Spider(_BaseSpider):

    # ================= 可改配置区 =================
    host = "https://www.bttwo.life"          # 主站(站方发布页: bttwo.vip, 换域名改这行)
    name = "两个BT影视"
    ua = ("Mozilla/5.0 (Linux; Android 12; SM-G991B) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36")
    timeout = 20
    page_size = 24                           # 列表每页条数(站点固定 24)

    # 签名相关(站点前端同款常量, 不要改)
    _key = b"nbmovie2024secretkey"
    _mask_a = 0x36
    _mask_b = 0x5C

    # 分类 -> 站点 classify 编号
    CLASSES = [
        {"type_id": "1", "type_name": "电影"},
        {"type_id": "2", "type_name": "电视剧"},
        {"type_id": "3", "type_name": "动漫"},
        {"type_id": "4", "type_name": "综艺"},
    ]

    SORTS = [
        {"n": "最近更新", "v": "update_time"},
        {"n": "最多播放", "v": "hits"},
        {"n": "评分最高", "v": "score"},
    ]

    # 筛选面板缓存(站点筛选编号可能变, 直接从站上抓, 不用写死)
    _panel = None
    _panel_ts = 0
    _panel_ttl = 3600
    # =============================================

    def __init__(self):
        try:
            super().__init__()
        except Exception:
            pass
        self.extend = ""
        self.force_parse = False
        self._sess = None
        if requests is not None:
            self._sess = requests.Session()
            self._sess.headers.update({
                "User-Agent": self.ua,
                "Accept-Language": "zh-CN,zh;q=0.9",
            })
            try:
                self._sess.verify = False
            except Exception:
                pass

    # ---------------- 生命周期 ----------------
    def init(self, extend=""):
        """ext 可为空; 也支持 {"parse":1} / {"host":"https://..."} / 直接给个新域名"""
        if extend is None:
            extend = ""
        if not isinstance(extend, str):
            try:
                extend = json.dumps(extend)
            except Exception:
                extend = ""
        self.extend = (extend or "").strip()
        if self.extend.startswith("http"):
            self.host = self.extend.rstrip("/")
        elif self.extend:
            try:
                cfg = json.loads(self.extend)
                if isinstance(cfg, dict):
                    if cfg.get("host"):
                        self.host = str(cfg["host"]).rstrip("/")
                    self.force_parse = bool(cfg.get("parse"))
            except Exception:
                pass
        return ""

    def getName(self):
        return self.name

    def getDependence(self):
        return []

    def isVideoFormat(self, url):
        u = (url or "").lower()
        return any(k in u for k in (".m3u8", ".mp4", ".flv", ".mkv", ".ts"))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        try:
            if self._sess is not None:
                self._sess.close()
        except Exception:
            pass

    # ---------------- 网络 ----------------
    def _headers(self, referer=None):
        return {
            "User-Agent": self.ua,
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": referer or (self.host + "/"),
        }

    def _get_text(self, url, referer=None):
        """取网页/接口原文, 自动解 gzip; 失败重试一次"""
        if url.startswith("/"):
            url = self.host + url
        last = None
        for _ in range(2):
            try:
                if self._sess is not None:
                    r = self._sess.get(url, headers=self._headers(referer), timeout=self.timeout)
                    if r.status_code == 200:
                        r.encoding = r.encoding or "utf-8"
                        return r.text
                    continue
                import ssl
                import urllib.request
                ctx = ssl.create_default_context()
                try:
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                except Exception:
                    pass
                req = urllib.request.Request(url, headers=self._headers(referer))
                with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as resp:
                    raw = resp.read()
                    if resp.headers.get("Content-Encoding") == "gzip":
                        raw = gzip.decompress(raw)
                    return raw.decode("utf-8", "ignore")
            except Exception as e:
                last = e
        try:
            print("bttwo _get_text error:", url, last)
        except Exception:
            pass
        return ""

    def _get_json(self, url, referer=None):
        t = self._get_text(url, referer)
        if not t:
            return {}
        try:
            return json.loads(t)
        except Exception:
            return {}

    # ---------------- 页面解析 ----------------
    _CARD_RE = re.compile(r'<a href="/play/([^"]+)"[^>]*>(.*?)</a>', re.S)
    _TAG_RE = re.compile(r"<[^>]+>")

    def _clean(self, s):
        s = self._TAG_RE.sub(" ", s or "")
        return re.sub(r"\s+", " ", s).strip()

    def _parse_cards(self, html):
        """列表/搜索/首页通用: 解析成 vod 卡片(自动去重)"""
        out, seen = [], set()
        for slug, inner in self._CARD_RE.findall(html or ""):
            if slug in seen:
                continue
            m = re.search(r'alt="([^"]*)"', inner)
            p = re.search(r'data-src="([^"]+)"', inner)
            if not m or not p:
                continue
            title = self._clean(m.group(1))
            if not title:
                continue
            seen.add(slug)
            pic = p.group(1).replace("&amp;", "&")
            marks = ""
            sp = re.findall(r"<span[^>]*>\s*([^<>]{1,20}?)\s*</span>", inner, re.S)
            for s in sp:
                s = self._clean(s)
                if s and s not in ("播放", "详情"):
                    marks = s
                    break
            if not marks:
                y = re.search(r'px-2 py-1 rounded">\s*(\d{4})\s*<', inner)
                marks = y.group(1) if y else ""
            out.append({
                "vod_id": slug,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": marks,
            })
        return out

    # ---------------- 签名 & 播放 ----------------
    def _sign(self, dataid, secret, ts):
        """前端 wasm 同款签名(已还原成纯 Python)
        注意: ts 用【秒】级时间戳, 服务端校验的是秒"""
        vb = (secret or "").encode("utf-8")
        if len(vb) < 64:
            pad = vb + b"\x00" * (64 - len(vb))
        else:
            pad = vb[:64]
        a = bytes(b ^ self._mask_a for b in pad)
        b2 = bytes(b ^ self._mask_b for b in pad)
        # ★ 用秒级时间戳构造 msg
        msg = ("%s:%d:%s" % (dataid, int(ts), secret)).encode("utf-8")
        d1 = hashlib.sha256(a + msg).digest()
        return hashlib.sha256(b2 + d1).hexdigest()[:32]

    def _enc_key(self, userlink):
        """播放令牌: base64(XOR(userlink, 站点KEY))"""
        raw = bytes(b ^ self._key[i % len(self._key)]
                    for i, b in enumerate((userlink or "").encode("utf-8")))
        return base64.b64encode(raw).decode("ascii")

    def _page_ctx(self, slug):
        """从播放页取 userlink / 服务器时间(每页都有)"""
        html = self._get_text("/play/" + slug)
        if not html:
            return "", 0
        # ★ 兼容 x-data 里 userlink:'xxx' 的写法
        ul = re.search(r"userlink\s*:\s*'([^']*)'", html)
        st = re.search(r'id="nb-st"\s+content="(\d+)"', html)
        try:
            st_v = int(st.group(1)) if st else 0
        except Exception:
            st_v = 0
        return (ul.group(1) if ul else ""), st_v

    def _play_url(self, dataid, secret):
        """直连换 m3u8; 设备时钟不准时自动改用站点服务器时间重试"""
        userlink, st = self._page_ctx(secret)
        if not userlink:
            return ""
        now_ms = int(time.time() * 1000)
        tries_ms = [now_ms]
        # 页面上的 nb-st 是站点服务器时间(ms), 本地时钟偏太多时拿它兜底
        if st and abs(st - now_ms) > 30000:
            tries_ms = [st, now_ms]
        for ts_ms in tries_ms:
            ts_s = ts_ms // 1000                # ★ 秒
            q = urlencode({
                "p": str(dataid), "v": secret, "q": "1080",
                "s": self._sign(dataid, secret, ts_s),   # ★ 秒签名
                "t": str(ts_s),                          # ★ 秒参数
                "k": self._enc_key(userlink),
            })
            j = self._get_json("/video/play?" + q,
                               referer="%s/play/%s" % (self.host, secret))
            data = (j or {}).get("data") or {}
            qs = data.get("quality_urls") or []
            best = ""
            for item in qs:                            # 优先没锁的, 画质高的先给
                u = (item.get("url") or "").strip()
                if not u.startswith("http") or item.get("locked"):
                    continue
                best = u
                break
            if not best:                               # 全锁了就退回第一个能用的
                for item in qs:
                    u = (item.get("url") or "").strip()
                    if u.startswith("http"):
                        best = u
                        break
            if best:
                return best
        return ""

    # ---------------- 筛选面板 ----------------
    def _filter_panel(self):
        if self._panel and (time.time() - self._panel_ts) < self._panel_ttl:
            return self._panel
        panel = {}
        try:
            html = self._get_text("/filter")
            groups = {"types": [], "areas": [], "years": []}
            seen = set()
            for m in re.finditer(r'<a href="\?([^"]+)"[^>]*>\s*([^<]{1,16}?)\s*</a>', html, re.S):
                qs, label = m.group(1), self._clean(m.group(2))
                if not label:
                    continue
                for kv in qs.replace("&amp;", "&").split("&"):
                    if "=" not in kv:
                        continue
                    k, v = kv.split("=", 1)
                    if k in groups and (k, v) not in seen:
                        seen.add((k, v))
                        groups[k].append({"n": label, "v": v})
                    break
            titles = {"types": "类型", "areas": "地区", "years": "年份"}
            for k in ("types", "areas", "years"):
                opts = [{"n": "全部", "v": ""}] + groups[k][:40]
                if len(opts) > 1:
                    panel[k] = [{"key": k, "name": titles[k], "init": "", "value": opts}]
            panel["sort_by"] = [{"key": "sort_by", "name": "排序", "init": "update_time",
                                 "value": [dict(x) for x in self.SORTS]}]
        except Exception as e:
            print("bttwo filter error:", e)
        self._panel = panel
        self._panel_ts = time.time()
        return panel

    # ---------------- 标准接口 ----------------
    def homeContent(self, filter):
        result = {"class": [dict(c) for c in self.CLASSES]}
        try:
            result["filters"] = self._filter_panel()
        except Exception as e:
            print("bttwo home filter error:", e)
        try:
            result["list"] = self._parse_cards(self._get_text("/"))
        except Exception as e:
            print("bttwo home error:", e)
            result["list"] = []
        return result

    def homeVideoContent(self):
        try:
            return {"list": self._parse_cards(self._get_text("/"))}
        except Exception as e:
            print("bttwo homeVideo error:", e)
            return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        pg_s = str(pg or "1")
        page = int(pg_s) if pg_s.isdigit() else 1
        tid = str(tid or "1")
        if tid not in ("1", "2", "3", "4"):
            tid = "1"
        params = {"classify": tid, "page": page}
        ext = extend if isinstance(extend, dict) else {}
        for k in ("types", "areas", "years", "sort_by"):
            v = ext.get(k)
            if v not in (None, "", "全部"):
                params[k] = v
        try:
            html = self._get_text("/filter?" + urlencode(params))
            cards = self._parse_cards(html)
        except Exception as e:
            print("bttwo category error:", e)
            cards = []
        more = len(cards) >= self.page_size
        return {
            "list": cards,
            "page": page,
            "pagecount": page + 1 if more else page,
            "limit": self.page_size,
            "total": (page + 1) * self.page_size if more else page * self.page_size,
        }

    def detailContent(self, ids):
        if isinstance(ids, str):
            ids = [ids]
        slug = str(ids[0]).strip() if ids else ""
        if not slug:
            return {"list": []}
        slug = slug.split("/")[-1]
        html = self._get_text("/play/" + slug)
        if not html:
            return {"list": []}

        def meta(prop):
            m = re.search(r'<meta[^>]*(?:property|name)="%s"[^>]*content="([^"]*)"' % prop, html)
            return m.group(1).replace("&amp;", "&") if m else ""

        title = meta("og:title") or ""
        title = re.sub(r"\s*-\s*第\d+集\s*$", "", title).strip()
        if not title:
            mt = re.search(r"<title>(.*?)</title>", html, re.S)
            title = self._clean(mt.group(1)) if mt else slug
            title = re.sub(r"\s*-\s*第\d+集.*$", "", title).strip()

        # 详情信息行
        rows = {}
        for k, v in re.findall(
                r'<div class="col-span-1 text-gray-500">\s*([^<]+?)\s*</div>\s*'
                r'<div class="col-span-2 text-gray-300">\s*([^<]*?)\s*</div>', html):
            rows[self._clean(k)] = self._clean(v)

        content = meta("description")
        kw = meta("keywords")
        year = ""
        area = rows.get("地区", "")
        if kw:
            parts = [p.strip() for p in kw.split(",") if p.strip()]
            for p in parts:
                if re.match(r"^(19|20)\d{2}$", p):
                    year = p
                    break
        if not year and rows.get("上映"):
            m = re.match(r"(\d{4})", rows["上映"])
            year = m.group(1) if m else ""

        # 剧集: href=/play/<secret> + handleEpisodeClick(href,'dataid',line,ep)
        eps = re.findall(
            r'href="/play/([^"]+)"\s*@click\.prevent="handleEpisodeClick\([^,]+,\s*\'(\d+)\',\s*(\d+),\s*(\d+)\)"',
            html)
        ep_list, seen_ep = [], set()
        for ep_slug, dataid, line, ep in eps:
            key = (line, ep)
            if key in seen_ep:
                continue
            seen_ep.add(key)
            ep_list.append((int(ep), "%s@%s" % (dataid, ep_slug)))
        ep_list.sort(key=lambda x: x[0])
        play_url = "#".join(["第%d集$%s" % (n, u) for n, u in ep_list])
        if not play_url:                       # 兜底: 至少能播当前页这一集
            did = re.search(r'dataid="(\d+)"', html)
            if did:
                play_url = "播放$%s@%s" % (did.group(1), slug)

        info = []
        for k in ("又名", "导演", "编剧", "主演", "类型", "地区", "语言", "上映"):
            if rows.get(k):
                info.append("%s: %s" % (k, rows[k]))
        info.append("集数: %d" % len(ep_list) if ep_list else "集数: 1")
        if content:
            info.append("")
            info.append(content)

        item = {
            "vod_id": slug,
            "vod_name": title,
            "vod_pic": meta("og:image"),
            "type_name": rows.get("类型", "").replace(" / ", "/"),
            "vod_year": year,
            "vod_area": area,
            "vod_remarks": ("更新至%d集" % len(ep_list)) if len(ep_list) > 1 else "全1集",
            "vod_actor": rows.get("主演", ""),
            "vod_director": rows.get("导演", ""),
            "vod_content": "\n".join(info),
        }
        if play_url:
            item["vod_play_from"] = "两个BT"
            item["vod_play_url"] = play_url
        return {"list": [item]}

    def searchContent(self, key, quick, pg="1"):
        pg_s = str(pg or "1")
        page = int(pg_s) if pg_s.isdigit() else 1
        try:
            url = "/search?" + urlencode({"q": key, "page": page})
            cards = self._parse_cards(self._get_text(url))
        except Exception as e:
            print("bttwo search error:", e)
            cards = []
        more = len(cards) >= self.page_size
        return {
            "list": cards,
            "page": page,
            "pagecount": page + 1 if more else page,
            "limit": self.page_size,
            "total": (page + 1) * self.page_size if more else page * self.page_size,
        }

    def playerContent(self, flag, id, vipFlags=None):
        header = {"User-Agent": self.ua, "Referer": self.host + "/"}
        raw = (id or "").strip()
        if raw.startswith("http"):                     # 已经是直链
            return {"parse": 0, "jx": 0, "url": raw, "header": header}
        if "@" not in raw:
            return {"parse": 0, "jx": 0, "url": "", "header": header, "msg": "无效的播放参数"}
        dataid, secret = raw.split("@", 1)
        page_url = "%s/play/%s" % (self.host, secret)
        if not self.force_parse:
            try:
                url = self._play_url(dataid, secret)
                if url:
                    return {"parse": 0, "jx": 0, "url": url, "header": header}
            except Exception as e:
                print("bttwo player error:", e)
        # 兜底: 交给壳子嗅探(播放页会自己拉 m3u8)
        return {"parse": 1, "jx": 0, "url": page_url, "header": header}

    # ---------------- 备用直连 ----------------
    def localProxy(self, param):
        url = ""
        if isinstance(param, dict):
            url = param.get("url") or ""
        if not url:
            return [400, "text/plain; charset=utf-8", "", {}]
        try:
            h = dict(self._headers())
            h["Referer"] = self.host + "/"
            if self._sess is not None:
                r = self._sess.get(url, headers=h, timeout=self.timeout)
                return [r.status_code,
                        r.headers.get("Content-Type") or "application/octet-stream",
                        r.content, {}]
            import urllib.request
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return [200, resp.headers.get("Content-Type") or "application/octet-stream",
                        resp.read(), {}]
        except Exception as e:
            return [500, "text/plain; charset=utf-8", str(e), {}]


# ---------------- 本地自测(部署到壳子里时不走这里) ----------------
if __name__ == "__main__":
    s = Spider()
    s.init("")
    print("== 分类 ==")
    hc = s.homeContent(True)
    print([c["type_name"] for c in hc["class"]], "首页条数:", len(hc.get("list") or []))
    print("== 分类页(电视剧 第1页) ==")
    cat = s.categoryContent("2", "1", True, {})
    for it in cat["list"][:3]:
        print("  ", it["vod_name"], it["vod_remarks"])
    print("== 搜索(斗罗大陆) ==")
    sr = s.searchContent("斗罗大陆", False, "1")
    for it in sr["list"][:3]:
        print("  ", it["vod_name"], it["vod_id"])
    if sr["list"]:
        vid = sr["list"][0]["vod_id"]
        print("== 详情 ==", vid)
        d = s.detailContent([vid])["list"][0]
        print("  ", d["vod_name"], d["vod_year"], d["vod_remarks"])
        eps = (d.get("vod_play_url") or "").split("#")
        print("   集数:", len(eps), "首集:", eps[0] if eps else "")
        if eps:
            pid = eps[0].split("$")[-1]
            print("== 播放 ==", pid)
            print("  ", s.playerContent("两个BT", pid))