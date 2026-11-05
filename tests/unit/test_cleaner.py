import unittest
from src.infrastructure.transformers.utils import clean_markdown_response


class TestCleaner(unittest.TestCase):
    def test_clean_fenced_markdown(self):
        raw = "```markdown\n# Title\nContent\n```"
        self.assertEqual(clean_markdown_response(raw), "# Title\nContent")

    def test_clean_generic_fence(self):
        raw = "```\n# Title\nContent\n```"
        self.assertEqual(clean_markdown_response(raw), "# Title\nContent")

    def test_clean_plain_markdown(self):
        raw = "# Title\nContent"
        self.assertEqual(clean_markdown_response(raw), "# Title\nContent")

    def test_clean_empty(self):
        self.assertEqual(clean_markdown_response(""), "")
        self.assertEqual(clean_markdown_response(None), "")


if __name__ == "__main__":
    unittest.main()
