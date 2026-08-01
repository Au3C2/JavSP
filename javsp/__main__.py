import os
import sys

# --- PyInstaller 资源重定向补丁 ---
if getattr(sys, 'frozen', False):
    _base_path = getattr(sys, '_MEIPASS', os.getcwd())
    # 采用版本感知的标准布局
    _tcl_root = os.path.join(_base_path, 'tcl_tk')
    
    # 递归寻找包含 init.tcl 的目录
    for root, dirs, files in os.walk(_tcl_root):
        if 'init.tcl' in files:
            os.environ['TCL_LIBRARY'] = root
        if 'tk.tcl' in files:
            os.environ['TK_LIBRARY'] = root

import re
import json
import time
import logging
from pydantic import ValidationError

# 强制设置控制台编码
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

def entry():
    # 1. 配置自愈优先
    try:
        from javsp.config import Cfg
        Cfg()
    except ValidationError as e:
        print("\n[!] 配置文件校验失败：")
        print(e.errors())
        sys.exit(1)
    except SystemExit:
        sys.exit(0)
    except Exception as e:
        print(f"\n[!] 程序初始化异常: {e}")
        sys.exit(1)

    # 2. 延迟加载业务模块 (模块级导入，彻底避开命名空间地狱)
    import requests
    import threading
    import colorama
    import pretty_errors
    from typing import Dict, List
    from PIL import Image
    from tqdm import tqdm
    from colorama import Fore, Style
    from pydantic_extra_types.pendulum_dt import Duration

    pretty_errors.configure(display_link=True)

    import javsp.print
    import javsp.cropper
    import javsp.lib
    import javsp.nfo
    import javsp.file
    import javsp.func
    import javsp.image
    import javsp.datatype
    import javsp.config
    import javsp.web.base
    import javsp.web.exceptions
    import javsp.web.translate
    import javsp.web
    import javsp.prompt

    # 日志输出拦截
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if type(handler) == logging.StreamHandler:
            handler.stream = javsp.print.TqdmOut
    logger = logging.getLogger('main')

    # 女优别名支持
    actressAliasMap = {}
    if javsp.config.Cfg().crawler.normalize_actress_name:
        try:
            actressAliasFilePath = javsp.lib.resource_path("data/actress_alias.json")
            with open(actressAliasFilePath, "r", encoding="utf-8") as file:
                actressAliasMap = json.load(file)
        except Exception as e:
            logging.debug(f"加载女优别名失败: {e}")

    def resolve_alias(name):
        for fixedName, aliases in actressAliasMap.items():
            if name in aliases: return fixedName
        return name

    def import_crawlers():
        """验证配置中的抓取器是否都在注册表中"""
        unknown_mods = []
        selection_dict = javsp.config.Cfg().crawler.selection.model_dump()
        for mods in selection_dict.values():
            for name in mods:
                key = name.value if hasattr(name, 'value') else str(name)
                if key not in javsp.web.CRAWLER_MAP: unknown_mods.append(key)
        if unknown_mods:
            logger.warning('配置的抓取器无效: ' + ', '.join(set(unknown_mods)))
            return False
        return True

    def parallel_crawler(movie, tqdm_bar=None):
        def wrapper(parser, mod_name, info, retry):
            for cnt in range(retry):
                try:
                    parser(info)
                    setattr(info, 'success', True)
                    if isinstance(tqdm_bar, tqdm): tqdm_bar.set_description(f'{mod_name}: 抓取完成')
                    break
                except Exception as e:
                    logger.debug(f"{mod_name}: {e}")
                    # 网络错误则重试
                    if isinstance(e, requests.exceptions.RequestException): continue
                    break

        crawler_mods = javsp.config.Cfg().crawler.selection[movie.data_src]
        all_info = {i.value: javsp.datatype.MovieInfo(movie) for i in crawler_mods}
        thread_pool = []
        for mod_id, info in all_info.items():
            if mod_id not in javsp.web.CRAWLER_MAP: continue
            mod = javsp.web.CRAWLER_MAP[mod_id]
            parser = getattr(mod, 'parse_data')
            retry_count = 1 if hasattr(mod, 'parse_data_raw') else javsp.config.Cfg().network.retry
            th = threading.Thread(target=wrapper, name=mod_id, args=(parser, mod_id, info, retry_count))
            th.start()
            thread_pool.append(th)
        timeout = javsp.config.Cfg().network.retry * javsp.config.Cfg().network.timeout.total_seconds()
        for th in thread_pool: th.join(timeout=timeout)
        all_info = {k:v for k,v in all_info.items() if hasattr(v, 'success')}
        for info in all_info.values(): del info.success
        return all_info

    def info_summary(movie, all_info):
        final_info = javsp.datatype.MovieInfo(movie)
        if 'javdb' in all_info and all_info['javdb'].genre:
            final_info.genre = all_info['javdb'].genre
        if javsp.config.Cfg().summarizer.title.remove_trailing_actor_name:
            for data in all_info.values():
                data.title = javsp.func.remove_trail_actor_in_title(data.title, data.actress)
        attrs = [i for i in dir(final_info) if not i.startswith('_')]
        covers, big_covers = [], []
        for data in all_info.values():
            for attr in attrs:
                incoming = getattr(data, attr)
                current = getattr(final_info, attr)
                if attr == 'cover' and incoming and incoming not in covers: covers.append(incoming)
                elif attr == 'big_cover' and incoming and incoming not in big_covers: big_covers.append(incoming)
                elif not current and incoming: setattr(final_info, attr, incoming)
        
        javdb_cover = getattr(all_info.get('javdb'), 'cover', None)
        if javdb_cover:
            match javsp.config.Cfg().crawler.use_javdb_cover:
                case javsp.config.UseJavDBCover.fallback:
                    if javdb_cover in covers: covers.remove(javdb_cover); covers.append(javdb_cover)
                case javsp.config.UseJavDBCover.no:
                    if javdb_cover in covers: covers.remove(javdb_cover)

        setattr(final_info, 'covers', covers)
        setattr(final_info, 'big_covers', big_covers)
        if covers: final_info.cover = covers[0]
        if big_covers: final_info.big_cover = big_covers[0]
        if final_info.genre is None: final_info.genre = []
        if movie.hard_sub: final_info.genre.append('内嵌字幕')
        if movie.uncensored: final_info.genre.append('无码流出/破解')
        if javsp.config.Cfg().crawler.normalize_actress_name:
            final_info.actress = [resolve_alias(i) for i in final_info.actress]
        for attr in javsp.config.Cfg().crawler.required_keys:
            if not getattr(final_info, attr, None): return False
        movie.info = final_info
        return True

    def generate_names(movie):
        info = movie.info
        d = info.get_info_dic()
        if info.actress and len(info.actress) > javsp.config.Cfg().summarizer.path.max_actress_count:
            actress = info.actress[:javsp.config.Cfg().summarizer.path.max_actress_count] + ['…']
        else: actress = info.actress
        d['actress'] = ','.join(actress) if actress else javsp.config.Cfg().summarizer.default.actress
        setattr(info, 'label', d['label'].upper())
        for k, v in d.items(): d[k] = javsp.file.replace_illegal_chars(v.strip())
        nfo_title = javsp.config.Cfg().summarizer.nfo.title_pattern.format(**d)
        setattr(info, 'nfo_title', nfo_title)
        copyd = d.copy()
        copyd['num'] = copyd['num'] + movie.attr_str
        movie.save_dir = os.path.normpath(javsp.config.Cfg().summarizer.path.output_folder_pattern.format(**copyd)).strip()
        movie.basename = os.path.normpath(javsp.config.Cfg().summarizer.path.basename_pattern.format(**copyd)).strip()
        movie.nfo_file = os.path.join(movie.save_dir, javsp.config.Cfg().summarizer.nfo.basename_pattern.format(**copyd) + '.nfo')
        movie.fanart_file = os.path.join(movie.save_dir, javsp.config.Cfg().summarizer.fanart.basename_pattern.format(**copyd) + '.jpg')
        movie.poster_file = os.path.join(movie.save_dir, javsp.config.Cfg().summarizer.cover.basename_pattern.format(**copyd) + '.jpg')

    def RunNormalMode(all_movies):
        outer_bar = tqdm(all_movies, desc='整理影片', ascii=True, ncols=120, leave=False)
        for movie in outer_bar:
            inner_bar = tqdm(total=8, desc='步骤', ascii=True, ncols=120, leave=False)
            try:
                filenames = [os.path.split(i)[1] for i in movie.files]
                logger.info('正在整理: ' + ', '.join(filenames))
                all_info = parallel_crawler(movie, inner_bar)
                if not all_info: continue
                inner_bar.update()
                if not info_summary(movie, all_info): continue
                inner_bar.update()
                if javsp.config.Cfg().translator.engine:
                    javsp.web.translate.translate_movie_info(movie.info)
                inner_bar.update()
                generate_names(movie)
                if not os.path.exists(movie.save_dir): os.makedirs(movie.save_dir, exist_ok=True)
                inner_bar.update()
                # 封面下载逻辑 (补全)
                if javsp.config.Cfg().summarizer.cover.highres:
                    # 依次尝试所有封面
                    for url in (movie.info.big_covers + movie.info.covers):
                        try:
                            javsp.web.base.download(url, movie.fanart_file)
                            if javsp.image.valid_pic(movie.fanart_file): break
                        except: continue
                inner_bar.update()
                # 封面裁剪
                cropper = javsp.cropper.get_cropper(javsp.config.Cfg().summarizer.cover.crop.engine)
                if os.path.exists(movie.fanart_file):
                    try:
                        img = Image.open(movie.fanart_file)
                        cropper.crop(img).save(movie.poster_file)
                    except: pass
                inner_bar.update()
                javsp.nfo.write_nfo(movie.info, movie.nfo_file)
                inner_bar.update()
                if javsp.config.Cfg().summarizer.move_files: 
                    movie.rename_files(javsp.config.Cfg().summarizer.path.hard_link)
                inner_bar.update()
                logger.info(f'整理完成: {movie.save_dir}')
            except Exception as e:
                logger.error(f"整理中途出错: {e}")
            finally:
                inner_bar.close()

    colorama.init(autoreset=True)
    javsp.func.check_update(javsp.config.Cfg().other.check_update, javsp.config.Cfg().other.auto_update)
    root = javsp.func.get_scan_dir(javsp.config.Cfg().scanner.input_directory)
    if not root: sys.exit(1)
    import_crawlers()
    # Pre-check JavDB cookie once at startup to avoid repeated popups during batch processing
    try:
        javsp.web.javdb.ensure_javdb_cookie_ready()
    except Exception as e:
        logger.debug(f"Pre-checking JavDB cookie failed: {e}")

    os.chdir(root)
    recognized = javsp.file.scan_movies(root)
    if not recognized:
        logger.error("未找到影片文件")
        sys.exit(1)
    logger.info(f'扫描影片文件：共找到 {len(recognized)} 部影片')
    if javsp.config.Cfg().scanner.manual:
        javsp.prompt.reviewMovieID(recognized, root)
    RunNormalMode(recognized)
    sys.exit(0)

if __name__ == "__main__":
    entry()
