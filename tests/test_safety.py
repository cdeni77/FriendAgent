from friendagent import safety
from friendagent.safety import Severity


def test_ordinary_chitchat_is_not_flagged():
    r = safety.assess("Good morning! The roses are blooming and I made tea.")
    assert r.severity == Severity.NONE
    assert not r.is_flagged


def test_gift_card_request_is_high():
    r = safety.assess("He asked me to buy Amazon gift cards and send the codes.")
    assert r.severity == Severity.HIGH
    assert r.is_flagged
    assert "gift_cards" in r.categories


def test_fake_general_plus_money_flags():
    r = safety.assess(
        "The general is deployed overseas and needs me to wire money for his flight home."
    )
    assert r.is_flagged
    assert "romance_scam_persona" in r.categories
    assert "money_transfer" in r.categories


def test_secrecy_is_high():
    r = safety.assess("He said to keep this a secret and don't tell your family.")
    assert r.severity == Severity.HIGH
    assert "secrecy" in r.categories


def test_crypto_investment_flags():
    r = safety.assess(
        "My darling says I should invest in bitcoin on his trading platform for guaranteed returns."
    )
    assert r.is_flagged
    assert "crypto_investment" in r.categories


def test_single_weak_signal_is_low_not_alert():
    r = safety.assess("It's urgent that I water the garden today.")
    assert r.severity <= Severity.LOW
    assert not r.is_flagged
