/*
@header({
  searchable: 1,
  filterable: 0,
  quickSearch: 0,
  title: '急救指南',
  lang: 'cat'
})
*/

let host = 'https://m.youlai.cn';
let headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
};

// 后备占位图（仅极端情况用）
const DEFAULT_PIC = 'https://static.cnkang.com/images/youlai/patient/dissicon/jijiu/title_jjjn.png';

async function request(url) {
    try {
        let res = await req(url, { headers });
        return res.content || '';
    } catch (e) {
        return '';
    }
}

function home() {
    let classes = [
        { type_id: 'jijiu|0', type_name: '急救技能' },
        { type_id: 'jijiu|1', type_name: '家庭生活' },
        { type_id: 'jijiu|2', type_name: '急危重症' },
        { type_id: 'jijiu|3', type_name: '常见损伤' },
        { type_id: 'jijiu|4', type_name: '动物致伤' },
        { type_id: 'jijiu|5', type_name: '海洋急救' },
        { type_id: 'jijiu|6', type_name: '中毒急救' },
        { type_id: 'jijiu|7', type_name: '意外事故' }
    ];
    return JSON.stringify({ class: classes, filters: {} });
}

async function homeVod() {
    return JSON.stringify({ list: [] });
}

// ========== 重点修改：每个条目单独抓视频封面 ==========
async function category(tid, pg, filter, extend) {
    let index = parseInt(tid.split('|')[1]) || 0;
    let html = await request(host + '/jijiu');
    if (!html) return JSON.stringify({ list: [], page: 1, pagecount: 1, limit: 0, total: 0 });

    const fixedPics = [
        'https://static.cnkang.com/images/youlai/patient/dissicon/jijiu/title_jjjn.png',
        'https://static.cnkang.com/images/youlai/patient/dissicon/jijiu/title_jtsh.png',
        'https://static.cnkang.com/images/youlai/patient/dissicon/jijiu/title_jwzz.png',
        'https://static.cnkang.com/images/youlai/patient/dissicon/jijiu/title_cjss.png',
        'https://static.cnkang.com/images/youlai/patient/dissicon/jijiu/title_dwzs.png',
        'https://static.cnkang.com/images/youlai/patient/dissicon/jijiu/title_hyjj.png',
        'https://static.cnkang.com/images/youlai/patient/dissicon/jijiu/title_zdjj.png',
        'https://static.cnkang.com/images/youlai/patient/dissicon/jijiu/title_ywsg.png'
    ];

    let blocks = html.split('<div class="jj-list-wrap">').slice(1);
    if (index >= blocks.length) return JSON.stringify({ list: [], page: 1, pagecount: 1, limit: 0, total: 0 });

    let blockHtml = blocks[index];
    let fallbackPic = fixedPics[index] || DEFAULT_PIC;   // 后备封面图

    // 1) 先解析出所有条目的链接和标题
    let reg = /<a\s+[^>]*?href="(\/jijiu\/article\/[^"]+)"[^>]*>[\s\S]*?<div\s+class="[^"]*line-clamp1[^"]*">([^<]+)<\/div>/gi;
    let matches = [];
    let m;
    while ((m = reg.exec(blockHtml)) !== null) {
        matches.push({
            href: host + m[1],
            title: m[2].trim()
        });
    }

    if (matches.length === 0) return JSON.stringify({ list: [], page: 1, pagecount: 1, limit: 0, total: 0 });

    // 2) 同时请求每个条目的详情页，提取视频封面（优先 poster，其次 .video-cover img）
    const MAX_CONCURRENT = 5;   // 同时最多5个请求
    let items = new Array(matches.length);
    let cursor = 0;

    async function fetchCover(href) {
        try {
            let detailHtml = await request(href);
            if (!detailHtml) return fallbackPic;
            // 优先 <video poster="...">
            let posterM = detailHtml.match(/<video\s+[^>]*poster\s*=\s*["']([^"']+)["'][^>]*>/i);
            if (posterM) {
                let pic = posterM[1];
                if (pic.startsWith('//')) pic = 'https:' + pic;
                else if (pic.startsWith('/')) pic = host + pic;
                return pic;
            }
            // 其次 .video-cover 里的 img
            let coverM = detailHtml.match(/<div[^>]+class="[^"]*video-cover[^"]*"[^>]*>\s*<img\s+[^>]*src\s*=\s*["']([^"']+)["'][^>]*>/i);
            if (coverM) {
                let pic = coverM[1];
                if (pic.startsWith('//')) pic = 'https:' + pic;
                else if (pic.startsWith('/')) pic = host + pic;
                return pic;
            }
        } catch (e) {}
        return fallbackPic;
    }

    async function worker() {
        while (true) {
            let i = cursor++;
            if (i >= matches.length) break;
            let cover = await fetchCover(matches[i].href);
            items[i] = {
                vod_id: matches[i].href,
                vod_name: matches[i].title,
                vod_pic: cover,
                vod_remarks: ''
            };
        }
    }

    // 启动并发 worker
    let workers = [];
    let workerCount = Math.min(MAX_CONCURRENT, matches.length);
    for (let i = 0; i < workerCount; i++) {
        workers.push(worker());
    }
    await Promise.all(workers);

    return JSON.stringify({
        list: items,
        page: 1,
        pagecount: 1,
        limit: items.length,
        total: items.length
    });
}

