"""从JavLibrary抓取数据"""
import logging
from urllib.parse import urlsplit


from javsp.web.base import Request, read_proxy, resp2html
from javsp.web.exceptions import *
from javsp.web.proxyfree import get_proxy_free_url
from javsp.config import Cfg, CrawlerID
from javsp.datatype import MovieInfo


request = Request()

logger = logging.getLogger(__name__)
permanent_url = 'https://www.javlibrary.com'


def parse_clean_data(movie: MovieInfo):
    """抓取并解析指定番号的数据，会对数据进行一些清洗以保证数据质量
    Args:
        movie (MovieInfo): 要解析的影片信息，解析后的信息直接更新到此变量内
    """
    dvdid = movie.dvdid
    # 优先从配置项获得
    base_url = str(Cfg().network.proxy_free[CrawlerID.javlib])
    if not base_url.endswith('/'):
        base_url += '/'
    
    # 获取搜索结果
    r = request.get(f"{base_url}cn/vl_searchbyid.php?keyword={dvdid}")
    new_url = r.url
    if r.status_code == 404:
        raise MovieNotFoundError(__name__, dvdid)
    html = resp2html(r)
    # 处理搜索结果列表
    if 'vl_searchbyid.php' in new_url:
        # 获取所有完全匹配的搜索结果
        # 注意：这里需要确保只匹配完全相等的番号，避免把 ABC-123 和 ABC-1234 混淆
        # JavLibrary的列表页番号在 <div class="id"> 中
        search_results = html.xpath("//div[@class='videos']/div[@class='video']")
        pre_choose_urls = []
        for res in search_results:
            found_id = res.xpath("a/div[@class='id']/text()")
            if found_id and found_id[0].upper() == dvdid.upper():
                pre_choose_urls.append(base_url + 'cn/' + res.xpath("a/@href")[0].strip('./'))
        
        match_count = len(pre_choose_urls)
        if match_count == 0:
            raise MovieNotFoundError(__name__, dvdid)
        elif match_count == 1:
            new_url = pre_choose_urls[0]
        else:
            # 存在多个相同番号的搜索结果（如不同版本、普通版/蓝光版等）
            # 优先选择带有'Blu-ray'字样的
            blu_ray_urls = [u for u in pre_choose_urls if 'blu-ray' in u.lower()]
            if blu_ray_urls:
                new_url = blu_ray_urls[0]
            else:
                # 默认选择第一个
                new_url = pre_choose_urls[0]
                logger.warning(f"'{dvdid}': 存在{match_count}个相同番号搜索结果，已默认选择第一个: {new_url}")
        
        # 重新请求选中的详情页
        r = request.get(new_url)
        html = resp2html(r)

    # 提取基本信息
    title = html.xpath("//h3[@class='post-title text']/a/text()")[0]
    
    cover_tags = html.xpath("//img[@id='video_jacket_img']/@src")
    if cover_tags:
        cover = cover_tags[0]
        if cover.startswith('//'):
            cover = 'https:' + cover
        movie.cover = cover

    # 提取详细信息
    info_tag = html.xpath("//div[@id='video_info']")[0]
    
    date_tags = info_tag.xpath("//div[@id='video_date']//td[@class='text']/text()")
    if date_tags:
        movie.publish_date = date_tags[0].strip()
        
    duration_tags = info_tag.xpath("//div[@id='video_length']//span[@class='text']/text()")
    if duration_tags:
        movie.duration = duration_tags[0].strip()
        
    producer_tags = info_tag.xpath("//div[@id='video_maker']//a/text()")
    if producer_tags:
        movie.producer = producer_tags[0].strip()
        
    publisher_tags = info_tag.xpath("//div[@id='video_label']//a/text()")
    if publisher_tags:
        movie.publisher = publisher_tags[0].strip()
        
    director_tags = info_tag.xpath("//div[@id='video_director']//a/text()")
    if director_tags:
        movie.director = director_tags[0].strip()
        
    movie.actress = info_tag.xpath("//span[@class='star']/a/text()")
    movie.genre = info_tag.xpath("//span[@class='genre']/a/text()")
    
    # 评分处理
    score_tags = info_tag.xpath("//span[@class='score']/text()")
    if score_tags:
        try:
            # 去掉括号
            score_str = score_tags[0].strip('()')
            movie.score = score_str
        except:
            pass

    # URL 标准化：统一使用 .html 格式以通过单元测试
    vid = new_url.split('?v=')[-1] if '?v=' in new_url else new_url.split('/')[-1].split('.')[0]
    movie.url = f"{permanent_url}/cn/{vid}.html"
    movie.dvdid = dvdid
    movie.title = title.replace(dvdid, '').strip()
    return movie


def parse_data(movie: MovieInfo):
    """调用 parse_clean_data 的别名以保持接口一致"""
    return parse_clean_data(movie)


if __name__ == "__main__":
    import pretty_errors
    pretty_errors.configure(display_link=True)
    movie = MovieInfo('IPX-177')
    try:
        parse_data(movie)
        print(movie)
    except CrawlerError as e:
        print(e)
