"""Synthetic, automatically labeled training screens.

Fake app screens (chat, email, banking, password manager, editor, terminal,
checkout, profile, plus harmless pages) are generated as HTML with every
sensitive element tagged ``data-s="<class>"``. A headless browser renders them
and reads each tagged element's on-screen box, so labels come for free and are
pixel-exact.

Synthetic data is used for TRAINING only. Validation and test use real
screenshots, so reported numbers measure transfer to real apps, not how well
the model learned this generator. All content is fabricated (Faker + invented
brand names); no real organization is imitated.
"""
