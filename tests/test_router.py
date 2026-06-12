from friendagent.channels.router import parse_address, WHATSAPP, SMS, EMAIL


def test_explicit_prefixes():
    assert parse_address("whatsapp:+14155550123") == (WHATSAPP, "whatsapp:+14155550123")
    assert parse_address("sms:+14155550123") == (SMS, "+14155550123")
    assert parse_address("email:grandma@example.com") == (EMAIL, "grandma@example.com")


def test_inferred_addresses():
    assert parse_address("grandma@example.com")[0] == EMAIL
    assert parse_address("+14155550123")[0] == SMS
    assert parse_address("whatsapp:+1999")[0] == WHATSAPP
