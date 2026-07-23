"""Company blocklist: word-boundary matching, no false positives."""

from __future__ import annotations

from job_agent.scrapers.blocklist import CompanyBlocklist


def test_inactive_when_empty() -> None:
    assert CompanyBlocklist([]).active is False
    assert CompanyBlocklist(["tiktok"]).active is True


def test_blocks_listed_companies() -> None:
    b = CompanyBlocklist(["tiktok", "bytedance"])
    assert b.blocks("TikTok") is True
    assert b.blocks("ByteDance Ltd") is True
    assert b.blocks("TikTok Inc.") is True


def test_does_not_block_others() -> None:
    b = CompanyBlocklist(["tiktok", "bytedance"])
    assert b.blocks("Anthropic") is False
    assert b.blocks("Spotify") is False
    assert b.blocks("") is False


def test_word_boundary_no_substring_false_positive() -> None:
    b = CompanyBlocklist(["meta"])
    assert b.blocks("Meta") is True
    assert b.blocks("Metabolic Labs") is False
