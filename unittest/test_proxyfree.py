import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from javsp.web.proxyfree import *


def test_get_url():
    if os.getenv('GITHUB_ACTIONS'):
        pytest.skip("检测到 Github Actions 环境，跳过 proxyfree 测试")
    assert get_proxy_free_url('javlib') != ''
    assert get_proxy_free_url('javdb') != ''


def test_get_url_with_prefer():
    prefer_url = 'https://www.baidu.com'
    assert prefer_url == get_proxy_free_url('javlib', prefer_url)

if __name__ == "__main__":
    print(get_proxy_free_url('javlib'))
