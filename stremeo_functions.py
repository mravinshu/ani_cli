from app import *


@app.route("/manifest.json")
def manifest():
    return {
        "id": "com.ravinshu.allanime",
        "version": "1.0.0",
        "name": "AllAnime Stremio Addon",
        "description": "Stream anime from AllAnime via Stremio",
        "types": ["anime"],
        "catalogs": [
            {
                "type": "anime",
                "id": "allanime.catalog",
                "name": "AllAnime",
            }
        ],
        "resources": [
            "catalog",
            "meta",
            "stream"
        ],
        "idPrefixes": ["allanime"]
    }

@app.route("/catalog/<type_>/<id>.json")
def catalog(type_, id):
    print("/catalog/<type_>/<id>.json", type_, id)
    print("args", request.args)
    print("json", request.json)

    query = request.args.get("search", "")
    shows, _q = get_shows()  # you already have get_shows()

    metas = []
    for show in shows:
        metas.append({
            "id": f"allanime:{show['_id']}",
            "type": "anime",
            "name": show.get("name", "Unknown"),
            "poster": show.get("poster", "/static/no-image.png"),
        })

    return {"metas": metas}

@app.route("/meta/<type_>/<id>.json")
def meta(type_, id):
    print("/meta/<type_>/<id>.json", type_, id)
    print("args", request.args)
    print("json", request.json)
    anime_id = id.replace("allanime:", "")
    query = """
    query ($showId: String!) {
      show(_id: $showId) {
        _id
        name
        availableEpisodesDetail
      }
    }
    """
    payload = {"query": query, "variables": {"showId": anime_id}}
    response = requests.post(API_URL, headers=HEADERS, json=payload)
    data = response.json()
    show = data.get("data", {}).get("show", {})
    episodes = sorted(show.get("availableEpisodesDetail", {}).get("sub", []), key=lambda x: float(x))

    metas = {
        "id": f"allanime:{anime_id}",
        "type": "anime",
        "name": show.get("name", "Unknown Anime"),
        "poster": "/static/no-image.png",
        "videos": [
            {
                "id": f"allanime:{anime_id}:{ep}",
                "title": f"Episode {ep}",
                "season": 1,
                "episode": int(float(ep)),
            }
            for ep in episodes
        ],
    }

    return {"meta": metas}

@app.route("/stream/<type_>/<id>.json")
def stream(type_, id):
    print("/stream/<type_>/<id>.json", type_, id)
    print("args", request.args)
    print("json", request.json)
    # id looks like "allanime:<anime_id>:<episode_number>"
    parts = id.split(":")
    anime_id = parts[1]
    ep_number = parts[2]

    urls = fetch_usable_urls({
        "anime_id": anime_id,
        "ep_number": ep_number,
        "lang": "sub"
    }).get("urls", [])

    streams = []
    for url in urls:
        streams.append({
            "title": "AllAnime",
            "url": url,
        })

    return {"streams": streams}
