import unittest

from first import resolve_txt_file_mode


class TxtFileModeTests(unittest.TestCase):
    def test_txt_file_mode_defaults_to_transliteration(self):
        self.assertEqual(resolve_txt_file_mode({}), {"mode": "transliterate"})

    def test_txt_file_mode_uses_selected_translation_language(self):
        self.assertEqual(
            resolve_txt_file_mode({"txt_translate_target": "ru"}),
            {"mode": "translate", "target_lang": "ru"},
        )

    def test_txt_file_mode_rejects_invalid_language(self):
        self.assertEqual(resolve_txt_file_mode({"txt_translate_target": "fr"}), {"mode": "transliterate"})


if __name__ == "__main__":
    unittest.main()
