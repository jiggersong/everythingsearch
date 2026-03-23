"""Pytest 配置和共享 fixtures"""
import pytest
import sys
import os
import tempfile
import shutil

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, project_root)


@pytest.fixture(scope="session")
def project_root_dir():
    """返回项目根目录路径"""
    return project_root


@pytest.fixture
def temp_dir():
    """创建临时目录，测试后自动清理"""
    tmpdir = tempfile.mkdtemp()
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def temp_file():
    """创建临时文件，测试后自动清理"""
    fd, path = tempfile.mkstemp()
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except:
        pass


@pytest.fixture
def sample_text_file():
    """创建示例文本文件"""
    fd, path = tempfile.mkstemp(suffix='.txt')
    try:
        os.write(fd, b"This is a sample text file for testing.")
        os.close(fd)
        yield path
    finally:
        try:
            os.unlink(path)
        except:
            pass


@pytest.fixture
def sample_md_file():
    """创建示例 Markdown 文件"""
    fd, path = tempfile.mkstemp(suffix='.md')
    content = b"# Sample Title\n\nThis is a sample markdown file.\n\n## Section 1\n\nContent here."
    try:
        os.write(fd, content)
        os.close(fd)
        yield path
    finally:
        try:
            os.unlink(path)
        except:
            pass
