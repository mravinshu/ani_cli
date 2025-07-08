import subprocess
import json
import re
from flask import Flask, render_template, request, redirect, url_for, send_file
import os

app = Flask(__name__)

# --- Configuration ---
# Set the path to your ani-cli script.
# If ani-cli is in your system's PATH, you can just use "ani-cli".
ANI_CLI_SCRIPT_PATH = "./ani-cli" # Assuming ani-cli is in the same directory as app.py
DOWNLOAD_FOLDER = "downloads" # Folder to temporarily store downloaded files

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

# --- Helper Functions (Replicating ani-cli logic) ---

def run_ani_cli_command(command_args):
    """Executes a command using the ani-cli script and returns stdout."""
    try:
        # We need to capture stderr as well because ani-cli often prints useful info there
        result = subprocess.run(
            [ANI_CLI_SCRIPT_PATH] + command_args,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        print(f"Error running ani-cli: {e.stderr}")
        return "", e.stderr
    except FileNotFoundError:
        return "", "Error: ani-cli script not found. Please check ANI_CLI_SCRIPT_PATH."

def search_anime(query):
    """Searches for anime using ani-cli and returns a list of dictionaries."""
    stdout, stderr = run_ani_cli_command([query])
    anime_list = []
    # ani-cli's search output format needs careful parsing
    # It's usually like: "ID\tTITLE (EPISODES)"
    for line in stdout.strip().split('\n'):
        match = re.match(r'(\S+)\t(.+) \((\d+) episodes\)', line)
        if match:
            anime_id, title, episodes = match.groups()
            anime_list.append({
                'id': anime_id,
                'title': title,
                'episodes': int(episodes)
            })
    return anime_list

def get_episodes_list(anime_id):
    """Gets the list of episodes for a given anime ID."""
    # ani-cli doesn't have a direct "list episodes" command that outputs clean JSON.
    # We'll use a hack by asking it to select an episode without providing an index,
    # which makes it print the list of episodes to select from.
    stdout, stderr = run_ani_cli_command(["-S", "invalid_index", "--no-detach", anime_id]) # Use --no-detach to ensure it prints to stdout
    episodes = []
    # Parse the stderr output for the episode list. This is fragile.
    # Example: "  1.00\n  2.00\n" or "  1\n  2\n"
    for line in stderr.splitlines():
        ep_match = re.match(r'^\s*([0-9.]+)\s*$', line.strip())
        if ep_match:
            episodes.append(ep_match.group(1))
    return sorted(list(set(episodes)), key=float) # Sort and remove duplicates

def get_episode_download_link(anime_id, episode_number):
    """
    Attempts to get a direct download link for an episode.
    This is the trickiest part as ani-cli is designed for playback, not direct link extraction.
    We'll run ani-cli with the download flag and capture its output to find the URL.
    This is highly dependent on ani-cli's internal output for the 'download' function.
    """
    # Temporarily set the download directory to our Flask app's download folder
    # and use a unique filename to avoid conflicts.
    temp_download_file = os.path.join(DOWNLOAD_FOLDER, f"temp_ani_cli_download_{anime_id}_{episode_number}.mp4")
    # Set ANI_CLI_DOWNLOAD_DIR environment variable for the subprocess call
    env = os.environ.copy()
    env["ANI_CLI_DOWNLOAD_DIR"] = DOWNLOAD_FOLDER

    # Run ani-cli with download option and a dummy player to get the link
    # We are forcing it to *not* download, but to just print the information it would use for download.
    # This is a bit of a hack and might break with future ani-cli versions.
    # We use 'debug' as a player function to see what links it finds.
    # The links are typically printed to stderr by ani-cli's 'get_links' function.
    command = [
        ANI_CLI_SCRIPT_PATH,
        "-d", # Download flag
        "-e", str(episode_number),
        "--no-detach", # Don't detach the player, so output goes to stdout/stderr
        "--exit-after-play", # Exit after playing (or attempting to prepare download)
        "--logview", # A trick to get more output, sometimes
        anime_id
    ]

    try:
        # ani-cli prints the direct link it will download to stderr, usually from `download()` or `get_links()`
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        stdout, stderr = process.communicate(timeout=60) # Add a timeout

        # Look for the actual video URL in the combined output (stdout and stderr)
        # This regex will need to be robust and potentially adapted if ani-cli changes its output.
        # It looks for typical video file extensions or common streaming formats.
        all_output = stdout + stderr
        # Example output for direct MP4: "640 >https://example.com/video.mp4"
        # Example output for M3U8: "master.m3u8 >https://example.com/stream/master.m3u8"
        # We need to find the *actual* video URL, not just any link.

        # Prioritize .mp4 links if available
        mp4_match = re.search(r'(https?://[^\s]+\.mp4)', all_output)
        if mp4_match:
            return mp4_match.group(1)

        # Fallback to .m3u8 or other video links
        m3u8_match = re.search(r'(https?://[^\s]+\.m3u8)', all_output)
        if m3u8_match:
            return m3u8_match.group(1)

        # If we got a 'Yt' or 'repackager' type link, these often need further processing
        yt_match = re.search(r'Yt >(https?://[^\s]+)', all_output)
        if yt_match:
            # ani-cli's Yt links are often just the base URL for YouTube videos
            # For simplicity, we'll return this directly, but it might not be a direct video file.
            return yt_match.group(1)

        repackager_match = re.search(r'repackager\.wixmp\.com/([^>]*)', all_output)
        if repackager_match:
            # These links are complex and often require special handling by ani-cli itself.
            # We'll just return the base for now, but it's unlikely to be playable directly.
            return f"https://repackager.wixmp.com/{repackager_match.group(1)}"


        print(f"Warning: Could not extract direct video link for {anime_id} episode {episode_number}. Full output:\n{all_output}")
        return None # No direct link found

    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        print(f"Timeout running ani-cli for link extraction: {stderr}")
        return None
    except Exception as e:
        print(f"Error extracting link: {e}")
        return None

# --- Flask Routes ---

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        query = request.form['query']
        if query:
            return redirect(url_for('search_results', query=query))
    return render_template('index.html')

@app.route('/search_results')
def search_results():
    query = request.args.get('query')
    if not query:
        return redirect(url_for('index'))

    anime_results = search_anime(query)
    return render_template('search_results.html', query=query, anime_results=anime_results)

@app.route('/anime/<anime_id>/<anime_title>')
def anime_details(anime_id, anime_title):
    episodes = get_episodes_list(anime_id)
    return render_template('anime_details.html', anime_id=anime_id, anime_title=anime_title, episodes=episodes)

@app.route('/play_episode/<anime_id>/<anime_title>/<episode_number>')
def play_episode_web(anime_id, anime_title, episode_number):
    video_url = get_episode_download_link(anime_id, episode_number)

    if video_url:
        # Determine the player command based on the OS (simplified)
        player_command_template = ""
        # Example for mpv (Linux/macOS)
        player_command_template = f"mpv \"{video_url}\" --force-media-title=\"{anime_title} Episode {episode_number}\""
        # Example for VLC (Windows)
        # player_command_template = f"vlc \"{video_url}\" --meta-title=\"{anime_title} Episode {episode_number}\""

        # You could also offer a direct download via Flask (less robust for large files)
        # Or simply redirect to the video URL for browsers that can play it directly.
        return render_template(
            'play_episode.html',
            anime_title=anime_title,
            episode_number=episode_number,
            video_url=video_url,
            player_command=player_command_template
        )
    else:
        return render_template(
            'play_episode.html',
            anime_title=anime_title,
            episode_number=episode_number,
            error="Could not retrieve a direct video link for this episode. It might require specific player setup or is not directly streamable."
        )

@app.route('/download/<path:filename>')
def download_file(filename):
    """
    Serves a file for download.
    NOTE: For large video files, directly serving via Flask is not recommended for production.
    Consider using Nginx/Apache or cloud storage for serving large media.
    """
    return send_file(os.path.join(DOWNLOAD_FOLDER, filename), as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True) # Set debug=False in production