# Reverse Engineering Walkthrough

## Real-World Scenario

A client needs 12,000+ records from a professional registry. The website has a search interface but no documented API. Here's exactly how I approach this.

## Step 1: Open DevTools

Open Chrome DevTools (F12), navigate to the **Network** tab, and filter by **XHR/Fetch**. Then perform a search on the target website — any search. Watch what requests fire.

**What to look for:**
- Requests returning JSON (not HTML)
- URLs containing patterns like `/api/`, `/search`, `/v1/`, `/.json`
- Query parameters with `page`, `offset`, `limit`, `cursor`

## Step 2: Identify the API Call

Click on the JSON-returning request. Check:

- **URL pattern**: `https://registry.example.com/api/search?q=smith&page=1`
- **Response body**: Look for arrays of objects — that's your data
- **Headers**: Note any required cookies, tokens, or custom headers
- **Method**: Almost always GET for search endpoints

**Example (Open Library):**
```
GET https://openlibrary.org/search/authors.json?q=a&offset=0&limit=100
```

Response:
```json
{
  "numFound": 10847,
  "docs": [
    {"key": "OL1234A", "name": "Margaret Atwood", ...},
    ...
  ]
}
```

The `numFound` field tells us the total — 10,847 author records available.

## Step 3: Analyze Pagination

Change pages on the site and watch how URL parameters change:

**Offset-based** (most common):
```
?offset=0&limit=100   → first 100 records
?offset=100&limit=100 → next 100 records
```

**Page-number based:**
```
?page=1&size=50 → first page
?page=2&size=50 → second page
```

**Cursor-based** (modern APIs):
```
?cursor=abc123  → response includes next_cursor: "def456"
?cursor=def456  → next page
```

**Link header** (GitHub-style):
```
Link: <https://api.example.com/items?page=2>; rel="next"
```

## Step 4: Replicate in Python

Minimal script to verify the API works outside a browser:

```python
import httpx

async def test_api():
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://openlibrary.org/search/authors.json",
            params={"q": "a", "offset": 0, "limit": 10},
        )
        data = response.json()
        print(f"Total: {data['numFound']}")
        print(f"First author: {data['docs'][0]['name']}")
```

If this works, the API is accessible server-side. No browser automation needed.

## Step 5: Handle Edge Cases

### Rate Limiting (429 responses)
Most APIs enforce rate limits. Start slow (1 req/sec), use exponential backoff on 429s:

```python
if response.status_code == 429:
    wait = (2 ** attempt) + random.uniform(0, 1)
    await asyncio.sleep(wait)
```

### Session Cookies
Some registries require an active session. Solution: visit the homepage first, capture cookies, include them in API requests.

### Dynamic Tokens
Some APIs embed tokens in the page HTML. Solution: fetch the page, extract the token with regex or parsing, include it as a header.

### CORS Headers
CORS only applies to browsers. Server-side requests bypass CORS entirely — one of the key advantages of this approach.

## Step 6: Verify Data Completeness

After extraction, compare:
- **API metadata total** (e.g., `numFound: 10,847`)
- **Records actually extracted** (e.g., 10,621)

A small gap (2-3%) is normal due to records being added/removed during extraction. Larger gaps indicate pagination bugs or rate limiting issues.

## The Payoff

| Method | Time for 12K records | Reliability | Resources |
|--------|---------------------|-------------|-----------|
| Browser automation (Selenium) | ~10 hours | Fragile — breaks on UI changes | High (headless browser, memory) |
| API reverse engineering | ~45 minutes | Stable — APIs change less than UI | Minimal (HTTP only) |

**93% faster. More reliable. Fewer resources.**

The API approach also produces cleaner data — JSON fields are already structured, unlike scraped HTML that requires parsing and cleaning.
