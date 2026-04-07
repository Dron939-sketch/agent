"""Тесты Varitype-профиля."""

from __future__ import annotations

from app.services.profile import build_profile_prompt, describe_vector


_FAKE_KB = {
    "vectors": {
        "СБ": {
            "name": "Силовик-Беспредельщик",
            "essence": "Выживает через контроль силы и территории",
            "language": "Кратко, прямо, командами",
            "levels": {
                "3": {
                    "name": "Восьмёрка — Боец",
                    "what_they_need": "Учиться договариваться",
                    "how_to_lead": "Уважать силу, давать структуру",
                }
            },
        }
    }
}


def test_describe_vector_returns_level_data() -> None:
    info = describe_vector(_FAKE_KB, "СБ", 3)
    assert info["name"] == "Силовик-Беспредельщик"
    assert info["level_name"] == "Восьмёрка — Боец"
    assert "договариваться" in info["what_they_need"]


def test_build_profile_prompt_contains_key_fields() -> None:
    profile = {
        "dominant": "СБ",
        "СБ": 3,
        "ТФ": 2,
        "УБ": 2,
        "ЧВ": 2,
        "perception_type": "ПРАКТИКО-ОРИЕНТИРОВАННЫЙ",
        "thinking_level": 6,
    }
    text = build_profile_prompt(profile, kb=_FAKE_KB)
    assert "Доминанта: СБ" in text
    assert "Восьмёрка" in text
    assert "ПРАКТИКО-ОРИЕНТИРОВАННЫЙ" in text
    assert "Учитывай эти особенности" in text


def test_build_profile_prompt_empty_when_no_dominant() -> None:
    assert build_profile_prompt({}, kb=_FAKE_KB) == ""
    assert build_profile_prompt({"dominant": "СБ"}, kb={}) == ""
