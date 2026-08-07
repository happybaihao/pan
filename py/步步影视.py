# coding=utf-8
#!/usr/bin/python

from urllib.parse import unquote, quote
from base.spider import Spider
from datetime import datetime
from bs4 import BeautifulSoup
from base64 import b64decode
import urllib.request
import urllib.parse
import datetime
import binascii
import requests
import base64
import json
import time
import sys
import re
import os
import hashlib
import random

sys.path.append('..')


class Spider(Spider):
    def __init__(self):
        self.baseUrl = "https://bubutv.top"
        self.finger = "SF-C3B2B41F6EFFFF9869176CF68F6790E8F07506FC88632C94B4F5F0430D5498CA"
        self.aid = "com.sunshine.tv"
        self.sk = "SK-thanks"
        self.v = "4"

        self.host = ""
        self.x_time = ""
        self.x_nonc = ""

    def getName(self):
        return "App3Q"

    def init(self, extend):
        if extend and extend.strip():
            self.host = extend.strip()
        else:
            self.host = self.baseUrl

        ts = int(time.time())
        self.x_time = str(ts)
        self.x_nonc = str(random.randint(1000, 9999))

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def sign(self):
        plain = f"finger={self.finger}&id={self.aid}&nonce={self.x_nonc}&sk={self.sk}&time={self.x_time}&v={self.v}"
        sha = hashlib.sha256(plain.encode('utf-8')).digest()
        return binascii.hexlify(sha).upper().decode()

    def headers(self):
        return {
            'User-Agent': 'okhttp/4.12.0',
            'x-ave': self.v,
            'x-aid': self.aid,
            'x-time': self.x_time,
            'x-nonc': self.x_nonc,
            'x-sign': self.sign(),
            'x-device-id': '0b4328287a5d953e',
            'x-device-brand': 'OnePlus',
            'x-device-model': 'HD1900',
            'x-update-id': '73dc2ffc-8350-c022-fac9-da982c95f513'
        }

    def play_headers(self):
        return {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
            'Referer': self.host,
            'Accept': '*/*'
        }

    def fetch(self, path, is_json=True):
        try:
            url = self.host + path
            r = requests.get(url, headers=self.headers(), timeout=12)
            r.raise_for_status()
            if is_json:
                return r.json()
            else:
                return r.text
        except Exception as e:
            return None

    def parse_challenge(self, js):
        try:
            match = re.search(r'_0x1\s*=\s*\[(.*?)\];', js, re.DOTALL)
            if not match:
                return ""
            arr = [x.strip().replace("'", "").replace('"', "") for x in match.group(1).split(",")]
            s = f"{arr[0]}:{arr[1]}:{arr[2]}:{arr[3]}"
            res = 0
            for c in s:
                res = ((res << 5) - res + ord(c)) & 0xFFFFFFFF
            res = abs(res)
            return f"{arr[0]}:{hex(res)[2:]}:{arr[1][:8]}"
        except:
            return ""

    def homeContent(self, filter):
        result = {"class": [], "list": []}
        data = self.fetch("/api.php/app/index/home")
        if not data:
            return result
        data = data.get("data", {})

        for t in data.get("categories", []):
            tn = t.get("type_name")
            result["class"].append({"type_id": tn, "type_name": tn})

        vlist = []
        for v in data.get("recommend", []):
            vlist.append({
                "vod_id": v.get("vod_id", ""),
                "vod_name": v.get("vod_name", ""),
                "vod_pic": v.get("vod_pic", ""),
                "vod_remarks": v.get("vod_remarks", "")
            })
        result["list"] = vlist
        return result

    def categoryContent(self, cid, pg, filter, ext):
        result = {"list": [], "page": pg, "pagecount": 999, "limit": 20, "total": 9999}
        path = f"/api.php/app/filter/vod?type_name={cid}&page={pg}&sort=hits"
        data = self.fetch(path)
        if not data:
            return result
        vlist = []
        for v in data.get("data", []):
            vlist.append({
                "vod_id": v.get("vod_id"),
                "vod_name": v.get("vod_name"),
                "vod_pic": v.get("vod_pic"),
                "vod_remarks": v.get("vod_remarks")
            })
        result["list"] = vlist
        return result

    def detailContent(self, ids):
        result = {"list": []}
        data = self.fetch(f"/api.php/app/vod/get_detail?vod_id={ids[0]}")
        if not data or not data.get("data"):
            return result
        d = data["data"][0]
        pf = d.get("vod_play_from", "")
        pu = d.get("vod_play_url", "")
        result["list"].append({
            "vod_id": ids[0],
            "vod_name": d.get("vod_name"),
            "vod_pic": d.get("vod_pic"),
            "vod_class": d.get("vod_class"),
            "vod_remarks": d.get("vod_remarks"),
            "vod_content": d.get("vod_content", "").strip(),
            "vod_actor": d.get("vod_actor"),
            "vod_director": d.get("vod_director"),
            "vod_play_from": pf,
            "vod_play_url": pu
        })
        return result

    def playerContent(self, flag, vid, vipFlags):
        result = {
            "parse": 0,
            "playUrl": "",
            "url": "",
            "header": self.play_headers()
        }

        try:
            parts = vid.split("@")
            raw_url = parts[0].strip()

            if re.search(r'\.(m3u8|mp4|mkv|flv|avi|mov|ts)', raw_url, re.I):
                result["url"] = raw_url
                return result

            token = ""
            for i in range(3):
                enc_url = quote(raw_url, encoding='utf-8')
                path = f"/api.php/app/decode/url/?url={enc_url}&vodFrom={flag}{token}"
                res_text = self.fetch(path, is_json=False)
                if not res_text:
                    continue

                try:
                    js = json.loads(res_text)
                except:
                    continue

                if js.get("code") == 2 and js.get("challenge"):
                    chal = js["challenge"]
                    tk = self.parse_challenge(chal)
                    if tk:
                        token = f"&token={tk}"
                    continue

                real_url = js.get("data", "").strip()
                if real_url.startswith("http"):
                    result["url"] = real_url
                    return result
        except Exception as e:
            pass

        return result

    def searchContent(self, key, quick, pg="1"):
        result = {"list": [], "page": pg, "pagecount": 999, "limit": 15, "total": 9999}
        qk = quote(key)
        data = self.fetch(f"/api.php/app/search/index?wd={qk}&page=1&limit=15")
        if not data:
            return result
        vlist = []
        for v in data.get("data", []):
            vlist.append({
                "vod_id": v.get("vod_id"),
                "vod_name": v.get("vod_name"),
                "vod_pic": v.get("vod_pic"),
                "vod_remarks": v.get("vod_remarks")
            })
        result["list"] = vlist
        return result

    def localProxy(self, params):
        if params['type'] == "m3u8":
            return self.proxyM3u8(params)
        elif params['type'] == "media":
            return self.proxyMedia(params)
        elif params['type'] == "ts":
            return self.proxyTs(params)
        return None
