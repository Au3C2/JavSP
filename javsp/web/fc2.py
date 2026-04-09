"""从FC2官网抓取数据"""
import re
import logging


from javsp.web.base import get_html, request_get, resp2html
from javsp.web.exceptions import *
from javsp.config import Cfg
from javsp.lib import strftime_to_minutes
from javsp.datatype import MovieInfo


logger = logging.getLogger(__name__)
base_url = 'https://adult.contents.fc2.com'


def get_movie_score(fc2_id):
    """通过评论数据来计算FC2的影片评分（10分制），无法获得评分时返回None"""
    html = get_html(f'{base_url}/article/{fc2_id}/review')
    review_tags = html.xpath("//ul[@class='items_comment_headerReviewInArea']/li")
    reviews = {}
    for tag in review_tags:
        score = int(tag.xpath("div/span/text()")[0])
        vote = int(tag.xpath("span")[0].text_content())
        reviews[score] = vote
    total_votes = sum(reviews.values())
    if (total_votes >= 2):   # 至少也该有两个人评价才有参考意义一点吧
        summary = sum([k*v for k, v in reviews.items()])
        final_score = summary / total_votes * 2   # 乘以2转换为10分制
        return final_score


def parse_data(movie: MovieInfo):
    """解析指定番号的影片数据"""
    # 去除番号中的'FC2'字样
    id_uc = movie.dvdid.upper()
    if not id_uc.startswith('FC2-'):
        raise ValueError('Invalid FC2 number: ' + movie.dvdid)
    fc2_id = id_uc.replace('FC2-', '')
    # 抓取网页
    url = f'{base_url}/article/{fc2_id}/'
    resp = request_get(url)
    if '/id.fc2.com/' in resp.url:
        raise SiteBlocked('FC2要求当前IP登录账号才可访问，请尝试更换为日本IP')
    html = resp2html(resp)
    container_tags = html.xpath("//div[@class='items_article_left']")
    if not container_tags:
        raise MovieNotFoundError(__name__, movie.dvdid)
    container = container_tags[0]
    
    # FC2 标题增加反爬乱码，使用数组合并标题
    title_arr = container.xpath("//div[@class='items_article_headerInfo']/h3/text()")
    title = ''.join(title_arr)
    # 彻底清理 FC2 各种各样的修饰符，例如：【個人撮影】、【背徳の編】
    title = re.sub(r'【.*?】', '', title).strip()
    
    thumb_tags = container.xpath("//div[@class='items_article_MainitemThumb']")
    if thumb_tags:
        thumb_tag = thumb_tags[0]
        thumb_pic_tags = thumb_tag.xpath("span/img/@src")
        thumb_pic = thumb_pic_tags[0] if thumb_pic_tags else ""
        duration_tags = thumb_tag.xpath("span/p[@class='items_article_info']/text()")
        duration_str = duration_tags[0] if duration_tags else ""
    else:
        thumb_pic, duration_str = '', ''

    # FC2没有制作商和发行商的区分，作为个人市场，影片页面的'by'更接近于制作商
    producer_tags = container.xpath("//li[contains(text(), 'by')]/a/text()")
    producer = producer_tags[0] if producer_tags else ''
    
    genre = container.xpath("//a[@class='tag tagTag']/text()")
    
    # 日期提取：兼容 Releasedate 和 softDevice 类名
    date_tags = container.xpath("//div[contains(@class, 'items_article_Releasedate') or contains(@class, 'softDevice')]/p/text()")
    if date_tags:
        # 寻找包含日期格式的部分
        date_str = ""
        for t in date_tags:
            m = re.search(r'\d{4}/\d{2}/\d{2}', t)
            if m:
                date_str = m.group(0)
                break
        publish_date = date_str.replace('/', '-')
    else:
        publish_date = ''

    preview_pics = container.xpath("//ul[@data-feed='sample-images']/li/a/@href")

    if Cfg().crawler.hardworking:
        score = get_movie_score(fc2_id)
        if score:
            movie.score = f'{score:.2f}'
        desc_frame_url_tags = container.xpath("//section[@class='items_article_Contents']/iframe/@src")
        if desc_frame_url_tags:
            desc_frame_url = desc_frame_url_tags[0]
            key = desc_frame_url.split('=')[-1]
            api_url = f'{base_url}/api/v2/videos/{fc2_id}/sample?key={key}'
            try:
                r = request_get(api_url).json()
                movie.preview_video = r.get('path')
            except:
                pass
    else:
        score_tag_attr = container.xpath("//a[@class='items_article_Stars']/p/span/@class")
        if score_tag_attr:
            score = int(score_tag_attr[0][-1]) * 2
            movie.score = f'{score:.2f}'

    movie.dvdid = id_uc
    movie.url = url
    movie.title = title
    movie.genre = genre
    movie.producer = producer
    movie.duration = str(strftime_to_minutes(duration_str))
    movie.publish_date = publish_date
    movie.preview_pics = preview_pics
    if movie.preview_pics:
        movie.cover = preview_pics[0]
    else:
        movie.cover = thumb_pic


if __name__ == "__main__":
    import pretty_errors
    pretty_errors.configure(display_link=True)
    movie = MovieInfo('FC2-718323')
    try:
        parse_data(movie)
        print(movie)
    except Exception as e:
        print(e)