// ========== 详情页（海报已经是视频封面，不需要改） ==========
async function detail(id) {
    let html = await request(id);
    if (!html) return JSON.stringify({ list: [] });

    // 标题
    let vod_name = '';
    let titleM = html.match(/<h[12]\s+[^>]*class="[^"]*(?:video-title[^"]*h1-title|h1-title[^"]*video-title)[^"]*"[^>]*>([^<]+)<\/h[12]>/i);
    if (titleM) {
        vod_name = titleM[1].trim();
    } else {
        let fallback = html.match(/<h[12][^>]*>([^<]+)<\/h[12]>/i);
        if (fallback) vod_name = fallback[1].trim();
    }

    // 海报：优先 video poster，其次 .video-cover img
    let vod_pic = '';
    let posterM = html.match(/<video\s+[^>]*poster\s*=\s*["']([^"']+)["'][^>]*>/i);
    if (posterM) {
        vod_pic = posterM[1];
    } else {
        let coverM = html.match(/<div[^>]+class="[^"]*video-cover[^"]*"[^>]*>\s*<img\s+[^>]*src\s*=\s*["']([^"']+)["'][^>]*>/i);
        if (coverM) vod_pic = coverM[1];
    }
    if (vod_pic) {
        if (vod_pic.startsWith('//')) vod_pic = 'https:' + vod_pic;
        else if (vod_pic.startsWith('/')) vod_pic = host + vod_pic;
    } else {
        vod_pic = DEFAULT_PIC;
    }

    let vod_actor = (html.match(/<span[^>]+class="[^"]*doc-name[^"]*"[^>]*>([^<]+)<\/span>/) || [])[1] || '';
    let vod_content = '';
    let descM = html.match(/<div[^>]+class="[^"]*img-text-con[^"]*"[^>]*>([\s\S]*?)<\/div>/i);
    if (descM) vod_content = descM[1].replace(/<[^>]+>/g, '').trim();

    let videoSrc = '';
    let srcM = html.match(/<source[^>]+src="([^"]+)"/i);
    if (srcM) videoSrc = srcM[1];
    else {
        let vM = html.match(/<video[^>]+src="([^"]+)"[^>]*>/i);
        if (vM) videoSrc = vM[1];
    }
    if (videoSrc && videoSrc.startsWith('/')) videoSrc = host + videoSrc;

    return JSON.stringify({
        list: [{
            vod_id: id,
            vod_name,
            vod_pic,
            vod_content,
            vod_play_from: 'Qile',
            vod_play_url: '视频教学$' + videoSrc,
            vod_director: '',
            vod_actor,
            type_name: '🆘',
            vod_remarks: ''
        }]
    });
}

async function play(flag, id, flags) {
    return JSON.stringify({
        parse: 0,
        url: id,
        header: JSON.stringify(headers)
    });
}

async function search(wd, quick, pg) {
    let url = host + '/cse/search?q=' + encodeURIComponent(wd);
    let html = await request(url);
    if (!html) return JSON.stringify({ list: [] });
    let list = [];
    let reg = /<a\s+[^>]*href="([^"]+)"[^>]*>[\s\S]*?<img[^>]+src="([^"]+)"[^>]*>[\s\S]*?<[^>]+class="[^"]*line-clamp1[^"]*"[^>]*>([^<]+)<\/[^>]+>/gi;
    let m;
    while ((m = reg.exec(html))) {
        let href = m[1];
        if (!href.startsWith('http')) href = host + href;
        let pic = m[2];
        if (!pic.startsWith('http')) {
            pic = pic.startsWith('//') ? 'https:' + pic : host + '/' + pic.replace(/^\//, '');
        }
        let title = m[3].trim();
        list.push({ vod_id: href, vod_name: title, vod_pic: pic, vod_remarks: '' });
    }
    return JSON.stringify({ list });
}

export function __jsEvalReturn() {
    return { init: () => {}, home, homeVod, category, detail, play, search };
}