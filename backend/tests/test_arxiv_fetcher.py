"""Regression tests for historical arXiv Atom feed parsing."""

import unittest
from datetime import date
from unittest.mock import patch

from src.fetcher.arxiv_fetcher import _fetch_from_date


ATOM_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2607.12345v1</id>
    <title>Sample mathematical physics paper</title>
    <summary>A rigorous result for a periodic operator.</summary>
    <author><name>Alice Example</name></author>
    <author><name>Bob Example</name></author>
    <category term="math-ph" />
    <category term="math.SP" />
  </entry>
</feed>
"""


class FakeResponse:
    """Minimal context-manager response used to mock urlopen."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return ATOM_FEED


class HistoricalArxivFetcherTests(unittest.TestCase):
    @patch("src.fetcher.arxiv_fetcher.urllib.request.urlopen")
    def test_parses_atom_authors_and_yaml_date_types(self, mock_urlopen):
        mock_urlopen.return_value = FakeResponse()

        for target_date in ("2026-07-20", date(2026, 7, 20)):
            with self.subTest(target_date=target_date):
                papers = _fetch_from_date(
                    target_date=target_date,
                    categories=["math-ph"],
                    max_results=1,
                    timezone_name="Asia/Shanghai",
                )

                self.assertEqual(len(papers), 1)
                self.assertEqual(papers[0]["id"], "2607.12345v1")
                self.assertEqual(
                    papers[0]["authors"],
                    ["Alice Example", "Bob Example"],
                )
                self.assertIn("math-ph", papers[0]["categories"])


if __name__ == "__main__":
    unittest.main()
