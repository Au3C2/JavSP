from . import airav, arzon, arzon_iv, avsox, avwiki, dl_getchu, fanza, fc2, fc2fan, fc2ppvdb, gyutto, jav321, javbus, javdb, javlib, javmenu, mgstage, njav, prestige, proxyfree

# 静态注册表：建立 字符串 ID 到 模块对象 的映射
# 这样 PyInstaller 能够通过静态分析直接打包所有引用的模块
CRAWLER_MAP = {
    'airav': airav,
    'arzon': arzon,
    'arzon_iv': arzon_iv,
    'avsox': avsox,
    'avwiki': avwiki,
    'dl_getchu': dl_getchu,
    'fanza': fanza,
    'fc2': fc2,
    'fc2fan': fc2fan,
    'fc2ppvdb': fc2ppvdb,
    'gyutto': gyutto,
    'jav321': jav321,
    'javbus': javbus,
    'javdb': javdb,
    'javlib': javlib,
    'javmenu': javmenu,
    'mgstage': mgstage,
    'njav': njav,
    'prestige': prestige,
    'proxyfree': proxyfree
}
