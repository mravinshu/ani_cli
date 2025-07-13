from flask import Flask, render_template, request, redirect
import requests
import urllib.parse

app = Flask(__name__)

API_URL = "https://api.allanime.day/api"

HEADERS = {
    "Referer": "https://allanime.to",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Content-Type": "application/json"
}

GRAPHQL_SEARCH_QUERY = """
query(
    $search: SearchInput
    $limit: Int
    $page: Int
    $translationType: VaildTranslationTypeEnumType
    $countryOrigin: VaildCountryOriginEnumType
) {
    shows(
        search: $search
        limit: $limit
        page: $page
        translationType: $translationType
        countryOrigin: $countryOrigin
    ) {
        edges {
            _id
            name
            availableEpisodes
        }
    }
}
"""

GRAPHQL_EPISODE_QUERY = """
query($showId: String!) {
    episodeList(showId: $showId) {
        episodeString
    }
}
"""

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search')
def search():
    query = request.args.get('query', '').strip()
    if not query:
        return render_template('index.html', error="Please enter a search term.")

    payload = {
        "query": GRAPHQL_SEARCH_QUERY,
        "variables": {
            "search": {
                "allowAdult": False,
                "allowUnknown": False,
                "query": query
            },
            "limit": 40,
            "page": 1,
            "translationType": "sub",
            "countryOrigin": "ALL"
        }
    }

    response = requests.post(API_URL, headers=HEADERS, json=payload)
    if response.status_code != 200:
        return f"Error: {response.status_code}"

    data = response.json()
    shows = data.get("data", {}).get("shows", {}).get("edges", [])
    shows = sorted(shows, key=lambda x: x.get("name", "z"))
    # Limit 10 shows for display
    shows = shows[:10]

    # Fetch image from OMDb for each show
    for show in shows:
        title = show.get("name", "")
        omdb_response = requests.get("https://www.omdbapi.com/", params={
            "t": title,
            "apikey": 'bf007c6a'
        })

        if omdb_response.status_code == 200:
            omdb_data = omdb_response.json()
            poster_url = omdb_data.get("Poster")
            if poster_url and poster_url != "N/A":
                show["poster"] = poster_url
            else:
                show["poster"] = "/static/no-image.png"  # fallback image
        else:
            show["poster"] = "/static/no-image.png"

    return render_template("results.html", shows=shows, query=query)

@app.route('/anime/<anime_id>')
def anime_detail(anime_id):
    query = """
    query ($showId: String!) {
      show(_id: $showId) {
        _id
        name
        availableEpisodesDetail
      }
    }
    """

    payload = {
        "query": query,
        "variables": {
            "showId": anime_id
        }
    }

    response = requests.post(API_URL, headers=HEADERS, json=payload)
    if response.status_code != 200:
        return f"Error loading episodes for ID {anime_id}"

    data = response.json()
    show = data.get("data", {}).get("show", {})
    name = show.get("name", "Unknown Anime")
    episode_data = show.get("availableEpisodesDetail", {})
    episodes = sorted(episode_data.get("sub", []), key=lambda x: float(x))

    return render_template("episodes.html", anime_id=anime_id, name=name, episodes=episodes)

def substitute_hex(input_str):
    subs = {'01': '9', '08': '0', '05': '=', '0a': '2', '0b': '3', '0c': '4', '07': '?', '00': '8', '5c': 'd',
        '0f': '7', '5e': 'f', '17': '/', '54': 'l', '09': '1', '48': 'p', '4f': 'w', '0e': '6', '5b': 'c', '5d': 'e',
        '0d': '5', '53': 'k', '1e': '&', '5a': 'b', '59': 'a', '4a': 'r', '4c': 't', '4e': 'v', '57': 'o', '51': 'i', }

    # Split input string into 2-character hex pairs
    pairs = [input_str[i:i+2] for i in range(0, len(input_str), 2)]

    # Apply substitutions
    result = ''.join(subs.get(pair, chr(int(pair, 16))) for pair in pairs)
    if "clock" in result:
        result = result.replace("clock", "clock.json")
        result = f"https://allanime.day{result}"

    return result

@app.route('/anime/<anime_id>/episode/<ep_number>')
def episode_stream(anime_id, ep_number):
    # Step 1: GraphQL query
    query = """
    query ($showId: String!, $translationType: VaildTranslationTypeEnumType!, $episodeString: String!) {
      episode(
        showId: $showId
        translationType: $translationType
        episodeString: $episodeString
      ) {
        episodeString
        sourceUrls
      }
    }
    """

    payload = {
        "query": query,
        "variables": {
            "showId": anime_id,
            "translationType": "sub",
            "episodeString": ep_number
        }
    }

    response = requests.post(API_URL, headers=HEADERS, json=payload)
    if response.status_code != 200:
        return f"Error fetching episode stream data"

    data = response.json()
    sources = data.get("data", {}).get("episode", {}).get("sourceUrls", [])

    parsed_sources = []

    for src in sources:
        source_name = src.get("sourceName")
        raw_url = src.get("sourceUrl")

        # Clean up obfuscated sourceUrl if it starts with '--'
        if raw_url.startswith('--'):
            cleaned_url = raw_url[2:]  # remove leading '--'
            cleaned_url = substitute_hex(cleaned_url)
        else:
            cleaned_url = raw_url

        parsed_sources.append({
            "name": source_name,
            "url": cleaned_url,
            "type": src.get("type"),
            "priority": src.get("priority"),
            "download": src.get("downloads", {}).get("downloadUrl")
        })

    return parsed_sources

    return render_template("player.html", ep_number=ep_number, providers=providers)


@app.route('/anime/<anime_id>/episode/<ep_number>/play')
def play_episode_online(anime_id, ep_number):
    query = """
    query ($showId: String!, $translationType: VaildTranslationTypeEnumType!, $episodeString: String!) {
      episode(
        showId: $showId
        translationType: $translationType
        episodeString: $episodeString
      ) {
        episodeString
        sourceUrls
      }
    }
    """

    payload = {
        "query": query,
        "variables": {
            "showId": anime_id,
            "translationType": "sub",
            "episodeString": ep_number
        }
    }

    response = requests.post(API_URL, headers=HEADERS, json=payload)
    if response.status_code != 200:
        return f"Error fetching episode {ep_number} for ID {anime_id}"

    data = response.json()
    sources = data.get("data", {}).get("episode", {}).get("sourceUrls", [])
    usable_urls = []

    for src in sources:
        raw_url = src.get("sourceUrl")

        if raw_url.startswith('--'):
            cleaned_url = raw_url[2:]  # remove leading '--'
            cleaned_url = substitute_hex(cleaned_url)
            if "apivtwo" in cleaned_url:
                try:
                    res = requests.get(cleaned_url, headers=HEADERS)
                    res.raise_for_status()
                except requests.RequestException:
                    continue
                res = res.json()
                links = res.get("links", [])
                for link in links:
                    usable_urls.append(link.get("link"))

    if not usable_urls:
        return "No usable stream URLs found."

    # If only one .m3u8 URL, redirect to external player
    non_m3u8_url = False
    if len(usable_urls) > 0:
        for _url in usable_urls:
            if not _url.endswith('.m3u8'):
                selected_source = _url
                non_m3u8_url = True
                break
    if not non_m3u8_url:
        encoded_url = urllib.parse.quote(usable_urls[0], safe='')
        redirect_url = f"https://allanime.day/player?url={encoded_url}"
        return redirect(redirect_url)
    return render_template("video_player.html", video_url=selected_source, episode_number=ep_number, player_title= f"Episode {ep_number}")


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=10000)
