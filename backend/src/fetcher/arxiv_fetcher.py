"""Fetcher for arXiv paper metadata."""

import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from loguru import logger


def _fetch_from_single_field(
    field: str,
    categories: list[str] | None = None,
) -> list[dict]:
    """
    Fetch papers from a single arXiv field.

    Args:
        field: arXiv field abbreviation (e.g., "cs", "math", "physics")
        categories: List of category names to filter

    Returns:
        List of paper dicts with keys: id, title, authors, categories, abstract, url
    """
    url = f"https://arxiv.org/list/{field}/new"
    logger.info(f"Fetching papers from {url}")

    try:
        with urllib.request.urlopen(url) as page:
            soup = BeautifulSoup(page, features="html.parser")
    except Exception as e:
        logger.error(f"Failed to fetch papers from arXiv field '{field}': {e}")
        return []

    if not soup.body:
        logger.error(f"Could not find body in arXiv page for field '{field}'")
        return []

    content = soup.body.find("div", {"id": "content"})
    if not content:
        logger.error(f"Could not find content div in arXiv page for field '{field}'")
        return []

    # Extract date
    h3 = content.find("h3")
    if h3:
        date_str = h3.text.replace("New submissions for", "").strip()
        logger.debug(f"Papers date for field '{field}': {date_str}")

    # Find all paper entries
    dt_list = content.dl.find_all("dt") if content.dl else []
    dd_list = content.dl.find_all("dd") if content.dl else []

    if len(dt_list) != len(dd_list):
        logger.error(f"Mismatch between dt and dd elements for field '{field}'")
        return []

    papers = []

    for dt, dd in zip(dt_list, dd_list, strict=True):
        try:
            # Extract paper ID
            paper_link = dt.find("a", {"title": "Abstract"})
            if not paper_link or "href" not in paper_link.attrs:
                continue
            href = paper_link.get("href")
            if not isinstance(href, str):
                continue
            paper_id = href.split("/")[-1]

            # Extract title
            title_tag = dd.find("div", {"class": "list-title"})
            if not title_tag:
                continue
            title = title_tag.text.replace("Title:", "").strip()

            # Extract authors
            authors_tag = dd.find("div", {"class": "list-authors"})
            authors = []
            if authors_tag:
                author_links = authors_tag.find_all("a")
                authors = [a.text.strip() for a in author_links]

            # Extract categories/subjects
            subjects_tag = dd.find("div", {"class": "list-subjects"})
            paper_categories = []
            if subjects_tag:
                subjects_text = subjects_tag.text.replace("Subjects:", "").strip()
                paper_categories = [s.strip() for s in subjects_text.split(";")]

            # Extract abstract
            abstract_tag = dd.find("p", {"class": "mathjax"})
            abstract = abstract_tag.text.strip() if abstract_tag else ""

            # Filter by categories if specified
            # If categories is None or empty, don't filter (fetch all papers from the field)
            if categories is None:
                categories = []
            if len(categories) > 0:
                # Only filter if paper has categories and any match the filter
                if paper_categories:
                    category_match = any(
                        any(
                            filter_cat.lower() in paper_cat.lower()
                            for paper_cat in paper_categories
                        )
                        for filter_cat in categories
                    )
                    if not category_match:
                        continue
                else:
                    # Paper has no categories but filter is specified, skip it
                    continue

            paper = {
                "id": paper_id,
                "title": title,
                "authors": authors,
                "categories": paper_categories,
                "abstract": abstract,
                "abs_url": f"https://arxiv.org/abs/{paper_id}",
                "pdf_url": f"https://arxiv.org/pdf/{paper_id}.pdf",
            }

            papers.append(paper)

        except Exception as e:
            logger.warning(f"Error parsing paper in field '{field}': {e}")
            continue

    logger.info(f"Fetched {len(papers)} papers from arXiv field '{field}'")
    return papers
