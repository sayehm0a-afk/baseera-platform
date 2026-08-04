from src.domain.arabic_text import normalize_arabic


class TestNormalizeArabic:
    def test_empty_string(self):
        assert normalize_arabic("") == ""

    def test_alef_hamza_variants_collapse(self):
        assert normalize_arabic("أرامكو") == normalize_arabic("ارامكو")
        assert normalize_arabic("إرامكو") == normalize_arabic("ارامكو")
        assert normalize_arabic("آرامكو") == normalize_arabic("ارامكو")

    def test_alef_maksura_collapses_to_yaa(self):
        assert normalize_arabic("مصطفى") == normalize_arabic("مصطفي")

    def test_taa_marbuta_collapses_to_haa(self):
        assert normalize_arabic("شركة") == normalize_arabic("شركه")

    def test_tashkeel_stripped(self):
        assert normalize_arabic("أَرَامْكُو") == normalize_arabic("ارامكو")

    def test_tatweel_stripped(self):
        assert normalize_arabic("ارامـــكو") == normalize_arabic("ارامكو")

    def test_extra_internal_whitespace_collapsed(self):
        assert normalize_arabic("أرامكو  السعودية") == normalize_arabic("أرامكو السعودية")

    def test_leading_trailing_whitespace_stripped(self):
        assert normalize_arabic("  أرامكو  ") == normalize_arabic("أرامكو")

    def test_distinct_words_stay_distinct(self):
        assert normalize_arabic("أرامكو") != normalize_arabic("سابك")
