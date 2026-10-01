from carsafety.privacy import MASK, scrub


def test_masks_emails_phones_and_vins():
    text = "Call me at (555) 123-4567 or 555.987.6543, email jo.doe+car@example.com. VIN 1HGCM82633A004352."
    out = scrub(text)
    assert "555" not in out
    assert "example.com" not in out
    assert "1HGCM82633A004352" not in out
    assert out.count(MASK) == 4


def test_leaves_normal_complaint_text_alone():
    text = "THE CONTACT OWNS A 2019 HONDA CR-V. AT 45 MPH THE ENGINE STALLED. MILEAGE WAS 32,000."
    assert scrub(text) == text