def _fetch_from_date(
    target_date: str,
    categories: list[str] | None = None,
    max_results: int = 0,
    timezone_name: str = "UTC",
) -> list[dict]:
    """Fetch arXiv papers submitted on one calendar day."""

    try:
        local_tz = ZoneInfo(timezone_name)
        start_local = datetime.strptime(target_date, "%Y-%m-%d").replace(
            tzinfo=local_tz
        )
    except ValueError as exc:
        logger.error(
            f"Invalid date or timezone: date={target_date}, timezone={timezone_name}"
        )
        raise exc

    end_local = start_local + timedelta(days=1) - timedelta(minutes=1)
    start_utc = start_local.astimezone(ZoneInfo("UTC"))
    end_utc = end_local.astimezone(ZoneInfo("UTC"))

    date_query = (
        f"submittedDate:[{start_utc.strftime('%Y%m%d%H%M')} "
        f"TO {end_utc.strftime('%Y%m%d%H%M')}]"
    )

    query_params = {
        "search_query": date_query,
        "start": 0,
        "max_results": max_results if max_results > 0 else 2000,
        "sortBy": "submittedDate",
        "sortOrder": "ascending",
    }
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
        query_params
    )
    logger.info(f"Fetching historical arXiv papers: {url}")

    try:
        with urllib.request.urlopen(url) as page:
            soup = BeautifulSoup(page.read(), features="xml")
    except Exception as exc:
        logger.error(f"Failed to fetch historical arXiv papers: {exc}")
        return []

    papers = []

    for entry in soup.find_all("entry"):
        paper_categories = [
            category.get("term", "")
            for category in entry.find_all("category")
            if category.get("term")
        ]

        if categories:
            category_match = any(
                filter_category.lower() in paper_category.lower()
                for filter_category in categories
                for paper_category in paper_categories
            )
            if not category_match:
                continue

        paper_id = entry.id.text.strip().rsplit("/", 1)[-1]
        title = " ".join(entry.title.stripped_strings)
        abstract = " ".join(entry.summary.stripped_strings)
        authors = [
            author.name.text.strip()
            for author in entry.find_all("author")
            if author.find("name")
        ]

        papers.append(
            {
                "id": paper_id,
                "title": title,
                "authors": authors,
                "categories": paper_categories,
                "abstract": abstract,
                "abs_url": f"https://arxiv.org/abs/{paper_id}",
                "pdf_url": f"https://arxiv.org/pdf/{paper_id}.pdf",
            }
        )

    logger.info(
        f"Fetched {len(papers)} historical papers for {target_date} "
        f"({timezone_name})"
    )
    return papers

def fetch_arxiv_papers(
    categories: list[str] | None = None,
    field: str | list[str] = "cs",
    max_results: int = 0,
    target_date: str | None = None,
    timezone_name: str = "UTC",
) -> list[dict]:
    """
    Fetch new papers from arXiv.

    Args:
        categories: List of category names to filter (e.g., ["Computer Vision and Pattern Recognition"])
        field: arXiv field abbreviation(s). Can be a single string (e.g., "cs") or a list (e.g., ["cs", "math"])
        max_results: Maximum number of papers to return (0 = no limit)

    Returns:
        List of paper dicts with keys: id, title, authors, categories, abstract, url
    """
    if target_date:
        return _fetch_from_date(
            target_date=target_date,
            categories=categories,
            max_results=max_results,
            timezone_name=timezone_name,
        )
    # Normalize field to list
    fields = [field] if isinstance(field, str) else field

    logger.info(f"Fetching papers from fields: {fields}")

    # Fetch papers from all fields and deduplicate by paper ID
    papers_dict: dict[str, dict] = {}

    for single_field in fields:
        field_papers = _fetch_from_single_field(single_field, categories)

        for paper in field_papers:
            paper_id = paper["id"]
            # Only add if not already present (first field wins)
            if paper_id not in papers_dict:
                papers_dict[paper_id] = paper

            # Check max_results limit
            if max_results > 0 and len(papers_dict) >= max_results:
                break

        # Early exit if max_results reached
        if max_results > 0 and len(papers_dict) >= max_results:
            break

    papers = list(papers_dict.values())
    logger.info(f"Total unique papers fetched: {len(papers)}")

    return papers
