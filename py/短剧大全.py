# coding=utf-8
#!/usr/bin/python
import sys
sys.path.append('..')
from base.spider import Spider
import urllib.parse
import requests
from lxml import etree
from urllib.parse import urljoin

class Spider(Spider):

    def getName(self):
        return "短剧大全"

    def init(self, extend=""):
        self.host = "https://lssy.net"
        self.pan_host = "https://pan.lssy.net"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Referer': self.host,
        }

    def homeContent(self, filter):
        classes = [
            {'type_id': 'online', 'type_name': '在线短剧'},
            {'type_id': 'quark', 'type_name': '夸克网盘短剧'}
        ]
        return {'class': classes, 'list': [], 'filters': {}}

    def categoryContent(self, tid, pg, filter, extend):
        if tid == 'online':
            url = self.host if pg == "1" else f"{self.host}/?p={pg}&keyword="
            return {'list': self._fetch_videos(url, self.host), 'page': int(pg)}
        else:
            # 夸克网盘分类翻页
            url = self.pan_host if pg == "1" else f"{self.pan_host}/page/{pg}/"
            return {'list': self._fetch_videos(url, self.pan_host), 'page': int(pg)}

    def detailContent(self, ids):
        try:
            url = ids[0]
            if not url.startswith('http'):
                url = urljoin(self.host, url)
                
            rsp = self.fetch(url)
            if not rsp: return {'list': []}
            html = etree.HTML(rsp.text)
            
            title = self.clean_text(html.xpath('//h1[contains(@class,"page-title")]/text() | //h1[contains(@class,"title")]/text()'))
            pic = html.xpath('//img[contains(@class,"cover-image")]/@src | //img[contains(@class,"cover")]/@src | //img/@src')
            pic = urljoin(url, pic[0]) if pic else ""
            content = self.clean_text(html.xpath('//div[contains(@class,"summary")]/text() | //div[contains(@class,"desc")]/text()')) or "暂无简介"

            play_from = []
            play_url = []

            # 1. 提取夸克网盘链接
            quark_links = html.xpath('//a[contains(@href, "quark.cn")]/@href')
            if quark_links:
                unique_links = []
                for l in quark_links:
                    if l not in unique_links: unique_links.append(l)
                play_from.append("夸克网盘")
                # 存入原始链接，在 playerContent 里处理协议转换
                play_url.append("#".join([f"夸克推送{i+1}${l}" for i, l in enumerate(unique_links)]))

            # 2. 在线播放逻辑
            episode_nodes = html.xpath('//div[contains(@class, "episode")] | //a[contains(@class, "ep-link")]')
            if episode_nodes:
                play_from.append("在线播放")
                eps = []
                for node in episode_nodes:
                    name = self.clean_text(node.xpath('./text()')) or f"第{len(eps)+1}集"
                    src = node.xpath('./@data-src | ./@href')
                    if src:
                        eps.append(f"{name}${urljoin(url, src[0])}")
                if eps:
                    play_url.append("#".join(eps))

            return {'list': [{
                'vod_id': url,
                'vod_name': title,
                'vod_pic': pic,
                'vod_content': content,
                'vod_play_from': '$$$'.join(play_from),
                'vod_play_url': '$$$'.join(play_url)
            }]}
        except: return {'list': []}

    def searchContent(self, key, quick, pg="1"):
        wd = urllib.parse.quote(key)
        url = f"{self.host}/?p={pg}&keyword={wd}"
        return {'list': self._fetch_videos(url, self.host), 'page': int(pg)}

    def playerContent(self, flag, id, vipFlags):
        # 针对 OK 影视的 push 协议头转换逻辑
        if "quark.cn" in id:
            # 将 http://... 替换为 push://http://... 
            # 这样壳子会自动识别并触发内置的网盘解析器
            push_url = id
            if id.startswith('http'):
                push_url = "push://" + id
            return {'parse': 0, 'url': push_url, 'header': self.headers}
        
        # 在线播放逻辑：m3u8直连，其余解析
        is_direct = any(x in id for x in ['.m3u8', '.mp4'])
        return {'parse': 0 if is_direct else 1, 'url': id, 'header': self.headers}

    def _fetch_videos(self, url, current_host):
        try:
            rsp = self.fetch(url)
            if not rsp: return []
            html = etree.HTML(rsp.text)
            videos = []
            seen_ids = set()
            
            items = html.xpath('//div[contains(@class,"card")]')
            for item in items:
                href = item.xpath('.//a/@href')
                if not href: continue
                
                vod_id = urljoin(current_host, href[0])
                if vod_id in seen_ids: continue
                seen_ids.add(vod_id)
                
                name = self.clean_text(item.xpath('.//div[contains(@class,"title")]/text()'))
                img = item.xpath('.//img/@src')
                
                videos.append({
                    'vod_id': vod_id,
                    'vod_name': name,
                    'vod_pic': urljoin(current_host, img[0]) if img else "",
                    'vod_remarks': "网盘资源" if "pan." in current_host else "在线观看"
                })
            return videos
        except: return []

    def clean_text(self, text_list):
        if isinstance(text_list, str): text_list = [text_list]
        return ' '.join(''.join(text_list).split()).strip() if text_list else ''

    def fetch(self, url):
        try: 
            return requests.get(url, headers=self.headers, timeout=10, verify=False)
        except: 
            return None
