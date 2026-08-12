from src.domain.sector_labels import SECTOR_LABELS_AR, sector_label_ar


def test_exact_key_matches_translate_correctly():
    for english, arabic in SECTOR_LABELS_AR.items():
        assert sector_label_ar(english) == arabic


def test_none_and_empty_return_none():
    assert sector_label_ar(None) is None
    assert sector_label_ar("") is None


def test_unmapped_sector_falls_back_to_unspecified_not_raw_english():
    assert sector_label_ar("Totally Unknown Sector") == "غير محدد"


def test_svc_abbreviation_variant_matches_the_spelled_out_key():
    # Real production evidence (M7 audit, symbol 6004): SAHMK returned
    # "Commercial & Professional Svc" while the canonical map's key
    # spells "Services" in full.
    assert sector_label_ar("Commercial & Professional Svc") == sector_label_ar(
        "Commercial & Professional Services"
    )
    assert sector_label_ar("Commercial & Professional Svc") == "الخدمات التجارية والمهنية"


def test_development_spelled_out_variant_matches_the_abbreviated_key():
    # Real production evidence (M7 audit, symbol 9591): SAHMK returned
    # "Real Estate Mgmt & Development" while the canonical map's key
    # abbreviates "Dev't".
    assert sector_label_ar("Real Estate Mgmt & Development") == sector_label_ar(
        "Real Estate Mgmt & Dev't"
    )
    assert sector_label_ar("Real Estate Mgmt & Development") == "إدارة وتطوير العقارات"


def test_mgmt_spelled_out_variant_also_matches():
    assert sector_label_ar("Real Estate Management & Dev't") == "إدارة وتطوير العقارات"


def test_normalization_is_case_and_whitespace_insensitive():
    assert sector_label_ar("commercial & professional svc") == "الخدمات التجارية والمهنية"
    assert sector_label_ar("  Commercial   &   Professional   Svc  ") == "الخدمات التجارية والمهنية"
