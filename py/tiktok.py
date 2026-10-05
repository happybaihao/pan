# -*- coding: utf-8 -*-
import json
import random
import re
import sys
import socket
import time
from urllib.parse import quote, unquote
import urllib3
urllib3.disable_warnings()
from requests import Session
from requests.adapters import HTTPAdapter

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    NAME = "tiotok"

    def init(self, extend="{}"):
        self.proxies = {}
        # 仅从extend读取代理，不再自动填充默认PG代理
        try:
            cfg = json.loads(extend)
            proxy = cfg.get("proxy")
            if proxy:
                px = proxy if proxy.startswith("http") else f"http://{proxy}"
                self.proxies = {"http": px, "https": px}
        except Exception:
            # extend解析失败，不启用代理
            pass

        self.session = Session()
        self.session.verify = False
        self.session.proxies.update(self.proxies)

        # 关闭重试，移动弱网优化
        retry_strategy = HTTPAdapter(max_retries=0)
        self.session.mount("https://", retry_strategy)
        self.session.mount("http://", retry_strategy)

        # 请求头，适配PG代理转发
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 13; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.tiktok.com/',
            'sec-ch-ua-mobile': '?1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
        }
        self.session.headers.update(self.headers)

    def req(self, url, timeout=7, **kwargs):
        """请求封装，使用extend配置的代理，捕获移动网络常见错误"""
        kwargs.setdefault('timeout', timeout)
        kwargs.setdefault('headers', self.headers)
        kwargs.setdefault('proxies', self.proxies)
        kwargs.setdefault('verify', False)
        try:
            resp = self.session.get(url,** kwargs)
            resp.raise_for_status()
            return resp
        except (socket.timeout, ConnectionResetError, OSError, Exception) as e:
            self.log(f"请求异常 {url} -> {str(e)}")
            return None

    def log(self, *args):
        try:
            print(*args)
        except Exception:
            pass

    def getName(self):
        return self.NAME

    def getDependence(self):
        return []

    def homeContent(self, filter):
        """首页推荐"""
        result = {"class": [], "list": []}
        # TikTok推荐页
        url = "https://www.tiktok.com/recommend"
        resp = self.req(url)
        if not resp:
            # 失败重试一次
            resp = self.req(url)
        if resp:
            lst = self.parse_video_list(resp.text)
            result["list"] = lst
        return result

    def homeVideoContent(self):
        url = "https://www.tiktok.com/recommend"
        resp = self.req(url)
        lst = []
        if resp:
            lst = self.parse_video_list(resp.text)
        return {"list": lst}

    def categoryContent(self, tid, pg, filter, extend):
        """分类/用户主页"""
        pg = int(pg or 1)
        url = f"https://www.tiktok.com/@{tid}"
        resp = self.req(url)
        lst = []
        if resp:
            lst = self.parse_video_list(resp.text)
        return {
            "list": lst,
            "page": pg,
            "pagecount": 999,
            "limit": 20,
            "total": 9999
        }

    def searchContent(self, key, quick, pg="1"):
        """搜索"""
        pg = int(pg)
        url = f'https://www.tiktok.com/search?q={quote(key)}'
        resp = self.req(url)
        lst = []
        if resp:
            lst = self.parse_video_list(resp.text)
        return {"list": lst, "page": pg}

    def detailContent(self, ids):
        """详情页"""
        vid = ids[0]
        url = vid
        resp = self.req(url)
        vod = None
        if resp:
            vod = self.parse_detail(resp.text, url)
        return {"list": [vod] if vod else []}

    def playerContent(self, flag, id, vipFlags):
        """播放器，直连视频地址，携带headers走extend配置的代理"""
        return {
            "parse": 0,
            "url": id,
            "header": self.headers
        }

    def parse_video_list(self, html):
        """解析视频列表，提取标题、封面、视频链接"""
        videos = []
        # 提取网页内JSON数据
        pattern = re.compile(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});', re.S)
        match = pattern.search(html)
        if not match:
            return videos
        try:
            js_data = json.loads(match.group(1))
            item_list = js_data.get('ItemList', {})
            for _, item in item_list.items():
                video_info = item.get('itemInfo', {}).get('itemStruct', {})
                if not video_info:
                    continue
                video_url = video_info.get('video', {}).get('playAddr')
                cover = video_info.get('video', {}).get('cover', {}).get('urlList', [''])[0]
                title = video_info.get('desc', 'TikTok短视频')
                author = video_info.get('author', {}).get('uniqueId', '')
                if not video_url:
                    continue
                vod = {
                    "vod_id": video_url,
                    "vod_name": f"{author} - {title}",
                    "vod_pic": cover,
                    "vod_play_url": f"{title}${video_url}"
                }
                videos.append(vod)
        except Exception as e:
            self.log(f"列表解析失败: {e}")
        return videos

    def parse_detail(self, html, video_url):
        """解析详情"""
        pattern = re.compile(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});', re.S)
        match = pattern.search(html)
        if not match:
            return None
        try:
            js_data = json.loads(match.group(1))
            item_data = js_data.get('ItemList', {})
            for _, item in item_data.items():
                video_info = item.get('itemInfo', {}).get('itemStruct', {})
                if not video_info:
                    continue
                video_url = video_info.get('video', {}).get('playAddr')
                cover = video_info.get('video', {}).get('cover', {}).get('urlList', [''])[0]
                title = video_info.get('desc', 'TikTok短视频')
                desc = video_info.get('desc', '')
                vod = {
                    "vod_id": video_url,
                    "vod_name": title,
                    "vod_pic": cover,
                    "vod_content": desc,
                    "vod_play_url": f"{title}${video_url}"
                }
                return vod
        except Exception as e:
            self.log(f"详情解析失败: {e}")
        return None

    def action(self, action):
        return {}

    def proxy(self, param):
        return self.localProxy(param)

    def localProxy(self, param):
        return [200, "video/mp4", b""]

    def destroy(self):
        try:
            self.session.close()
        except Exception:
            pass
