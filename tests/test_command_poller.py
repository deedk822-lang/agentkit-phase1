import unittest
from datetime import datetime
import sys
import os

# Add the agents directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'agents', 'command-poller')))

from command_poller import CommandParser, CommandType, ParsedCommand

class TestCommandParser(unittest.TestCase):

    def test_parse_simple_command(self):
        line = "SCAN_SITE domain=example.com"
        parsed = CommandParser.parse_line(line, 1)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.command_type, CommandType.SCAN_SITE)
        self.assertEqual(parsed.params, {"domain": "example.com"})
        self.assertEqual(parsed.raw_text, line)
        self.assertEqual(parsed.line_number, 1)

    def test_parse_command_with_multiple_params(self):
        line = "PUBLISH_REPORT client=acme dataset=q1_2024 format=pdf"
        parsed = CommandParser.parse_line(line, 2)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.command_type, CommandType.PUBLISH_REPORT)
        self.assertEqual(parsed.params, {"client": "acme", "dataset": "q1_2024", "format": "pdf"})

    def test_parse_command_with_quoted_params(self):
        line = 'POST_VIMEO title="My Awesome Video" url=https://example.com/video.mp4'
        parsed = CommandParser.parse_line(line, 3)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.command_type, CommandType.POST_VIMEO)
        self.assertEqual(parsed.params, {"title": "My Awesome Video", "url": "https://example.com/video.mp4"})

    def test_parse_invalid_command(self):
        line = "INVALID_COMMAND"
        parsed = CommandParser.parse_line(line, 4)
        self.assertIsNone(parsed)

    def test_parse_empty_line(self):
        line = ""
        parsed = CommandParser.parse_line(line, 5)
        self.assertIsNone(parsed)

    def test_parse_comment_line(self):
        line = "# This is a comment"
        parsed = CommandParser.parse_line(line, 6)
        self.assertIsNone(parsed)

if __name__ == '__main__':
    unittest.main()
