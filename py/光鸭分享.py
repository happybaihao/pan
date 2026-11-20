#!/usr/bin/python
# -*- coding: utf-8 -*-
import re, json, base64, sys, time
import requests
from urllib.parse import quote, urljoin, urlparse, parse_qs
try:
    from base.spider import Spider
except Exception:  # 本地离线调试用
    class Spider(object):
        pass


def _log(enabled, *a):
    if enabled:
        try:
            sys.stderr.write("[光鸭] " + " ".join(str(x) for x in a) + "\n")
        except Exception:
            pass


class Spider(Spider):
    def getName(self):
        return "光鸭·臻影社"

    def init(self, extend=""):
        self.host = "https://www.guangya.net"
        self.api = self.host + "/wp-json/wp/v2"
        self.pan_host = "https://www.guangyapan.com"
        self.pan_api = "https://api.guangyapan.com"
        self.cookie = ""
        self.pan_auth = ""           # 光鸭网盘 access_token（或整段 "Bearer xxx"）
        self.pan_device_id = ""      # 光鸭网盘 X-Device-Id（jar 里是扫码生成的设备ID）
        self.comment = "感谢分享资源"
        self.debug = False
        self.auto_comment = False  # 是否允许自动发评论解锁（默认关，需显式开启）
        # 网盘直连模式：mode="netdisk" 时，直接列出你自己网盘里的视频并播放，
        # 完全绕开 www.guangya.net 的 WAF / 评论墙。需在 ext 里提供 pan_auth（网盘 Bearer token）。
        self.mode = "site"           # site | netdisk | sharelist(分享清单播放)
        self.netdisk_root = ""       # 网盘根目录 parentId，留空=网盘根目录
        self.netdisk_folders = []    # 可选：指定要作为分类展示的文件夹 [{id,name}]
        self.share_txt = ""          # 方案2：分享链接清单 txt（http(s) 或本地路径）
        self.use_member = True       # 填了 pan_auth 时是否启用会员直链增强（可设 0 关闭）
        self._share_items = None     # 清单解析缓存
        self.ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
        # 顶级分类 -> WP category ID（实测 2026-11）
        self.cat_ids = {
            "movie": 1,        # 电影
            "tv-series": 3,    # 剧集
            "anime": 7,        # 动漫
            "variety": 4,      # 综艺
            "documentary": 9,  # 纪录片
            "music": 27,       # 音乐
            "collection": 11752,  # 资源合集
        }
        self.classes = {
            "movie": "电影", "tv-series": "电视剧", "anime": "动漫",
            "variety": "综艺", "documentary": "纪录片", "music": "音乐",
            "collection": "合集",
        }
        self.session = requests.Session()
        self.session.verify = False
        try:
            requests.packages.urllib3.disable_warnings(
                requests.packages.urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass

        if extend:
            try:
                c = json.loads(extend)
                self.cookie = c.get("cookie", "") or c.get("site_cookie", "") or ""
                self.pan_auth = c.get("pan_auth", "") or c.get("auth", "") or ""
                self.pan_device_id = c.get("pan_device_id", "") or c.get("device_id", "") or ""
                self.comment = c.get("comment", "") or self.comment
                if c.get("ua"):
                    self.ua = c.get("ua")
                self.debug = str(c.get("debug", "0")) == "1"
                self.auto_comment = str(c.get("auto_comment", "0")) == "1"
                self.mode = c.get("mode", "site") or "site"
                self.netdisk_root = c.get("netdisk_root", "") or ""
                self.netdisk_folders = c.get("netdisk_folders", []) or []
                self.share_txt = c.get("share_txt", "") or c.get("share_list", "") or ""
                self.use_member = str(c.get("use_member", "1")) != "0"
            except Exception:
                self.cookie = extend

        self.hdr = {"User-Agent": self.ua, "Accept": "application/json, */*",
                    "Accept-Language": "zh-CN,zh;q=0.9"}
        if self.cookie:
            self.hdr["Cookie"] = self.cookie
        _log(self.debug, "init host=", self.host, "api=", self.api,
             "cookie长度=", len(self.cookie))

    # ---------------- 网络 ----------------
    def _api(self, path, params=None):
        """调用 wp-json，返回 (json数据, 总页数)。失败返回 ({}, 1)。"""
        try:
            url = self.api + path
            r = self.session.get(url, headers=self.hdr, params=params or {}, timeout=20,
                                 verify=False, allow_redirects=True)
            pages = int(r.headers.get("X-WP-TotalPages", "1") or 1)
            total = int(r.headers.get("X-WP-Total", "0") or 0)
            data = r.json()
            return (data, pages, total)
        except Exception as e:
            _log(self.debug, "_api 异常:", e)
            return {}, 1, 0

    def _html(self, u, ref=""):
        """抓前端 HTML（详情页取分享链接用，需要登录态 cookie）。"""
        try:
            h = dict(self.hdr)
            h["Accept"] = "text/html,application/xhtml+xml,*/*"
            h["Referer"] = ref or self.host + "/"
            r = self.session.get(u if u.startswith("http") else self.host + u,
                                 headers=h, timeout=20, verify=False, allow_redirects=True)
            r.encoding = r.apparent_encoding or "utf-8"
            txt = r.text
            if "正在解密" in txt or "Just a moment" in txt:
                _log(self.debug, "前端页被 WAF 拦截:", u)
                return ""
            return txt
        except Exception as e:
            _log(self.debug, "_html 异常:", e)
            return ""

    def _post_json(self, u, data, auth=False, ref=""):
        try:
            h = {"User-Agent": self.ua, "Accept": "application/json, text/plain, */*",
                 "Content-Type": "application/json;charset=UTF-8",
                 "Origin": self.pan_host, "Referer": ref or self.pan_host + "/", "dt": "4"}
            if auth and self.pan_auth:
                h["Authorization"] = self.pan_auth if self.pan_auth.lower().startswith("bearer ") \
                    else "Bearer " + self.pan_auth
            url = u if u.startswith("http") else self.pan_api + u
            return self.session.post(url, headers=h, data=json.dumps(data, ensure_ascii=False),
                                     timeout=20, verify=False).json()
        except Exception as e:
            _log(self.debug, "_post_json 异常:", e)
            return {}

    def _pan_headers(self, auth=True):
        """光鸭网盘 API 请求头 —— 对齐 vox.jar 反编译实证的 q()/v()。

        实证来源：vox.jar -> com.github.catvod.spider.merge.d.L
          - X-Client-Id : 硬编码 client_id = aMe-8VSlkrbQXpUR
          - X-Device-Id : 设备 ID（可用用户的，留空时用占位）
          - User-Agent  : Chrome 142 Mac
          - Referer/Origin : www.guangyapan.com
          - Authorization : {token_type} {access_token}（扫码登录后拿到）
        2026-11 实测：client_id 有效，account.guangyapan.com/v1/auth/device/code
        可正常返回 device_code/verification_url，扫码链路现役可用。
        """
        h = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
            "Referer": "https://www.guangyapan.com/",
            "Origin": "https://www.guangyapan.com",
            "X-Client-Id": "aMe-8VSlkrbQXpUR",
            "X-Device-Id": self.pan_device_id,
        }
        if auth and self.pan_auth:
            tok = self.pan_auth.strip()
            # 用户可能整段复制 "Bearer xxx"；统一成 Bearer <token>
            h["Authorization"] = tok if tok.lower().startswith(("bearer ", "basic ")) else "Bearer " + tok
        return h

    # ============ 网盘直连模式（mode=netdisk，绕开站点 WAF/评论墙）============
    def _pan(self, path, data, auth=True):
        """调用光鸭网盘 API，参数对齐 vox.jar 实证。"""
        try:
            url = path if path.startswith("http") else self.pan_api + path
            r = self.session.post(url, headers=self._pan_headers(auth),
                                  data=json.dumps(data, ensure_ascii=False), timeout=20)
            j = r.json()
            _log(self.debug, "_pan", path, "->", str(j)[:200])
            return j
        except Exception as e:
            _log(self.debug, "_pan 异常:", e)
            return {}

    def _pan_authed(self):
        return bool(self.pan_auth)

    def _pan_list(self, parent_id="", page=0, size=50):
        """列自己网盘某文件夹下的文件/文件夹。
        端点/请求体对齐 vox.jar: nd.bizuserres.s/v1/file/get_file_list
        body: {orderBy:3, page:n, pageSize:50, parentId, sortType:1}
        resType: 2=文件夹, 1=视频文件。返回 (视频项列表, 文件夹列表, hasMore)。
        """
        j = self._pan("/nd.bizuserres.s/v1/file/get_file_list", {
            "orderBy": 3, "page": page, "pageSize": size,
            "parentId": parent_id or "", "sortType": 1,
        })
        data = j.get("data") or {}
        vids, dirs = [], []
        for it in (data.get("list") or []):
            fid = str(it.get("fileId", ""))
            name = it.get("fileName") or "未命名"
            res_type = int(it.get("resType", 0) or 0)
            if res_type == 2:
                dirs.append({"id": fid, "name": name})
            elif res_type == 1 or re.search(r"\.(mp4|mkv|avi|mov|flv|wmv|m4v|ts|rmvb|webm)$", name, re.I):
                vids.append({"id": fid, "name": name, "size": int(it.get("fileSize", 0) or 0),
                             "pic": it.get("thumbnail", "")})
        has_more = bool(data.get("hasMore"))
        return vids, dirs, has_more

    def _pan_item(self, f):
        name = re.sub(r"\.(mp4|mkv|avi|mov|flv|wmv|m4v|ts|rmvb|webm)$", "", f.get("name", ""), flags=re.I)
        name = re.sub(r"\s*(2160p|1080p|720p|4K|WEB-DL|BluRay|x265|H\.265).*$", "", name, flags=re.I)
        return {"vod_id": "pf:" + self._b64e({"fileId": f.get("id"), "name": f.get("name")}),
                "vod_name": name.strip() or f.get("name"), "vod_pic": f.get("pic", ""),
                "vod_remarks": self._pan_size(f.get("size", 0))}

    def _pan_size(self, b):
        try:
            b = float(b)
        except Exception:
            return ""
        return ("%.1fGB" % (b / 1e9)) if b >= 1e9 else (("%.0fMB" % (b / 1e6)) if b >= 1e6 else "")

    def _pan_play(self, file_id):
        """拿自己网盘文件的播放直链 —— 对齐 vox.jar: L.A()/L.x()。
        A(): POST nd.bizuserres.s/v1/get_res_download_url {fileId}
             -> data.signedURL
        x(): VIP 直接单条直链；非 VIP 用本地 127.0.0.1:3334 多线程代理
             （TVBox/py 环境通常无该本地代理，故统一返回直链本身）。
        """
        j = self._pan("/nd.bizuserres.s/v1/get_res_download_url", {"fileId": file_id})
        data = j.get("data") or {}
        u = (data.get("signedURL") or data.get("downloadUrl") or data.get("url")
             or data.get("directLink") or "")
        if u:
            return u
        # 兜底：旧端点
        j2 = self._pan("/userres/v1/file/get_vod_download_url", {"fileId": file_id})
        d2 = j2.get("data") or {}
        return d2.get("signedURL") or d2.get("downloadUrl") or d2.get("url") or ""

    def netdisk_home(self):
        if not self._pan_authed():
            return {"class": [], "filters": {}, "list": [],
                    "error": "网盘直连模式需要在 ext.pan_auth 填入光鸭网盘 Bearer token"}
        classes, lst = [], []
        if self.netdisk_folders:
            for d in self.netdisk_folders:
                classes.append({"type_id": "pdir:" + self._b64e({"id": str(d.get("id", ""))}),
                                "type_name": d.get("name", "文件夹")})
        vids, dirs, _ = self._pan_list(self.netdisk_root)
        for d in dirs[:30]:
            lst.append({"vod_id": "pdir:" + self._b64e({"id": d["id"]}),
                        "vod_name": "📁 " + d["name"], "vod_pic": "", "vod_remarks": "文件夹",
                        "vod_tag": "folder"})
        for f in vids[:30]:
            lst.append(self._pan_item(f))
        return {"class": classes, "filters": {}, "list": lst}

    def netdisk_category(self, tid, pg):
        pdir = ""
        if str(tid).startswith("pdir:"):
            try:
                pdir = self._b64d(str(tid)[5:]).get("id", "")
            except Exception:
                pdir = ""
        page = int(pg) if str(pg).isdigit() else 1
        vids, dirs, has_more = self._pan_list(pdir, page - 1)
        lst = []
        for d in dirs:
            lst.append({"vod_id": "pdir:" + self._b64e({"id": d["id"]}),
                        "vod_name": "📁 " + d["name"], "vod_pic": "", "vod_remarks": "文件夹",
                        "vod_tag": "folder"})
        for f in vids:
            lst.append(self._pan_item(f))
        return {"page": page, "pagecount": page + (1 if has_more else 0),
                "limit": 100, "total": len(lst), "list": lst}

    def netdisk_search(self, key, pg):
        page = int(pg) if str(pg).isdigit() else 1
        j = self._pan("/nd.bizuserres.s/v1/file/search_files", {
            "name": key, "page": page - 1, "pageSize": 50,
        })
        data = j.get("data") or {}
        out = []
        for it in (data.get("list") or []):
            fid = str(it.get("fileId", ""))
            name = it.get("fileName") or ""
            if int(it.get("resType", 0) or 0) == 2:
                continue
            if not re.search(r"\.(mp4|mkv|avi|mov|flv|wmv|m4v|ts|rmvb|webm)$", name, re.I):
                continue
            out.append(self._pan_item({"id": fid, "name": name,
                                       "size": it.get("fileSize", 0),
                                       "pic": it.get("thumbnail", "")}))
        return {"page": page, "pagecount": page + (1 if (data.get("hasMore") or data.get("list")) else 0),
                "limit": 100, "total": len(out), "list": out}

    # ============ 方案2：分享链接清单播放（mode=sharelist，免用户token）============
    def _load_share_list(self):
        """读取分享清单 txt。每行：`片名 分享链接 [提取码]`。
        支持 http(s) 链接与本地路径。返回 [{name, share_url, code}]。
        """
        if self._share_items is not None:
            return self._share_items
        raw = ""
        src = str(self.share_txt or "").strip()
        if not src:
            self._share_items = []
            return self._share_items
        try:
            if src.startswith("http://") or src.startswith("https://"):
                r = self.session.get(src, headers={"User-Agent": self.ua}, timeout=20, verify=False)
                r.encoding = r.apparent_encoding or "utf-8"
                raw = r.text
            else:
                with open(src, "r", encoding="utf-8") as f:
                    raw = f.read()
        except Exception as e:
            _log(self.debug, "_load_share_list 读取失败:", e)
            self._share_items = []
            return self._share_items
        items = []
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # 找分享链接（guangyapan.com/s/ 或 golink=）
            m = re.search(r'https?://[^\s"\'<>]*guangyapan\.com/s/[^\s"\'<>]+', line)
            if not m:
                m = re.search(r'https?://[^\s"\'<>]+\?golink=[A-Za-z0-9_\-=%]+', line)
            if not m:
                continue
            url = m.group(0).replace("&amp;", "&")
            # 链接前面那段当片名，后面剩余第一段当提取码
            head = line[:m.start()].strip(" -_·|\t")
            tail = line[m.end():].strip()
            toks = tail.split()
            code = toks[0] if toks else ""
            if not code or len(code) > 12 or "/" in code:
                code = ""
            su = self._share_url(url)
            items.append({"name": head or "光鸭分享", "share_url": su or url,
                          "code": code, "id": self._sid(su or url)})
        self._share_items = items
        _log(self.debug, "_load_share_list:", len(items), "条")
        return items

    def _share_list_vod(self, it):
        return {"vod_id": "sl:" + self._b64e({"u": it["share_url"], "c": it.get("code", ""), "n": it["name"]}),
                "vod_name": it["name"], "vod_pic": "", "vod_remarks": "光鸭分享"}

    def sharelist_home(self):
        items = self._load_share_list()
        if not items:
            return {"class": [], "filters": {}, "list": [],
                    "error": ("方案2需在 ext.share_txt 配置分享清单txt地址（http或本地路径）；"
                              "清单每行：片名 分享链接 [提取码]")}
        return {"class": [{"type_id": "all", "type_name": "全部"}], "filters": {},
                "list": [self._share_list_vod(it) for it in items[:60]]}

    def sharelist_category(self, tid, pg):
        items = self._load_share_list()
        page = int(pg) if str(pg).isdigit() else 1
        start = (page - 1) * 60
        return {"page": page, "pagecount": max(1, (len(items) + 59) // 60),
                "limit": 60, "total": len(items),
                "list": [self._share_list_vod(it) for it in items[start:start + 60]]}

    def sharelist_search(self, key, pg):
        items = self._load_share_list()
        if key:
            items = [it for it in items if key.lower() in it["name"].lower()]
        return {"page": 1, "pagecount": 1, "limit": len(items), "total": len(items),
                "list": [self._share_list_vod(it) for it in items]}

    # ---------------- 工具 ----------------
    def _b64e(self, o):
        s = o if isinstance(o, str) else json.dumps(o, ensure_ascii=False, separators=(",", ":"))
        return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")

    def _b64d(self, s):
        try:
            return json.loads(base64.urlsafe_b64decode((s + "=" * (-len(s) % 4)).encode()).decode())
        except Exception:
            try:
                return base64.urlsafe_b64decode((s + "=" * (-len(s) % 4)).encode()).decode()
            except Exception:
                return s

    def _clean(self, s):
        s = str(s or "").replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()

    def _pic_from(self, html):
        m = re.search(r'<img[^>]+(?:data-src|data-original|src)=["\']([^"\']+)', html or "", re.S | re.I)
        return m.group(1) if m else ""

    def _post_to_vod(self, p):
        """把 WP post 对象转成播放列表卡片。"""
        title = self._clean(p.get("title", {}).get("rendered", "")) or "光鸭资源"
        title = re.sub(r"\s*[-－|·]?\s*光鸭.*$", "", title).strip()
        return {"vod_id": str(p.get("id", "")), "vod_name": title,
                "vod_pic": self._pic_from(p.get("content", {}).get("rendered", "")),
                "vod_remarks": ""}

    # ---------------- 评论解锁（zibll 评论后可见，尽力而为） ----------------
    def _hidden(self, h):
        return ("此处内容已隐藏" in h or "评论后刷新" in h or "请评论" in h
                or "reply-show" in h or "hidden-box" in h or "评论后" in h or "回复后" in h)

    def _form_value(self, h, name):
        m = (re.search(r'name=["\']' + re.escape(name) + r'["\'][^>]*value=["\']([^"\']*)', h, re.I)
             or re.search(r'value=["\']([^"\']*)["\'][^>]*name=["\']' + re.escape(name) + r'["\']', h, re.I))
        return m.group(1) if m else ""

    def _unlock(self, url, h):
        """尝试发评论解锁隐藏内容。
        实测：新评论多为「待审核」，审核通过前 hidden-box 仍无链接，故成功率有限。
        仅当 cookie 有效、评论被立刻批准时才可能成功。需谨慎：会给账号发公开评论。
        """
        if not self.cookie or not self._hidden(h):
            return h
        # 默认不发评论，除非配置显式开启 auto_comment=1（避免滥用/封号）
        if not getattr(self, "auto_comment", False):
            return h
        pid = self._form_value(h, "comment_post_ID")
        if not pid:
            return h
        parent = self._form_value(h, "comment_parent") or "0"
        nonce = self._form_value(h, "_wpnonce")
        data = {"comment": self.comment, "comment_post_ID": pid, "comment_parent": parent}
        if nonce:
            data["_wpnonce"] = nonce
        hd = dict(self.hdr)
        hd.update({"Referer": url, "Origin": self.host,
                   "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
        try:
            self.session.post(self.host + "/wp-comments-post.php", headers=hd, data=data,
                              timeout=20, verify=False, allow_redirects=False)
            h2 = self._html(url)
            if h2 and not self._hidden(h2):
                return h2
        except Exception as e:
            _log(self.debug, "_unlock 异常:", e)
        return h

    # ---------------- 详情：分享链接提取（需登录态 HTML） ----------------
    def _share_url(self, u):
        u = str(u or "").replace("&amp;", "&")
        if "guangyapan.com/s/" in u:
            return self._abs(u, self.pan_host + "/")
        if "golink=" in u:
            try:
                q = parse_qs(urlparse(u).query).get("golink", [""])[0].replace("-", "+").replace("_", "/")
                q += "=" * (-len(q) % 4)
                x = base64.b64decode(q.encode()).decode().strip()
                return x if x.startswith("http") else ""
            except Exception:
                return ""
        if re.search(r'(xunlei\.qsxy\.top|pan\.quark\.cn|www\.aliyundrive\.com|alipan\.com|115\.com|pan\.baidu\.com|caiyun\.app\.mi\.com|lanzou)', u):
            m = re.search(r'https?://[^\s"\'<>]+', u)
            if not m:
                return ""
            pp = urlparse(m.group(0))
            return m.group(0) if (pp.path.strip("/") or pp.query) else ""
        return ""

    def _abs(self, u, base=None):
        return urljoin(base or self.host + "/", str(u or "")) if u else ""

    def _shares(self, html):
        out, seen = [], set()
        pats = [
            r"https?://[^\s\"'<>]+guangyapan\.com/s/[^\s\"'<>]+",
            r"https?://[^\s\"'<>]+\?golink=[A-Za-z0-9_\-=%]+",
            r"https?://[^\s\"'<>]*(?:xunlei\.qsxy\.top|pan\.quark\.cn|www\.aliyundrive\.com|alipan\.com|115\.com|pan\.baidu\.com|caiyun\.app\.mi\.com|lanzou\.[a-z]+)[^\s\"'<>]*",
            r"(?:href|data-clipboard-text|data-url|data-link|data-href)=[\"']([^\"']+)[\"']",
        ]
        for p in pats:
            for u in re.findall(p, html, re.I):
                if re.search(r'guangya\.net/(user|wp-|category|author|newposts|rank|calendar)', u) \
                        or re.search(r'guangya\.net/[^"\']+\.html', u) \
                        or 't.me/' in u or 'pd.qq.com' in u or 'weibo' in u or 'qzone' in u:
                    continue
                su = self._share_url(u)
                if su and su not in seen:
                    seen.add(su)
                    out.append(su)
        _log(self.debug, "_shares:", len(out))
        return out

    def _sid(self, u):
        m = re.search(r"/s/([^/?#]+)", u)
        return m.group(1) if m else ""

    def _code(self, u):
        try:
            q = parse_qs(urlparse(u).query)
            return (q.get("code") or q.get("pwd") or [""])[0]
        except Exception:
            return ""

    def _pan_files(self, su):
        sid, code = self._sid(su), self._code(su)
        if not sid:
            return []
        tok = self._post_json("/userres/v1/get_share_access_token",
                              {"shareId": sid, **({"code": code} if code else {})},
                              False, self.pan_host + "/s/" + sid).get("data", {}).get("accessToken", "")
        if not tok:
            return []
        res, stack, seen = [], [""], set()
        for _ in range(4):
            if not stack:
                break
            pid = stack.pop(0)
            data = self._post_json("/userres/v1/get_share_page_files_list",
                                   {"accessToken": tok, "pageSize": 200, "orderBy": 0,
                                    "sortType": 0, "parentId": pid},
                                   False, self.pan_host + "/s/" + sid).get("data", {})
            lst = data.get("list", []) if isinstance(data.get("list", []), list) else []
            for it in lst:
                fid = str(it.get("fileId", "")).strip()
                name = str(it.get("fileName", "")).strip()
                rt = int(it.get("resType", 0) or 0)
                if not fid or fid in seen:
                    continue
                seen.add(fid)
                if rt == 2:
                    stack.append(fid)
                elif rt == 1 and re.search(r"\.(mp4|mkv|avi|mov|wmv|flv|m4v|ts|m2ts|webm|m3u8)$", name, re.I):
                    g = re.search(r"screenshot-thumbnails/([A-Fa-f0-9]{20,})/",
                                  str(it.get("thumbnail", "")) + str(it.get("gcid", "")))
                    res.append({"shareId": sid, "shareURL": su, "code": code, "fileId": fid,
                                "fileName": name, "gcid": g.group(1) if g else "",
                                "size": it.get("fileSize", 0)})
        return res

    def _share_token(self, sid, code, su=""):
        """拿分享 accessToken（只认分享链接，不需要用户 token）。"""
        return self._post_json("/userres/v1/get_share_access_token",
                               {"shareId": sid, **({"code": code} if code else {})},
                               False, su or (self.pan_host + "/s/" + sid)) \
            .get("data", {}).get("accessToken", "")

    def _member_play(self, f):
        """★会员直链增强：完全对齐 vox.jar 反编译的播放链路，用你自己的 token 身份拿直链。

        jar 实证(com.github.catvod.spider.merge.d.L: s()->z()->restore_share, x()->A()):
          1) get_share_access_token        拿分享 token（免用户 token）
          2) restore_share                 把文件转存到自己网盘根目录（带用户 token, q()）
          3) get_file_list                 在根目录按文件名找到转存后的 fileId（带用户 token）
          4) get_res_download_url          拿 signedURL（带用户 token, q()/A()）
        返回 signedURL；任何一步失败返回 ''，由 playerContent 回退免 token 直链。
        """
        if not self.pan_auth or not self.use_member:
            return ""
        try:
            sid = str(f.get("shareId", ""))
            fid = str(f.get("fileId", ""))
            name = str(f.get("fileName", ""))
            code = f.get("code", "")
            su = f.get("shareURL", "")
            if not sid or not fid:
                return ""
            # 1) 分享 token
            stok = self._share_token(sid, code, su)
            if not stok:
                _log(self.debug, "member: 分享token失败")
                return ""
            # 2) restore_share 转存（用 q() 头 = 带用户 token）
            rr = self._pan("/userres/v1/restore_share", {
                "accessToken": stok, "fileIds": [fid], "parentId": ""
            }, auth=True)
            _log(self.debug, "member restore_share:", str(rr)[:160])
            # jar 判 success；部分返回 code=0 也算成功
            msg = str(rr.get("msg", "")).lower()
            if msg and msg not in ("success", "ok") and rr.get("code") not in (0, 200):
                _log(self.debug, "member: 转存失败", msg)
                return ""
            # 3) 列根目录，按文件名找转存后的 fileId
            time.sleep(1.2)  # jar 里 g(2000L)，等转存落地
            real_fid = ""
            for pg in range(0, 5):
                jl = self._pan("/nd.bizuserres.s/v1/file/get_file_list", {
                    "orderBy": 3, "page": pg, "pageSize": 100,
                    "parentId": "", "sortType": 1,
                }, auth=True)
                data = jl.get("data") or {}
                lst = data.get("list", []) if isinstance(data, dict) else []
                for it in lst:
                    it_name = str(it.get("fileName", ""))
                    it_fid = str(it.get("fileId", ""))
                    if (name and it_name.lower() == name.lower()) or it_fid == fid:
                        real_fid = it_fid
                        break
                if real_fid or not (isinstance(data, dict) and data.get("hasMore")):
                    break
            if not real_fid:
                real_fid = fid  # 兜底：直接用原 fileId 试
            _log(self.debug, "member real_fid:", real_fid)
            # 4) get_res_download_url（A()：带用户 token）
            ju = self._pan("/nd.bizuserres.s/v1/get_res_download_url",
                           {"fileId": real_fid}, auth=True)
            d = ju.get("data") or {}
            u = d.get("signedURL") or d.get("downloadUrl") or d.get("url", "") if isinstance(d, dict) else ""
            if u:
                _log(self.debug, "member: 拿到 signedURL")
                return u
            # 兼容 userres/v1 老端点
            ju2 = self._pan("/userres/v1/get_res_download_url",
                            {"fileId": real_fid}, auth=True)
            d2 = ju2.get("data") or {}
            u2 = d2.get("signedURL") or d2.get("downloadUrl") or d2.get("url", "") if isinstance(d2, dict) else ""
            return u2 or ""
        except Exception as e:
            _log(self.debug, "member_play 异常:", e)
            return ""

    # ---------------- 标准接口（全部走 REST API） ----------------
    def homeContent(self, filter):
        if self.mode == "sharelist":
            return self.sharelist_home()
        if self.mode == "netdisk":
            return self.netdisk_home()
        posts, _, _ = self._api("/posts", {"per_page": 30, "page": 1})
        return {"class": [{"type_id": k, "type_name": v} for k, v in self.classes.items()],
                "filters": {}, "list": [self._post_to_vod(p) for p in posts]}

    def homeVideoContent(self):
        if self.mode == "sharelist":
            return {"list": self.sharelist_home().get("list", [])}
        if self.mode == "netdisk":
            return {"list": self.netdisk_home().get("list", [])}
        posts, _, _ = self._api("/posts", {"per_page": 30, "page": 1})
        return {"list": [self._post_to_vod(p) for p in posts]}

    def categoryContent(self, tid, pg, filter, extend):
        if self.mode == "sharelist":
            return self.sharelist_category(tid, pg)
        if self.mode == "netdisk":
            return self.netdisk_category(tid, pg)
        page = int(pg) if str(pg).isdigit() else 1
        params = {"per_page": 20, "page": page}
        cid = self.cat_ids.get(str(tid))
        if cid:
            params["categories"] = cid
        posts, pages, total = self._api("/posts", params)
        _log(self.debug, "category", tid, "page", page, "->", len(posts), "条 / 共", pages, "页")
        return {"page": page, "pagecount": pages, "limit": 20, "total": total,
                "list": [self._post_to_vod(p) for p in posts]}

    def searchContent(self, key, quick, pg="1"):
        if self.mode == "sharelist":
            return self.sharelist_search(key, pg)
        if self.mode == "netdisk":
            return self.netdisk_search(key, pg)
        page = int(pg) if str(pg).isdigit() else 1
        posts = []
        if key:
            posts, pages, _ = self._api("/posts", {"search": key, "per_page": 20, "page": page})
        else:
            pages = 1
        return {"page": page, "pagecount": pages, "limit": 20, "total": 0,
                "list": [self._post_to_vod(p) for p in posts]}

    def detailContent(self, ids):
        vid = ids[0]
        # 网盘直连模式：vod_id 形如 pf:<b64{fileId,name,name}>
        if self.mode == "netdisk" or str(vid).startswith("pf:"):
            try:
                o = self._b64d(str(vid)[3:])
                fid = str(o.get("fileId", ""))
                nm = o.get("name", "") or "光鸭网盘视频"
                u = self._pan_play(fid)
                play = ("播放$" + self._b64e({"panFile": fid})) if u else ("获取直链失败$noop")
                return {"list": [{"vod_id": vid, "vod_name": re.sub(r"\.[^.]+$", "", nm),
                                  "vod_pic": "", "vod_content": "光鸭网盘直连播放",
                                  "vod_play_from": "光鸭网盘", "vod_play_url": play}]}
            except Exception as e:
                _log(self.debug, "netdisk detail 异常:", e)
                return {"list": []}
        # 方案2 分享清单：vod_id 形如 sl:<b64{u,c,n}>，展开分享里的视频文件
        if self.mode == "sharelist" or str(vid).startswith("sl:"):
            try:
                o = self._b64d(str(vid)[3:])
                su = o.get("u", "")
                nm = o.get("n", "") or "光鸭分享"
                files = self._pan_files(su)
                eps = ["选择剧集$noop"]
                for i, f in enumerate(files):
                    label = (f.get("fileName") or ("资源%d" % (i + 1))).replace("#", "＃").replace("$", "￥")
                    eps.append(label + "$" + self._b64e(f))
                if not files:
                    eps.append("打开分享页$" + self._b64e({"shareURL": su}))
                mode_txt = ("会员直链增强（用你的token，VIP可加速）" if (self.pan_auth and self.use_member)
                            else "免token直链播放")
                return {"list": [{"vod_id": vid, "vod_name": re.sub(r"\.[^.]+$", "", nm),
                                  "vod_pic": "", "vod_content": "光鸭分享（%s）" % mode_txt,
                                  "vod_play_from": "光鸭分享", "vod_play_url": "#".join(eps)}]}
            except Exception as e:
                _log(self.debug, "sharelist detail 异常:", e)
                return {"list": []}
        # 用 API 拿标题/简介（稳定、不过 WAF）
        p = {}
        vid_num = ""
        if str(vid).isdigit():
            vid_num = str(vid)
        else:
            mm = re.search(r'/(\d+)\.html', str(vid))
            if mm:
                vid_num = mm.group(1)
        if vid_num:
            one, _, _ = self._api("/posts/" + vid_num)
            p = one if isinstance(one, dict) else {}
        title = self._clean(p.get("title", {}).get("rendered", "")) or "光鸭资源"
        title = re.sub(r"\s*[-－|·]?\s*光鸭.*$", "", title).strip()
        content_html = p.get("content", {}).get("rendered", "")
        content = self._clean(content_html)
        pic = self._pic_from(content_html)
        link = p.get("link", "") or (vid if str(vid).startswith("http") else "")

        # ★隐藏链接只在「前端 HTML、评论审核通过后」出现，wp-json 拿不到。
        # 尽力尝试：带 cookie 抓前端 HTML；若未解锁且配置允许，尝试自动发评论解锁。
        # 注意：新评论多为「待审核」，审核通过前 hidden-box 无链接；且前端有 WAF，
        # 纯 requests 常被拦。因此这一步成功率有限，属尽力而为。
        shares_html = ""
        if link:
            html = self._html(link)
            if html and "正在解密" not in html:
                if "评论后刷新" in html or "此处内容已隐藏" in html:
                    html = self._unlock(link, html)  # 尝试评论解锁
                shares_html = html
        if "内容已隐藏" in content or "评论后" in content:
            content = ("%s\n【说明】资源链接为「评论后可见」，且需评论审核通过后才会显示。"
                       "本站前端有 WAF，OK影视 纯 requests 环境通常无法自动取到；"
                       "列表/搜索/分类浏览不受影响。" % content).strip()

        pf, pu = [], []
        for idx, su in enumerate(self._shares(shares_html)):
            files = self._pan_files(su)
            eps = ["点击选择$noop"]
            if files:
                for i, f in enumerate(files):
                    label = (f.get("fileName") or ("资源%d" % (i + 1))).replace("#", "＃").replace("$", "￥")
                    eps.append(label + "$" + self._b64e(f))
            else:
                eps.append("打开分享页$" + self._b64e({"shareURL": su}))
            pf.append(("光鸭云盘%d" % (idx + 1)) if files else ("网盘%d" % (idx + 1)))
            pu.append("#".join(eps))
        if not pf:
            pf = ["详情页"]
            pu = ["打开详情页$" + self._b64e({"page": link or vid})]
        return {"list": [{"vod_id": vid, "vod_name": title, "vod_pic": pic,
                          "vod_content": content, "vod_play_from": "$$$".join(pf),
                          "vod_play_url": "$$$".join(pu)}]}

    def playerContent(self, flag, id, vipFlags):
        if not id or id == "noop":
            return {"parse": 1, "jx": 0, "url": ""}
        o = self._b64d(id)
        # 网盘直连：拿自己网盘文件的播放直链
        if isinstance(o, dict) and o.get("panFile"):
            u = self._pan_play(str(o.get("panFile")))
            if u:
                return {"parse": 0, "jx": 0, "url": u,
                        "header": json.dumps({"User-Agent": self.ua, "Referer": self.pan_host + "/"})}
            return {"parse": 1, "jx": 0, "url": ""}
        if isinstance(o, dict) and o.get("page"):
            return {"parse": 1, "jx": 0, "url": o.get("page", "")}
        if isinstance(o, dict) and o.get("shareURL") and not o.get("fileId"):
            return {"parse": 0, "jx": 0, "url": "push://" + o.get("shareURL", "")}
        if isinstance(o, dict) and o.get("shareId") and o.get("fileId"):
            su = o.get("shareURL", "")
            hdr = json.dumps({"User-Agent": self.ua, "Referer": self.pan_host + "/"})
            # ① 填了 pan_auth → 优先会员直链增强（用你自己账号身份，VIP 可享不限速）
            if self.pan_auth and self.use_member:
                mu = self._member_play(o)
                if mu:
                    return {"parse": 0, "jx": 0, "url": mu, "header": hdr}
            # ② 免 token 分享直链（任何人都可用）
            tok = self._share_token(str(o.get("shareId", "")), o.get("code", ""), su)
            if tok:
                u = self._post_json("/userres/v1/get_share_download_url",
                                    {"accessToken": tok, "fileId": o.get("fileId")},
                                    False, su).get("data", {}).get("downloadUrl", "")
                if u:
                    return {"parse": 0, "jx": 0, "url": u}
            # ③ 填了 token 且有 gcid → get_vod_download_url（另一条带身份线路）
            if self.pan_auth and o.get("gcid"):
                u = self._post_json("/userres/v1/file/get_vod_download_url",
                                    {"fileId": o.get("fileId"), "gcid": o.get("gcid")},
                                    True, su).get("data", {}).get("signedURL", "")
                if u:
                    return {"parse": 0, "jx": 0, "url": u}
            # ④ 兜底：交给播放器打开分享页
            return {"parse": 0, "jx": 0, "url": "push://" + su}
        return {"parse": 0, "jx": 0, "url": ""}
