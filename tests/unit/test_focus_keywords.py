import os
import tempfile
import pytest
import yaml

from utils.focus_keywords import FocusKeywordsManager


@pytest.fixture
def tmp_fk_file():
    """Crea un file temporaneo con struttura multi-dominio."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump({
            'domains': {
                'esempio.com': {
                    'keywords': {
                        '/': {
                            'primary': 'keyword principale',
                            'secondary': ['sec1', 'sec2'],
                        },
                        '/blog/post/': {
                            'primary': 'keyword blog',
                            'secondary': [],
                        },
                    }
                },
                'altro.com': {
                    'keywords': {
                        '/': {
                            'primary': 'altro principale',
                            'secondary': [],
                        },
                    }
                },
            },
            'options': {
                'min_density': 1.0,
                'max_density': 3.0,
            },
        }, f, allow_unicode=True)
        path = f.name
    yield path
    os.unlink(path)


class TestFocusKeywordsManager:

    def test_load_empty_file(self):
        mgr = FocusKeywordsManager('/tmp/non_esiste_xyz.yaml', domain='esempio.com')
        mgr.load()
        assert mgr.count == 0
        assert mgr.is_empty

    def test_load_multi_domain(self, tmp_fk_file):
        mgr = FocusKeywordsManager(tmp_fk_file, domain='esempio.com')
        mgr.load()
        assert mgr.count == 2

    def test_normalize_domain(self):
        mgr = FocusKeywordsManager('/dev/null', domain='https://www.EsemPio.com/')
        assert mgr.domain == 'esempio.com'

    def test_get_primary(self, tmp_fk_file):
        mgr = FocusKeywordsManager(tmp_fk_file, domain='esempio.com')
        mgr.load()
        assert mgr.get_primary('/') == 'keyword principale'
        assert mgr.get_primary('/blog/post/') == 'keyword blog'

    def test_get_primary_without_trailing_slash(self, tmp_fk_file):
        mgr = FocusKeywordsManager(tmp_fk_file, domain='esempio.com')
        mgr.load()
        assert mgr.get_primary('/blog/post') == 'keyword blog'

    def test_get_primary_with_full_url(self, tmp_fk_file):
        mgr = FocusKeywordsManager(tmp_fk_file, domain='esempio.com')
        mgr.load()
        assert mgr.get_primary('https://esempio.com/blog/post/') == 'keyword blog'

    def test_get_primary_nonexistent_url(self, tmp_fk_file):
        mgr = FocusKeywordsManager(tmp_fk_file, domain='esempio.com')
        mgr.load()
        assert mgr.get_primary('/non-esiste/') is None

    def test_get_secondary(self, tmp_fk_file):
        mgr = FocusKeywordsManager(tmp_fk_file, domain='esempio.com')
        mgr.load()
        assert mgr.get_secondary('/') == ['sec1', 'sec2']
        assert mgr.get_secondary('/blog/post/') == []

    def test_wrong_domain(self, tmp_fk_file):
        mgr = FocusKeywordsManager(tmp_fk_file, domain='terzo.com')
        mgr.load()
        assert mgr.count == 0

    def test_options_loaded(self, tmp_fk_file):
        mgr = FocusKeywordsManager(tmp_fk_file, domain='esempio.com')
        mgr.load()
        assert mgr.options['min_density'] == 1.0
        assert mgr.options['max_density'] == 3.0

    def test_flat_format_backward_compat(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({
                'keywords': {
                    '/': {'primary': 'vecchio formato', 'secondary': []},
                },
            }, f)
            path = f.name

        try:
            mgr = FocusKeywordsManager(path, domain='qualsiasi.com')
            mgr.load()
            assert mgr.count == 1
            assert mgr.get_primary('/') == 'vecchio formato'
        finally:
            os.unlink(path)

    def test_compact_format(self, tmp_fk_file):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({
                'domains': {
                    'compatto.com': {
                        'keywords': {
                            '/': 'keyword singola',
                        }
                    }
                }
            }, f)
            path = f.name

        try:
            mgr = FocusKeywordsManager(path, domain='compatto.com')
            mgr.load()
            assert mgr.get_primary('/') == 'keyword singola'
            assert mgr.get_secondary('/') == []
        finally:
            os.unlink(path)