"""FAANG adapter tests: parsing API payloads into correct posting URLs.

These exercise each adapter's pure ``_parse`` on a representative payload (no
network) and assert the real per-posting URL is captured and persisted.
"""

from __future__ import annotations

from job_agent.database.repository import Repository
from job_agent.scrapers.amazon import AmazonScraper
from job_agent.scrapers.base import ScraperConfig
from job_agent.scrapers.google import GoogleScraper
from job_agent.scrapers.netflix import NetflixScraper
from job_agent.scrapers.spotify import SpotifyScraper


def _cfg(source: str) -> ScraperConfig:
    return ScraperConfig(source=source, offline=True)


def test_amazon_parse_builds_posting_url() -> None:
    payload = {
        "jobs": [
            {
                "id_icims": "2481234",
                "title": "Applied Scientist Intern",
                "job_path": "/en/jobs/2481234/applied-scientist-intern",
                "normalized_location": "Seattle, WA, USA",
                "description": "Do ML.",
                "basic_qualifications": "MS or PhD in progress",
            }
        ]
    }
    jobs = AmazonScraper(_cfg("amazon"))._parse(payload)
    assert len(jobs) == 1
    assert jobs[0].url == "https://www.amazon.jobs/en/jobs/2481234/applied-scientist-intern"
    assert jobs[0].company == "Amazon"
    assert jobs[0].external_id == "2481234"


def test_spotify_parse_extracts_posting_links_from_index_html() -> None:
    html = """
    <a href="https://www.lifeatspotify.com/jobs/ml-engineer-intern">ML Intern</a>
    <a href="https://www.lifeatspotify.com/jobs/backend-engineer-platform">Backend</a>
    <a href="https://www.lifeatspotify.com/jobs/ml-engineer-intern">dup</a>
    """
    jobs = SpotifyScraper(_cfg("spotify"))._parse(html)
    urls = [j.url for j in jobs]
    assert "https://www.lifeatspotify.com/jobs/ml-engineer-intern" in urls
    assert len(jobs) == 2  # deduped
    assert jobs[0].title == "Ml Engineer Intern"
    assert all(j.company == "Spotify" for j in jobs)


def test_netflix_parse_prefers_canonical_url() -> None:
    payload = {
        "positions": [
            {
                "id": 790299000000,
                "name": "ML Intern",
                "canonicalPositionUrl": "https://explore.jobs.netflix.net/careers/job/790299000000",
                "job_description": "Recs.",
                "locations": ["Los Gatos, CA"],
                "t_update": 1717000000,
            }
        ]
    }
    jobs = NetflixScraper(_cfg("netflix"))._parse(payload)
    assert jobs[0].url == "https://explore.jobs.netflix.net/careers/job/790299000000"
    assert jobs[0].date_posted is not None  # unix timestamp parsed


def test_netflix_parse_builds_url_when_canonical_missing() -> None:
    payload = {"positions": [{"id": 42, "name": "X", "job_description": ""}]}
    jobs = NetflixScraper(_cfg("netflix"))._parse(payload)
    assert jobs[0].url == "https://explore.jobs.netflix.net/careers/job/42?domain=netflix.com"


def test_google_extract_ids_and_job_page() -> None:
    results_html = (
        "x jobs/results/128299363099607750-slug y jobs/results/999 z "
        "jobs/results/128299363099607750 dup"
    )
    ids = GoogleScraper.extract_ids(results_html)
    assert ids == ["128299363099607750", "999"]

    page = (
        '<meta property="og:title" content="Software Engineering Intern, MS — Google Careers">'
        '<meta property="og:description" content="Build things.">'
    )
    job = GoogleScraper(_cfg("google")).job_from_page("128299363099607750", page)
    assert job is not None
    assert job.title == "Software Engineering Intern, MS"  # "— Google Careers" stripped
    assert job.url == (
        "https://www.google.com/about/careers/applications/jobs/results/128299363099607750"
    )


def test_parse_skips_entries_without_a_url() -> None:
    # Amazon entry with neither job_path nor url must be dropped, not recorded blank.
    assert AmazonScraper(_cfg("amazon"))._parse({"jobs": [{"title": "X"}]}) == []


def test_scraped_url_is_persisted(repo: Repository) -> None:
    job = AmazonScraper(_cfg("amazon")).fetch()[0]  # sample mode
    assert job.url.startswith("https://www.amazon.jobs/")
    rec, created = repo.add_job(job)
    assert created and rec.url == job.url  # URL recorded in the database


# --- GitHub aggregator parser (the priority source) ------------------------
from job_agent.scrapers.github import GitHubJobsScraper  # noqa: E402


def test_github_markdown_table_extracts_apply_badge_url() -> None:
    md = (
        "| Company | Role | Location | Application |\n"
        "| --- | --- | --- | --- |\n"
        '| <a href="https://about.meta.com"><strong>Meta</strong></a> | ML Intern | '
        'NYC | <a href="https://www.metacareers.com/jobs/123"><img src="apply.png"></a> |\n'
        '| ↳ | Data Intern | SF | <a href="https://www.metacareers.com/jobs/456">'
        '<img src="apply.png"></a> |\n'
    )
    jobs = GitHubJobsScraper(_cfg("github"))._parse(md, "speedyapply/x")
    assert len(jobs) == 2
    # Posting URL is the Apply badge (with <img>), NOT the company link.
    assert jobs[0].url == "https://www.metacareers.com/jobs/123"
    assert jobs[0].company == "Meta"
    # "↳" continuation reuses the previous company.
    assert jobs[1].company == "Meta"
    assert jobs[1].url == "https://www.metacareers.com/jobs/456"


def test_github_html_table_prefers_direct_over_simplify() -> None:
    html = (
        "<table><tr><th>Company</th></tr>"
        "<tr>"
        '<td><strong><a href="https://simplify.jobs/c/abc">Bloxd</a></strong></td>'
        "<td>Software Engineer Intern</td><td>London, UK</td>"
        '<td><a href="https://jobs.ashbyhq.com/bloxd/xyz"><img src="a.png"></a> '
        '<a href="https://simplify.jobs/p/xyz"><img src="s.png"></a></td>'
        "<td>1d</td></tr></table>"
    )
    jobs = GitHubJobsScraper(_cfg("github"))._parse(html, "SimplifyJobs/x")
    assert len(jobs) == 1
    assert jobs[0].company == "Bloxd"
    # Prefer the direct company URL over the simplify.jobs tracker.
    assert jobs[0].url == "https://jobs.ashbyhq.com/bloxd/xyz"


def test_github_skips_closed_roles_without_apply_badge() -> None:
    md = "| Company | Role | Location | Application |\n" "| Acme | Closed Intern | NYC | 🔒 |\n"
    assert GitHubJobsScraper(_cfg("github"))._parse(md, "x/y") == []
