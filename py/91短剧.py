# -*- coding: utf-8 -*-
"""
shturl.cc/ T4 Spider (PeekPro)
Categories: 成人短剧, 成人漫剧, 真人剧, 成人视频, 成人漫画, 成人小说
Video: m3u8 via playInitialData / playbackEndpoint API
Comic: pics:// via localProxy (fix Content-Type: binary/octet-stream -> image/jpeg)
Novel: novel:// via <article> text on reader page
Sort: /api/list/fragment?scope=...&key=...&sort=new|hot&page=N
"""
import re
import json
import math
import html as html_parser
from urllib.parse import quote, unquote
try:
    from Crypto.Cipher import AES as _AES
    _HAS_AES = True
except Exception:
    _AES = None
    _HAS_AES = False
from base.spider import Spider
class Spider(Spider):
    Host = "shturl.cc/246W5Kkc"
    # AES-128-CBC keys from crypto-worker.js for comic image decryption
    _COMIC_KEY = b"f5d965df75336270"
    _COMIC_IV = b"97b60394abc2fbe1"
    def init(self, extend=""):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            "Referer": self.Host + "/",
        }
        # ==========仅此处新增pg内置代理解析，其余全部原代码不动==========
        self.session = getattr(self, "session", None)
        if extend and isinstance(extend, dict):
            proxy = extend.get("proxy", "")
            if proxy and self.session is not None:
                self.session.proxies = {
                    "http": "http://127.0.0.1:10172",
                    "https": "http://127.0.0.1:10172"
                }
        # ==============================================================
        self.classes = [
            {"type_id": "duanju", "type_name": "成人短剧"},
            {"type_id": "manju", "type_name": "成人漫剧"},
            {"type_id": "zhenrenju", "type_name": "真人剧"},
            {"type_id": "shipin", "type_name": "成人视频"},
            {"type_id": "manhua", "type_name": "成人漫画"},
            {"type_id": "xiaoshuo", "type_name": "成人小说"},
        ]
        self.video_cates = {"duanju", "manju", "zhenrenju", "shipin"}
        self.comic_cates = {"manhua"}
        self.novel_cates = {"xiaoshuo"}
        # scope/key mapping for /api/list/fragment
        self.cate_api = {
            "duanju":    ("category", "duanju"),
            "manju":     ("category", "dongman-sm"),
            "zhenrenju": ("category", "zhibo-huifang"),
            "shipin":    ("category", "videos"),
            "manhua":    ("comic", ""),
            "xiaoshuo":  ("novel", ""),
        }
        self.filter_config = [
            {
                "key": "sort",
                "name": "排序",
                "value": [
                    {"n": "最新", "v": "new"},
                    {"n": "最热", "v": "hot"},
                ],
            }
        ]
        self.filters = {c["type_id"]: self.filter_config for c in self.classes}
    def getName(self):
        return "91成人短剧"
    def isHome(self):
        return True
    def getProxyUrl(self):
        return super().getProxyUrl()
    def homeContent(self, filter):
        return {"class": self.classes, "filters": self.filters}
    def homeVideoContent(self):
        html = self._fetch(self.Host + "/")
        return {"list": self._parse_cards(html)}
    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if str(pg).isdigit() else 1
        ext = extend or {}
        sort = ext.get("sort", "new") if isinstance(ext, dict) else "new"
        scope, key = self.cate_api.get(tid, ("category", tid))
        api_url = (
            f"{self.Host}/api/list/fragment?scope={scope}&key={key}"
            f"&sort={sort}&page={page}"
        )
        api_headers = dict(self.headers)
        api_headers["X-Requested-With"] = "fetch"
        api_headers["Referer"] = f"{self.Host}/{tid}/"
        html = self._fetch(api_url, api_headers)
        videos = self._parse_cards(html)
        # Page count: try total from surrounding page, else check API response
        pagecount = self._parse_pagecount_api(html, page, tid)
        return {
            "list": videos,
            "page": page,
            "pagecount": pagecount,
            "limit": len(videos),
            "total": pagecount * 24,
        }
    def searchContent(self, key, quick, pg):
        page = int(pg) if str(pg).isdigit() else 1
        url = f"{self.Host}/search/?keyword={quote(key)}"
        if page > 1:
            url += f"&page={page}"
        html = self._fetch(url)
        videos = self._parse_cards(html)
        total_m = re.search(r'\u5171\s*(\d+)\s*\u90e8', html)
        total_count = int(total_m.group(1)) if total_m else len(videos)
        pagecount = max(1, math.ceil(total_count / 20)) if total_count else 1
        return {
            "list": videos,
            "page": page,
            "pagecount": pagecount,
            "limit": len(videos),
            "total": total_count,
        }
    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, list) else ids
        url = f"{self.Host}/{vid}/"
        html = self._fetch(url)
        title = re.sub(
            r'<[^>]+>', '', self._extract_one(html, r'<h1[^>]*>(.*?)</h1>', '')
        ).strip()
        poster = self._extract_one(
            html, r'src="(https://91crdj\.com/media/posters/[^"]+)"', ''
        )
        eps_raw = re.findall(
            rf'<a[^>]+href="https://91crdj\.com/{re.escape(vid)}/(\d+)/"[^>]*>([^<]*)</a>',
            html
        )
        _btn_texts = {
            "\u25b6 \u7acb\u5373\u89c2\u770b",
            "\u4ece\u5934\u770b",
            "\u25b6 \u5f00\u59cb\u9605\u8bfb",
            "\u4ece\u5934\u8bfb",
        }
        seen, episodes = set(), []
        for ep_num, ep_name in eps_raw:
            name = ep_name.strip()
            if not name or name in _btn_texts:
                continue
            if ep_num in seen:
                continue
            seen.add(ep_num)
            episodes.append((name, ep_num))
        if not episodes:
            episodes = [("\u7b2c1\u96c6", "1")]
        cate = vid.split('/')[0] if '/' in vid else ''
        vod = {
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": poster,
            "vod_play_from": cate,
            "vod_play_url": "#".join(f"{n}${vid}/{num}" for n, num in episodes),
        }
        if cate in self.comic_cates:
            vod["vod_player"] = "pics"
        elif cate in self.novel_cates:
            vod["vod_player"] = "novel"
        desc = self._extract_one(
            html, r'<meta\s+name="description"\s+content="([^"]+)"', ''
        )
        if desc:
            vod["vod_content"] = html_parser.unescape(desc)
        # Extract metadata from JSON-LD
        ld_m = re.search(
            r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S
        )
        if ld_m:
            try:
                ld = json.loads(ld_m.group(1).strip())
                for item in ld.get("@graph", []):
                    if item.get("@type") == "TVSeries":
                        dp = item.get("datePublished", "")
                        if dp:
                            vod["vod_year"] = dp[:4]
                        genres = item.get("genre", [])
                        if isinstance(genres, list) and genres:
                            vod["vod_class"] = ",".join(genres)
                        break
            except Exception:
                pass
        # Score
        score_m = re.search(r'class="score"[^>]*>\xe2\x98\x85([\d.]+)', html)
        if not score_m:
            score_m = re.search(r'\u2605([\d.]+)', html)
        if score_m:
            vod["vod_score"] = score_m.group(1)
        # Tags
        tags = re.findall(
            r'<a[^>]+href="https://91crdj\.com/biaoqian/[^"]+"[^>]*>([^<]+)</a>', html
        )
        if tags:
            vod["vod_tag"] = ",".join(tags)
        return {"list": [vod]}
    def playerContent(self, flag, id, vipFlags):
        cate = id.split('/')[0] if '/' in id else ''
        url = f"{self.Host}/{id}/"
        if cate in self.video_cates:
            return self._play_video(url, id)
        elif cate in self.comic_cates:
            return self._play_comic(url)
        elif cate in self.novel_cates:
            return self._play_novel(url)
        return {"parse": 0, "url": "", "header": ""}
    # ---- localProxy for comic images ----
    def localProxy(self, param):
        """Proxy and decrypt comic images via AES-128-CBC."""
        try:
            # PeekPro may pass dict instead of str
            if isinstance(param, dict):
                params = param
            elif isinstance(param, str):
                params = dict(pair.split("=", 1) for pair in param.split("&") if "=" in pair)
            else:
                params = {}
            img_url = unquote(params.get("url", ""))
            if not img_url:
                return [404, "text/plain", b"no url"]
            headers = {
                "User-Agent": self.headers["User-Agent"],
                "Referer": self.Host + "/",
            }
            enc_data = self._fetch_raw(img_url, headers)
            if not enc_data:
                return [404, "text/plain", b"fetch failed"]
            decrypted = self._aes_decrypt(enc_data)
            if not decrypted:
                return [404, "text/plain", b"decrypt failed"]
            # Detect MIME from magic bytes
            mime = "image/jpeg"
            if decrypted[:4] == b"\x89PNG":
                mime = "image/png"
            elif decrypted[:4] == b"GIF8":
                mime = "image/gif"
            elif decrypted[:12] == b"RIFF\x00\x00\x00\x00WEBP":
                mime = "image/webp"
            return [200, mime, decrypted]
        except Exception as e:
            return [500, "text/plain", str(e).encode("utf-8")]
        return [404, "text/plain", b""]
    def proxyLocal(self, param):
        """别名兼容：部分壳端调用 proxyLocal 而非 localProxy。"""
        return self.localProxy(param)
    def _aes_decrypt(self, data):
        """AES-128-CBC 解密，多库兜底。"""
        # 1. pycryptodome
        if _HAS_AES:
            cipher = _AES.new(self._COMIC_KEY, _AES.MODE_CBC, iv=self._COMIC_IV)
            return cipher.decrypt(data)
        # 2. cryptography
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            cipher = Cipher(algorithms.AES(self._COMIC_KEY), modes.CBC(self._COMIC_IV))
            dec = cipher.decryptor()
            return dec.update(data) + dec.finalize()
        except Exception:
            pass
        # 3. pyaes
        try:
            import pyaes
            decrypter = pyaes.Decrypter(
                pyaes.AESModeOfOperationCBC(self._COMIC_KEY, iv=self._COMIC_IV)
            )
            result = decrypter.feed(data)
            result += decrypter.feed()
            return result
        except Exception:
            pass
        # 无库可用，返回原始加密数据
        return data
    # ---- Player strategies ----
    def _play_video(self, url, id):
        html = self._fetch(url)
        m = re.search(
            r'<script[^>]+id="playInitialData"[^>]*>(.*?)</script>', html, re.S
        )
        if m:
            try:
                data = json.loads(m.group(1).strip())
                src = data.get("current", {}).get("src", "")
                if src:
                    return {"parse": 0, "url": src, "header": self.headers}
            except Exception:
                pass
        parts = id.split('/')
        if len(parts) >= 3:
            vid_id = parts[1].split('-')[0]
            ep_num = parts[2]
            api_url = f"{self.Host}/videos/{vid_id}/episodes/{ep_num}/playback"
            try:
                api_resp = self._fetch(api_url)
                api_data = json.loads(api_resp)
                src = api_data.get("data", {}).get("src", "")
                if src:
                    return {"parse": 0, "url": src, "header": self.headers}
            except Exception:
                pass
        return {"parse": 0, "url": "", "header": ""}
    def _play_comic(self, url):
        """Comic type: extract lazy images, return pics:// with proxy URLs for AES decryption."""
        html = self._fetch(url)
        imgs = re.findall(
            r'<img[^>]*class="comic-page[^"]*"[^>]*data-src="([^"]+)"', html
        )
        if not imgs:
            imgs = re.findall(r'data-src="(https://pic\.[^"]+)"', html)
        if not imgs:
            imgs = re.findall(r'src="(https://pic\.[^"]+)"', html)
        clean_imgs = []
        for img_url in imgs:
            if img_url not in clean_imgs:
                clean_imgs.append(img_url)
        imgs = clean_imgs
        if imgs:
            proxy_urls = []
            for img_url in imgs:
                proxy_url = self.getProxyUrl() + "&url=" + quote(img_url, safe='')
                proxy_urls.append(proxy_url)
            return {
                "parse": 0,
                "url": "pics://" + "&&".join(proxy_urls),
                "header": "",
            }
        return {"parse": 0, "url": "", "header": ""}
    def _play_novel(self, url):
        """Novel type: extract text from <article> on reader page, return novel://."""
        html = self._fetch(url)
        article_m = re.search(r'<article[^>]*>(.*?)</article>', html, re.S)
        if not article_m:
            article_m = re.search(
                r'<div[^>]*class="[^"]*(?:content|article|chapter|text|reader)'
                r'[^"]*"[^>]*>(.*?)</div>',
                html, re.S
            )
        if article_m:
            raw = article_m.group(1)
            raw = re.sub(r'<script[^>]*>.*?</script>', '', raw, flags=re.S)
            raw = re.sub(r'<style[^>]*>.*?</style>', '', raw, flags=re.S)
            raw = re.sub(r'<h2[^>]*>.*?</h2>', '', raw, flags=re.S)
            raw = raw.replace('<br>', '\n').replace('<br />', '\n').replace('<br />', '\n')
            raw = re.sub(r'</p>', '\n\n', raw)
            text = html_parser.unescape(re.sub(r'<[^>]+>', '', raw)).strip()
            text = re.sub(r'\n{3,}', '\n\n', text)
            ch_title_m = re.search(r'<h2[^>]*class="novel-h"[^>]*>(.*?)</h2>', html, re.S)
            ch_title = re.sub(r'<[^>]+>', '', ch_title_m.group(1)).strip() if ch_title_m else ""
            if not ch_title:
                title_m = re.search(r'<title>([^<]+)</title>', html)
                ch_title = title_m.group(1).strip() if title_m else "\u6b63\u6587"
            return {
                "parse": 0,
                "url": "novel://" + json.dumps(
                    {"title": ch_title, "content": text}, ensure_ascii=False
                ),
                "header": "",
            }
        return {"parse": 0, "url": "", "header": ""}
    # ---- Helpers ----
    def _fetch(self, url, headers=None):
        hdr = headers or self.headers
        try:
            r = self.fetch(url, headers=hdr)
            return r.text if hasattr(r, 'text') else str(r)
        except Exception:
            try:
                import requests
                r = requests.get(url, headers=hdr, timeout=15, verify=False)
                return r.text
            except Exception:
                return ""
    def _fetch_raw(self, url, headers=None):
        """Fetch and return raw binary bytes."""
        hdr = headers or self.headers
        # 1) try base fetch (response object)
        try:
            r = self.fetch(url, headers=hdr)
            if hasattr(r, 'content') and hasattr(r, 'status_code') and r.status_code == 200:
                return r.content
        except Exception:
            pass
        # 2) urllib (stdlib, always available)
        try:
            import urllib.request, ssl
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(url, headers=hdr)
            resp = urllib.request.urlopen(req, timeout=15, context=ctx)
            return resp.read()
        except Exception:
            pass
        # 3) requests fallback
        try:
            import requests
            r = requests.get(url, headers=hdr, timeout=15, verify=False)
            if r.status_code == 200:
                return r.content
        except Exception:
            pass
        return None
    def _parse_cards(self, html):
        """Parse video/card items from list pages (category, search, home, API fragment)."""
        cards = re.findall(
            r'<a[^>]*class="card"[^>]*'
            r'href="https://91crdj\.com/([^/]+)/([^"]+)"[^>]*'
            r'data-track-item-name="([^"]*)"[^>]*>(.*?)</a>',
            html, re.S
        )
        videos, seen = [], set()
        for cate, item_path, name, content in cards:
            item_path = item_path.rstrip('/')
            if item_path in seen:
                continue
            seen.add(item_path)
            img = self._extract_one(
                content, r'src="(https://91crdj\.com/media/posters/[^"]+)"', ''
            )
            eps_flag = self._extract_one(
                content, r'class="[^"]*eps-flag[^"]*">([^<]+)</span>', ''
            )
            videos.append({
                "vod_id": f"{cate}/{item_path}",
                "vod_name": html_parser.unescape(name),
                "vod_pic": img,
                "vod_remarks": eps_flag,
            })
        return videos
    def _parse_pagecount_api(self, html, current_page, tid):
        """Parse page count from API fragment response."""
        # API fragment includes pager HTML with data-pages attribute
        pages_m = re.search(r'data-pages="(\d+)"', html)
        if pages_m:
            return int(pages_m.group(1))
        # Fallback: look for page links
        pages = re.findall(r'data-page="(\d+)"', html)
        if pages:
            return max(int(p) for p in pages)
        # Fallback: check total count from category page
        total_m = re.search(r'\u5171\s*(\d+)\s*\u90e8', html)
        if total_m:
            total = int(total_m.group(1))
            return max(1, math.ceil(total / 24))
        return current_page
    def _extract_one(self, text, pattern, default=""):
        m = re.search(pattern, text, re.S)
        return m.group(1) if m else default
