import json
from pathlib import Path

import httpx
import respx

from generator.sources.wikidata import fetch_wikidata

FIXTURES = Path(__file__).parent / "fixtures"


@respx.mock
async def test_fetch_wikidata_happy_path():
    search_payload = json.loads((FIXTURES / "wikidata_search.json").read_text())
    sparql_payload = json.loads((FIXTURES / "wikidata_sparql.json").read_text())
    respx.get(host="www.wikidata.org", path__startswith="/w/api.php").mock(
        return_value=httpx.Response(200, json=search_payload)
    )
    respx.get(host="query.wikidata.org", path__startswith="/sparql").mock(
        return_value=httpx.Response(200, json=sparql_payload)
    )
    source, props = await fetch_wikidata("GPT-5.5")
    assert source is not None
    assert source.publisher.tier == "T2"
    assert "wikidata.org" in str(source.url)
    assert props.get("instance_of") == "language model"
    assert props.get("point_in_time") == "2026-05-01T00:00:00Z"


@respx.mock
async def test_fetch_wikidata_not_found():
    respx.get(host="www.wikidata.org", path__startswith="/w/api.php").mock(
        return_value=httpx.Response(200, json={"search": []})
    )
    source, props = await fetch_wikidata("Nonexistent Entity 9z9z9")
    assert source is None
    assert props == {}
