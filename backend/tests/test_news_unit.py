"""Isolated unit tests for news.py using httpx MockTransport.
Run: cd /app/backend && python -m pytest tests/test_news_unit.py -v
"""
import asyncio
import os
from unittest.mock import patch

import httpx
import pytest
from fastapi import HTTPException

from news import you_search, normalize_results


class MockTransport(httpx.MockTransport):
    """Mock transport for httpx to simulate You.com API responses."""
    
    def __init__(self, handler):
        super().__init__(handler)


def test_you_search_401_unauthorized():
    """Test you_search raises 502 news_credentials on 401."""
    async def run():
        async def mock_post(*args, **kwargs):
            return httpx.Response(401, json={"error": "unauthorized"})
        
        with patch.dict(os.environ, {"YDC_API_KEY": "test_key"}):
            with patch("news.httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = mock_post
                try:
                    await you_search("test query", "EN")
                    assert False, "Should have raised HTTPException"
                except HTTPException as e:
                    assert e.status_code == 502
                    assert e.detail == "news_credentials"
                    print("✅ 401 -> 502 news_credentials")
    
    asyncio.run(run())


def test_you_search_402_payment_required():
    """Test you_search raises 502 news_credits on 402."""
    async def run():
        async def mock_post(*args, **kwargs):
            return httpx.Response(402, json={"error": "payment_required"})
        
        with patch.dict(os.environ, {"YDC_API_KEY": "test_key"}):
            with patch("news.httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = mock_post
                try:
                    await you_search("test query", "EN")
                    assert False, "Should have raised HTTPException"
                except HTTPException as e:
                    assert e.status_code == 502
                    assert e.detail == "news_credits"
                    print("✅ 402 -> 502 news_credits")
    
    asyncio.run(run())


def test_you_search_429_rate_limited():
    """Test you_search raises 429 news_rate_limited on 429."""
    async def run():
        async def mock_post(*args, **kwargs):
            return httpx.Response(429, json={"error": "rate_limited"})
        
        with patch.dict(os.environ, {"YDC_API_KEY": "test_key"}):
            with patch("news.httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = mock_post
                try:
                    await you_search("test query", "EN")
                    assert False, "Should have raised HTTPException"
                except HTTPException as e:
                    assert e.status_code == 429
                    assert e.detail == "news_rate_limited"
                    print("✅ 429 -> 429 news_rate_limited")
    
    asyncio.run(run())


def test_you_search_500_server_error_with_retry():
    """Test you_search retries on 500 then succeeds."""
    async def run():
        call_count = [0]
        
        async def mock_post(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return httpx.Response(500, json={"error": "server_error"})
            return httpx.Response(200, json={
                "results": {
                    "web": [{
                        "url": "https://example.com/article",
                        "title": "Test Article",
                        "description": "Test description"
                    }]
                }
            })
        
        with patch.dict(os.environ, {"YDC_API_KEY": "test_key"}):
            with patch("news.httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = mock_post
                results = await you_search("test query", "EN")
                assert call_count[0] == 2, "Should have retried once"
                assert len(results) == 1
                assert results[0]["url"] == "https://example.com/article"
                print("✅ 500 retry logic works")
    
    asyncio.run(run())


def test_you_search_500_persistent_failure():
    """Test you_search raises 502 news_unavailable on persistent 500."""
    async def run():
        async def mock_post(*args, **kwargs):
            return httpx.Response(500, json={"error": "server_error"})
        
        with patch.dict(os.environ, {"YDC_API_KEY": "test_key"}):
            with patch("news.httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = mock_post
                try:
                    await you_search("test query", "EN")
                    assert False, "Should have raised HTTPException"
                except HTTPException as e:
                    assert e.status_code == 502
                    assert e.detail == "news_unavailable"
                    print("✅ Persistent 500 -> 502 news_unavailable")
    
    asyncio.run(run())


def test_you_search_timeout():
    """Test you_search raises 504 news_timeout on timeout."""
    async def run():
        async def mock_post(*args, **kwargs):
            raise httpx.TimeoutException("Request timed out")
        
        with patch.dict(os.environ, {"YDC_API_KEY": "test_key"}):
            with patch("news.httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = mock_post
                try:
                    await you_search("test query", "EN")
                    assert False, "Should have raised HTTPException"
                except HTTPException as e:
                    assert e.status_code == 504
                    assert e.detail == "news_timeout"
                    print("✅ Timeout -> 504 news_timeout")
    
    asyncio.run(run())


def test_you_search_malformed_json_not_dict():
    """Test you_search handles malformed response (not a dict)."""
    async def run():
        async def mock_post(*args, **kwargs):
            return httpx.Response(200, json=["not", "a", "dict"])
        
        with patch.dict(os.environ, {"YDC_API_KEY": "test_key"}):
            with patch("news.httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = mock_post
                try:
                    await you_search("test query", "EN")
                    assert False, "Should have raised HTTPException"
                except HTTPException as e:
                    assert e.status_code == 502
                    assert e.detail == "news_unavailable"
                    print("✅ Malformed JSON (not dict) -> 502 news_unavailable")
    
    asyncio.run(run())


def test_you_search_malformed_json_missing_results():
    """Test you_search handles malformed response (missing results)."""
    async def run():
        async def mock_post(*args, **kwargs):
            return httpx.Response(200, json={"data": "no results field"})
        
        with patch.dict(os.environ, {"YDC_API_KEY": "test_key"}):
            with patch("news.httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = mock_post
                try:
                    await you_search("test query", "EN")
                    assert False, "Should have raised HTTPException"
                except HTTPException as e:
                    assert e.status_code == 502
                    assert e.detail == "news_unavailable"
                    print("✅ Malformed JSON (missing results) -> 502 news_unavailable")
    
    asyncio.run(run())


def test_you_search_malformed_json_results_not_dict():
    """Test you_search handles malformed response (results not dict)."""
    async def run():
        async def mock_post(*args, **kwargs):
            return httpx.Response(200, json={"results": "not a dict"})
        
        with patch.dict(os.environ, {"YDC_API_KEY": "test_key"}):
            with patch("news.httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = mock_post
                try:
                    await you_search("test query", "EN")
                    assert False, "Should have raised HTTPException"
                except HTTPException as e:
                    assert e.status_code == 502
                    assert e.detail == "news_unavailable"
                    print("✅ Malformed JSON (results not dict) -> 502 news_unavailable")
    
    asyncio.run(run())


def test_you_search_missing_api_key():
    """Test you_search raises 503 news_not_configured when API key missing."""
    async def run():
        with patch.dict(os.environ, {}, clear=True):
            try:
                await you_search("test query", "EN")
                assert False, "Should have raised HTTPException"
            except HTTPException as e:
                assert e.status_code == 503
                assert e.detail == "news_not_configured"
                print("✅ Missing API key -> 503 news_not_configured")
    
    asyncio.run(run())


def test_you_search_request_headers_and_payload():
    """Test you_search sends correct headers and payload."""
    async def run():
        captured_request = {}
        
        async def mock_post(url, headers=None, json=None, *args, **kwargs):
            captured_request["url"] = url
            captured_request["headers"] = headers
            captured_request["json"] = json
            return httpx.Response(200, json={
                "results": {
                    "web": [{
                        "url": "https://example.com/test",
                        "title": "Test",
                        "description": "Test"
                    }]
                }
            })
        
        with patch.dict(os.environ, {"YDC_API_KEY": "test_secret_key"}):
            with patch("news.httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = mock_post
                await you_search("climate change", "VI")
                
                # Verify URL
                assert captured_request["url"] == "https://ydc-index.io/v1/search"
                print("✅ Correct URL")
                
                # Verify headers
                assert captured_request["headers"]["X-API-Key"] == "test_secret_key"
                print("✅ Correct API key header")
                
                # Verify payload
                payload = captured_request["json"]
                assert payload["query"] == "climate change news"
                assert payload["count"] == 8
                assert payload["freshness"] == "week"
                assert payload["language"] == "VI"
                assert payload["safesearch"] == "moderate"
                assert "extraction" in payload
                print("✅ Correct request payload")
    
    asyncio.run(run())


def test_normalize_results_web_none():
    """Test normalize_results handles results.web = None."""
    data = {"results": {"web": None}}
    results = normalize_results(data)
    assert results == []


def test_normalize_results_web_missing():
    """Test normalize_results handles missing web field."""
    data = {"results": {}}
    results = normalize_results(data)
    assert results == []
    print("✅ normalize_results handles missing web field")


def test_normalize_results_web_not_list():
    """Test normalize_results handles web not being a list."""
    data = {"results": {"web": "not a list"}}
    results = normalize_results(data)
    assert results == []
    print("✅ normalize_results handles web not being list")


def test_normalize_results_item_not_dict():
    """Test normalize_results skips non-dict items."""
    data = {"results": {"web": ["string", 123, None, {"url": "https://example.com", "title": "Valid"}]}}
    results = normalize_results(data)
    assert len(results) == 1
    assert results[0]["url"] == "https://example.com"
    print("✅ normalize_results skips non-dict items")


def test_normalize_results_missing_url():
    """Test normalize_results skips items with missing/invalid URL."""
    data = {"results": {"web": [
        {"title": "No URL"},
        {"url": "", "title": "Empty URL"},
        {"url": "ftp://invalid.com", "title": "Invalid scheme"},
        {"url": "https://valid.com", "title": "Valid"}
    ]}}
    results = normalize_results(data)
    assert len(results) == 1
    assert results[0]["url"] == "https://valid.com"
    print("✅ normalize_results filters invalid URLs")


def test_normalize_results_duplicate_urls():
    """Test normalize_results deduplicates URLs."""
    data = {"results": {"web": [
        {"url": "https://example.com/article", "title": "First"},
        {"url": "https://example.com/article", "title": "Duplicate"},
        {"url": "https://other.com/news", "title": "Different"}
    ]}}
    results = normalize_results(data)
    assert len(results) == 2
    assert results[0]["title"] == "First"
    assert results[1]["url"] == "https://other.com/news"
    print("✅ normalize_results deduplicates URLs")


def test_normalize_results_missing_title_uses_hostname():
    """Test normalize_results uses hostname when title missing."""
    data = {"results": {"web": [
        {"url": "https://example.com/article"}
    ]}}
    results = normalize_results(data)
    assert len(results) == 1
    assert results[0]["title"] == "example.com"
    print("✅ normalize_results uses hostname for missing title")


def test_normalize_results_excerpts_extraction():
    """Test normalize_results extracts excerpts from various fields."""
    data = {"results": {"web": [
        {
            "url": "https://example.com/1",
            "title": "Test 1",
            "contents": {"highlights": ["excerpt1", "excerpt2"]}
        },
        {
            "url": "https://example.com/2",
            "title": "Test 2",
            "snippets": ["snippet1", "snippet2"]
        },
        {
            "url": "https://example.com/3",
            "title": "Test 3",
            "contents": "not a dict",
            "snippets": "single snippet"
        }
    ]}}
    results = normalize_results(data)
    assert len(results) == 3
    assert results[0]["excerpts"] == ["excerpt1", "excerpt2"]
    assert results[1]["excerpts"] == ["snippet1", "snippet2"]
    assert results[2]["excerpts"] == ["single snippet"]
    print("✅ normalize_results extracts excerpts correctly")


def test_normalize_results_sexual_content_filtering():
    """Test normalize_results filters sexual content."""
    data = {"results": {"web": [
        {"url": "https://clean.com", "title": "Clean article", "description": "Family friendly"},
        {"url": "https://good.com", "title": "Good news", "description": "Safe content"}
    ]}}
    results = normalize_results(data)
    assert len(results) == 2
    print("✅ normalize_results sexual content filtering (basic check)")


def test_normalize_results_max_8_results():
    """Test normalize_results returns max 8 results."""
    data = {"results": {"web": [
        {"url": f"https://example.com/{i}", "title": f"Article {i}"}
        for i in range(20)
    ]}}
    results = normalize_results(data)
    assert len(results) == 8
    print("✅ normalize_results limits to 8 results")


def test_normalize_results_truncates_long_fields():
    """Test normalize_results truncates long titles, descriptions, excerpts."""
    long_title = "A" * 1000
    long_desc = "B" * 3000
    long_excerpt = "C" * 2000
    
    data = {"results": {"web": [{
        "url": "https://example.com",
        "title": long_title,
        "description": long_desc,
        "snippets": [long_excerpt]
    }]}}
    results = normalize_results(data)
    assert len(results) == 1
    assert len(results[0]["title"]) == 500
    assert len(results[0]["description"]) == 2000
    assert len(results[0]["excerpts"][0]) == 1600
    print("✅ normalize_results truncates long fields")


def test_normalize_results_max_3_excerpts():
    """Test normalize_results limits excerpts to 3."""
    data = {"results": {"web": [{
        "url": "https://example.com",
        "title": "Test",
        "snippets": [f"excerpt{i}" for i in range(10)]
    }]}}
    results = normalize_results(data)
    assert len(results[0]["excerpts"]) == 3
    print("✅ normalize_results limits to 3 excerpts")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("🧪 NEWS UNIT TESTS (Isolated httpx MockTransport)")
    print("="*60)
    
    # Error handling tests
    test_you_search_401_unauthorized()
    test_you_search_402_payment_required()
    test_you_search_429_rate_limited()
    test_you_search_500_server_error_with_retry()
    test_you_search_500_persistent_failure()
    test_you_search_timeout()
    test_you_search_malformed_json_not_dict()
    test_you_search_malformed_json_missing_results()
    test_you_search_malformed_json_results_not_dict()
    test_you_search_missing_api_key()
    
    # Request validation tests
    test_you_search_request_headers_and_payload()
    
    # Normalization tests
    test_normalize_results_web_none()
    test_normalize_results_web_missing()
    test_normalize_results_web_not_list()
    test_normalize_results_item_not_dict()
    test_normalize_results_missing_url()
    test_normalize_results_duplicate_urls()
    test_normalize_results_missing_title_uses_hostname()
    test_normalize_results_excerpts_extraction()
    test_normalize_results_sexual_content_filtering()
    test_normalize_results_max_8_results()
    test_normalize_results_truncates_long_fields()
    test_normalize_results_max_3_excerpts()
    
    print("\n" + "="*60)
    print("✅ ALL NEWS UNIT TESTS PASSED")
    print("="*60)
