"""从dl.getchu官网抓取数据"""
import re
import logging

from javsp.web.base import resp2html, request_get
from javsp.web.exceptions import *
from javsp.datatype import MovieInfo

logger = logging.getLogger(__name__)

def get_movie_title(html):
    title_tags = html.xpath("//h1[@id='item_name']/text()")
    if title_tags:
        return title_tags[0].strip()
    container = html.xpath("//form[@action='https://dl.getchu.com/cart/']/div/table[2]")
    if len(container) > 0:
        title_tags = container[0].xpath(".//td/div/text()")
        if title_tags:
            return title_tags[-1].strip()
    return ""

def parse_data(movie: MovieInfo):
    """从网页抓取并解析指定番号的数据"""
    id_parts = movie.dvdid.lower().split('-')
    getchu_id = id_parts[-1]
    url = f'https://dl.getchu.com/i/item{getchu_id}'
    
    resp = request_get(url, delay_raise=True)
    if resp.status_code == 404:
        raise MovieNotFoundError(__name__, movie.dvdid)
    
    # 强制指定编码并获取纯净的 HTML
    resp.encoding = 'euc-jp'
    html = resp2html(resp)

    title = get_movie_title(html)
    if not title:
        raise WebsiteError("无法提取 Getchu 标题")

    movie.title = title
    movie.url = url
    
    # 提取封面
    cover = None
    all_imgs = html.xpath("//img/@src")
    for img_url in all_imgs:
        if img_url.endswith('top.jpg') and getchu_id in img_url:
            cover = img_url
            break
    if not cover:
        highslide_links = html.xpath("//a[contains(@class, 'highslide')]/@href")
        if highslide_links:
            cover = highslide_links[0]
    if cover:
        if cover.startswith('//'): movie.cover = 'https:' + cover
        elif cover.startswith('/'): movie.cover = 'https://dl.getchu.com' + cover
        else: movie.cover = cover

    # 提取制作商
    producer_tags = html.xpath("//a[contains(@href, 'circle_id')]/text()")
    if producer_tags:
        movie.producer = producer_tags[0].strip()

    # 提取发布日期
    all_td_texts = html.xpath("//td/text()")
    for text in all_td_texts:
        match = re.search(r'(\d{4}/\d{2}/\d{2})', text)
        if match:
            movie.publish_date = match.group(1).replace('/', '-')
            break

    # 提取标签
    genre_tags = html.xpath("//a[contains(@href, 'genre_id')]/text()")
    if genre_tags:
        movie.genre = [g.strip() for r in genre_tags if (g := r.strip())]

    # 提取女优
    actress_tags = html.xpath("//a[contains(@href, 'actress_id')]/text()")
    if actress_tags:
        movie.actress = [a.strip() for r in actress_tags if (a := r.strip())]

    return movie

if __name__ == "__main__":
    import pretty_errors
    pretty_errors.configure(display_link=True)
    movie = MovieInfo('getchu-4041026')
    try:
        parse_data(movie)
        print(movie)
    except Exception as e:
        print(e)
